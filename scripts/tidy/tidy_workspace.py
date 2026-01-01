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

# Ensure sibling imports work when invoked from repo root
SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(SCRIPT_DIR.parent))

from glm_native_client import NativeGLMClient
from semantic_store import get_store

# Import memory-based classifier
try:
    from file_classifier_with_memory import classify_file_with_memory, ProjectMemoryClassifier
    MEMORY_CLASSIFIER_AVAILABLE = True
except ImportError:
    MEMORY_CLASSIFIER_AVAILABLE = False
    print("[WARN] file_classifier_with_memory not available, using pattern-based fallback")

# Import classification auditor
try:
    from classification_auditor import ClassificationAuditor
    AUDITOR_AVAILABLE = True
except ImportError:
    AUDITOR_AVAILABLE = False
    print("[WARN] classification_auditor not available, skipping auditor review")

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
    "FUTURE_PLAN.md",
    "FUTURE_PLAN_MAINTENANCE.md",
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
DEFAULT_UNSORTED_DIR = REPO_ROOT / "archive" / "unsorted"

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


def validate_destination_path(source: Path, dest: Path, repo_root: Path) -> tuple[bool, str]:
    """Validate destination path for common bugs that cause nesting issues.

    This prevents issues like:
    - docs/docs/ nesting (duplicate folder names)
    - archive/archive/archive/ deep nesting
    - Moving file to same location
    - Excessive path depth

    Returns: (is_valid, error_message)
    """
    try:
        # Normalize paths for comparison
        src_resolved = source.resolve()
        dest_resolved = dest.resolve()

        # Check for moving file to same location
        if src_resolved == dest_resolved:
            return False, "Source and destination are identical"

        # Check for moving file into subdirectory of itself (for directories)
        if source.is_dir() and dest_resolved.is_relative_to(src_resolved):
            return False, "Cannot move directory into its own subdirectory"

        # Check for duplicate nesting (e.g., docs/docs/, archive/archive/)
        # Get relative path from repo root to detect patterns
        try:
            rel_parts = dest_resolved.relative_to(repo_root).parts
        except ValueError:
            # Destination is outside repo root - allow but warn
            return True, ""

        # Check for consecutive duplicate folder names
        for i in range(len(rel_parts) - 1):
            if rel_parts[i] == rel_parts[i + 1]:
                return False, f"Duplicate nesting detected: .../{rel_parts[i]}/{rel_parts[i+1]}/... (probable path construction bug)"

        # Check for excessive depth (more than 10 levels is suspicious)
        if len(rel_parts) > 10:
            return False, f"Path too deep ({len(rel_parts)} levels) - possible runaway nesting"

        # Check for paths with "runs" appearing multiple times (common bug pattern)
        runs_count = sum(1 for part in rel_parts if part == "runs")
        if runs_count > 1:
            return False, f"'runs' appears {runs_count} times in path - probable duplication bug"

        # All checks passed
        return True, ""

    except Exception as e:
        # If validation itself fails, be conservative and reject
        return False, f"Path validation error: {str(e)}"


# ---------------------------------------------------------------------------
# Creation-time routing helper (for Cursor/manual saves)
# ---------------------------------------------------------------------------
def _discover_projects() -> set[str]:
    projects = set()
    auto_root = REPO_ROOT / ".autonomous_runs"
    if auto_root.exists():
        for child in auto_root.iterdir():
            if child.is_dir() and child.name not in {"archive", "checkpoints", "patches", "exports", "docs", "openai_delegations", "runs"}:
                projects.add(child.name)
    projects.add("file-organizer-app-v1")
    projects.add("autopack")
    return projects


def classify_project(project_hint: str | None) -> str:
    projects = _discover_projects()
    if project_hint and project_hint in projects:
        return project_hint
        return "file-organizer-app-v1"


def route_new_doc(
    name: str,
    purpose: str | None = None,
    project_hint: str | None = None,
    archived: bool = False,
) -> Path:
    """
    Return a destination path for a newly created doc based on purpose and project.
    Does not create the file/directories; caller may ensure_dir on parent if needed.
    """
    project = classify_project(project_hint)
    ln = name.lower()

    def bucket_for():
        if purpose:
            p = purpose.lower()
            if "plan" in p or "roadmap" in p or "design" in p or "strategy" in p:
                return "plans"
            if "analysis" in p or "review" in p or "retro" in p or "postmortem" in p:
                return "analysis"
            if "prompt" in p or "delegation" in p:
                return "prompts"
            if "log" in p or "diagnostic" in p or "trace" in p:
                return "logs"
            if "script" in p or "runner" in p or "tool" in p or "utility" in p:
                return "scripts"
            if "report" in p:
                return "reports"
        # name-based fallback
        if "plan" in ln or "roadmap" in ln or "design" in ln or "strategy" in ln:
            return "plans"
        if "analysis" in ln or "review" in ln or "retro" in ln or "postmortem" in ln:
            return "analysis"
        if "prompt" in ln or "delegation" in ln:
            return "prompts"
        if "log" in ln or "diagnostic" in ln or "trace" in ln:
            return "logs"
        if "script" in ln or "runner" in ln or "tool" in ln or "utility" in ln or "setup" in ln:
            return "scripts"
        if "report" in ln or "consolidated" in ln:
            return "reports"
        return "refs"

    bucket = bucket_for()

    try:
        if project == "autopack":
            if bucket == "plans":
                base = REPO_ROOT / "archive" / "plans"
            elif bucket == "analysis" or bucket == "reports":
                base = REPO_ROOT / "archive" / "analysis"
            elif bucket == "prompts":
                base = REPO_ROOT / "archive" / "prompts"
            elif bucket == "logs":
                base = REPO_ROOT / "archive" / "logs"
            elif bucket == "scripts":
                base = REPO_ROOT / "archive" / "scripts"
            else:
                base = REPO_ROOT / "docs"  # truth sources
            return base / name

        # project-specific (e.g., file-organizer-app-v1)
        project_root = REPO_ROOT / ".autonomous_runs" / project
        docs_root = project_root / "docs"
        archive_root = project_root / "archive"
        superseded_root = archive_root / "superseded"
        if archived:
            base = superseded_root
        else:
            base = archive_root

        if bucket == "plans":
            target = base / "plans"
        elif bucket == "analysis":
            target = base / "analysis"
        elif bucket == "prompts":
            target = base / "prompts"
        elif bucket == "logs":
            target = base / "diagnostics"
        elif bucket == "scripts":
            target = base / "scripts"
        elif bucket == "reports":
            target = base / "reports"
        else:
            target = docs_root
        return target / name
    except Exception:
        return DEFAULT_UNSORTED_DIR / name


def route_run_output(
    project_hint: str | None,
    family: str,
    run_id: str,
    archived: bool = False,
) -> Path:
    """
    Return the directory path where a run's outputs should live.
    Prefer to emit runs directly here at creation time to avoid later tidy moves.
    """
    project = classify_project(project_hint)
    if project == "autopack":
        # Autopack runs are rare; keep under archive/logs as a catch-all.
        base = REPO_ROOT / "archive" / "logs"
        return base / family / run_id

    project_root = REPO_ROOT / ".autonomous_runs" / project
    runs_root = project_root / "runs"
    superseded_runs_root = project_root / "archive" / "superseded" / "runs"
    base = superseded_runs_root if archived else runs_root
    return base / family / run_id


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


def collapse_consecutive_duplicates(parts: List[str]) -> List[str]:
    """Remove consecutive duplicate folder names (e.g., file-organizer-app-v1/file-organizer-app-v1 -> file-organizer-app-v1).

    This fixes path construction bugs where source paths contain duplicate nesting
    (e.g., archive/file-organizer-app-v1/file-organizer-app-v1/.autonomous_runs/...)
    and we want to normalize them by removing the duplicates.

    Args:
        parts: List of path components

    Returns:
        List with consecutive duplicates removed
    """
    if not parts:
        return parts
    collapsed: List[str] = [parts[0]]
    for i in range(1, len(parts)):
        if parts[i] != parts[i-1]:
            collapsed.append(parts[i])
    return collapsed


# ---------------------------------------------------------------------------
# Non-MD scanning
# ---------------------------------------------------------------------------
def plan_non_md_actions(root: Path, age_days: int, prune: bool, purge: bool, verbose: bool) -> List[Action]:
    actions: List[Action] = []
    # If targeting superseded root under global archive, route into project archive superseded
    if "superseded" in root.parts and root.as_posix().endswith("archive/superseded/archive"):
        project_root_path = REPO_ROOT / ".autonomous_runs" / "file-organizer-app-v1"
        archive_dir = project_root_path / "archive" / "superseded"
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
            # Validate destination path before moving
            is_valid, error_msg = validate_destination_path(action.src, action.dest, REPO_ROOT)
            if not is_valid:
                print(f"[VALIDATION ERROR] Skipping move {action.src} -> {action.dest}")
                print(f"[VALIDATION ERROR] Reason: {error_msg}")
                logger.log_move_error(str(action.src), str(action.dest), error_msg, run_id)
                continue

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
# Cursor File Detection
# ---------------------------------------------------------------------------
def detect_and_route_cursor_files(root: Path, project_id: str, logger: TidyLogger, run_id: str) -> List[Action]:
    """Detect files created by Cursor/Autopack in workspace root and route them.

    Detects all file types (.md, .py, .json, .log, .sql, etc.) and routes them
    to appropriate project locations based on project-first classification.

    Args:
        root: Workspace root path
        project_id: Project identifier (default hint, will be overridden by detection)
        logger: Tidy logger for tracking
        run_id: Run ID for logging

    Returns:
        List of actions to route files
    """
    actions = []

    # Only scan workspace root for files
    if root != REPO_ROOT:
        return actions

    # File extensions to process
    extensions = ["*.md", "*.py", "*.json", "*.log", "*.sql", "*.txt", "*.yaml", "*.yml", "*.toml", "*.sh", "*.ps1"]

    for pattern in extensions:
        for file in root.glob(pattern):
            # Skip protected files
            if is_protected(file):
                continue

            # Skip standard repo files
            if file.name in {"README.md", "LICENSE.md", "CONTRIBUTING.md", ".gitignore", "package.json",
                             "requirements.txt", "pyproject.toml", "setup.py", "Dockerfile", "docker-compose.yml"}:
                continue

            # Determine destination based on project-first classification
            dest = classify_cursor_file(file, project_id)
            if dest and dest != file:
                actions.append(Action("move", file, dest, "cursor file routing"))

    return actions


def classify_cursor_file(file: Path, project_id: str) -> Path | None:
    """Classify a file based on project, type, and content (project-first approach).

    Classification strategy (with memory):
    1. **PostgreSQL**: Check routing rules with keyword matching
    2. **Qdrant**: Query vector DB for semantic similarity with past classifications
    3. **Pattern-based fallback**: Use hardcoded patterns if DB methods fail
    4. **Learning**: Store successful classifications back to vector DB

    Args:
        file: Path to the file
        project_id: Default project identifier (can be overridden by detection)

    Returns:
        Destination path or None if should not move
    """
    name = file.name.lower()
    suffix = file.suffix.lower()

    # Read content for classification (first 500 chars)
    try:
        content = file.read_text(encoding="utf-8", errors="ignore")[:500].lower()
    except:
        content = ""

    # Try memory-based classification FIRST (PostgreSQL + Qdrant)
    if MEMORY_CLASSIFIER_AVAILABLE:
        try:
            detected_project, file_type, dest_path, confidence = classify_file_with_memory(
                file, content, default_project_id=project_id, enable_learning=True
            )

            # If confidence is acceptable, but could benefit from audit review
            if dest_path:
                # Apply auditor if confidence is low (<0.80) and auditor is available
                if AUDITOR_AVAILABLE and confidence < 0.80:
                    try:
                        # Read full content for auditor (not just 500 chars)
                        full_content = file.read_text(encoding="utf-8", errors="ignore")

                        # Initialize auditor (lazy initialization)
                        if not hasattr(classify_cursor_file, '_auditor'):
                            classify_cursor_file._auditor = ClassificationAuditor(
                                audit_threshold=0.80,
                                enable_auto_override=True
                            )

                        auditor = classify_cursor_file._auditor

                        # Audit the classification
                        classifier_result = (detected_project, file_type, dest_path, confidence)
                        approved, final_proj, final_type, final_dest, final_conf, reason = auditor.audit_classification(
                            file, full_content, classifier_result
                        )

                        if not approved:
                            print(f"[Auditor] FLAGGED for manual review: {file.name} - {reason}")
                            return None  # Don't move flagged files

                        # Use auditor's decision (may be override or approval)
                        if final_proj != detected_project or final_type != file_type:
                            print(f"[Auditor] OVERRIDE: {file.name} -> {final_proj}/{final_type} (confidence={final_conf:.2f})")
                        else:
                            print(f"[Auditor] APPROVED: {file.name} (confidence boosted to {final_conf:.2f})")

                        detected_project, file_type, dest_path, confidence = final_proj, final_type, final_dest, final_conf

                    except Exception as e:
                        print(f"[Auditor] Error: {e}, using classifier decision")

                # Accept if confidence meets threshold
                if confidence > 0.5:
                    print(f"[Memory Classifier] {file.name} -> {detected_project}/{file_type} (confidence={confidence:.2f})")
                    return dest_path

        except Exception as e:
            print(f"[Memory Classifier] Error: {e}, falling back to pattern matching")

    # Fallback to original pattern-based classification
    print(f"[Pattern Classifier] Using fallback for {file.name}")

    # Step 1: Detect project (project-first classification)
    detected_project = None

    # Check filename for project indicators
    if any(indicator in name for indicator in ["fileorg", "file-org", "file_org"]):
        detected_project = "file-organizer-app-v1"
    elif any(indicator in name for indicator in ["backlog", "maintenance"]):
        detected_project = "file-organizer-app-v1"
    elif any(indicator in name for indicator in ["autopack", "tidy", "autonomous"]):
        detected_project = "autopack"

    # Check content for project indicators if filename didn't match
    if not detected_project and content:
        if any(indicator in content for indicator in ["file organizer", "fileorg", "country pack"]):
            detected_project = "file-organizer-app-v1"
        elif any(indicator in content for indicator in ["autopack", "tidy", "autonomous executor"]):
            detected_project = "autopack"

    # Default to provided project_id if still unclear
    if not detected_project:
        detected_project = project_id if project_id else "autopack"

    # Step 2: Classify file type based on extension and content
    bucket = None
    sub_bucket = None  # For scripts: backend, frontend, test, temp, utility

    # Extension-based classification
    if suffix == ".log":
        bucket = "logs"
    elif suffix == ".json":
        # Check if it's a plan/phase file or data file
        if any(word in name for word in ["plan", "phase", "config"]):
            bucket = "plans"
        elif any(word in name for word in ["failure", "error", "builder"]):
            bucket = "logs"
        else:
            bucket = "unsorted"
    elif suffix == ".sql":
        bucket = "scripts"
        sub_bucket = "utility"
    elif suffix in [".yaml", ".yml", ".toml"]:
        if "config" in name or "settings" in name:
            bucket = "unsorted"  # Config files stay at project level
        else:
            bucket = "plans"
    elif suffix == ".py":
        # Python files need deeper classification
        bucket = "scripts"
        sub_bucket = _classify_python_script(file, name, content)
    elif suffix == ".md":
        # Markdown files - check name and content
        if "implementation_plan" in name or "plan_" in name:
            bucket = "plans"
        elif "analysis" in name or "review" in name or "revision" in name:
            bucket = "analysis"
        elif "prompt" in name or "delegation" in name:
            bucket = "prompts"
        elif "report" in name or "summary" in name or "consolidated" in name:
            bucket = "reports"
        elif "diagnostic" in name:
            bucket = "diagnostics"
        # Content-based fallback for .md
        elif content:
            if any(word in content for word in ["# implementation plan", "## goal", "implementation strategy"]):
                bucket = "plans"
            elif any(word in content for word in ["# analysis", "## findings", "review", "retrospective"]):
                bucket = "analysis"
            elif any(word in content for word in ["# prompt", "delegation", "instruction"]):
                bucket = "prompts"
            elif any(word in content for word in ["# report", "## summary", "consolidated"]):
                bucket = "reports"
    elif suffix in [".txt", ".sh", ".ps1"]:
        bucket = "scripts"
        sub_bucket = "utility"

    # Default to unsorted if classification failed
    if not bucket:
        bucket = "unsorted"

    # Step 3: Build destination path (project-first routing)
    if detected_project == "autopack":
        # Autopack files go to C:\dev\Autopack\archive\{bucket}\
        if bucket == "scripts" and sub_bucket:
            return REPO_ROOT / "scripts" / sub_bucket / file.name
        elif bucket == "scripts":
            return REPO_ROOT / "scripts" / file.name
        else:
            return REPO_ROOT / "archive" / bucket / file.name
    else:
        # File Organizer files go to .autonomous_runs/file-organizer-app-v1/archive/{bucket}/
        project_root = REPO_ROOT / ".autonomous_runs" / detected_project
        if bucket == "scripts" and sub_bucket:
            return project_root / "archive" / "scripts" / sub_bucket / file.name
        else:
            return project_root / "archive" / bucket / file.name


def _classify_python_script(file: Path, name: str, content: str) -> str:
    """Classify Python script by type: backend, frontend, test, temp, utility.

    Args:
        file: Path to the Python file
        name: Lowercase filename
        content: First 500 chars of file content (lowercase)

    Returns:
        Script type: "backend", "frontend", "test", "temp", or "utility"
    """
    # Check filename patterns
    if "test_" in name or "_test" in name or "tests" in name:
        return "test"
    elif "temp" in name or "tmp" in name or "scratch" in name:
        return "temp"
    elif any(word in name for word in ["api", "server", "endpoint", "route", "model", "db", "database"]):
        return "backend"
    elif any(word in name for word in ["ui", "component", "page", "view", "frontend", "client"]):
        return "frontend"
    elif any(word in name for word in ["runner", "create_", "run_", "executor", "script"]):
        return "utility"

    # Check content patterns
    if content:
        if any(word in content for word in ["fastapi", "flask", "django", "sqlalchemy", "database", "crud"]):
            return "backend"
        elif any(word in content for word in ["react", "vue", "angular", "dom", "html", "css"]):
            return "frontend"
        elif any(word in content for word in ["pytest", "unittest", "test_", "assert "]):
            return "test"
        elif any(word in content for word in ["# temp", "# temporary", "# scratch", "# one-off"]):
            return "temp"

    # Default to utility
    return "utility"


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
    # Default comes from config/models.yaml tool_models.tidy_semantic to avoid hardcoded model bumps.
    parser.add_argument("--semantic-model", type=str, default=None, help="LLM model name for semantic mode (default: config/models.yaml tool_models.tidy_semantic)")
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
        # Default truth anchors (all truth sources now in docs/ folders)
        truth_files = [
            REPO_ROOT / "README.md",
            REPO_ROOT / "docs" / "FUTURE_PLAN.md",
            REPO_ROOT / "docs" / "FUTURE_PLAN_MAINTENANCE.md",
            REPO_ROOT / "docs" / "WORKSPACE_ORGANIZATION_SPEC.md",
            REPO_ROOT / ".autonomous_runs" / "file-organizer-app-v1" / "docs" / "FUTURE_PLAN.md",
            REPO_ROOT / ".autonomous_runs" / "file-organizer-app-v1" / "archive" / "CONSOLIDATED_BUILD.md",
            REPO_ROOT / ".autonomous_runs" / "file-organizer-app-v1" / "archive" / "CONSOLIDATED_STRATEGY.md",
        ]

    # Default git commit messages if executing and none provided
    git_before = args.git_commit_before or ("tidy auto checkpoint (pre)" if args.execute and not dry_run else None)
    git_after = args.git_commit_after or ("tidy auto checkpoint (post)" if args.execute and not dry_run else None)

    if args.execute and git_before and not dry_run:
        run_git_commit(git_before, REPO_ROOT)

    logger = TidyLogger(REPO_ROOT)

    # Resolve default semantic model from config if not provided.
    if args.semantic and not args.semantic_model:
        try:
            # Import from src/ without requiring PYTHONPATH from caller.
            sys.path.insert(0, str(REPO_ROOT / "src"))
            from autopack.model_registry import get_tool_model  # noqa: WPS433

            args.semantic_model = get_tool_model("tidy_semantic", default="glm-4.6") or "glm-4.6"
        except Exception:
            # Conservative fallback if config load fails.
            args.semantic_model = "glm-4.6"

    for root in roots:
        root = root.resolve()
        project_id = "autopack"
        if "file-organizer-app-v1" in root.as_posix():
            project_id = "file-organizer-app-v1"
        elif "archive" in root.parts and "superseded" in root.parts:
            # default project for archived superseded docs
            project_id = "file-organizer-app-v1"
        elif root == REPO_ROOT / ".autonomous_runs":
            project_id = "file-organizer-app-v1"
        elif root.name:
            project_id = root.name
        if args.verbose:
            print(f"[INFO] Processing root: {root} (dry_run={dry_run})")
        selected_dsn = db_override

        logger = TidyLogger(REPO_ROOT, dsn=selected_dsn, project_id=project_id)

        # Detect and route Cursor-created files from workspace root
        if root == REPO_ROOT:
            cursor_actions = detect_and_route_cursor_files(root, project_id, logger, run_id)
            if cursor_actions:
                print(f"[INFO] Found {len(cursor_actions)} Cursor-created files to route")
                execute_actions(cursor_actions, dry_run=dry_run, checkpoint_dir=args.checkpoint_dir if not dry_run else None, logger=logger, run_id=run_id)

        # Markdown tidy; if superseded root, route files into project archive superseded
        superseded_mode = "superseded" in root.parts
        project_root_path = REPO_ROOT / ".autonomous_runs" / "file-organizer-app-v1"
        superseded_target = project_root_path / "archive" / "superseded"
        bucket_names = {"research", "delegations", "phases", "tiers", "prompts", "diagnostics", "runs", "refs", "reports", "plans", "analysis", "logs", "scripts"}

        def collapse_duplicate_buckets(parts: List[str]) -> List[str]:
            collapsed: List[str] = []
            for p in parts:
                if collapsed and p == collapsed[-1] and p in bucket_names:
                    continue
                collapsed.append(p)
            return collapsed

        def collapse_runs_any(parts: List[str]) -> List[str]:
            out: List[str] = []
            i = 0
            while i < len(parts):
                if i + 1 < len(parts) and parts[i] == "runs":
                    # drop runs/<anything>
                    i += 2
                    continue
                out.append(parts[i])
                i += 1
            return out

        def normalize_dest_generic(path: Path, superseded_root: Path, root_base: Path) -> Path:
            # Normalize any destination to live under superseded_root, stripping any archive/superseded segments,
            # runs/<*> pairs, and duplicate bucket segments.
            try:
                rel = path.relative_to(root_base)
            except Exception:
                rel = Path(path.name)
            parts = [p for p in rel.parts if p not in {"archive", "superseded"}]
            parts = collapse_runs_any(parts)
            parts = collapse_consecutive_duplicates(parts)  # <-- FIX: Remove consecutive duplicate folder names
            parts = collapse_duplicate_buckets(parts)
            return superseded_root / Path(*parts)

        # Special handling for generic archive root: bucket directly under archive/superseded with flattening
        normalize_dest_fn = lambda p: p

        # Special handling for .autonomous_runs root: regroup runs and refs into project superseded/runs
        if root == REPO_ROOT / ".autonomous_runs":
            actions: List[Action] = []
            superseded_mode = True
            superseded_target = project_root_path / "archive" / "superseded"
            ignore_dirs = {
                project_root_path.name,
                "archive",
                "checkpoints",
                "patches",
                "exports",
                "docs",
                "openai_delegations",
                "runs",
            }
            import re

            def run_group(name: str) -> str:
                m = re.match(r"(.+?)-\d{6,}", name)
                if m:
                    return m.group(1)
                m = re.match(r"(.+?)-20\\d{6}-\\d{6}", name)
                if m:
                    return m.group(1)
                return name

            for child in root.iterdir():
                if child.name in ignore_dirs:
                    continue
                if child.is_dir():
                    grp = run_group(child.name)
                    dest = superseded_target / "runs" / grp / child.name
                    actions.append(Action("move", child, dest, "runs regroup to project superseded"))
                elif child.is_file() and child.suffix.lower() in {".md", ".txt"}:
                    dest = superseded_target / "refs" / child.name
                    actions.append(Action("move", child, dest, "refs regroup to project superseded"))
            if actions:
                execute_actions(actions, dry_run=dry_run, checkpoint_dir=args.checkpoint_dir if not dry_run else None, logger=logger, run_id=run_id)
            continue

        if root == REPO_ROOT / "archive":
            actions: List[Action] = []
            superseded_mode = True
            superseded_target = REPO_ROOT / "archive" / "superseded"
            normalize_dest_fn = lambda p: normalize_dest_generic(p, superseded_target, root)
            research_keywords = ["research", "brief", "market", "strategy", "strategic_review", "immigration_visa", "tax", "fileorganizer_final"]
            delegation_keywords = ["delegation", "gpt", "openai", "codex"]
            phase_keywords = ["phase_", "p1", "p2", "p3", "p4", "p5", "p6", "p7", "p8", "p9"]
            tier_keywords = ["tier_00", "tier_01", "tier_02", "tier_03", "tier_04", "tier_05"]
            prompt_keywords = ["prompt"]
            debug_keywords = ["debug", "error", "journal", "diagnostic", "log", "trace"]
            ref_keywords = ["ref_", "ref"]
            report_keywords = ["consolidated", "build", "report", "readme", "setup", "tracking", "manual", "how_to", "spec", "summary", "checklist", "task"]
            plan_keywords = ["plan", "roadmap", "implementation_plan", "design_doc", "strategy", "spec"]
            analysis_keywords = ["analysis", "review", "retrospective", "postmortem"]
            script_keywords = ["script", "runner", "tool", "utility", "setup", "build", "deploy"]

            def bucket_for(name: str) -> str:
                ln = name.lower()
                if any(k in ln for k in research_keywords):
                    return "research"
                if any(k in ln for k in delegation_keywords):
                    return "delegations"
                if any(k in ln for k in plan_keywords):
                    return "plans"
                if any(k in ln for k in analysis_keywords):
                    return "analysis"
                if any(ln.startswith(k) for k in tier_keywords):
                    return "tiers"
                if ln.startswith("phase_") or any(k in ln for k in phase_keywords):
                    return "phases"
                if any(k in ln for k in prompt_keywords):
                    return "prompts"
                if any(k in ln for k in debug_keywords):
                    return "diagnostics"
                if any(k in ln for k in script_keywords):
                    return "scripts"
                if any(ln.startswith(k) for k in ref_keywords):
                    return "refs"
                if any(k in ln for k in report_keywords):
                    return "reports"
                return ""

            for dirpath, dirnames, filenames in os.walk(root):
                dirnames[:] = [d for d in dirnames if d not in {".git", "node_modules", ".pytest_cache", "__pycache__", ".venv", "venv"}]
                for fname in filenames:
                    src = Path(dirpath) / fname
                    if src.suffix.lower() not in {".md", ".txt"}:
                        continue
                    if is_protected(src):
                        continue
                    rel = src.relative_to(root)
                    rel_parts = list(rel.parts)
                    while rel_parts and rel_parts[0] in {"archive", "superseded"}:
                        rel_parts.pop(0)
                    rel_parts = collapse_runs_any(rel_parts)
                    rel_parts = collapse_consecutive_duplicates(rel_parts)  # <-- FIX: Remove consecutive duplicate folder names
                    bucket_hint = ""
                    if rel_parts and rel_parts[0] == "diagnostics":
                        bucket_hint = "diagnostics"
                        rel_parts.pop(0)
                    elif "diagnostics" in rel_parts:
                        bucket_hint = "diagnostics"
                        rel_parts = [p for p in rel_parts if p != "diagnostics"]
                    existing_bucket = ""
                    if rel_parts and rel_parts[0] in bucket_names:
                        existing_bucket = rel_parts.pop(0)
                    rel_parts = collapse_duplicate_buckets(rel_parts)
                    bucket = bucket_hint or existing_bucket or bucket_for(fname) or "reports"
                    target_base = superseded_target / bucket if bucket else superseded_target
                    dest = normalize_dest_generic(target_base / Path(*rel_parts), superseded_target, root)
                    actions.append(Action("move", src, dest, "archive->superseded"))
            execute_actions(actions, dry_run=dry_run, checkpoint_dir=args.checkpoint_dir if not dry_run else None, logger=logger, run_id=run_id)

        elif superseded_mode and root.as_posix().endswith("archive/superseded/archive"):
            actions: List[Action] = []
            research_keywords = ["research", "brief", "market", "strategy", "strategic_review", "immigration_visa", "tax", "fileorganizer_final"]
            delegation_keywords = ["delegation", "gpt", "openai", "codex"]
            phase_keywords = ["phase_", "p1", "p2", "p3", "p4", "p5", "p6", "p7", "p8", "p9"]
            tier_keywords = ["tier_00", "tier_01", "tier_02", "tier_03", "tier_04", "tier_05"]
            prompt_keywords = ["prompt"]
            debug_keywords = ["debug", "error", "journal", "diagnostic", "log", "trace"]
            ref_keywords = ["ref_", "ref"]
            report_keywords = ["consolidated", "build", "report", "readme", "setup", "tracking", "manual", "how_to", "spec", "summary", "checklist", "task"]
            plan_keywords = ["plan", "roadmap", "implementation_plan", "design_doc", "strategy", "spec"]
            analysis_keywords = ["analysis", "review", "retrospective", "postmortem"]
            script_keywords = ["script", "runner", "tool", "utility", "setup", "build", "deploy"]
            bucket_names = {"research", "delegations", "phases", "tiers", "prompts", "diagnostics", "runs", "refs", "reports", "plans", "analysis", "logs", "scripts"}

            def bucket_for(name: str) -> str:
                ln = name.lower()
                if any(k in ln for k in research_keywords):
                    return "research"
                if any(k in ln for k in delegation_keywords):
                    return "delegations"
                if any(k in ln for k in plan_keywords):
                    return "plans"
                if any(k in ln for k in analysis_keywords):
                    return "analysis"
                if any(ln.startswith(k) for k in tier_keywords):
                    return "tiers"
                if ln.startswith("phase_") or any(k in ln for k in phase_keywords):
                    return "phases"
                if any(k in ln for k in prompt_keywords):
                    return "prompts"
                if any(k in ln for k in debug_keywords):
                    return "diagnostics"
                if any(k in ln for k in script_keywords):
                    return "scripts"
                if any(ln.startswith(k) for k in ref_keywords):
                    return "refs"
                if any(k in ln for k in report_keywords):
                    return "reports"
                return ""

            def collapse_runs(parts: List[str]) -> List[str]:
                # Drop all runs/<project_id> pairs; diagnostics live under diagnostics bucket instead.
                out: List[str] = []
                i = 0
                while i < len(parts):
                    if i + 1 < len(parts) and parts[i] == "runs" and parts[i + 1] == project_id:
                        i += 2
                        continue
                    out.append(parts[i])
                    i += 1
                return out

            def normalize_dest(path: Path) -> Path:
                try:
                    rel = path.relative_to(superseded_target)
                except ValueError:
                    return normalize_dest_generic(path, superseded_target, root)
                parts = list(rel.parts)
                while parts and parts[0] in {"archive", "superseded"}:
                    parts.pop(0)
                parts = collapse_runs(parts)
                parts = collapse_consecutive_duplicates(parts)  # <-- FIX: Remove consecutive duplicate folder names
                parts = collapse_duplicate_buckets(parts)
                return superseded_target / Path(*parts)
            normalize_dest_fn = normalize_dest
        elif superseded_mode and normalize_dest_fn == (lambda p: p):
            # Generic superseded root: ensure we still normalize
            normalize_dest_fn = lambda p: normalize_dest_generic(p, superseded_target, root)

            for dirpath, dirnames, filenames in os.walk(root):
                dirnames[:] = [d for d in dirnames if d not in {".git", "node_modules", ".pytest_cache", "__pycache__", ".venv", "venv"}]
                for fname in filenames:
                    src = Path(dirpath) / fname
                    if src.suffix.lower() not in {".md", ".txt"}:
                        continue
                    if is_protected(src):
                        continue
                    rel = src.relative_to(root)
                    rel_parts = list(rel.parts)
                    # Drop redundant archive/superseded prefixes left from prior runs
                    while rel_parts and rel_parts[0] in {"archive", "superseded"}:
                        rel_parts.pop(0)
                    rel_parts = collapse_runs(rel_parts)
                    rel_parts = collapse_consecutive_duplicates(rel_parts)  # <-- FIX: Remove consecutive duplicate folder names
                    # If diagnostics folder present, force diagnostics bucket
                    bucket_hint = ""
                    if rel_parts and rel_parts[0] == "diagnostics":
                        bucket_hint = "diagnostics"
                        rel_parts.pop(0)
                    elif "diagnostics" in rel_parts:
                        bucket_hint = "diagnostics"
                        rel_parts = [p for p in rel_parts if p != "diagnostics"]
                    # Preserve existing bucket if present, but drop duplicate nesting
                    existing_bucket = ""
                    if rel_parts and rel_parts[0] in bucket_names:
                        existing_bucket = rel_parts.pop(0)
                    rel_parts = collapse_duplicate_buckets(rel_parts)
                    bucket = bucket_hint or existing_bucket or bucket_for(fname) or "reports"
                    target_base = superseded_target / bucket if bucket else superseded_target
                    dest = normalize_dest(target_base / Path(*rel_parts))
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

        # Normalize superseded destinations (dedup archive/superseded and runs/<project>)
        if superseded_mode:
            normed: List[Action] = []
            for a in actions:
                dest = normalize_dest_fn(a.dest) if a.dest else None
                normed.append(Action(a.kind, a.src, dest, a.reason))
            actions = normed

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

