"""Contract tests for apply/policy.py module.

Tests the patch policy configuration and path validation functions
extracted from governed_apply.py.
"""

from __future__ import annotations

from autopack.apply.policy import (
    ALLOWED_PATHS,
    MAINTENANCE_RUN_TYPES,
    PROTECTED_PATHS,
    extract_justification_from_patch,
    get_effective_allowed_paths,
    get_effective_protected_paths,
    is_path_protected,
    normalize_relpath,
    validate_patch_paths,
)


class TestProtectedPathsConfig:
    """Tests for protected paths configuration."""

    def test_protected_paths_includes_core_directories(self) -> None:
        """Protected paths should include core Autopack directories."""
        assert "src/autopack/" in PROTECTED_PATHS
        assert "config/" in PROTECTED_PATHS
        assert ".git/" in PROTECTED_PATHS
        assert ".autonomous_runs/" in PROTECTED_PATHS

    def test_protected_paths_includes_critical_files(self) -> None:
        """Protected paths should include critical individual files."""
        assert "src/autopack/config.py" in PROTECTED_PATHS
        assert "src/autopack/governed_apply.py" in PROTECTED_PATHS
        assert "src/autopack/autonomous_executor.py" in PROTECTED_PATHS

    def test_allowed_paths_includes_maintenance_modules(self) -> None:
        """Allowed paths should include maintenance-safe modules."""
        assert "src/autopack/learned_rules.py" in ALLOWED_PATHS
        assert "src/autopack/llm_service.py" in ALLOWED_PATHS

    def test_maintenance_run_types_defined(self) -> None:
        """Maintenance run types should be defined."""
        assert "autopack_maintenance" in MAINTENANCE_RUN_TYPES
        assert "autopack_upgrade" in MAINTENANCE_RUN_TYPES
        assert "self_repair" in MAINTENANCE_RUN_TYPES


class TestIsPathProtected:
    """Tests for is_path_protected function."""

    def test_core_autopack_path_is_protected(self) -> None:
        """src/autopack/ paths should be protected by default."""
        assert is_path_protected(
            "src/autopack/some_module.py",
            PROTECTED_PATHS,
            [],
        )

    def test_git_directory_is_protected(self) -> None:
        """.git/ paths should be protected."""
        assert is_path_protected(
            ".git/config",
            PROTECTED_PATHS,
            [],
        )

    def test_project_file_is_not_protected(self) -> None:
        """Project files outside protected areas should not be protected."""
        assert not is_path_protected(
            "myproject/src/main.py",
            PROTECTED_PATHS,
            [],
        )

    def test_allowed_path_overrides_protection(self) -> None:
        """Allowed paths should override protection."""
        assert not is_path_protected(
            "src/autopack/learned_rules.py",
            PROTECTED_PATHS,
            ALLOWED_PATHS,
        )

    def test_normalizes_windows_paths(self) -> None:
        """Windows-style paths should be normalized."""
        assert is_path_protected(
            "src\\autopack\\some_module.py",
            PROTECTED_PATHS,
            [],
        )


class TestNormalizeRelpath:
    """Tests for normalize_relpath function."""

    def test_normalizes_backslashes(self) -> None:
        """Backslashes should be converted to forward slashes."""
        assert normalize_relpath("src\\pkg\\file.py") == "src/pkg/file.py"

    def test_strips_leading_dot_slash(self) -> None:
        """Leading ./ should be stripped."""
        assert normalize_relpath("./src/file.py") == "src/file.py"

    def test_strips_leading_slash(self) -> None:
        """Leading / should be stripped."""
        assert normalize_relpath("/src/file.py") == "src/file.py"

    def test_collapses_duplicate_slashes(self) -> None:
        """Duplicate slashes should be collapsed."""
        assert normalize_relpath("src//pkg///file.py") == "src/pkg/file.py"

    def test_handles_empty_string(self) -> None:
        """Empty string should return empty string."""
        assert normalize_relpath("") == ""

    def test_handles_none(self) -> None:
        """None should return empty string."""
        assert normalize_relpath(None) == ""


class TestValidatePatchPaths:
    """Tests for validate_patch_paths function."""

    def test_allows_project_files(self) -> None:
        """Project files should be allowed."""
        files = ["project/src/main.py", "project/tests/test_main.py"]

        is_valid, violations = validate_patch_paths(
            files,
            PROTECTED_PATHS,
            ALLOWED_PATHS,
        )

        assert is_valid
        assert violations == []

    def test_blocks_protected_paths(self) -> None:
        """Protected paths should be blocked."""
        files = ["src/autopack/database.py"]

        is_valid, violations = validate_patch_paths(
            files,
            PROTECTED_PATHS,
            [],
        )

        assert not is_valid
        assert len(violations) == 1
        assert "Protected path" in violations[0]

    def test_allows_explicitly_allowed_paths(self) -> None:
        """Explicitly allowed paths should override protection."""
        files = ["src/autopack/learned_rules.py"]

        is_valid, violations = validate_patch_paths(
            files,
            PROTECTED_PATHS,
            ALLOWED_PATHS,
        )

        assert is_valid
        assert violations == []

    def test_enforces_scope_exact_match(self) -> None:
        """Scope enforcement should block files not in scope."""
        files = ["src/module.py", "src/other.py"]
        scope_paths = ["src/module.py"]

        is_valid, violations = validate_patch_paths(
            files,
            [],
            [],
            scope_paths,
        )

        assert not is_valid
        assert any("Outside scope" in v for v in violations)

    def test_enforces_scope_directory_prefix(self) -> None:
        """Scope directories should allow all files under them."""
        files = ["src/pkg/module.py", "src/pkg/sub/file.py"]
        scope_paths = ["src/pkg/"]

        is_valid, violations = validate_patch_paths(
            files,
            [],
            [],
            scope_paths,
        )

        assert is_valid
        assert violations == []

    def test_combines_protection_and_scope(self) -> None:
        """Both protection and scope violations should be reported."""
        files = [".git/config", "outside/file.py"]
        scope_paths = ["allowed/"]

        is_valid, violations = validate_patch_paths(
            files,
            PROTECTED_PATHS,
            [],
            scope_paths,
        )

        assert not is_valid
        assert any("Protected path" in v for v in violations)
        assert any("Outside scope" in v for v in violations)


class TestGetEffectiveProtectedPaths:
    """Tests for get_effective_protected_paths function."""

    def test_returns_default_protected_paths(self) -> None:
        """Should return default protected paths."""
        paths = get_effective_protected_paths()

        assert "src/autopack/" in paths
        assert ".git/" in paths

    def test_includes_additional_paths(self) -> None:
        """Should include additional protected paths."""
        paths = get_effective_protected_paths(additional_protected=["custom/protected/"])

        assert "custom/protected/" in paths

    def test_internal_mode_unlocks_autopack(self) -> None:
        """Internal mode should remove src/autopack/ from protection."""
        paths = get_effective_protected_paths(autopack_internal_mode=True)

        assert "src/autopack/" not in paths
        # But critical files should still be protected
        assert "src/autopack/config.py" in paths


class TestGetEffectiveAllowedPaths:
    """Tests for get_effective_allowed_paths function."""

    def test_returns_default_allowed_paths(self) -> None:
        """Should return default allowed paths."""
        paths = get_effective_allowed_paths()

        assert "src/autopack/learned_rules.py" in paths

    def test_includes_additional_paths(self) -> None:
        """Should include additional allowed paths."""
        paths = get_effective_allowed_paths(additional_allowed=["custom/allowed.py"])

        assert "custom/allowed.py" in paths

    def test_normalizes_directory_paths(self) -> None:
        """Directory paths without trailing slash should get one."""
        paths = get_effective_allowed_paths(additional_allowed=["custom/dir"])

        assert "custom/dir/" in paths


class TestExtractJustificationFromPatch:
    """Tests for extract_justification_from_patch function."""

    def test_extracts_comment_justification(self) -> None:
        """Should extract justification from # comments."""
        patch = """# This patch fixes bug X
# by updating the handler
diff --git a/file.py b/file.py"""

        result = extract_justification_from_patch(patch)

        assert "fixes bug X" in result

    def test_extracts_subject_line(self) -> None:
        """Should extract justification from Subject: line."""
        patch = """Subject: Fix authentication flow
diff --git a/file.py b/file.py"""

        result = extract_justification_from_patch(patch)

        assert "Fix authentication flow" in result

    def test_extracts_summary_line(self) -> None:
        """Should extract justification from Summary: line."""
        patch = """Summary: Update error handling
diff --git a/file.py b/file.py"""

        result = extract_justification_from_patch(patch)

        assert "Update error handling" in result

    def test_returns_default_when_no_justification(self) -> None:
        """Should return default message when no justification found."""
        patch = """diff --git a/file.py b/file.py
--- a/file.py
+++ b/file.py"""

        result = extract_justification_from_patch(patch)

        assert "No justification provided" in result

    def test_limits_to_first_50_lines(self) -> None:
        """Should only check first 50 lines for justification."""
        patch = "\n".join(["line"] * 60)
        patch += "\n# Late justification"

        result = extract_justification_from_patch(patch)

        assert "Late justification" not in result
