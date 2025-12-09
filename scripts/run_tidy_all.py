#!/usr/bin/env python3
"""
One-shot tidy runner with safe defaults:
- Scopes: loaded from tidy_scope.yaml if present; else .autonomous_runs/file-organizer-app-v1, .autonomous_runs, archive
- Semantic on (glm-4.6), apply semantic moves; semantic deletes are downgraded to archive moves by default.
- Execute enabled with checkpoint zip; auto git commits pre/post unless overridden.
- Prune aged artifacts (30 days) to archive/superseded; no purge.
"""

import subprocess
from pathlib import Path
import sys
import yaml


def load_scope(repo_root: Path):
    scope_file = repo_root / "tidy_scope.yaml"
    if scope_file.exists():
        data = yaml.safe_load(scope_file.read_text(encoding="utf-8")) or {}
        roots = data.get("roots") or []
        return roots
    return [".autonomous_runs/file-organizer-app-v1", ".autonomous_runs", "archive"]


def main():
    repo_root = Path(__file__).resolve().parent.parent
    roots = load_scope(repo_root)
    cmd = [
        sys.executable,
        str(repo_root / "scripts" / "tidy_workspace.py"),
    ]
    for r in roots:
        cmd.extend(["--root", r])
    cmd.extend([
        "--semantic",
        "--semantic-model", "glm-4.6",
        "--semantic-max-files", "200",
        "--apply-semantic",
        "--execute",
        "--prune",
        "--age-days", "30",
        "--verbose",
    ])
    print("[INFO] Running tidy with scope:", roots)
    subprocess.check_call(cmd, cwd=repo_root)


if __name__ == "__main__":
    main()

