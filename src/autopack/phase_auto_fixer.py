"""
Phase auto-fixing utilities.

Goal: reduce human intervention by normalizing queued phases into a "known-good" shape
before execution:
- Normalize deliverables (strip annotations, normalize slashes, dedupe)
- Ensure scope.paths exists (derive from deliverables if missing)
- Add/adjust CI timeouts (store under scope['ci'] for persistence)
- Use prior failure metadata (scope['last_builder_result'] / last_failure_reason) to tune defaults
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any, Dict, List, Tuple


_RE_ANNOTATION = re.compile(r"\s*\([^)]*\)\s*$")  # "path (10+ tests)" -> "path"


def _norm_path(p: str) -> str:
    p = (p or "").strip()
    if not p:
        return ""
    # Drop backticks and quotes sometimes present in YAML/markdown-derived plans
    p = p.strip("`").strip("\"'").strip()
    # Normalize Windows separators to POSIX
    p = p.replace("\\", "/")
    # Remove accidental leading "./"
    while p.startswith("./"):
        p = p[2:]
    # Collapse duplicated slashes
    while "//" in p:
        p = p.replace("//", "/")
    return p


def normalize_deliverables(raw: Any) -> List[str]:
    """
    Normalize deliverables list:
    - Accepts list[str] or string.
    - Strips trailing annotations like " (10+ tests)".
    - Normalizes path separators and removes empty entries.
    """
    if raw is None:
        return []
    if isinstance(raw, str):
        items = [raw]
    elif isinstance(raw, list):
        items = raw
    else:
        return []

    out: List[str] = []
    seen = set()
    for item in items:
        if not isinstance(item, str):
            continue
        s = _norm_path(item)
        s = _RE_ANNOTATION.sub("", s).strip()
        if not s:
            continue
        if s not in seen:
            seen.add(s)
            out.append(s)
    return out


def derive_scope_paths_from_deliverables(deliverables: List[str]) -> List[str]:
    """
    Derive scope.paths entries from deliverables:
    - For files: include parent directory (with trailing '/')
    - For directory deliverables (ending with '/'): include directory as-is
    """
    roots: List[str] = []
    seen = set()
    for d in deliverables:
        d = _norm_path(d)
        if not d:
            continue
        if d.endswith("/"):
            root = d
        else:
            parent = str(PurePosixPath(d).parent)
            root = parent + "/" if parent not in ("", ".") else ""
        if not root:
            continue
        if root not in seen:
            seen.add(root)
            roots.append(root)
    return roots


def infer_ci_timeout_seconds(phase: Dict[str, Any], deliverables: List[str]) -> Tuple[int, int]:
    """
    Heuristic CI timeouts tuned to reduce code-143 timeouts.
    Returns: (timeout_seconds, per_test_timeout)
    """
    complexity = (phase.get("complexity") or "").lower().strip()
    base = {"low": 600, "medium": 900, "high": 1200, "maintenance": 1200}.get(complexity, 900)

    # Frontend / docker / integration tends to run longer
    text = " ".join([str(phase.get("name") or ""), str(phase.get("description") or "")]).lower()
    if any(
        k in text for k in ("docker", "compose", "frontend", "vite", "react", "integration", "e2e")
    ):
        base = max(base, 1200)

    # If deliverables include many files/tests, increase further
    if len(deliverables) >= 8:
        base = max(base, 1200)
    if any(d.startswith("tests/") or "/tests/" in d for d in deliverables):
        base = max(base, 900)

    per_test = 60
    if base >= 1200:
        per_test = 90

    return base, per_test


@dataclass
class PhaseFixResult:
    changed: bool
    new_scope: Dict[str, Any]
    notes: List[str]


def auto_fix_phase_scope(phase: Dict[str, Any]) -> PhaseFixResult:
    """
    Given an API phase dict (from GET /runs/{run_id}), produce an updated scope dict.
    The updated scope is intended to be persisted via the Phase update endpoint metadata merge.
    """
    scope_in = phase.get("scope") or {}
    if not isinstance(scope_in, dict):
        scope_in = {}

    notes: List[str] = []
    scope = dict(scope_in)

    # Idempotency marker
    if scope.get("_autofix_v1_applied"):
        return PhaseFixResult(changed=False, new_scope=scope, notes=["already_applied"])

    # Deliverables normalization (support multiple locations)
    deliverables_raw = scope.get("deliverables") or phase.get("deliverables")
    deliverables = normalize_deliverables(deliverables_raw)
    if deliverables_raw and deliverables != deliverables_raw:
        notes.append("deliverables_normalized")
    if deliverables:
        scope["deliverables"] = deliverables

    # Scope normalization
    paths = scope.get("paths")
    if not isinstance(paths, list):
        paths = []
    paths_norm = [p for p in (_norm_path(x) for x in paths if isinstance(x, str)) if p]

    if not paths_norm and deliverables:
        derived = derive_scope_paths_from_deliverables(deliverables)
        if derived:
            paths_norm = derived
            notes.append("scope_paths_derived_from_deliverables")

    # Ensure directory-ish paths end with '/'
    fixed_paths: List[str] = []
    for p in paths_norm:
        # Heuristic: treat anything with a file extension as a file, otherwise a dir
        is_fileish = bool(PurePosixPath(p).suffix) and not p.endswith("/")
        if is_fileish:
            fixed_paths.append(p)
        else:
            fixed_paths.append(p if p.endswith("/") else p + "/")
    # Deduplicate, preserve order
    seen = set()
    fixed_paths2 = []
    for p in fixed_paths:
        if p not in seen:
            seen.add(p)
            fixed_paths2.append(p)
    if fixed_paths2 != paths:
        scope["paths"] = fixed_paths2
        notes.append("scope_paths_normalized")

    # Ensure read_only_context is present
    roc = scope.get("read_only_context")
    if roc is None:
        scope["read_only_context"] = []

    # CI tuning: store under scope['ci'] so we can persist it without API schema changes
    ci = scope.get("ci") or {}
    if not isinstance(ci, dict):
        ci = {}

    timeout_seconds, per_test_timeout = infer_ci_timeout_seconds(phase, deliverables)
    if ci.get("timeout_seconds") is None:
        ci["timeout_seconds"] = timeout_seconds
        notes.append("ci_timeout_set")
    else:
        # Increase timeout if previously too low
        try:
            if int(ci.get("timeout_seconds")) < timeout_seconds:
                ci["timeout_seconds"] = timeout_seconds
                notes.append("ci_timeout_increased")
        except Exception:
            ci["timeout_seconds"] = timeout_seconds
            notes.append("ci_timeout_set")

    if ci.get("per_test_timeout") is None:
        ci["per_test_timeout"] = per_test_timeout
        notes.append("ci_per_test_timeout_set")

    # If prior attempt shows timeout, increase aggressively
    last = scope.get("last_builder_result") or {}
    last_status = str((last.get("metadata") or {}).get("status") or "").lower()
    last_failure_reason = str(scope.get("last_failure_reason") or "").lower()
    if "timeout" in last_status or "timeout" in last_failure_reason or "143" in last_failure_reason:
        ci["timeout_seconds"] = max(int(ci.get("timeout_seconds") or 0), 1200)
        ci["per_test_timeout"] = max(int(ci.get("per_test_timeout") or 0), 90)
        notes.append("ci_timeout_escalated_due_to_previous_timeout")

    scope["ci"] = ci

    scope["_autofix_v1_applied"] = True
    scope["_autofix_v1_notes"] = notes[:20]
    scope["_autofix_v1_ts"] = os.environ.get("AUTOPACK_AUTOFIX_TS")  # optional operator stamp

    changed = scope != scope_in
    return PhaseFixResult(changed=changed, new_scope=scope, notes=notes)
