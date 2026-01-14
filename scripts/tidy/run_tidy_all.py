#!/usr/bin/env python3
"""
One-shot tidy runner with safe defaults:
- Scopes: loaded from tidy_scope.yaml if present; else .autonomous_runs/file-organizer-app-v1, .autonomous_runs, archive
- Semantic on (default from config/models.yaml tool_models.tidy_semantic), apply semantic moves; semantic deletes are downgraded to archive moves by default.
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
        db_overrides = data.get("db_overrides") or {}
        purge = data.get("purge", False)
        return roots, db_overrides, purge
    return [".autonomous_runs/file-organizer-app-v1", ".autonomous_runs", "archive"], {}, False


def main():
    repo_root = Path(__file__).resolve().parent.parent.parent
    # Resolve semantic model from config/models.yaml (single source of truth).
    sys.path.insert(0, str(repo_root / "src"))
    try:
        from autopack.model_registry import get_tool_model  # type: ignore

        semantic_model = get_tool_model("tidy_semantic", default="glm-4.6") or "glm-4.6"
    except Exception:
        semantic_model = "glm-4.6"
    roots, db_overrides, purge = load_scope(repo_root)
    for r in roots:
        cmd = [
            sys.executable,
            str(repo_root / "scripts" / "tidy" / "tidy_workspace.py"),
            "--root",
            r,
            "--semantic",
            "--semantic-model",
            semantic_model,
            "--semantic-max-files",
            "200",
            "--apply-semantic",
            "--execute",
            "--prune",
            "--age-days",
            "30",
            "--verbose",
        ]
        dsn = db_overrides.get(r)
        if dsn:
            cmd.extend(["--database-url", dsn])
        if purge:
            cmd.append("--purge")
        print(f"[INFO] Running tidy for root: {r}")
        subprocess.check_call(cmd, cwd=repo_root)


if __name__ == "__main__":
    main()
