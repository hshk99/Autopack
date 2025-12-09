"""
Backlog maintenance helpers.

Parses a curated backlog markdown file and produces scoped phase specs
for propose-first maintenance runs. Intended to be opt-in and read-only
by default; apply should be guarded by governed_apply in executor flows.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from autopack.maintenance_auditor import DiffStats


@dataclass
class BacklogItem:
    """Single backlog entry parsed from a markdown file."""

    id: str
    title: str
    summary: str
    allowed_paths: List[str] = field(default_factory=list)


def _slug(text: str, max_len: int = 32) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "-", text.lower()).strip("-")
    if len(cleaned) <= max_len:
        return cleaned
    digest = hashlib.sha1(text.encode("utf-8", errors="ignore")).hexdigest()[:8]
    return f"{cleaned[: max_len - 9]}-{digest}"


def parse_backlog_markdown(path: Path, max_items: int = 10) -> List[BacklogItem]:
    """
    Parse a backlog markdown file by collecting top-level bullet lines.

    Heuristic: any line starting with '- ' (top-level) becomes an item title;
    the following non-empty lines until the next bullet are captured as summary.
    """
    if not path.exists():
        raise FileNotFoundError(f"Backlog file not found: {path}")

    lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    items: List[BacklogItem] = []
    idx = 0
    i = 0
    while i < len(lines) and len(items) < max_items:
        line = lines[i].rstrip()
        if line.startswith("- "):
            title = line[2:].strip()
            summary_parts = []
            i += 1
            while i < len(lines) and not lines[i].startswith("- "):
                if lines[i].strip():
                    summary_parts.append(lines[i].strip())
                i += 1
            summary = " ".join(summary_parts)[:500]
            slug = _slug(title or f"item-{idx}")
            items.append(
                BacklogItem(
                    id=f"backlog-{slug}",
                    title=title or f"Backlog item {idx+1}",
                    summary=summary,
                )
            )
            idx += 1
            continue
        i += 1
    return items


def backlog_items_to_phases(
    items: List[BacklogItem],
    default_allowed_paths: Optional[List[str]] = None,
    max_commands: int = 20,
    max_seconds: int = 600,
) -> Dict[str, List[Dict]]:
    """
    Convert backlog items into phase specs compatible with the executor format.

    Fields kept minimal and scoped for maintenance:
    - task_category: maintenance
    - complexity: low
    - scope.allowed_paths: union of item-specific and defaults
    - diagnostics enabled implicitly via executor hooks
    """
    phases: List[Dict] = []
    for item in items:
        paths = list(item.allowed_paths or [])
        if default_allowed_paths:
            for p in default_allowed_paths:
                if p not in paths:
                    paths.append(p)
        phases.append(
            {
                "id": item.id,
                "description": item.title,
                "task_category": "maintenance",
                "complexity": "low",
                "acceptance_criteria": [
                    "Diagnostics run with artifacts stored under .autonomous_runs/<run_id>/diagnostics",
                    "Proposed patch and targeted tests attached (propose-first)",
                    "No apply unless governed_apply approves scope",
                ],
                "scope": {"paths": paths},
                "budgets": {
                    "max_commands": max_commands,
                    "max_seconds": max_seconds,
                },
                "metadata": {
                    "backlog_summary": item.summary,
                    "mode": "backlog_maintenance",
                },
            }
        )
    return {"phases": phases}


def write_plan(plan: Dict[str, List[Dict]], out_path: Path) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(plan, indent=2), encoding="utf-8")
    return out_path


# --------------------------------------------------------------------------- #
# Checkpoint helpers (optional, used by maintenance runs)
# --------------------------------------------------------------------------- #


def create_git_checkpoint(repo_path: Path, message: str = "[Autopack] Backlog checkpoint") -> Tuple[bool, Optional[str]]:
    """
    Create a lightweight git checkpoint (add + commit) to allow rollback.

    Returns (success, commit_hash_or_error)
    """
    repo_path = repo_path.resolve()
    try:
        subprocess.run(["git", "add", "-A"], cwd=repo_path, check=True, capture_output=True, text=True, timeout=30)
        commit = subprocess.run(
            ["git", "commit", "-m", message],
            cwd=repo_path,
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
        # Extract last commit hash
        show = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo_path, check=True, capture_output=True, text=True)
        return True, show.stdout.strip()
    except subprocess.CalledProcessError as e:
        return False, e.stderr.strip() if e.stderr else str(e)
    except Exception as e:  # pragma: no cover
        return False, str(e)


def revert_to_checkpoint(repo_path: Path, commit_hash: str) -> Tuple[bool, Optional[str]]:
    """
    Revert working tree to a given commit (hard reset).

    Returns (success, error_message_or_None)
    """
    repo_path = repo_path.resolve()
    try:
        subprocess.run(["git", "reset", "--hard", commit_hash], cwd=repo_path, check=True, capture_output=True, text=True, timeout=30)
        return True, None
    except subprocess.CalledProcessError as e:
        return False, e.stderr.strip() if e.stderr else str(e)
    except Exception as e:  # pragma: no cover
        return False, str(e)


def parse_patch_stats(patch_content: str) -> DiffStats:
    """
    Compute basic diff stats from a unified diff patch.
    """
    files = set()
    added = deleted = 0
    for line in patch_content.splitlines():
        if line.startswith("+++ b/"):
            files.add(line[6:])
        elif line.startswith("--- a/"):
            files.add(line[6:])
        elif line.startswith("+") and not line.startswith("+++"):
            added += 1
        elif line.startswith("-") and not line.startswith("---"):
            deleted += 1
    return DiffStats(files_changed=sorted(files), lines_added=added, lines_deleted=deleted)

