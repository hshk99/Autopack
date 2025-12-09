#!/usr/bin/env python3
"""
Workspace Tidy Orchestrator

Safely organizes documentation and run artifacts without touching protected
files (plans, DBs, learned rules, active truth sources). Designed to run in
dry-run by default and to create a checkpoint archive before any move/delete.

Functions:
- Markdown organization via tidy_docs.DocumentationOrganizer (optional)
- Optional docs consolidation via scripts/consolidate_docs.py
- Non-MD handling (logs/diagnostics/patches/exports) with per-run bucketing

Token usage: none (local file ops only).
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import zipfile
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable, List, Tuple
import subprocess

# Ensure sibling imports work when invoked from repo root
SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
sys.path.append(str(SCRIPT_DIR))

try:
    from tidy_docs import (
        DocumentationOrganizer,
        AUTOPACK_RULES,
        FILEORGANIZER_RULES,
    )
except Exception as exc:  # pragma: no cover - defensive import
    print(f"[ERROR] Failed to import tidy_docs: {exc}", file=sys.stderr)
    raise


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
PROTECTED_BASENAMES = {
    "project_learned_rules.json",
    "project_learned_rules",
    "autopack.db",
    "fileorganizer.db",
    "test.db",
    "rules_updated.json",
    "project_learned_rules.md",
}

PROTECTED_PREFIXES = {
    "plan_",
    "plan-generated",
    "plan_generated",
}

PROTECTED_FILES = {
    "WHATS_LEFT_TO_BUILD.md",
    "WHATS_LEFT_TO_BUILD_MAINTENANCE.md",
    "autopack_phase_plan.json",
}

PROTECTED_SUFFIXES = {
    ".db",
    ".sqlite",
}

LOG_EXTS = {".log", ".txt"}
EXPORT_EXTS = {".csv", ".xlsx", ".xls", ".pdf"}
PATCH_EXTS = {".patch", ".diff"}

DEFAULT_CHECKPOINT_DIR = REPO_ROOT / ".autonomous_runs" / "checkpoints"


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------
@dataclass
class Action:
    kind: str  # move|delete|skip
    src: Path
    dest: Path | None
    reason: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def is_protected(path: Path) -> bool:
    name = path.name
    if name in PROTECTED_BASENAMES or name in PROTECTED_FILES:
        return True
    if any(name.startswith(prefix) for prefix in PROTECTED_PREFIXES):
        return True
    if any(name.endswith(suf) for suf in PROTECTED_SUFFIXES):
        return True
    return False


def is_under(dirpath: Path, ancestor: Path) -> bool:
    try:
        dirpath.relative_to(ancestor)
        return True
    except ValueError:
        return False


def ensure_dir(path: Path):
    path.mkdir(parents=True, exist_ok=True)


def checkpoint_files(checkpoint_dir: Path, files: Iterable[Path]) -> Path:
    ensure_dir(checkpoint_dir)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    archive = checkpoint_dir / f"tidy_checkpoint_{ts}.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in files:
            if f.exists() and f.is_file():
                # Store relative to repo root for readability
                try:
                    arcname = f.relative_to(REPO_ROOT)
                except ValueError:
                    arcname = f.name
                zf.write(f, arcname)
    return archive


def detect_project_rules(root: Path):
    """Choose tidy_docs rules based on path heuristics."""
    if "file-organizer" in root.as_posix() or root.name == "file-organizer-app-v1":
        return FILEORGANIZER_RULES
    return AUTOPACK_RULES


def find_run_id(path: Path) -> str | None:
    parts = path.parts
    if ".autonomous_runs" in parts:
        idx = parts.index(".autonomous_runs")
        if idx + 1 < len(parts):
            return parts[idx + 1]
    return None


def age_filter(path: Path, age_days: int) -> bool:
    if age_days <= 0:
        return False
    cutoff = datetime.now() - timedelta(days=age_days)
    mtime = datetime.fromtimestamp(path.stat().st_mtime)
    return mtime < cutoff


# ---------------------------------------------------------------------------
# Non-MD scanning
# ---------------------------------------------------------------------------
def plan_non_md_actions(root: Path, age_days: int, prune: bool, purge: bool, verbose: bool) -> List[Action]:
    actions: List[Action] = []
    archive_dir = root / "archive"
    exports_dir = root / "exports"
    patches_dir = root / "patches"
    ensure_dir(archive_dir)
    ensure_dir(exports_dir)
    ensure_dir(patches_dir)

    for dirpath, dirnames, filenames in os.walk(root):
        # Skip git/node_modules/venv/temp
        dirnames[:] = [
            d for d in dirnames
            if d not in {".git", "node_modules", ".pytest_cache", "__pycache__", ".venv", "venv"}
        ]
        current = Path(dirpath)

        for fname in filenames:
            src = current / fname

            # Skip protected
            if is_protected(src):
                continue

            # Skip source code/config
            if src.suffix in {".py", ".ts", ".tsx", ".js", ".json", ".yaml", ".yml"} and "diagnostics" not in src.parts:
                continue

            # Exports
            if src.suffix.lower() in EXPORT_EXTS:
                if is_under(src, exports_dir):
                    continue
                dest = exports_dir / src.name
                actions.append(Action("move", src, dest, "move export to exports/"))
                continue

            # Patches
            if src.suffix.lower() in PATCH_EXTS:
                if is_under(src, patches_dir):
                    continue
                dest = patches_dir / src.name
                actions.append(Action("move", src, dest, "move patch to patches/"))
                continue

            # Logs / diagnostics / errors
            if src.suffix.lower() in LOG_EXTS or any(seg in {"diagnostics", "errors", "logs"} for seg in src.parts):
                run_id = find_run_id(src) or "general"
                dest_base = archive_dir / "runs" / run_id
                # preserve relative path under run dir
                try:
                    rel = src.relative_to(root)
                except ValueError:
                    rel = Path(src.name)
                dest = dest_base / rel
                if src == dest:
                    continue
                actions.append(Action("move", src, dest, "archive log/diagnostic"))
                # pruning
                if prune and age_filter(src, age_days):
                    if purge:
                        actions.append(Action("delete", dest, None, f"purge aged ({age_days}d)"))
                    else:
                        superseded = archive_dir / "superseded" / rel
                        actions.append(Action("move", dest, superseded, "move aged to superseded"))
                continue

            # Other temp artifacts (keep conservative)
            if fname.lower().endswith((".tmp", ".bak")):
                if prune or purge:
                    actions.append(Action("delete" if purge else "move", src, archive_dir / "superseded" / fname,
                                           "temp artifact"))

    if verbose:
        print(f"[INFO] Planned {len(actions)} non-MD actions under {root}")
    return actions


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------
def execute_actions(actions: List[Action], dry_run: bool, checkpoint_dir: Path | None) -> Tuple[int, int]:
    if not actions:
        return 0, 0

    files_for_checkpoint = [a.src for a in actions if a.src.exists()]
    if not dry_run and checkpoint_dir:
        archive = checkpoint_files(checkpoint_dir, files_for_checkpoint)
        print(f"[CHECKPOINT] Saved {len(files_for_checkpoint)} files to {archive}")

    moves = deletes = 0
    for action in actions:
        if action.kind == "move":
            moves += 1
            if dry_run:
                print(f"[DRY-RUN][MOVE] {action.src} -> {action.dest} ({action.reason})")
                continue
            ensure_dir(action.dest.parent)
            shutil.move(str(action.src), str(action.dest))
            print(f"[MOVE] {action.src} -> {action.dest} ({action.reason})")
        elif action.kind == "delete":
            deletes += 1
            if dry_run:
                print(f"[DRY-RUN][DELETE] {action.src} ({action.reason})")
                continue
            try:
                action.src.unlink(missing_ok=True)
                print(f"[DELETE] {action.src} ({action.reason})")
            except Exception as exc:
                print(f"[WARN] Failed to delete {action.src}: {exc}")
        else:
            print(f"[SKIP] {action.src} ({action.reason})")

    return moves, deletes


def run_git_commit(message: str, repo_root: Path):
    """Create a git checkpoint commit if there are staged/unstaged changes."""
    try:
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=True,
        )
        if not status.stdout.strip():
            print("[GIT] No changes to commit; skipping checkpoint commit")
            return

        subprocess.run(["git", "add", "-A"], cwd=repo_root, check=True)
        subprocess.run(["git", "commit", "-m", message], cwd=repo_root, check=True)
        print(f"[GIT] Created checkpoint commit: {message}")
    except FileNotFoundError:
        print("[WARN] git not found; skipping git checkpoint")
    except subprocess.CalledProcessError as exc:
        print(f"[WARN] git command failed ({exc}); checkpoint commit skipped")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Safely tidy workspace artifacts.")
    parser.add_argument("--root", action="append", type=Path, help="Root path to tidy (default: repo root)")
    parser.add_argument("--dry-run", action="store_true", help="Dry run only (default)")
    parser.add_argument("--execute", action="store_true", help="Execute moves/deletes (overrides --dry-run)")
    parser.add_argument("--consolidate-md", action="store_true", help="Run consolidate_docs after MD tidy")
    parser.add_argument("--age-days", type=int, default=30, help="Age threshold for pruning (days)")
    parser.add_argument("--prune", action="store_true", help="Prune aged artifacts (move to superseded)")
    parser.add_argument("--purge", action="store_true", help="Delete aged artifacts (only with --prune)")
    parser.add_argument("--checkpoint-dir", type=Path, default=DEFAULT_CHECKPOINT_DIR, help="Checkpoint archive dir")
    parser.add_argument("--verbose", action="store_true", help="Verbose logging")
    parser.add_argument("--git-commit-before", type=str, help="Commit message for checkpoint commit before actions")
    parser.add_argument("--git-commit-after", type=str, help="Commit message for checkpoint commit after actions")
    args = parser.parse_args()

    dry_run = not args.execute or args.dry_run
    roots = args.root or [REPO_ROOT]

    if args.execute and args.git_commit_before and not dry_run:
        run_git_commit(args.git_commit_before, REPO_ROOT)

    for root in roots:
        root = root.resolve()
        if args.verbose:
            print(f"[INFO] Processing root: {root} (dry_run={dry_run})")

        # Markdown tidy
        rules = detect_project_rules(root)
        organizer = DocumentationOrganizer(project_root=root, rules_config=rules, dry_run=dry_run, verbose=args.verbose)
        organizer.organize()

        # Non-MD tidy
        actions = plan_non_md_actions(
            root=root,
            age_days=args.age_days,
            prune=args.prune,
            purge=args.purge and args.prune,
            verbose=args.verbose,
        )

        # Execute moves/deletes with checkpoint
        execute_actions(actions, dry_run=dry_run, checkpoint_dir=args.checkpoint_dir if not dry_run else None)

    # Optional consolidation
    if args.consolidate_md:
        if args.verbose:
            print("[INFO] Running consolidate_docs.py")
        if dry_run:
            print("[DRY-RUN] Skipping consolidate_docs execution")
        else:
            os.system(f"{sys.executable} {SCRIPT_DIR / 'consolidate_docs.py'}")

    if args.execute and args.git_commit_after and not dry_run:
        run_git_commit(args.git_commit_after, REPO_ROOT)

    print("\n[SUCCESS] Tidy complete (dry_run=%s)" % dry_run)


if __name__ == "__main__":
    main()

