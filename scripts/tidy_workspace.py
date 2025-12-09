#!/usr/bin/env python3
"""
Workspace Tidy Orchestrator

Category: MANUAL ONLY
Triggers: Intent Router, Explicit Call
Excludes: Automatic Maintenance, Error Reports, Test Runs

Safely organizes documentation and run artifacts without touching protected
files (plans, DBs, learned rules, active truth sources). Designed to run in
dry-run by default and to create a checkpoint archive before any move/delete.

This tool should NOT be included in automatic maintenance runs.
Workspace cleanup should be a deliberate user action.

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
from typing import Iterable, List, Tuple, Dict, Any
import subprocess
import hashlib
import json

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None

from glm_native_client import NativeGLMClient
from semantic_store import get_store

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
    from tidy_logger import TidyLogger
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
DEFAULT_SEMANTIC_CACHE = REPO_ROOT / ".autonomous_runs" / "tidy_semantic_cache.json"

# Cap content sent to LLM to avoid large payloads
MAX_CONTENT_CHARS = 6000


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


def compute_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


_embedding_model = None
_embedding_model_name = None


def embed_text(text: str) -> list[float]:
    """
    Embedding with optional sentence-transformers; falls back to deterministic hash.
    Set EMBEDDING_MODEL (e.g., BAAI/bge-m3 or sentence-transformers/all-MiniLM-L6-v2) to use HF model.
    """
    global _embedding_model
    global _embedding_model_name
    model_name = os.getenv("EMBEDDING_MODEL") or "BAAI/bge-m3"
    if model_name:
        try:
            from sentence_transformers import SentenceTransformer  # type: ignore
            if _embedding_model is None or _embedding_model_name != model_name:
                _embedding_model = SentenceTransformer(model_name)
                _embedding_model_name = model_name
            emb = _embedding_model.encode([text[:2000]], normalize_embeddings=True)
            return emb[0].tolist()
        except Exception:
            pass
    # hash fallback
    h = hashlib.sha256(text.encode("utf-8")).digest()
    vec = []
    for i in range(8):
        chunk = h[i * 4:(i + 1) * 4]
        val = int.from_bytes(chunk, byteorder="big", signed=False)
        vec.append((val % 1000000) / 1000000.0)
    return vec


def _insert_into_markdown(target_path: Path, block: str, heading_hint: str | None) -> None:
    """
    Section-aware insert: place block under a matching heading if present; else append.
    """
    heading = None
    if target_path.exists():
        lines = target_path.read_text(encoding="utf-8").splitlines()
    else:
        lines = []
    if heading_hint:
        lowered = heading_hint.lower()
        for i, line in enumerate(lines):
            if line.strip().startswith("#") and lowered in line.lower():
                heading = i
                break
    if heading is None:
        # append with a heading
        lines.append(f"\n## Merged: {heading_hint or target_path.stem}")
        lines.append(block)
    else:
        insert_at = heading + 1
        lines.insert(insert_at, block)
    target_path.write_text("\n".join(lines), encoding="utf-8")


def apply_truth_merges(suggestions: list[dict], repo_root: Path, run_id: str, logger: TidyLogger):
    for item in suggestions:
        path = Path(item.get("path", ""))
        target = item.get("target")
        reason = item.get("reason", "")
        if not target:
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except Exception:
            continue
        target_path = (repo_root / target).resolve() if not Path(target).is_absolute() else Path(target)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        heading_hint = path.stem
        marker = f"<!-- merged-from:{path} run:{run_id} reason:{reason} -->\n"
        block = marker + content + "\n<!-- end-merged-from -->\n"
        try:
            src_sha = compute_sha256(path) if path.is_file() else None
            dest_sha_before = compute_sha256(target_path) if target_path.exists() and target_path.is_file() else None
            _insert_into_markdown(target_path, block, heading_hint)
            dest_sha_after = compute_sha256(target_path) if target_path.is_file() else None
            logger.log(run_id, "merge", str(path), str(target_path), f"truth merge: {reason}", src_sha=src_sha, dest_sha=dest_sha_after)
        except Exception:
            logger.log(run_id, "merge_failed", str(path), str(target_path), f"truth merge failed: {reason}")


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
    # If targeting superseded root under global archive, route into project archive superseded
    if "superseded" in root.parts and root.as_posix().endswith("archive/superseded/archive"):
        project_root_path = REPO_ROOT / ".autonomous_runs" / "file-organizer-app-v1"
        archive_dir = project_root_path / "archive" / "superseded" / "archive"
    else:
        archive_dir = root / "archive"
    exports_dir = (root / "exports") if "superseded" not in root.parts else archive_dir
    patches_dir = (root / "patches") if "superseded" not in root.parts else archive_dir
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
# Semantic analysis (optional)
# ---------------------------------------------------------------------------
def summarize_and_classify(
    path: Path,
    content: str,
    truth_snippets: str,
    model: str,
    client,
) -> Dict[str, str]:
    """
    Attempt to classify file via LLM (keep/archive/delete) with rationale.
    Falls back to heuristic if LLM unavailable.
    """
    prompt = f"""You are a documentation cleaner. Decide for this file if it should be kept as-is, archived (move to superseded/archive), or deleted as redundant noise. Output JSON with keys: decision (keep|archive|delete), rationale.

Truth context (for freshness/uniqueness):
{truth_snippets[:2000]}

File content (truncated):
{content[:MAX_CONTENT_CHARS]}
"""
    if client is None:
        return {
            "decision": "archive",
            "rationale": "LLM client unavailable; defaulting to archive suggestion for safety.",
        }
    try:
        text = client.chat(
            messages=[
                {"role": "system", "content": "You are a concise documentation cleaner."},
                {"role": "user", "content": prompt},
            ],
            temperature=0,
        )
        # lightweight parse
        decision = "archive"
        rationale = text.strip()
        for token in ["keep", "archive", "delete"]:
            if token in text.lower():
                decision = token
                break
        return {"decision": decision, "rationale": rationale}
    except Exception as exc:
        return {
            "decision": "archive",
            "rationale": f"LLM call failed: {exc}; suggest archive.",
        }


def suggest_truth_merge(path: Path, content: str, truth_files: list[Path], client, model: str) -> str:
    """
    Ask LLM to suggest where this content should live (which truth file or new file).
    """
    truth_names = [str(p) for p in truth_files if p.exists()]
    prompt = f"""You are an allocator for documentation. Decide the best target file (from the list) for this content, or propose a new file name under archive/superseded if it is outdated.

Target files to choose from:
{json.dumps(truth_names, indent=2)}

File path: {path}
Content (truncated):
{content[:MAX_CONTENT_CHARS]}

Respond with JSON: {{ "target": "<existing or new file path>", "reason": "<short reason>" }}"""
    if client is None:
        return json.dumps({"target": "archive/superseded/allocator_suggestion.md", "reason": "LLM unavailable"}, ensure_ascii=False)
    try:
        text = client.chat(
            messages=[
                {"role": "system", "content": "You are a concise allocator for documentation storage."},
                {"role": "user", "content": prompt},
            ],
            temperature=0,
        )
        return text.strip()
    except Exception as exc:
        return json.dumps({"target": "archive/superseded/allocator_error.md", "reason": str(exc)}, ensure_ascii=False)


def semantic_analysis(
    root: Path,
    cache_path: Path,
    model: str,
    max_files: int,
    truth_files: list[Path],
    verbose: bool,
    truth_merge_report: Path | None = None,
    project_id: str | None = None,
    dsn_override: str | None = None,
) -> list[dict]:
    """Run semantic classification over markdown-like files; no filesystem mutations."""
    client = get_glm_client(model)
    store = get_store(cache_path, dsn_override, project_id)
    results = []

    truth_chunks = []
    for tf in truth_files:
        if tf.exists() and tf.is_file():
            try:
                truth_chunks.append(tf.read_text(encoding="utf-8")[:2000])
            except Exception:
                continue
    truth_snippets = "\n---\n".join(truth_chunks)[:4000]

    candidates = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in {".git", "node_modules", ".pytest_cache", "__pycache__", ".venv", "venv"}]
        for fname in filenames:
            p = Path(dirpath) / fname
            if p.suffix.lower() not in {".md", ".txt"}:
                continue
            if is_protected(p):
                continue
            candidates.append(p)
            if len(candidates) >= max_files:
                break
        if len(candidates) >= max_files:
            break

    merge_suggestions = []
    for path in candidates:
        try:
            content = path.read_text(encoding="utf-8")
        except Exception:
            continue
        sha = compute_sha256(path)
        cache_entry = store.get(str(path), sha, model, project_id=project_id)
        if cache_entry:
            result = cache_entry
        else:
            result = summarize_and_classify(path, content, truth_snippets, model, client)
            result.update({
                "sha": sha,
                "model": model,
                "path": str(path),
                "project_id": project_id,
                "vector": embed_text(content[:MAX_CONTENT_CHARS]),
            })
            store.set(result, vector=result.get("vector"))
        if verbose:
            rationale_display = (result.get("rationale") or "")
            try:
                rationale_display = rationale_display.encode("ascii", "replace").decode("ascii")
            except Exception:
                pass
            print(f"[SEMANTIC] {path}: {result.get('decision')} ({rationale_display[:120]})")
        results.append(result)

        if truth_merge_report:
            suggestion = suggest_truth_merge(path, content, truth_files, client, model)
            merge_suggestions.append({"path": str(path), "suggestion": suggestion})

    if truth_merge_report and merge_suggestions:
        ensure_dir(truth_merge_report.parent)
        truth_merge_report.write_text(json.dumps(merge_suggestions, indent=2, ensure_ascii=False), encoding="utf-8")
        if verbose:
            print(f"[INFO] Wrote truth-merge suggestions to {truth_merge_report}")

    return results


def get_glm_client(model: str):
    """Instantiate native GLM client using GLM_API_KEY/GLM_API_BASE."""
    if load_dotenv:
        load_dotenv()
    try:
        return NativeGLMClient(model=model)
    except Exception as exc:
        print(f"[WARN] GLM client unavailable: {exc}")
        return None


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------
def execute_actions(actions: List[Action], dry_run: bool, checkpoint_dir: Path | None, logger: TidyLogger, run_id: str) -> Tuple[int, int]:
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
            src_sha = compute_sha256(action.src) if action.src.is_file() else None
            ensure_dir(action.dest.parent)
            shutil.move(str(action.src), str(action.dest))
            dest_sha = compute_sha256(action.dest) if action.dest.is_file() else None
            print(f"[MOVE] {action.src} -> {action.dest} ({action.reason})")
            logger.log(run_id, "move", str(action.src), str(action.dest), action.reason, src_sha=src_sha, dest_sha=dest_sha)
        elif action.kind == "delete":
            deletes += 1
            if dry_run:
                print(f"[DRY-RUN][DELETE] {action.src} ({action.reason})")
                continue
            try:
                src_sha = compute_sha256(action.src) if action.src.is_file() else None
                action.src.unlink(missing_ok=True)
                print(f"[DELETE] {action.src} ({action.reason})")
                logger.log(run_id, "delete", str(action.src), None, action.reason, src_sha=src_sha)
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
    parser.add_argument("--purge", action="store_true", help="Delete aged artifacts (only with --prune; defaults to false)")
    parser.add_argument("--checkpoint-dir", type=Path, default=DEFAULT_CHECKPOINT_DIR, help="Checkpoint archive dir")
    parser.add_argument("--verbose", action="store_true", help="Verbose logging")
    parser.add_argument("--git-commit-before", type=str, help="Commit message for checkpoint commit before actions")
    parser.add_argument("--git-commit-after", type=str, help="Commit message for checkpoint commit after actions")
    parser.add_argument("--semantic", action="store_true", help="Enable semantic classification (no file mutations)")
    parser.add_argument("--semantic-model", type=str, default="glm-4.6", help="LLM model name for semantic mode")
    parser.add_argument("--semantic-cache", type=Path, default=DEFAULT_SEMANTIC_CACHE, help="Cache file for semantic results")
    parser.add_argument("--semantic-max-files", type=int, default=50, help="Max files to classify per run")
    parser.add_argument("--semantic-truth", action="append", type=Path, help="Additional truth/reference files")
    parser.add_argument("--apply-semantic", action="store_true", help="Apply semantic decisions (archive/delete) instead of report-only")
    parser.add_argument("--semantic-delete", action="store_true", help="Allow semantic delete; otherwise deletes are converted to archive moves")
    parser.add_argument("--truth-merge-report", type=Path, help="Path to write truth-merge suggestions (no apply)")
    parser.add_argument("--apply-truth-merge", action="store_true", help="Apply allocator suggestions into target files (append content)")
    parser.add_argument("--run-id", type=str, help="Run identifier for logging/checkpoints")
    parser.add_argument("--database-url", type=str, help="Override DATABASE_URL for this run")
    args = parser.parse_args()

    dry_run = not args.execute or args.dry_run
    roots = args.root or [REPO_ROOT]
    run_id = args.run_id or datetime.now().strftime("tidy-%Y%m%d-%H%M%S")
    db_override = args.database_url
    truth_files = args.semantic_truth or []
    if not truth_files:
        # Default truth anchors
        truth_files = [
            REPO_ROOT / "README.md",
            REPO_ROOT / ".autonomous_runs" / "file-organizer-app-v1" / "WHATS_LEFT_TO_BUILD.md",
            REPO_ROOT / ".autonomous_runs" / "file-organizer-app-v1" / "WHATS_LEFT_TO_BUILD_MAINTENANCE.md",
            REPO_ROOT / ".autonomous_runs" / "file-organizer-app-v1" / "archive" / "CONSOLIDATED_BUILD.md",
            REPO_ROOT / ".autonomous_runs" / "file-organizer-app-v1" / "archive" / "CONSOLIDATED_STRATEGY.md",
        ]

    # Default git commit messages if executing and none provided
    git_before = args.git_commit_before or ("tidy auto checkpoint (pre)" if args.execute and not dry_run else None)
    git_after = args.git_commit_after or ("tidy auto checkpoint (post)" if args.execute and not dry_run else None)

    if args.execute and git_before and not dry_run:
        run_git_commit(git_before, REPO_ROOT)

    logger = TidyLogger(REPO_ROOT)

    for root in roots:
        root = root.resolve()
        project_id = "autopack"
        if "file-organizer-app-v1" in root.as_posix():
            project_id = "file-organizer-app-v1"
        elif "archive" in root.parts and "superseded" in root.parts:
            # default project for archived superseded docs
            project_id = "file-organizer-app-v1"
        elif root.name:
            project_id = root.name
        if args.verbose:
            print(f"[INFO] Processing root: {root} (dry_run={dry_run})")
        selected_dsn = db_override

        logger = TidyLogger(REPO_ROOT, dsn=selected_dsn, project_id=project_id)

        # Markdown tidy; if superseded root, route files into project archive superseded
        superseded_mode = "superseded" in root.parts
        project_root_path = REPO_ROOT / ".autonomous_runs" / "file-organizer-app-v1"
        superseded_target = project_root_path / "archive" / "superseded" / "archive"

        if superseded_mode and root.as_posix().endswith("archive/superseded/archive"):
            actions: List[Action] = []
            research_keywords = ["research", "brief", "market", "strategy", "strategic_review", "immigration_visa", "tax", "fileorganizer_final"]
            delegation_keywords = ["delegation", "gpt", "openai", "codex"]
            phase_keywords = ["phase_", "p1", "p2", "p3", "p4", "p5", "p6", "p7", "p8", "p9"]
            tier_keywords = ["tier_00", "tier_01", "tier_02", "tier_03", "tier_04", "tier_05"]
            prompt_keywords = ["prompt"]
            debug_keywords = ["debug", "error", "journal", "diagnostic"]

            def bucket_for(name: str) -> Path:
                ln = name.lower()
                if any(k in ln for k in research_keywords):
                    return superseded_target / "research"
                if any(k in ln for k in delegation_keywords):
                    return superseded_target / "delegations"
                if any(ln.startswith(k) for k in tier_keywords):
                    return superseded_target / "tiers"
                if ln.startswith("phase_") or any(k in ln for k in phase_keywords):
                    return superseded_target / "phases"
                if any(k in ln for k in prompt_keywords):
                    return superseded_target / "prompts"
                if any(k in ln for k in debug_keywords):
                    return superseded_target / "diagnostics"
                return superseded_target

            for dirpath, dirnames, filenames in os.walk(root):
                dirnames[:] = [d for d in dirnames if d not in {".git", "node_modules", ".pytest_cache", "__pycache__", ".venv", "venv"}]
                for fname in filenames:
                    src = Path(dirpath) / fname
                    if src.suffix.lower() not in {".md", ".txt"}:
                        continue
                    if is_protected(src):
                        continue
                    rel = src.relative_to(root)
                    target_base = bucket_for(fname)
                    dest = target_base / rel
                    actions.append(Action("move", src, dest, "superseded->project archive"))
            execute_actions(actions, dry_run=dry_run, checkpoint_dir=args.checkpoint_dir if not dry_run else None, logger=logger, run_id=run_id)
        else:
            rules = detect_project_rules(root)
            organizer = DocumentationOrganizer(project_root=root, rules_config=rules, dry_run=dry_run, verbose=args.verbose)
            organizer.organize()

        semantic_results = []
        merge_suggestions_out = args.truth_merge_report
        if args.semantic:
            if args.verbose:
                print(f"[INFO] Running semantic analysis (max {args.semantic_max_files} files) with model {args.semantic_model}")
            semantic_results = semantic_analysis(
                root=root,
                cache_path=args.semantic_cache,
                model=args.semantic_model,
                max_files=args.semantic_max_files,
                truth_files=truth_files,
                verbose=args.verbose,
                truth_merge_report=merge_suggestions_out,
                project_id=project_id,
                dsn_override=selected_dsn,
            )
            print(f"[INFO] Semantic results ({len(semantic_results)} files):")
            for r in semantic_results:
                rationale_display = (r.get("rationale") or "")
                try:
                    rationale_display = rationale_display.encode("ascii", "replace").decode("ascii")
                except Exception:
                    pass
                print(f" - {r.get('path')}: {r.get('decision')} ({rationale_display[:160]})")

        # Non-MD tidy
        actions = plan_non_md_actions(
            root=root,
            age_days=args.age_days,
            prune=args.prune,
            purge=args.purge and args.prune,
            verbose=args.verbose,
        )

        # Apply semantic decisions if requested
        if args.semantic and args.apply_semantic and not dry_run:
            for r in semantic_results:
                decision = (r.get("decision") or "").lower()
                p = Path(r.get("path"))
                if decision == "delete":
                    if args.semantic_delete:
                        actions.append(Action("delete", p, None, "semantic delete"))
                    else:
                        # downgrade delete to archive move for safety
                        archive_dir = root / "archive" / "superseded"
                        rel = p.relative_to(root)
                        dest = archive_dir / rel
                        actions.append(Action("move", p, dest, "semantic delete->archive"))
                elif decision == "archive":
                    archive_dir = root / "archive" / "superseded"
                    rel = p.relative_to(root)
                    dest = archive_dir / rel
                    actions.append(Action("move", p, dest, "semantic archive"))

        # Apply truth merge suggestions (append content) if requested
        if args.semantic and args.apply_truth_merge and args.truth_merge_report and not dry_run:
            if args.truth_merge_report.exists():
                try:
                    suggestions = json.loads(args.truth_merge_report.read_text(encoding="utf-8"))
                    # suggestions is a list of {path, suggestion(json str)}
                    parsed = []
                    for s in suggestions:
                        try:
                            sug = json.loads(s.get("suggestion", "{}"))
                            parsed.append({
                                "path": s.get("path"),
                                "target": sug.get("target"),
                                "reason": sug.get("reason", sug.get("target_reason", "")),
                            })
                        except Exception:
                            continue
                    apply_truth_merges(parsed, REPO_ROOT, run_id, logger)
                except Exception:
                    print("[WARN] Failed to apply truth merges; continuing")

        # Execute moves/deletes with checkpoint
        execute_actions(actions, dry_run=dry_run, checkpoint_dir=args.checkpoint_dir if not dry_run else None, logger=logger, run_id=run_id)

    # Optional consolidation
    if args.consolidate_md:
        if args.verbose:
            print("[INFO] Running consolidate_docs.py")
        if dry_run:
            print("[DRY-RUN] Skipping consolidate_docs execution")
        else:
            os.system(f"{sys.executable} {SCRIPT_DIR / 'consolidate_docs.py'}")

    if args.execute and git_after and not dry_run:
        run_git_commit(git_after, REPO_ROOT)

    print("\n[SUCCESS] Tidy complete (dry_run=%s)" % dry_run)


if __name__ == "__main__":
    main()

