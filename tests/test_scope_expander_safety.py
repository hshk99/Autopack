from pathlib import Path

from autopack.repo_scanner import RepoScanner
from autopack.scope_expander import ScopeExpander


def _touch(path: Path, content: str = "# x\n") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_scope_expander_file_to_parent_dir_adds_files_not_directory(tmp_path: Path):
    _touch(tmp_path / "src" / "auth" / "jwt.py", "x=1\n")
    _touch(tmp_path / "src" / "auth" / "middleware.py", "x=2\n")

    scanner = RepoScanner(tmp_path)
    expander = ScopeExpander(workspace=tmp_path, repo_scanner=scanner, max_added_files_per_expansion=10)

    res = expander.expand_scope(
        current_scope=["src/auth/jwt.py"],
        failure_reason="file_not_in_scope",
        proposed_file="src/auth/middleware.py",
        phase_goal="Add JWT authentication",
        phase_id="p1",
    )

    assert res.success is True
    assert "src/auth/jwt.py" in res.expanded_scope
    assert "src/auth/middleware.py" in res.expanded_scope
    assert all(not p.endswith("/") for p in res.expanded_scope)


