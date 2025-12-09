#!/usr/bin/env python3
"""
One-shot tidy runner with safe defaults:
- Scopes: .autonomous_runs/file-organizer-app-v1, .autonomous_runs, archive
- Semantic on (glm-4.6), apply semantic moves; semantic deletes are downgraded to archive moves.
- Execute enabled with auto checkpoint zip and auto git commits pre/post.
- Prune aged artifacts (30 days) to archive/superseded; no purge.
"""

import subprocess
from pathlib import Path
import sys


def main():
    repo_root = Path(__file__).resolve().parent.parent
    cmd = [
        sys.executable,
        str(repo_root / "scripts" / "tidy_workspace.py"),
        "--root", ".autonomous_runs/file-organizer-app-v1",
        "--root", ".autonomous_runs",
        "--root", "archive",
        "--semantic",
        "--semantic-model", "glm-4.6",
        "--semantic-max-files", "200",
        "--apply-semantic",
        "--execute",
        "--prune",
        "--age-days", "30",
        "--verbose",
    ]
    # Semantic deletes are converted to archive moves by default (no --semantic-delete flag)
    print("[INFO] Running tidy with defaults:")
    print(" ".join(str(c) for c in cmd))
    subprocess.check_call(cmd, cwd=repo_root)


if __name__ == "__main__":
    main()

