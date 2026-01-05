"""
Maintenance auditor for backlog proposals.

Decides whether a proposed maintenance fix should be auto-approved,
require human review, or be rejected, using conservative defaults:
- Scope must stay within allowed_paths
- No protected path touches
- Diff size under thresholds
- Targeted tests present and passing
- Failure class/context aligned
- Diagnostics present
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class DiffStats:
    files_changed: List[str] = field(default_factory=list)
    lines_added: int = 0
    lines_deleted: int = 0


@dataclass
class TestResult:
    name: str
    status: str  # passed|failed|skipped|not_run


@dataclass
class AuditorInput:
    allowed_paths: List[str]
    protected_paths: List[str]
    diff: DiffStats
    tests: List[TestResult]
    failure_class: Optional[str] = None
    item_context: Optional[str] = None
    diagnostics_summary: Optional[str] = None
    max_files: int = 10
    max_lines: int = 500


@dataclass
class AuditorDecision:
    verdict: str  # approve | require_human | reject
    reasons: List[str]


def _path_within(path: str, prefixes: List[str]) -> bool:
    normalized = path.replace("\\", "/")
    return any(
        normalized.startswith(p.rstrip("/") + "/") or normalized == p.rstrip("/") for p in prefixes
    )


def evaluate(input: AuditorInput) -> AuditorDecision:
    reasons: List[str] = []

    if not input.diagnostics_summary:
        reasons.append("no diagnostics summary")

    # Handle None diff (no patch provided)
    if input.diff is None:
        reasons.append("no diff provided")
    else:
        if not input.diff.files_changed:
            reasons.append("no diff provided")

        # Protected path check
        for f in input.diff.files_changed:
            if _path_within(f, input.protected_paths):
                reasons.append(f"protected path touched: {f}")

        # Allowed path check
        for f in input.diff.files_changed:
            if input.allowed_paths and not _path_within(f, input.allowed_paths):
                reasons.append(f"out of scope: {f}")

        # Size checks
        if len(input.diff.files_changed) > input.max_files:
            reasons.append(f"too many files: {len(input.diff.files_changed)}>{input.max_files}")
        if (input.diff.lines_added + input.diff.lines_deleted) > input.max_lines:
            reasons.append(
                f"too many lines: {input.diff.lines_added + input.diff.lines_deleted}>{input.max_lines}"
            )

    # Tests
    if not input.tests:
        reasons.append("no targeted tests")
    else:
        failed = [t.name for t in input.tests if t.status != "passed"]
        if failed:
            reasons.append(f"tests not passing: {failed}")

    # Context alignment (lightweight)
    if (
        input.failure_class
        and input.item_context
        and input.failure_class not in input.item_context.lower()
    ):
        reasons.append("failure class not aligned with item context")

    if reasons:
        verdict = "require_human"
        # Reject if protected paths are touched
        if any("protected path" in r for r in reasons):
            verdict = "reject"
        return AuditorDecision(verdict=verdict, reasons=reasons)

    return AuditorDecision(verdict="approve", reasons=["meets minimal, safe criteria"])
