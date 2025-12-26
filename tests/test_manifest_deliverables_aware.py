"""Tests for BUILD-128 Deliverables-Aware Manifest System.

Tests the deliverables inference logic that prevents category mismatches.
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, MagicMock

from autopack.manifest_generator import ManifestGenerator
from autopack.repo_scanner import RepoScanner
from autopack.pattern_matcher import PatternMatcher
from autopack.preflight_validator import PreflightValidator


@pytest.fixture
def mock_scanner():
    """Mock RepoScanner with file_exists checks."""
    scanner = Mock(spec=RepoScanner)
    scanner.file_exists = Mock(side_effect=lambda path: path in [
        "src/autopack/models.py",
        "src/autopack/database.py",
        "tests/conftest.py",
        "alembic.ini",
        "alembic/env.py"
    ])
    return scanner


@pytest.fixture
def generator(mock_scanner):
    """Create ManifestGenerator with mocked dependencies."""
    matcher = Mock(spec=PatternMatcher)
    validator = Mock(spec=PreflightValidator)
    gen = ManifestGenerator(
        workspace=Path("/fake"),
        enable_plan_analyzer=False
    )
    gen.scanner = mock_scanner
    gen.matcher = matcher
    gen.validator = validator
    return gen


class TestInferCategoryFromDeliverables:
    """Test _infer_category_from_deliverables() method."""

    def test_backend_single_autopack_file(self, generator):
        """Single backend autopack file should be categorized as backend with 1.0 confidence."""
        deliverables = ["src/autopack/phase_finalizer.py"]
        category, confidence = generator._infer_category_from_deliverables(deliverables)

        assert category == "backend"
        assert confidence == 1.0

    def test_backend_multiple_autopack_files(self, generator):
        """Multiple backend files should be categorized as backend with 1.0 confidence."""
        deliverables = [
            "src/autopack/phase_finalizer.py",
            "src/autopack/test_baseline_tracker.py",
            "src/autopack/governance_request_handler.py"
        ]
        category, confidence = generator._infer_category_from_deliverables(deliverables)

        assert category == "backend"
        assert confidence == 1.0

    def test_frontend_tsx_files(self, generator):
        """Frontend TypeScript files should be categorized as frontend."""
        deliverables = [
            "src/frontend/App.tsx",
            "src/frontend/components/Button.tsx"
        ]
        category, confidence = generator._infer_category_from_deliverables(deliverables)

        assert category == "frontend"
        assert confidence == 1.0

    def test_tests_category(self, generator):
        """Test files should be categorized as tests."""
        deliverables = [
            "tests/test_phase_finalizer.py",
            "tests/test_baseline_tracker.py"
        ]
        category, confidence = generator._infer_category_from_deliverables(deliverables)

        assert category == "tests"
        assert confidence == 1.0

    def test_database_migrations(self, generator):
        """Database migration files should be categorized as database."""
        deliverables = [
            "alembic/versions/abc123_add_governance_requests.py",
            "src/autopack/models.py"
        ]
        category, confidence = generator._infer_category_from_deliverables(deliverables)

        # Should match either database or backend (models.py)
        assert category in ["database", "backend"]
        assert confidence >= 0.5

    def test_documentation_files(self, generator):
        """Documentation files should be categorized as documentation."""
        deliverables = [
            "docs/BUILD-128_DELIVERABLES_AWARE_MANIFEST.md",
            "README.md"
        ]
        category, confidence = generator._infer_category_from_deliverables(deliverables)

        assert category == "documentation"
        assert confidence == 1.0

    def test_empty_deliverables(self, generator):
        """Empty deliverables should return unknown with 0.0 confidence."""
        deliverables = []
        category, confidence = generator._infer_category_from_deliverables(deliverables)

        assert category == "unknown"
        assert confidence == 0.0

    def test_mixed_categories_backend_dominant(self, generator):
        """Mixed categories should pick dominant one (backend in this case)."""
        deliverables = [
            "src/autopack/phase_finalizer.py",
            "src/autopack/test_baseline_tracker.py",
            "tests/test_phase_finalizer.py"  # 2 backend, 1 test
        ]
        category, confidence = generator._infer_category_from_deliverables(deliverables)

        assert category == "backend"
        assert confidence == pytest.approx(0.666, abs=0.01)  # 2/3

    def test_build127_scenario(self, generator):
        """BUILD-127 scenario should correctly categorize as backend."""
        deliverables = [
            "src/autopack/test_baseline_tracker.py",
            "src/autopack/phase_finalizer.py",
            "src/autopack/governance_request_handler.py",
            "alembic/versions/xyz_add_governance_requests.py",
            "tests/test_baseline_tracker.py",
            "tests/test_phase_finalizer.py",
            "tests/test_governance_request_handler.py",
        ]
        category, confidence = generator._infer_category_from_deliverables(deliverables)

        # Should be backend (3), database (1), or tests (3) - any is acceptable
        # The important thing is it's NOT frontend
        assert category in ["backend", "database", "tests"]
        assert category != "frontend"
        assert confidence >= 0.4


class TestExpandScopeFromDeliverables:
    """Test _expand_scope_from_deliverables() method."""

    def test_backend_adds_models_context(self, generator):
        """Backend deliverables should add models.py to read_only_context."""
        deliverables = ["src/autopack/phase_finalizer.py"]
        scope_paths, read_only = generator._expand_scope_from_deliverables(
            deliverables=deliverables,
            category="backend",
            phase_id="test-phase"
        )

        assert scope_paths == ["src/autopack/phase_finalizer.py"]
        assert "src/autopack/models.py" in read_only

    def test_backend_with_database_adds_database_py(self, generator):
        """Backend with 'database' or 'models' in deliverables adds database.py."""
        deliverables = ["src/autopack/models.py"]
        scope_paths, read_only = generator._expand_scope_from_deliverables(
            deliverables=deliverables,
            category="backend",
            phase_id="database-phase"
        )

        assert scope_paths == ["src/autopack/models.py"]
        assert "src/autopack/database.py" in read_only

    def test_tests_adds_conftest(self, generator):
        """Test deliverables should add conftest.py to context."""
        deliverables = ["tests/test_feature.py"]
        scope_paths, read_only = generator._expand_scope_from_deliverables(
            deliverables=deliverables,
            category="tests",
            phase_id="test-phase"
        )

        assert scope_paths == ["tests/test_feature.py"]
        assert "tests/conftest.py" in read_only

    def test_database_adds_alembic_context(self, generator):
        """Database deliverables should add alembic configuration."""
        deliverables = ["alembic/versions/abc_migration.py"]
        scope_paths, read_only = generator._expand_scope_from_deliverables(
            deliverables=deliverables,
            category="database",
            phase_id="migration-phase"
        )

        assert scope_paths == ["alembic/versions/abc_migration.py"]
        assert "src/autopack/models.py" in read_only
        assert "alembic.ini" in read_only
        assert "alembic/env.py" in read_only

    def test_no_duplicates_in_scope(self, generator):
        """Duplicates should be removed from scope_paths."""
        deliverables = [
            "src/autopack/models.py",
            "src/autopack/models.py"  # Duplicate
        ]
        scope_paths, read_only = generator._expand_scope_from_deliverables(
            deliverables=deliverables,
            category="backend",
            phase_id="test-phase"
        )

        assert scope_paths == ["src/autopack/models.py"]  # No duplicate


class TestEnhancePhaseWithDeliverables:
    """Test _enhance_phase() with BUILD-128 deliverables logic."""

    def test_skip_generation_when_scope_paths_provided(self, generator):
        """Should skip generation if scope.paths already provided."""
        phase = {
            "phase_id": "test-phase",
            "goal": "Test goal",
            "scope": {
                "paths": ["src/autopack/existing.py"]
            }
        }

        enhanced, confidence, warnings = generator._enhance_phase(phase)

        assert enhanced == phase
        assert confidence == 1.0
        assert warnings == []
        # Pattern matcher should not be called
        assert not generator.matcher.match.called

    def test_infer_from_deliverables_backend(self, generator):
        """Should infer backend category from deliverables."""
        phase = {
            "phase_id": "build127-phase1",
            "goal": "Implement authoritative completion gates",
            "scope": {
                "deliverables": [
                    "src/autopack/phase_finalizer.py",
                    "src/autopack/test_baseline_tracker.py"
                ]
            }
        }

        enhanced, confidence, warnings = generator._enhance_phase(phase)

        # Should infer backend, not run pattern matching
        assert enhanced["metadata"]["category"] == "backend"
        assert enhanced["metadata"]["inferred_from"] == "deliverables"
        assert confidence == 1.0
        assert warnings == []

        # Scope should include deliverables
        assert "src/autopack/phase_finalizer.py" in enhanced["scope"]["paths"]
        assert "src/autopack/test_baseline_tracker.py" in enhanced["scope"]["paths"]

        # Should add models.py as context
        assert "src/autopack/models.py" in enhanced["scope"]["read_only_context"]

        # Pattern matcher should NOT be called
        assert not generator.matcher.match.called

    def test_infer_from_deliverables_frontend(self, generator):
        """Should infer frontend category from deliverables."""
        phase = {
            "phase_id": "frontend-phase",
            "goal": "Add dashboard component",
            "scope": {
                "deliverables": [
                    "src/frontend/components/Dashboard.tsx"
                ]
            }
        }

        enhanced, confidence, warnings = generator._enhance_phase(phase)

        assert enhanced["metadata"]["category"] == "frontend"
        assert enhanced["metadata"]["inferred_from"] == "deliverables"
        assert confidence == 1.0

        # Pattern matcher should NOT be called
        assert not generator.matcher.match.called

    def test_fallback_to_pattern_matching_without_deliverables(self, generator):
        """Should run pattern matching if no deliverables provided."""
        from autopack.pattern_matcher import MatchResult

        # Mock pattern matcher and get_test_scope
        generator.matcher.match = Mock(return_value=MatchResult(
            category="backend",
            confidence=0.8,
            scope_paths=["src/autopack/matched.py"],
            read_only_context=[],
            confidence_breakdown={},
            anchor_files_found=[],
            match_density=0.8,
            directory_locality=0.9
        ))
        generator.matcher.get_test_scope = Mock(return_value=["tests/test_matched.py"])

        phase = {
            "phase_id": "test-phase",
            "goal": "Add new feature",
            "scope": {}  # No deliverables, no paths
        }

        enhanced, confidence, warnings = generator._enhance_phase(phase)

        # Should call pattern matcher
        assert generator.matcher.match.called
        assert enhanced["metadata"]["category"] == "backend"
        assert confidence == 0.8

    def test_infer_from_bucketed_deliverables_dict_flattens_paths(self, generator):
        """Bucketed deliverables dict (code/tests/docs) should be flattened (no 'code' key leaked into scope.paths)."""
        phase = {
            "phase_id": "bucketed-phase",
            "goal": "Implement research system components",
            "scope": {
                "deliverables": {
                    "code": ["src/research/agents/meta_auditor.py"],
                    "tests": ["tests/research/agents/test_meta_auditor.py"],
                    "docs": ["docs/research/meta_analysis.md"],
                }
            },
        }

        enhanced, confidence, warnings = generator._enhance_phase(phase)

        assert warnings == []
        # scope.paths should contain actual file paths, not bucket keys like "code"
        assert "code" not in enhanced["scope"]["paths"]
        assert "tests" not in enhanced["scope"]["paths"]
        assert "docs" not in enhanced["scope"]["paths"]
        assert "src/research/agents/meta_auditor.py" in enhanced["scope"]["paths"]
        assert "tests/research/agents/test_meta_auditor.py" in enhanced["scope"]["paths"]
        assert "docs/research/meta_analysis.md" in enhanced["scope"]["paths"]
        # Top-level deliverables should be a flattened list
        assert isinstance(enhanced.get("deliverables"), list)
        assert "src/research/agents/meta_auditor.py" in enhanced["deliverables"]


class TestBuild127Regression:
    """Regression tests for BUILD-127 manifest issue."""

    def test_build127_phase1_generates_correct_scope(self, generator):
        """BUILD-127 Phase 1 should generate backend scope, not frontend."""
        phase = {
            "phase_id": "build127-phase1-self-healing-governance",
            "goal": "Implement authoritative completion gates and governance negotiation to prevent false completions and enable autonomous protected path access.",
            "description": "Authoritative completion gates and governance negotiation",
            "scope": {
                "deliverables": [
                    "src/autopack/test_baseline_tracker.py",
                    "src/autopack/phase_finalizer.py",
                    "src/autopack/governance_request_handler.py",
                    "alembic/versions/add_governance_requests.py",
                    "tests/test_baseline_tracker.py",
                    "tests/test_phase_finalizer.py",
                    "tests/test_governance_request_handler.py",
                    "tests/test_build127_phase1_integration.py",
                    "requirements.txt",
                    "docs/BUILD-127_PHASE1_COMPLETION.md"
                ]
            }
        }

        enhanced, confidence, warnings = generator._enhance_phase(phase)

        # Should infer backend/database, NOT frontend
        assert enhanced["metadata"]["category"] in ["backend", "database", "tests"]
        assert enhanced["metadata"]["category"] != "frontend"

        # Should have high confidence
        assert confidence >= 0.5

        # Scope should NOT include frontend files
        frontend_files = [p for p in enhanced["scope"]["paths"] if "frontend" in p]
        assert len(frontend_files) == 0, f"Found frontend files in scope: {frontend_files}"

        # Should include deliverables in scope
        for deliverable in phase["scope"]["deliverables"]:
            assert deliverable in enhanced["scope"]["paths"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
