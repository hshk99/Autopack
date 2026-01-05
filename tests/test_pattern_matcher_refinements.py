from pathlib import Path

from autopack.repo_scanner import RepoScanner
from autopack.pattern_matcher import PatternMatcher


def _touch(path: Path, content: str = "# test\n") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_tests_category_uses_root_tests_templates_not_src_autopack_tests(tmp_path: Path):
    """
    Regression: tests category previously still used RepoScanner anchors even after
    anchor_dirs was removed, pulling in protected src/autopack/tests/.
    """
    _touch(tmp_path / "tests" / "test_root.py")
    _touch(tmp_path / "src" / "autopack" / "tests" / "test_internal.py")

    scanner = RepoScanner(tmp_path)
    matcher = PatternMatcher(scanner, autopack_internal_mode=False, run_type="project_build")

    result = matcher.match(goal="Add pytest tests for the feature", phase_id="p1")

    # Should include only root-level tests, never internal protected tests.
    assert "tests/test_root.py" in result.scope_paths
    assert all(
        not p.replace("\\", "/").startswith("src/autopack/tests/") for p in result.scope_paths
    )
    # Scope must be explicit files only (no directory entries).
    assert all(not p.endswith("/") for p in result.scope_paths)


def test_glob_double_star_matches_zero_directory_depth(tmp_path: Path):
    """Regression: tests/**/*.py should match tests/test_a.py (0 subdirectories)."""
    _touch(tmp_path / "tests" / "test_a.py")

    scanner = RepoScanner(tmp_path)
    matcher = PatternMatcher(scanner)

    result = matcher.match(goal="pytest: add tests", phase_id="p1")
    assert "tests/test_a.py" in result.scope_paths


def test_anchor_strategy_does_not_add_directory_entries(tmp_path: Path):
    """Regression: anchor strategy used to append the anchor directory itself to scope.paths."""
    _touch(tmp_path / "src" / "auth" / "jwt.py", "def foo():\n    return 1\n")

    scanner = RepoScanner(tmp_path)
    matcher = PatternMatcher(scanner)

    result = matcher.match(goal="Add jwt login/logout authentication", phase_id="auth")

    assert "src/auth/jwt.py" in result.scope_paths
    assert all(not p.endswith("/") for p in result.scope_paths)
