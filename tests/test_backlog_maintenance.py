from pathlib import Path

from autopack.backlog_maintenance import (
    parse_backlog_markdown,
    backlog_items_to_phases,
    create_git_checkpoint,
    revert_to_checkpoint,
    parse_patch_stats,
)


def test_parse_backlog_markdown_collects_bullets(tmp_path: Path):
    content = """
# Notes
- Fix YAML schema for packs
  Ensure --- header and required keys.
- Patch apply mismatch
  Rebase patch against latest main
"""
    md = tmp_path / "backlog.md"
    md.write_text(content)

    items = parse_backlog_markdown(md, max_items=5)
    assert len(items) == 2
    assert "Fix YAML" in items[0].title
    assert "Ensure" in items[0].summary


def test_backlog_items_to_phases_has_scope_and_budgets(tmp_path: Path):
    content = "- A sample backlog item\nMore details"
    md = tmp_path / "backlog.md"
    md.write_text(content)
    items = parse_backlog_markdown(md, max_items=1)

    plan = backlog_items_to_phases(
        items, default_allowed_paths=["src/"], max_commands=5, max_seconds=100
    )
    assert "phases" in plan
    phase = plan["phases"][0]
    assert phase["task_category"] == "maintenance"
    assert "src/" in phase["scope"]["paths"]
    assert phase["budgets"]["max_commands"] == 5
    assert phase["budgets"]["max_seconds"] == 100


def test_checkpoint_and_revert(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "file.txt").write_text("v1")
    # init git
    import subprocess

    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.name", "Test User"], cwd=repo, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(["git", "add", "file.txt"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo, check=True, capture_output=True)

    (repo / "file.txt").write_text("v2")
    ok, commit_hash_or_err = create_git_checkpoint(repo, "[test] checkpoint")
    assert ok
    checkpoint_hash = commit_hash_or_err
    (repo / "file.txt").write_text("v3")
    ok, err = revert_to_checkpoint(repo, checkpoint_hash)
    assert ok, err
    assert (repo / "file.txt").read_text() == "v2"


def test_parse_patch_stats_counts_files_and_lines():
    patch = """diff --git a/src/foo.py b/src/foo.py
--- a/src/foo.py
+++ b/src/foo.py
@@
-old
+new
+new2
"""
    stats = parse_patch_stats(patch)
    assert stats.files_changed == ["src/foo.py"]
    assert stats.lines_added == 2
    assert stats.lines_deleted == 1
