"""Tests for failure hardening system (Phase 4 of True Autonomy)."""

from autopack.failure_hardening import (
    FailureHardeningRegistry,
    FailurePattern,
    MitigationResult,
    detect_and_mitigate_failure,
    get_registry,
)


class TestFailurePattern:
    """Test FailurePattern dataclass."""

    def test_failure_pattern_creation(self):
        """Test creating a failure pattern."""
        pattern = FailurePattern(
            pattern_id="test_pattern",
            name="Test Pattern",
            description="Test description",
            detector=lambda e, c: True,
            mitigation=lambda c: {"success": True},
            priority=3,
            enabled=True,
        )

        assert pattern.pattern_id == "test_pattern"
        assert pattern.name == "Test Pattern"
        assert pattern.priority == 3
        assert pattern.enabled is True
        assert pattern.detector("", {}) is True
        assert pattern.mitigation({}) == {"success": True}


class TestMitigationResult:
    """Test MitigationResult dataclass."""

    def test_mitigation_result_creation(self):
        """Test creating a mitigation result."""
        result = MitigationResult(
            success=True,
            pattern_id="test_pattern",
            actions_taken=["action1", "action2"],
            suggestions=["suggestion1"],
            fixed=True,
        )

        assert result.success is True
        assert result.pattern_id == "test_pattern"
        assert len(result.actions_taken) == 2
        assert len(result.suggestions) == 1
        assert result.fixed is True

    def test_mitigation_result_default_fixed(self):
        """Test default fixed value is False."""
        result = MitigationResult(
            success=True,
            pattern_id="test_pattern",
            actions_taken=[],
            suggestions=[],
        )

        assert result.fixed is False


class TestFailureHardeningRegistry:
    """Test FailureHardeningRegistry."""

    def test_registry_initialization(self):
        """Test registry initializes with built-in patterns."""
        registry = FailureHardeningRegistry()

        # Should have 6 built-in patterns
        assert len(registry.patterns) == 6

        # Check pattern IDs
        expected_ids = [
            "python_missing_dep",
            "wrong_working_dir",
            "missing_test_discovery",
            "scope_mismatch",
            "node_missing_dep",
            "permission_error",
        ]

        for pattern_id in expected_ids:
            assert pattern_id in registry.patterns

    def test_list_patterns(self):
        """Test list_patterns returns pattern IDs sorted by priority."""
        registry = FailureHardeningRegistry()

        pattern_ids = registry.list_patterns()

        # Should return all pattern IDs
        assert len(pattern_ids) == 6

        # Should be sorted by priority (lowest first)
        priorities = [registry.patterns[pid].priority for pid in pattern_ids]
        assert priorities == sorted(priorities)

    def test_list_patterns_with_custom_pattern(self):
        """Test list_patterns includes custom patterns in priority order."""
        registry = FailureHardeningRegistry()

        # Add a high-priority custom pattern
        custom_pattern = FailurePattern(
            pattern_id="custom_highest",
            name="Custom Highest Priority",
            description="Test",
            detector=lambda e, c: False,
            mitigation=lambda c: {},
            priority=0,  # Highest priority
        )
        registry.register_pattern(custom_pattern)

        pattern_ids = registry.list_patterns()

        # Custom pattern should be first (highest priority = lowest number)
        assert pattern_ids[0] == "custom_highest"
        assert len(pattern_ids) == 7

    def test_register_pattern(self):
        """Test registering a custom pattern."""
        registry = FailureHardeningRegistry()
        initial_count = len(registry.patterns)

        custom_pattern = FailurePattern(
            pattern_id="custom_pattern",
            name="Custom Pattern",
            description="Test",
            detector=lambda e, c: False,
            mitigation=lambda c: {},
        )

        registry.register_pattern(custom_pattern)

        assert len(registry.patterns) == initial_count + 1
        assert "custom_pattern" in registry.patterns
        assert registry.patterns["custom_pattern"] == custom_pattern

    def test_detect_no_match(self):
        """Test detection when no pattern matches."""
        registry = FailureHardeningRegistry()

        error_text = "This is a completely unknown error that matches nothing"
        context = {}

        result = registry.detect_and_mitigate(error_text, context)

        assert result is None

    def test_detect_disabled_pattern(self):
        """Test that disabled patterns are skipped."""
        registry = FailureHardeningRegistry()

        # Disable all patterns
        for pattern in registry.patterns.values():
            pattern.enabled = False

        error_text = "ModuleNotFoundError: No module named 'foo'"
        context = {}

        result = registry.detect_and_mitigate(error_text, context)

        assert result is None

    def test_priority_ordering(self):
        """Test that patterns are checked in priority order."""
        registry = FailureHardeningRegistry()

        # Create two patterns that both match
        calls = []

        def detector1(e, c):
            calls.append("detector1")
            return True

        def detector2(e, c):
            calls.append("detector2")
            return True

        pattern1 = FailurePattern(
            pattern_id="low_priority",
            name="Low Priority",
            description="Test",
            detector=detector1,
            mitigation=lambda c: {"success": True, "pattern": "low"},
            priority=10,  # Lower priority (higher number)
        )

        pattern2 = FailurePattern(
            pattern_id="high_priority",
            name="High Priority",
            description="Test",
            detector=detector2,
            mitigation=lambda c: {"success": True, "pattern": "high"},
            priority=1,  # Higher priority (lower number)
        )

        registry.register_pattern(pattern1)
        registry.register_pattern(pattern2)

        result = registry.detect_and_mitigate("error", {})

        # High priority pattern should be checked first and match
        assert calls[0] == "detector2"
        assert result.pattern_id == "high_priority"

    def test_detector_exception_handling(self):
        """Test that detector exceptions are caught and logged."""
        registry = FailureHardeningRegistry()

        def failing_detector(e, c):
            raise ValueError("Detector failed")

        pattern = FailurePattern(
            pattern_id="failing_pattern",
            name="Failing Pattern",
            description="Test",
            detector=failing_detector,
            mitigation=lambda c: {},
            priority=1,
        )

        registry.register_pattern(pattern)

        # Should not raise exception
        result = registry.detect_and_mitigate("error", {})

        # Should continue to next pattern (none match)
        assert result is None


class TestPythonMissingDep:
    """Test Python missing dependency pattern."""

    def test_detect_module_not_found(self):
        """Test detecting ModuleNotFoundError."""
        registry = FailureHardeningRegistry()

        error_text = "ModuleNotFoundError: No module named 'pytest'"
        context = {}

        assert registry._detect_missing_python_dep(error_text, context) is True

    def test_detect_import_error(self):
        """Test detecting ImportError."""
        registry = FailureHardeningRegistry()

        error_text = "ImportError: cannot import name 'foo' from 'bar'"
        context = {}

        assert registry._detect_missing_python_dep(error_text, context) is True

    def test_detect_import_error_no_module_named(self):
        """Test detecting ImportError: No module named."""
        registry = FailureHardeningRegistry()

        error_text = "ImportError: No module named mypackage"
        context = {}

        assert registry._detect_missing_python_dep(error_text, context) is True

    def test_no_match(self):
        """Test non-matching error."""
        registry = FailureHardeningRegistry()

        error_text = "SyntaxError: invalid syntax"
        context = {}

        assert registry._detect_missing_python_dep(error_text, context) is False

    def test_mitigate_with_requirements_txt(self, tmp_path):
        """Test mitigation with requirements.txt."""
        registry = FailureHardeningRegistry()

        # Create requirements.txt
        (tmp_path / "requirements.txt").write_text("pytest==7.0.0\n")

        context = {"workspace": tmp_path}

        result = registry._mitigate_missing_python_dep(context)

        assert result["success"] is True
        assert "pip install -r requirements.txt" in result["suggestions"]
        assert result["fixed"] is False

    def test_mitigate_with_poetry(self, tmp_path):
        """Test mitigation with poetry."""
        registry = FailureHardeningRegistry()

        # Create pyproject.toml with poetry
        (tmp_path / "pyproject.toml").write_text("[tool.poetry]\nname = 'test'\n")

        context = {"workspace": tmp_path}

        result = registry._mitigate_missing_python_dep(context)

        assert result["success"] is True
        assert "poetry install" in result["suggestions"]

    def test_mitigate_with_uv(self, tmp_path):
        """Test mitigation with uv."""
        registry = FailureHardeningRegistry()

        # Create pyproject.toml with uv
        (tmp_path / "pyproject.toml").write_text("[tool.uv]\nenabled = true\n")

        context = {"workspace": tmp_path}

        result = registry._mitigate_missing_python_dep(context)

        assert result["success"] is True
        assert "uv pip install -r requirements.txt" in result["suggestions"]

    def test_mitigate_with_setup_py(self, tmp_path):
        """Test mitigation with setup.py."""
        registry = FailureHardeningRegistry()

        # Create setup.py
        (tmp_path / "setup.py").write_text("from setuptools import setup\n")

        context = {"workspace": tmp_path}

        result = registry._mitigate_missing_python_dep(context)

        assert result["success"] is True
        assert "pip install -e ." in result["suggestions"]

    def test_mitigate_with_pyproject_no_poetry_or_uv(self, tmp_path):
        """Test mitigation with pyproject.toml without poetry or uv."""
        registry = FailureHardeningRegistry()

        # Create pyproject.toml without poetry or uv markers
        (tmp_path / "pyproject.toml").write_text("[project]\nname = 'test'\nversion = '1.0.0'\n")

        context = {"workspace": tmp_path}

        result = registry._mitigate_missing_python_dep(context)

        assert result["success"] is True
        assert "pip install -e ." in result["suggestions"]

    def test_mitigate_with_detected_module(self, tmp_path):
        """Test mitigation suggests specific module install when detected."""
        registry = FailureHardeningRegistry()

        context = {"workspace": tmp_path, "detected_module": "requests"}

        result = registry._mitigate_missing_python_dep(context)

        assert result["success"] is True
        assert "pip install requests" in result["suggestions"]

    def test_detect_and_mitigate_extracts_module_name(self, tmp_path):
        """Test that detect_and_mitigate extracts module name for Python deps."""
        registry = FailureHardeningRegistry()

        (tmp_path / "requirements.txt").write_text("requests==2.28.0\n")

        error_text = "ModuleNotFoundError: No module named 'requests'"
        context = {"workspace": tmp_path}

        result = registry.detect_and_mitigate(error_text, context)

        assert result is not None
        assert result.pattern_id == "python_missing_dep"
        # The specific module install suggestion should be first
        assert "pip install requests" in result.suggestions


class TestWrongWorkingDir:
    """Test wrong working directory pattern."""

    def test_detect_file_not_found(self):
        """Test detecting FileNotFoundError for project files."""
        registry = FailureHardeningRegistry()

        error_text = "FileNotFoundError: [Errno 2] No such file or directory: 'package.json'"
        context = {}

        assert registry._detect_wrong_working_dir(error_text, context) is True

    def test_detect_enoent(self):
        """Test detecting ENOENT for project files."""
        registry = FailureHardeningRegistry()

        error_text = "ENOENT: no such file or directory, open 'requirements.txt'"
        context = {}

        assert registry._detect_wrong_working_dir(error_text, context) is True

    def test_detect_cargo_toml(self):
        """Test detecting FileNotFoundError for Cargo.toml (Rust)."""
        registry = FailureHardeningRegistry()

        error_text = "FileNotFoundError: [Errno 2] No such file or directory: 'Cargo.toml'"
        context = {}

        assert registry._detect_wrong_working_dir(error_text, context) is True

    def test_detect_go_mod(self):
        """Test detecting FileNotFoundError for go.mod (Go)."""
        registry = FailureHardeningRegistry()

        error_text = "FileNotFoundError: [Errno 2] No such file or directory: 'go.mod'"
        context = {}

        assert registry._detect_wrong_working_dir(error_text, context) is True

    def test_detect_pom_xml(self):
        """Test detecting FileNotFoundError for pom.xml (Maven/Java)."""
        registry = FailureHardeningRegistry()

        error_text = "FileNotFoundError: [Errno 2] No such file or directory: 'pom.xml'"
        context = {}

        assert registry._detect_wrong_working_dir(error_text, context) is True

    def test_no_match_without_project_marker(self):
        """Test no match when FileNotFoundError doesn't mention project files."""
        registry = FailureHardeningRegistry()

        error_text = "FileNotFoundError: [Errno 2] No such file or directory: 'random_file.txt'"
        context = {}

        assert registry._detect_wrong_working_dir(error_text, context) is False

    def test_mitigate(self, tmp_path):
        """Test mitigation suggestions."""
        registry = FailureHardeningRegistry()

        context = {"workspace": tmp_path}

        result = registry._mitigate_wrong_working_dir(context)

        assert result["success"] is True
        assert any("working directory" in s.lower() for s in result["suggestions"])
        assert result["fixed"] is False


class TestMissingTestDiscovery:
    """Test missing test discovery pattern."""

    def test_detect_collected_0_items(self):
        """Test detecting 'collected 0 items'."""
        registry = FailureHardeningRegistry()

        error_text = "============================= collected 0 items ============================="
        context = {}

        assert registry._detect_missing_test_discovery(error_text, context) is True

    def test_detect_no_tests_ran(self):
        """Test detecting 'no tests ran'."""
        registry = FailureHardeningRegistry()

        error_text = "Ran 0 tests in 0.001s\nno tests ran"
        context = {}

        assert registry._detect_missing_test_discovery(error_text, context) is True

    def test_detect_cannot_find_test(self):
        """Test detecting 'cannot find test'."""
        registry = FailureHardeningRegistry()

        error_text = "ERROR: cannot find test files"
        context = {}

        assert registry._detect_missing_test_discovery(error_text, context) is True

    def test_detect_error_not_found_test(self):
        """Test detecting 'ERROR: not found test'."""
        registry = FailureHardeningRegistry()

        error_text = "ERROR: not found: test_example.py"
        context = {}

        assert registry._detect_missing_test_discovery(error_text, context) is True

    def test_no_match_normal_errors(self):
        """Test no match for normal errors without test keywords."""
        registry = FailureHardeningRegistry()

        error_text = "AttributeError: 'NoneType' object has no attribute 'items'"
        context = {}

        assert registry._detect_missing_test_discovery(error_text, context) is False

    def test_mitigate_with_tests_dir(self, tmp_path):
        """Test mitigation when tests/ directory exists."""
        registry = FailureHardeningRegistry()

        # Create tests directory
        (tmp_path / "tests").mkdir()

        context = {"workspace": tmp_path}

        result = registry._mitigate_missing_test_discovery(context)

        assert result["success"] is True
        assert any("pytest tests/" in s for s in result["suggestions"])

    def test_mitigate_without_tests_dir(self, tmp_path):
        """Test mitigation when no test directory exists."""
        registry = FailureHardeningRegistry()

        context = {"workspace": tmp_path}

        result = registry._mitigate_missing_test_discovery(context)

        assert result["success"] is True
        assert any("Create tests/" in s for s in result["suggestions"])

    def test_mitigate_with_test_dir(self, tmp_path):
        """Test mitigation when test/ directory exists (singular)."""
        registry = FailureHardeningRegistry()

        # Create test directory (singular, common in some projects)
        (tmp_path / "test").mkdir()

        context = {"workspace": tmp_path}

        result = registry._mitigate_missing_test_discovery(context)

        assert result["success"] is True
        assert any("pytest test/" in s for s in result["suggestions"])

    def test_mitigate_with_jest_tests_dir(self, tmp_path):
        """Test mitigation when __tests__/ directory exists (Jest convention)."""
        registry = FailureHardeningRegistry()

        # Create __tests__ directory (Jest convention)
        (tmp_path / "__tests__").mkdir()

        context = {"workspace": tmp_path}

        result = registry._mitigate_missing_test_discovery(context)

        assert result["success"] is True
        assert any("pytest __tests__/" in s for s in result["suggestions"])

    def test_mitigate_with_spec_dir(self, tmp_path):
        """Test mitigation when spec/ directory exists (Ruby/RSpec convention)."""
        registry = FailureHardeningRegistry()

        # Create spec directory (common in Ruby projects)
        (tmp_path / "spec").mkdir()

        context = {"workspace": tmp_path}

        result = registry._mitigate_missing_test_discovery(context)

        assert result["success"] is True
        assert any("pytest spec/" in s for s in result["suggestions"])


class TestScopeMismatch:
    """Test scope mismatch pattern."""

    def test_detect_outside_scope(self):
        """Test detecting 'outside scope'."""
        registry = FailureHardeningRegistry()

        error_text = "Error: File is outside the governed scope"
        context = {}

        assert registry._detect_scope_mismatch(error_text, context) is True

    def test_detect_not_in_scope(self):
        """Test detecting 'not in governed scope'."""
        registry = FailureHardeningRegistry()

        error_text = "not in governed scope"
        context = {}

        assert registry._detect_scope_mismatch(error_text, context) is True

    def test_detect_blocked_scope(self):
        """Test detecting 'blocked by scope'."""
        registry = FailureHardeningRegistry()

        error_text = "Action blocked by scope restrictions"
        context = {}

        assert registry._detect_scope_mismatch(error_text, context) is True

    def test_mitigate_with_scope(self):
        """Test mitigation with defined scope."""
        registry = FailureHardeningRegistry()

        context = {"scope_paths": ["src/foo.py", "src/bar.py", "tests/test_foo.py"]}

        result = registry._mitigate_scope_mismatch(context)

        assert result["success"] is True
        assert any("src/foo.py" in s for s in result["suggestions"])

    def test_mitigate_without_scope(self):
        """Test mitigation without defined scope."""
        registry = FailureHardeningRegistry()

        context = {}

        result = registry._mitigate_scope_mismatch(context)

        assert result["success"] is True
        assert any("No scope defined" in s for s in result["suggestions"])

    def test_mitigate_with_many_scope_paths(self):
        """Test mitigation truncates long scope path lists."""
        registry = FailureHardeningRegistry()

        # More than 5 paths - should be truncated with '...'
        context = {
            "scope_paths": [
                "src/a.py",
                "src/b.py",
                "src/c.py",
                "src/d.py",
                "src/e.py",
                "src/f.py",
                "src/g.py",
            ]
        }

        result = registry._mitigate_scope_mismatch(context)

        assert result["success"] is True
        # Should contain truncation indicator
        assert any("..." in s for s in result["suggestions"])
        # First 5 paths should be shown
        assert any("src/a.py" in s for s in result["suggestions"])


class TestNodeMissingDep:
    """Test Node.js missing dependency pattern."""

    def test_detect_cannot_find_module(self):
        """Test detecting 'Cannot find module'."""
        registry = FailureHardeningRegistry()

        error_text = "Error: Cannot find module 'express'"
        context = {}

        assert registry._detect_missing_node_dep(error_text, context) is True

    def test_detect_module_not_found(self):
        """Test detecting MODULE_NOT_FOUND."""
        registry = FailureHardeningRegistry()

        error_text = "MODULE_NOT_FOUND"
        context = {}

        assert registry._detect_missing_node_dep(error_text, context) is True

    def test_mitigate_with_yarn(self, tmp_path):
        """Test mitigation with yarn.lock."""
        registry = FailureHardeningRegistry()

        # Create yarn.lock
        (tmp_path / "yarn.lock").write_text("# yarn lockfile v1\n")

        context = {"workspace": tmp_path}

        result = registry._mitigate_missing_node_dep(context)

        assert result["success"] is True
        assert "yarn install" in result["suggestions"]

    def test_mitigate_with_pnpm(self, tmp_path):
        """Test mitigation with pnpm-lock.yaml."""
        registry = FailureHardeningRegistry()

        # Create pnpm-lock.yaml
        (tmp_path / "pnpm-lock.yaml").write_text("lockfileVersion: 5.3\n")

        context = {"workspace": tmp_path}

        result = registry._mitigate_missing_node_dep(context)

        assert result["success"] is True
        assert "pnpm install" in result["suggestions"]

    def test_mitigate_with_npm(self, tmp_path):
        """Test mitigation defaults to npm."""
        registry = FailureHardeningRegistry()

        context = {"workspace": tmp_path}

        result = registry._mitigate_missing_node_dep(context)

        assert result["success"] is True
        assert "npm install" in result["suggestions"]

    def test_mitigate_with_detected_module_yarn(self, tmp_path):
        """Test specific module install suggestion with yarn."""
        registry = FailureHardeningRegistry()

        (tmp_path / "yarn.lock").write_text("# yarn lockfile v1\n")

        context = {"workspace": tmp_path, "detected_module": "express"}

        result = registry._mitigate_missing_node_dep(context)

        assert result["success"] is True
        assert "yarn add express" in result["suggestions"]
        assert "yarn install" in result["suggestions"]

    def test_mitigate_with_detected_module_pnpm(self, tmp_path):
        """Test specific module install suggestion with pnpm."""
        registry = FailureHardeningRegistry()

        (tmp_path / "pnpm-lock.yaml").write_text("lockfileVersion: 5.3\n")

        context = {"workspace": tmp_path, "detected_module": "lodash"}

        result = registry._mitigate_missing_node_dep(context)

        assert result["success"] is True
        assert "pnpm add lodash" in result["suggestions"]
        assert "pnpm install" in result["suggestions"]

    def test_mitigate_with_detected_module_npm(self, tmp_path):
        """Test specific module install suggestion with npm."""
        registry = FailureHardeningRegistry()

        context = {"workspace": tmp_path, "detected_module": "axios"}

        result = registry._mitigate_missing_node_dep(context)

        assert result["success"] is True
        assert "npm install axios" in result["suggestions"]
        assert "npm install" in result["suggestions"]

    def test_detect_and_mitigate_extracts_node_module_name(self, tmp_path):
        """Test that detect_and_mitigate extracts module name for Node.js deps."""
        registry = FailureHardeningRegistry()

        error_text = "Error: Cannot find module 'express'"
        context = {"workspace": tmp_path}

        result = registry.detect_and_mitigate(error_text, context)

        assert result is not None
        assert result.pattern_id == "node_missing_dep"
        # The specific module install suggestion should be present
        assert "npm install express" in result.suggestions


class TestPermissionError:
    """Test permission error pattern."""

    def test_detect_permission_error(self):
        """Test detecting PermissionError."""
        registry = FailureHardeningRegistry()

        error_text = "PermissionError: [Errno 13] Permission denied: '/path/to/file'"
        context = {}

        assert registry._detect_permission_error(error_text, context) is True

    def test_detect_eacces(self):
        """Test detecting EACCES."""
        registry = FailureHardeningRegistry()

        error_text = "EACCES: permission denied, open '/path/to/file'"
        context = {}

        assert registry._detect_permission_error(error_text, context) is True

    def test_detect_permission_denied(self):
        """Test detecting 'permission denied'."""
        registry = FailureHardeningRegistry()

        error_text = "bash: permission denied: ./script.sh"
        context = {}

        assert registry._detect_permission_error(error_text, context) is True

    def test_mitigate(self):
        """Test mitigation suggestions."""
        registry = FailureHardeningRegistry()

        context = {}

        result = registry._mitigate_permission_error(context)

        assert result["success"] is True
        assert any("permission" in s.lower() for s in result["suggestions"])
        assert result["fixed"] is False


class TestEndToEnd:
    """Test end-to-end failure detection and mitigation."""

    def test_detect_and_mitigate_python_dep(self, tmp_path):
        """Test complete flow for Python dependency."""
        registry = FailureHardeningRegistry()

        # Create requirements.txt
        (tmp_path / "requirements.txt").write_text("pytest==7.0.0\n")

        error_text = "ModuleNotFoundError: No module named 'pytest'"
        context = {"workspace": tmp_path}

        result = registry.detect_and_mitigate(error_text, context)

        assert result is not None
        assert result.success is True
        assert result.pattern_id == "python_missing_dep"
        assert len(result.suggestions) > 0
        assert "pip install -r requirements.txt" in result.suggestions
        assert result.fixed is False

    def test_detect_and_mitigate_test_discovery(self, tmp_path):
        """Test complete flow for test discovery."""
        registry = FailureHardeningRegistry()

        # Create tests directory
        (tmp_path / "tests").mkdir()

        error_text = "collected 0 items"
        context = {"workspace": tmp_path}

        result = registry.detect_and_mitigate(error_text, context)

        assert result is not None
        assert result.success is True
        assert result.pattern_id == "missing_test_discovery"
        assert any("pytest tests/" in s for s in result.suggestions)

    def test_detect_and_mitigate_no_match(self):
        """Test complete flow when no pattern matches."""
        registry = FailureHardeningRegistry()

        error_text = "Some completely unknown error"
        context = {}

        result = registry.detect_and_mitigate(error_text, context)

        assert result is None


class TestGlobalRegistry:
    """Test global registry functions."""

    def test_get_registry_singleton(self):
        """Test that get_registry returns singleton."""
        registry1 = get_registry()
        registry2 = get_registry()

        assert registry1 is registry2

    def test_detect_and_mitigate_failure_convenience(self, tmp_path):
        """Test convenience function."""
        # Create requirements.txt
        (tmp_path / "requirements.txt").write_text("pytest==7.0.0\n")

        error_text = "ModuleNotFoundError: No module named 'pytest'"
        context = {"workspace": tmp_path}

        result = detect_and_mitigate_failure(error_text, context)

        assert result is not None
        assert result.pattern_id == "python_missing_dep"
        assert result.success is True
