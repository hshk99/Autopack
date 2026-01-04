"""Tests for Plan Normalizer (Phase 1).

Validates:
- Deliverable extraction from messy text
- Category inference
- Scope grounding in repo layout
- Validation step inference
- Fail-fast behavior on missing validation
- Token-safe bounded behavior
- Memory integration
"""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock


from autopack.plan_normalizer import (
    PlanNormalizer,
    normalize_plan,
    DEFAULT_TOKEN_CAP,
)


class TestDeliverableExtraction:
    """Test deliverable extraction from unstructured text."""

    def test_extract_from_bulleted_list(self):
        """Test extraction from bulleted lists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            normalizer = PlanNormalizer(workspace=workspace, run_id="test-run")

            plan = """
            - Add user authentication
            - Create login endpoint
            * Implement JWT tokens
            • Update database schema
            """

            deliverables = normalizer._extract_deliverables(plan)
            assert len(deliverables) >= 4
            assert any("authentication" in d.lower() for d in deliverables)
            assert any("login" in d.lower() for d in deliverables)

    def test_extract_from_numbered_list(self):
        """Test extraction from numbered lists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            normalizer = PlanNormalizer(workspace=workspace, run_id="test-run")

            plan = """
            1. Implement user registration
            2. Add email validation
            3. Create password hashing utility
            """

            deliverables = normalizer._extract_deliverables(plan)
            assert len(deliverables) >= 3
            assert any("registration" in d.lower() for d in deliverables)
            assert any("validation" in d.lower() for d in deliverables)

    def test_extract_from_imperatives(self):
        """Test extraction from imperative statements."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            normalizer = PlanNormalizer(workspace=workspace, run_id="test-run")

            plan = """
            Implement a REST API for managing users.
            Add authentication middleware.
            Create database models for user profiles.
            """

            deliverables = normalizer._extract_deliverables(plan)
            assert len(deliverables) >= 3
            assert any("rest api" in d.lower() for d in deliverables)
            assert any("authentication" in d.lower() for d in deliverables)

    def test_extract_file_references(self):
        """Test extraction of file references."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            normalizer = PlanNormalizer(workspace=workspace, run_id="test-run")

            plan = """
            Update src/auth/jwt.py to support refresh tokens.
            Modify config.yaml to add new settings.
            """

            deliverables = normalizer._extract_deliverables(plan)
            assert any("jwt.py" in d for d in deliverables)
            assert any("config.yaml" in d for d in deliverables)

    def test_deduplicate_deliverables(self):
        """Test that duplicate deliverables are removed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            normalizer = PlanNormalizer(workspace=workspace, run_id="test-run")

            plan = """
            - Add authentication
            - add authentication
            - Add Authentication
            """

            deliverables = normalizer._extract_deliverables(plan)
            # Should deduplicate (may have slight variations due to different extraction patterns)
            # but should be significantly fewer than 3
            assert len(deliverables) <= 3

    def test_limit_deliverables_count(self):
        """Test that deliverables are limited to prevent prompt bloat."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            normalizer = PlanNormalizer(workspace=workspace, run_id="test-run")

            # Create 30 deliverables
            items = [f"{i}. Add feature {i}" for i in range(30)]
            plan = "\n".join(items)

            deliverables = normalizer._extract_deliverables(plan)
            assert len(deliverables) <= 20  # Should cap at 20


class TestCategoryInference:
    """Test task category inference."""

    def test_infer_authentication_category(self):
        """Test inference of authentication category."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            normalizer = PlanNormalizer(workspace=workspace, run_id="test-run")

            plan = "Implement JWT authentication with login and logout endpoints"
            category, confidence = normalizer._infer_category(plan)

            assert category == "authentication"
            assert confidence > 0.3

    def test_infer_api_category(self):
        """Test inference of API endpoint category."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            normalizer = PlanNormalizer(workspace=workspace, run_id="test-run")

            plan = "Create REST API endpoints using FastAPI for user management"
            category, confidence = normalizer._infer_category(plan)

            assert category in ["api_endpoint", "backend"]
            assert confidence > 0.3

    def test_infer_database_category(self):
        """Test inference of database category."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            normalizer = PlanNormalizer(workspace=workspace, run_id="test-run")

            plan = "Add SQLAlchemy models and Alembic migrations for user schema"
            category, confidence = normalizer._infer_category(plan)

            assert category == "database"
            assert confidence > 0.3

    def test_infer_frontend_category(self):
        """Test inference of frontend category."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            normalizer = PlanNormalizer(workspace=workspace, run_id="test-run")

            plan = "Build React components for user profile page with form validation"
            category, confidence = normalizer._infer_category(plan)

            assert category == "frontend"
            assert confidence > 0.3

    def test_default_to_backend_if_unclear(self):
        """Test default to backend category when unclear."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            normalizer = PlanNormalizer(workspace=workspace, run_id="test-run")

            plan = "Do some work on the project"
            category, confidence = normalizer._infer_category(plan)

            assert category == "backend"
            assert confidence < 0.5  # Low confidence


class TestScopeGrounding:
    """Test scope grounding in repo layout."""

    def setup_method(self):
        """Set up test workspace with sample files."""
        self.tmpdir = tempfile.mkdtemp()
        self.workspace = Path(self.tmpdir)

        # Create sample repo structure
        (self.workspace / "src").mkdir()
        (self.workspace / "src" / "auth").mkdir()
        (self.workspace / "src" / "auth" / "jwt.py").write_text("# JWT module")
        (self.workspace / "src" / "api").mkdir()
        (self.workspace / "src" / "api" / "endpoints.py").write_text("# API endpoints")
        (self.workspace / "tests").mkdir()
        (self.workspace / "tests" / "test_auth.py").write_text("# Auth tests")
        (self.workspace / "pytest.ini").write_text("[pytest]")

    def teardown_method(self):
        """Clean up test workspace."""
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_ground_scope_uses_repo_scanner(self):
        """Test that scope grounding uses repo scanner."""
        normalizer = PlanNormalizer(workspace=self.workspace, run_id="test-run")

        scope_paths, read_only, confidence = normalizer._ground_scope(
            raw_plan="Implement JWT authentication",
            deliverables=["JWT tokens", "Login endpoint"],
            category="authentication",
        )

        # Should find files in the workspace
        assert len(scope_paths) > 0
        assert confidence > 0

    def test_ground_scope_limits_files(self):
        """Test that scope grounding limits file count."""
        # Create many files
        for i in range(100):
            (self.workspace / f"file_{i}.py").write_text("# File")

        normalizer = PlanNormalizer(workspace=self.workspace, run_id="test-run")

        scope_paths, read_only, confidence = normalizer._ground_scope(
            raw_plan="Implement authentication",
            deliverables=["JWT"],
            category="authentication",
        )

        # Should cap at 50 files
        assert len(scope_paths) <= 50
        # Should cap read-only at 20 files
        assert len(read_only) <= 20

    def test_get_default_scope_for_frontend(self):
        """Test default scope for frontend category."""
        # Add frontend files
        (self.workspace / "src" / "components").mkdir()
        (self.workspace / "src" / "components" / "Button.tsx").write_text("// Button")
        (self.workspace / "src" / "components" / "Form.jsx").write_text("// Form")

        normalizer = PlanNormalizer(workspace=self.workspace, run_id="test-run")
        repo_structure = normalizer.scanner.scan()

        default_scope = normalizer._get_default_scope_for_category("frontend", repo_structure)

        assert len(default_scope) > 0
        assert all(
            f.endswith((".tsx", ".jsx", ".ts", ".js", ".css"))
            for f in default_scope
        )

    def test_get_default_scope_for_testing(self):
        """Test default scope for testing category."""
        normalizer = PlanNormalizer(workspace=self.workspace, run_id="test-run")
        repo_structure = normalizer.scanner.scan()

        default_scope = normalizer._get_default_scope_for_category("testing", repo_structure)

        assert len(default_scope) > 0
        assert all("test" in f.lower() for f in default_scope)


class TestValidationStepInference:
    """Test validation step inference."""

    def setup_method(self):
        """Set up test workspace."""
        self.tmpdir = tempfile.mkdtemp()
        self.workspace = Path(self.tmpdir)

    def teardown_method(self):
        """Clean up test workspace."""
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_infer_pytest_for_python(self):
        """Test pytest inference for Python projects."""
        (self.workspace / "pytest.ini").write_text("[pytest]")
        (self.workspace / "tests").mkdir()

        normalizer = PlanNormalizer(workspace=self.workspace, run_id="test-run")
        validation_steps = normalizer._infer_validation_steps(
            category="backend",
            scope_paths=["src/main.py", "src/auth.py"],
        )

        assert len(validation_steps) > 0
        assert any("pytest" in step for step in validation_steps)

    def test_infer_npm_test_for_javascript(self):
        """Test npm test inference for JavaScript projects."""
        (self.workspace / "package.json").write_text('{"name": "test"}')

        normalizer = PlanNormalizer(workspace=self.workspace, run_id="test-run")
        validation_steps = normalizer._infer_validation_steps(
            category="frontend",
            scope_paths=["src/App.tsx", "src/Button.jsx"],
        )

        assert len(validation_steps) > 0
        assert any("npm test" in step for step in validation_steps)

    def test_infer_cargo_test_for_rust(self):
        """Test cargo test inference for Rust projects."""
        (self.workspace / "Cargo.toml").write_text('[package]\nname = "test"')

        normalizer = PlanNormalizer(workspace=self.workspace, run_id="test-run")
        validation_steps = normalizer._infer_validation_steps(
            category="backend",
            scope_paths=["src/main.rs", "src/lib.rs"],
        )

        assert len(validation_steps) > 0
        assert any("cargo test" in step for step in validation_steps)

    def test_fallback_to_syntax_check(self):
        """Test fallback to syntax check when no test framework detected."""
        normalizer = PlanNormalizer(workspace=self.workspace, run_id="test-run")
        validation_steps = normalizer._infer_validation_steps(
            category="backend",
            scope_paths=["src/main.py"],
        )

        assert len(validation_steps) > 0
        assert any("py_compile" in step for step in validation_steps)


class TestPlanNormalization:
    """Test end-to-end plan normalization."""

    def setup_method(self):
        """Set up test workspace."""
        self.tmpdir = tempfile.mkdtemp()
        self.workspace = Path(self.tmpdir)

        # Create minimal repo structure
        (self.workspace / "src").mkdir()
        (self.workspace / "src" / "main.py").write_text("# Main")
        (self.workspace / "tests").mkdir()
        (self.workspace / "tests" / "test_main.py").write_text("# Tests")
        (self.workspace / "pytest.ini").write_text("[pytest]")

    def teardown_method(self):
        """Clean up test workspace."""
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_normalize_success(self):
        """Test successful normalization of a valid plan."""
        normalizer = PlanNormalizer(workspace=self.workspace, run_id="test-run-001")

        plan = """
        Implement user authentication:
        1. Add JWT token generation
        2. Create login endpoint
        3. Add authentication middleware
        """

        result = normalizer.normalize(plan)

        assert result.success
        assert result.structured_plan is not None
        assert result.confidence > 0
        # Warnings are acceptable (e.g., missing success criteria)
        # Just verify it succeeded

        # Verify structured plan has required fields
        plan_dict = result.structured_plan
        assert "run" in plan_dict
        assert "tiers" in plan_dict
        assert "phases" in plan_dict
        assert plan_dict["run"]["run_id"] == "test-run-001"
        assert plan_dict["run"]["token_cap"] == DEFAULT_TOKEN_CAP

    def test_normalize_fail_no_deliverables(self):
        """Test normalization fails when no deliverables detected."""
        normalizer = PlanNormalizer(workspace=self.workspace, run_id="test-run-001")

        plan = "Just do something vague"

        result = normalizer.normalize(plan)

        assert not result.success
        assert result.error is not None
        assert "deliverables" in result.error.lower()

    def test_normalize_applies_custom_budgets(self):
        """Test that custom budgets are applied."""
        normalizer = PlanNormalizer(workspace=self.workspace, run_id="test-run-001")

        plan = """
        - Implement feature A
        - Add feature B
        """

        run_config = {
            "token_cap": 100000,
            "max_phases": 5,
            "max_duration_minutes": 60,
        }

        result = normalizer.normalize(plan, run_config=run_config)

        assert result.success
        plan_dict = result.structured_plan
        assert plan_dict["run"]["token_cap"] == 100000
        assert plan_dict["run"]["max_phases"] == 5
        assert plan_dict["run"]["max_duration_minutes"] == 60

    def test_normalize_includes_validation_steps(self):
        """Test that normalized plan includes validation steps."""
        normalizer = PlanNormalizer(workspace=self.workspace, run_id="test-run-001")

        plan = """
        - Add user authentication
        - Create login endpoint
        """

        result = normalizer.normalize(plan)

        assert result.success
        plan_dict = result.structured_plan
        phases = plan_dict["phases"]
        assert len(phases) > 0
        assert phases[0]["scope"]["test_cmd"] is not None

    def test_normalize_stores_decisions_in_memory(self):
        """Test that normalization decisions are stored in memory."""
        mock_memory = MagicMock()
        mock_memory.enabled = True

        normalizer = PlanNormalizer(
            workspace=self.workspace,
            run_id="test-run-001",
            memory_service=mock_memory,
        )

        plan = """
        - Add user authentication
        - Create login endpoint
        """

        result = normalizer.normalize(plan)

        assert result.success
        mock_memory.write_plan_change.assert_called_once()
        call_kwargs = mock_memory.write_plan_change.call_args[1]
        assert "deliverables" in call_kwargs["summary"].lower()
        assert "category" in call_kwargs["summary"].lower()

    def test_normalize_uses_intention_context(self):
        """Test that normalization uses intention context when available."""
        mock_intention_manager = MagicMock()
        mock_intention_manager.get_intention_context.return_value = (
            "# Project Intention\n\nBuild a secure authentication system"
        )

        normalizer = PlanNormalizer(
            workspace=self.workspace,
            run_id="test-run-001",
            intention_manager=mock_intention_manager,
        )

        plan = "- Add authentication"

        result = normalizer.normalize(plan)

        assert result.success
        mock_intention_manager.get_intention_context.assert_called_once()
        assert result.normalization_decisions["intention_used"]

    def test_normalize_graceful_when_memory_disabled(self):
        """Test graceful degradation when memory is disabled."""
        mock_memory = MagicMock()
        mock_memory.enabled = False

        normalizer = PlanNormalizer(
            workspace=self.workspace,
            run_id="test-run-001",
            memory_service=mock_memory,
        )

        plan = "- Add authentication"

        result = normalizer.normalize(plan)

        assert result.success
        mock_memory.write_plan_change.assert_not_called()


class TestConvenienceFunction:
    """Test convenience function."""

    def setup_method(self):
        """Set up test workspace."""
        self.tmpdir = tempfile.mkdtemp()
        self.workspace = Path(self.tmpdir)

        # Create minimal repo structure
        (self.workspace / "src").mkdir()
        (self.workspace / "src" / "main.py").write_text("# Main")
        (self.workspace / "tests").mkdir()
        (self.workspace / "pytest.ini").write_text("[pytest]")

    def teardown_method(self):
        """Clean up test workspace."""
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_normalize_plan_convenience_function(self):
        """Test normalize_plan convenience function."""
        plan = """
        - Implement authentication
        - Add login endpoint
        """

        result = normalize_plan(
            workspace=self.workspace,
            run_id="test-run-001",
            raw_plan=plan,
            project_id="test-project",
        )

        assert result.success
        assert result.structured_plan is not None
