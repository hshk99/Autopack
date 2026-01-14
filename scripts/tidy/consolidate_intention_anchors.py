"""
Tidy hook: Consolidate Intention Anchor artifacts into SOT ledgers.

Intention behind it: Provide a human-triggered (or scheduled) consolidation of
run-local anchor artifacts into BUILD_HISTORY/DEBUG_LOG, without requiring
autonomous runs to write directly to SOT ledgers during execution.

Implementation phases (per docs/IMPLEMENTATION_PLAN_INTENTION_ANCHOR_CONSOLIDATION.md):
- B1: Report mode (deterministic, read-only, no SOT writes) ✓
- B2: Plan mode (generate reviewable consolidation plan with idempotency hashes) ✓
- B3: Apply mode (gated, double opt-in, idempotent SOT writes) ✓

Safety hardening (P0):
- Project ID validation (rejects path traversal, separators, invalid patterns)
- Resolution-based path containment checks
- Strict project filtering by default (--include-unknown-project to override)

Design principles:
- Run-local artifacts are append-only and never modified during consolidation
- Consolidation is idempotent (safe to run multiple times)
- SOT ledgers remain manually curated (this script assists, doesn't replace)
- Report/Plan modes are safe-by-default (no SOT writes)
- Apply mode requires explicit --execute flag (double opt-in)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# Add project root to path for imports
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root / "src"))

from autopack.intention_anchor.artifacts import (
    get_anchor_events_path,
    get_anchor_summary_path,
    get_anchor_summary_version_path,
    read_anchor_events,
)
from autopack.intention_anchor.storage import get_canonical_path, load_anchor

logger = logging.getLogger(__name__)

PROJECT_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


def validate_project_id(project_id: str) -> str:
    """
    Validate project_id for safety (prevents path traversal / separators).

    Rules:
    - Must match: ^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$
    - Must not contain path separators or '..'
    """
    if not PROJECT_ID_PATTERN.match(project_id or ""):
        raise ValueError("Invalid --project-id. Must match: ^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
    if "/" in project_id or "\\" in project_id or ".." in project_id:
        raise ValueError("Invalid --project-id. Must not contain '/', '\\\\', or '..'")
    return project_id


def assert_path_within(child: Path, parent: Path) -> None:
    """
    Assert that child resolves within parent (or equals parent).
    Uses resolution-based containment to avoid path traversal issues.
    """
    child_resolved = child.resolve()
    parent_resolved = parent.resolve()
    if child_resolved != parent_resolved and parent_resolved not in child_resolved.parents:
        raise ValueError(
            f"Safety check failed: resolved target escaped allowed directory "
            f"(target={child_resolved}, allowed_dir={parent_resolved})"
        )


def resolve_target_build_history(project_id: str, base_dir: Path) -> tuple[Path, Path]:
    """
    Resolve the allowed docs directory and the exact BUILD_HISTORY.md target.
    Returns (allowed_docs_dir, target_file).
    """
    if project_id == "autopack":
        allowed_dir = base_dir / "docs"
        target_file = allowed_dir / "BUILD_HISTORY.md"
    else:
        allowed_dir = base_dir / ".autonomous_runs" / project_id / "docs"
        target_file = allowed_dir / "BUILD_HISTORY.md"

    # Resolution-based containment check
    assert_path_within(target_file, allowed_dir)

    # Final bounded target check (must be BUILD_HISTORY.md)
    if target_file.name != "BUILD_HISTORY.md":
        raise ValueError(
            f"Safety check failed: target file must be BUILD_HISTORY.md (got: {target_file})"
        )

    return allowed_dir, target_file


# =============================================================================
# Core Discovery Functions
# =============================================================================


def find_runs_with_anchors(base_dir: Path = Path(".")) -> list[str]:
    """
    Find all run IDs that have intention anchors.

    Args:
        base_dir: Base directory to search (default: ".").

    Returns:
        List of run IDs with intention anchors (sorted).
    """
    runs_dir = base_dir / ".autonomous_runs"
    if not runs_dir.exists():
        return []

    run_ids = []
    for run_dir in runs_dir.iterdir():
        if not run_dir.is_dir():
            continue

        anchor_path = get_canonical_path(run_dir.name, base_dir=base_dir)
        if anchor_path.exists():
            run_ids.append(run_dir.name)

    return sorted(run_ids)


def analyze_anchor_artifacts(run_id: str, base_dir: Path = Path(".")) -> dict:
    """
    Analyze anchor artifacts for a run.

    Args:
        run_id: Run identifier.
        base_dir: Base directory (default: ".").

    Returns:
        Dictionary with analysis results.
    """
    analysis = {
        "run_id": run_id,
        "project_id": None,
        "anchor_id": None,
        "version": None,
        "last_updated": None,
        "has_anchor": False,
        "has_summary": False,
        "has_events": False,
        "event_count": 0,
        "event_types": {},
        "malformed_events": 0,
        # P1 validation fields (populated even in report-only mode)
        "invalid_format_version_events": 0,
        "unknown_event_types": {},
        "missing_summary_snapshots": [],
    }

    # Check for anchor JSON
    try:
        anchor = load_anchor(run_id, base_dir=base_dir)
        analysis["has_anchor"] = True
        analysis["project_id"] = anchor.project_id
        analysis["anchor_id"] = anchor.anchor_id
        analysis["version"] = anchor.version
        analysis["last_updated"] = anchor.updated_at.isoformat()
    except (FileNotFoundError, Exception) as e:
        logger.debug(f"Could not load anchor for {run_id}: {e}")

    # Check for summary
    summary_path = get_anchor_summary_path(run_id, base_dir=base_dir)
    analysis["has_summary"] = summary_path.exists()

    # Snapshot completeness (Part A): for readable anchors, expect v1..vN snapshots.
    if analysis["has_anchor"] and isinstance(analysis["version"], int) and analysis["version"] >= 1:
        missing_versions: list[int] = []
        for v in range(1, int(analysis["version"]) + 1):
            v_path = get_anchor_summary_version_path(run_id, v, base_dir=base_dir)
            if not v_path.exists():
                missing_versions.append(v)
        analysis["missing_summary_snapshots"] = missing_versions

    # Check for events
    events_path = get_anchor_events_path(run_id, base_dir=base_dir)
    if events_path.exists():
        analysis["has_events"] = True

        # Count events and event types
        events = []
        malformed_count = 0
        invalid_format_version = 0
        unknown_event_type_counts: Counter[str] = Counter()

        allowed_event_types = {
            "anchor_created",
            "anchor_updated",
            "prompt_injected_builder",
            "prompt_injected_auditor",
            "prompt_injected_doctor",
            "validation_warning",
            "validation_error",
        }

        with events_path.open("r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                    events.append(event)

                    fv = event.get("format_version")
                    if fv != 1:
                        invalid_format_version += 1

                    et = event.get("event_type")
                    if not et:
                        unknown_event_type_counts["missing_event_type"] += 1
                    elif et not in allowed_event_types:
                        unknown_event_type_counts[str(et)] += 1
                except json.JSONDecodeError:
                    malformed_count += 1
                    logger.debug(f"{run_id}: Malformed event at line {line_num}")

        analysis["event_count"] = len(events)
        analysis["malformed_events"] = malformed_count
        analysis["invalid_format_version_events"] = invalid_format_version
        analysis["unknown_event_types"] = dict(sorted(unknown_event_type_counts.items()))

        # Count by event type
        event_type_counts = Counter(e.get("event_type", "unknown") for e in events)
        analysis["event_types"] = dict(sorted(event_type_counts.items()))

    return analysis


# =============================================================================
# B1: Report Mode
# =============================================================================


def generate_report_markdown(analyses: list[dict]) -> str:
    """
    Generate deterministic markdown report.

    Args:
        analyses: List of analysis dictionaries (sorted).

    Returns:
        Markdown-formatted report.
    """
    lines = [
        "# Intention Anchor Consolidation Report",
        "",
        f"**Total runs analyzed**: {len(analyses)}",
        "",
    ]

    if not analyses:
        lines.append("*No runs with intention anchors found.*")
        lines.append("")
        return "\n".join(lines)

    # Summary table
    lines.append("## Summary")
    lines.append("")
    lines.append("| Run ID | Anchor ID | Version | Last Updated | Events | Artifacts Complete |")
    lines.append("|--------|-----------|---------|--------------|--------|--------------------|")

    for analysis in analyses:
        complete = (
            "✅"
            if (analysis["has_anchor"] and analysis["has_summary"] and analysis["has_events"])
            else "⚠️"
        )

        last_updated = analysis["last_updated"] or "N/A"
        if last_updated != "N/A" and "T" in last_updated:
            # Truncate to date only for readability
            last_updated = last_updated.split("T")[0]

        lines.append(
            f"| {analysis['run_id']} | "
            f"{analysis['anchor_id'] or 'N/A'} | "
            f"{analysis['version'] or 'N/A'} | "
            f"{last_updated} | "
            f"{analysis['event_count']} | "
            f"{complete} |"
        )

    lines.append("")

    # Detailed breakdown
    lines.append("## Detailed Breakdown")
    lines.append("")

    for analysis in analyses:
        lines.append(f"### {analysis['run_id']}")
        lines.append("")
        lines.append(f"- **Project ID**: {analysis['project_id'] or 'N/A'}")
        lines.append(f"- **Anchor ID**: `{analysis['anchor_id'] or 'N/A'}`")
        lines.append(f"- **Version**: {analysis['version'] or 'N/A'}")
        lines.append(f"- **Last Updated**: {analysis['last_updated'] or 'N/A'}")
        lines.append("")

        lines.append("**Artifact Completeness:**")
        lines.append(f"- Anchor JSON: {'✅' if analysis['has_anchor'] else '❌'}")
        lines.append(f"- Summary MD: {'✅' if analysis['has_summary'] else '❌'}")
        lines.append(f"- Events NDJSON: {'✅' if analysis['has_events'] else '❌'}")
        lines.append("")

        if analysis["event_count"] > 0:
            lines.append(f"**Events**: {analysis['event_count']} total")
            if analysis["event_types"]:
                lines.append("- Event type breakdown:")
                for event_type, count in analysis["event_types"].items():
                    lines.append(f"  - `{event_type}`: {count}")
            if analysis["malformed_events"] > 0:
                lines.append(f"- ⚠️ Malformed events: {analysis['malformed_events']}")
            lines.append("")

    return "\n".join(lines)


def generate_report_json(analyses: list[dict]) -> dict:
    """
    Generate deterministic JSON report.

    Args:
        analyses: List of analysis dictionaries.

    Returns:
        Report dictionary.
    """
    return {
        "format_version": 1,
        "total_runs": len(analyses),
        "runs": analyses,
    }


def run_report_mode(
    run_id: Optional[str] = None,
    base_dir: Path = Path("."),
    output_md: Optional[Path] = None,
    output_json: Optional[Path] = None,
) -> int:
    """
    Execute report-only mode.

    Args:
        run_id: Optional single run ID to analyze.
        base_dir: Base directory.
        output_md: Optional markdown output path.
        output_json: Optional JSON output path.

    Returns:
        Exit code (0 on success).
    """
    logger.info("Starting Intention Anchor consolidation report...")

    # Find runs
    if run_id:
        run_ids = [run_id]
    else:
        run_ids = find_runs_with_anchors(base_dir)

    logger.info(f"Found {len(run_ids)} run(s) with intention anchors")

    # Analyze all runs
    analyses = []
    for rid in run_ids:
        analysis = analyze_anchor_artifacts(rid, base_dir=base_dir)
        analyses.append(analysis)

    # Sort by last_updated desc, then by run_id (deterministic)
    analyses.sort(
        key=lambda a: (a["last_updated"] or "", a["run_id"]),
        reverse=True,
    )

    # Generate reports
    md_report = generate_report_markdown(analyses)
    json_report = generate_report_json(analyses)

    # Output markdown
    if output_md:
        output_md.write_text(md_report, encoding="utf-8")
        logger.info(f"Markdown report written to: {output_md}")
    else:
        print(md_report)

    # Output JSON
    if output_json:
        output_json.write_text(
            json.dumps(json_report, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        logger.info(f"JSON report written to: {output_json}")

    return 0


# =============================================================================
# B2: Plan Mode
# =============================================================================


def compute_idempotency_hash(content: str) -> str:
    """
    Compute stable idempotency hash for content.

    Args:
        content: Content to hash.

    Returns:
        Hex digest (first 12 chars).
    """
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:12]


def generate_consolidation_block(analysis: dict, base_dir: Path = Path(".")) -> str:
    """
    Generate proposed consolidation block (short reference).

    Args:
        analysis: Analysis dictionary.
        base_dir: Base directory.

    Returns:
        Markdown block (deterministic, short).
    """
    lines = [
        f"### {analysis['run_id']}",
        "",
        f"**Anchor**: `{analysis['anchor_id']}` (v{analysis['version']})",
        f"**Project**: {analysis['project_id']}",
        f"**Updated**: {analysis['last_updated']}",
        "",
    ]

    # Add event summary if available
    if analysis["event_count"] > 0:
        total_injections = sum(
            count
            for event_type, count in analysis["event_types"].items()
            if event_type.startswith("prompt_injected_")
        )
        lines.append(
            f"**Events**: {analysis['event_count']} total, {total_injections} prompt injections"
        )

    lines.append("")
    lines.append(f"See: `.autonomous_runs/{analysis['run_id']}/anchor_summary.md`")
    lines.append("")

    return "\n".join(lines)


def generate_consolidation_plan(
    project_id: str,
    analyses: list[dict],
    base_dir: Path = Path("."),
    max_runs: int = 10,
    *,
    include_unknown_project: bool = False,
) -> dict:
    """
    Generate consolidation plan (reviewable JSON).

    Args:
        project_id: Project identifier (e.g., 'autopack').
        analyses: List of analysis dictionaries (sorted).
        base_dir: Base directory.
        max_runs: Maximum runs to include in plan.

    Returns:
        Plan dictionary.
    """
    # Determine target docs directory
    if project_id == "autopack":
        target_docs_dir = base_dir / "docs"
    else:
        target_docs_dir = base_dir / ".autonomous_runs" / project_id / "docs"

    candidates = []
    for analysis in analyses:
        # Skip incomplete artifacts
        if not (analysis["has_anchor"] and analysis["has_summary"]):
            logger.debug(f"Skipping {analysis['run_id']} (incomplete artifacts)")
            continue
        if len(candidates) >= max_runs:
            break

        # Generate proposed block
        proposed_block = generate_consolidation_block(analysis, base_dir=base_dir)

        # Compute idempotency hash
        idempotency_hash = compute_idempotency_hash(proposed_block)

        candidate = {
            "run_id": analysis["run_id"],
            "anchor_id": analysis["anchor_id"],
            "version": analysis["version"],
            "target_docs_dir": str(target_docs_dir),
            "target_file": str(target_docs_dir / "BUILD_HISTORY.md"),
            "idempotency_hash": idempotency_hash,
            "proposed_block_md": proposed_block,
        }

        candidates.append(candidate)

    return {
        "format_version": 1,
        "project_id": project_id,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "filters": {
            "max_runs": max_runs,
            "include_unknown_project": include_unknown_project,
        },
        "candidates": candidates,
    }


def run_plan_mode(
    project_id: str,
    base_dir: Path = Path("."),
    out: Path = None,
    max_runs: int = 10,
    include_unknown_project: bool = False,
) -> int:
    """
    Execute plan generation mode.

    Args:
        project_id: Project identifier.
        base_dir: Base directory.
        out: Output path for plan JSON.
        max_runs: Maximum runs to include.

    Returns:
        Exit code (0 on success).
    """
    try:
        project_id = validate_project_id(project_id)
    except ValueError as e:
        logger.error(str(e))
        return 2

    logger.info(f"Generating consolidation plan for project: {project_id}")

    # Find all runs with anchors
    run_ids = find_runs_with_anchors(base_dir)
    logger.info(f"Found {len(run_ids)} run(s) with intention anchors")

    # Analyze all runs
    analyses = []
    for run_id in run_ids:
        analysis = analyze_anchor_artifacts(run_id, base_dir=base_dir)
        # Filter strictly by project_id by default to prevent cross-project mixing.
        if analysis["project_id"] == project_id:
            analyses.append(analysis)
        elif include_unknown_project and analysis["project_id"] is None:
            analyses.append(analysis)

    # Sort by last_updated desc (deterministic)
    analyses.sort(
        key=lambda a: (a["last_updated"] or "", a["run_id"]),
        reverse=True,
    )

    logger.info(f"Analyzing {len(analyses)} run(s) for consolidation plan...")

    # Generate plan
    plan = generate_consolidation_plan(
        project_id,
        analyses,
        base_dir,
        max_runs,
        include_unknown_project=include_unknown_project,
    )

    logger.info(f"Generated plan with {len(plan['candidates'])} candidate(s)")

    # Write plan
    if out:
        out.write_text(
            json.dumps(plan, indent=2, sort_keys=False),
            encoding="utf-8",
        )
        logger.info(f"Plan written to: {out}")
    else:
        print(json.dumps(plan, indent=2, sort_keys=False))

    return 0


# =============================================================================
# B3: Apply Mode (Gated Consolidation)
# =============================================================================


def check_marker_exists(file_path: Path, idempotency_hash: str) -> bool:
    """
    Check if idempotency marker already exists in file.

    Args:
        file_path: Path to file to check.
        idempotency_hash: Idempotency hash to search for.

    Returns:
        True if marker exists, False otherwise.
    """
    if not file_path.exists():
        return False

    content = file_path.read_text(encoding="utf-8")
    # P2.3: Stricter marker matching - require full IA_CONSOLIDATION comment structure
    marker_pattern = f"<!-- IA_CONSOLIDATION:.*hash={idempotency_hash}.*-->"
    return re.search(marker_pattern, content) is not None


def apply_consolidation_entry(
    file_path: Path,
    proposed_block: str,
    idempotency_hash: str,
    anchor_id: str,
    version: int,
) -> bool:
    """
    Apply consolidation entry to file (idempotent).

    Args:
        file_path: Path to target file.
        proposed_block: Markdown block to insert.
        idempotency_hash: Idempotency hash for this entry.
        anchor_id: Anchor ID.
        version: Anchor version.

    Returns:
        True if entry was applied, False if skipped (already exists).
    """
    # Check idempotency
    if check_marker_exists(file_path, idempotency_hash):
        logger.info(
            f"Skipping {anchor_id} v{version} (already consolidated, hash={idempotency_hash})"
        )
        return False

    # Ensure file exists
    if not file_path.exists():
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text("# Build History\n\n", encoding="utf-8")

    # Read current content
    current_content = file_path.read_text(encoding="utf-8")

    # Prepare entry with marker
    marker = f"<!-- IA_CONSOLIDATION: anchor_id={anchor_id} version={version} hash={idempotency_hash} -->"
    entry = f"{proposed_block}\n{marker}\n\n"

    # Append to file
    new_content = current_content.rstrip() + "\n\n" + entry

    # P2.2: Atomic write with unique temp file naming (same directory for atomic replace)
    import os
    import time
    import random

    pid = os.getpid()
    timestamp = int(time.time() * 1000)  # millisecond precision
    rand = random.randint(1000, 9999)
    temp_filename = f"{file_path.name}.tmp.{pid}.{timestamp}.{rand}"
    temp_path = file_path.parent / temp_filename

    try:
        temp_path.write_text(new_content, encoding="utf-8")
        temp_path.replace(file_path)
    finally:
        # Best-effort cleanup if replace failed
        if temp_path.exists():
            try:
                temp_path.unlink()
            except Exception:
                pass  # Ignore cleanup failures

    logger.info(f"Applied consolidation for {anchor_id} v{version} to {file_path}")
    return True


def run_apply_mode(
    project_id: str,
    base_dir: Path = Path("."),
    execute: bool = False,
    max_runs: int = 10,
    include_unknown_project: bool = False,
) -> int:
    """
    Execute gated apply mode (write to SOT ledgers).

    Args:
        project_id: Project identifier.
        base_dir: Base directory.
        execute: If True, actually perform writes (double opt-in).
        max_runs: Maximum runs to consolidate.

    Returns:
        Exit code (0 on success).
    """
    try:
        project_id = validate_project_id(project_id)
    except ValueError as e:
        logger.error(str(e))
        return 2

    if not execute:
        # P2.1: Preview mode - show what would be done without executing
        logger.info("Apply mode preview (no writes performed)")
        logger.info(f"Project: {project_id}")
        logger.info(f"Max runs: {max_runs}")
        logger.info(f"Include unknown project: {include_unknown_project}")

        # Generate preview plan
        run_ids = find_runs_with_anchors(base_dir)
        analyses = []
        for run_id in run_ids:
            analysis = analyze_anchor_artifacts(run_id, base_dir=base_dir)
            if analysis["project_id"] == project_id:
                analyses.append(analysis)
            elif include_unknown_project and analysis["project_id"] is None:
                analyses.append(analysis)

        analyses.sort(
            key=lambda a: (a["last_updated"] or "", a["run_id"]),
            reverse=True,
        )

        plan = generate_consolidation_plan(
            project_id,
            analyses,
            base_dir,
            max_runs,
            include_unknown_project=include_unknown_project,
        )

        _, target_file = resolve_target_build_history(project_id, base_dir)

        logger.info(f"\nTarget file: {target_file}")
        logger.info(f"Candidates found: {len(plan['candidates'])}")

        if plan["candidates"]:
            logger.info("\nFirst 3 candidates:")
            for i, candidate in enumerate(plan["candidates"][:3], 1):
                logger.info(
                    f"  {i}. {candidate['run_id']} (anchor={candidate['anchor_id']}, hash={candidate['idempotency_hash']})"
                )

        logger.error("\nNo writes performed. Use --execute to apply changes.")
        return 1

    logger.warning("⚠️  APPLY MODE: Will write to SOT ledgers")
    logger.info(f"Consolidating intention anchors for project: {project_id}")

    # Find all runs with anchors
    run_ids = find_runs_with_anchors(base_dir)
    logger.info(f"Found {len(run_ids)} run(s) with intention anchors")

    # Analyze all runs
    analyses = []
    for run_id in run_ids:
        analysis = analyze_anchor_artifacts(run_id, base_dir=base_dir)
        # Filter strictly by project_id by default to prevent cross-project mixing.
        if analysis["project_id"] == project_id:
            analyses.append(analysis)
        elif include_unknown_project and analysis["project_id"] is None:
            analyses.append(analysis)

    # Sort by last_updated desc (deterministic)
    analyses.sort(
        key=lambda a: (a["last_updated"] or "", a["run_id"]),
        reverse=True,
    )

    logger.info(f"Analyzing {len(analyses)} run(s) for consolidation...")

    # Generate consolidation plan
    plan = generate_consolidation_plan(
        project_id,
        analyses,
        base_dir,
        max_runs,
        include_unknown_project=include_unknown_project,
    )

    if not plan["candidates"]:
        logger.info("No candidates to consolidate")
        return 0

    logger.info(f"Processing {len(plan['candidates'])} candidate(s)...")

    # Determine target file with resolution-based safety checks
    try:
        _, target_file = resolve_target_build_history(project_id, base_dir)
    except ValueError as e:
        logger.error(str(e))
        return 1

    # Apply each candidate
    applied_count = 0
    skipped_count = 0

    for candidate in plan["candidates"]:
        was_applied = apply_consolidation_entry(
            file_path=target_file,
            proposed_block=candidate["proposed_block_md"],
            idempotency_hash=candidate["idempotency_hash"],
            anchor_id=candidate["anchor_id"],
            version=candidate["version"],
        )

        if was_applied:
            applied_count += 1
        else:
            skipped_count += 1

    logger.info(
        f"Consolidation complete: {applied_count} applied, {skipped_count} skipped (already consolidated)"
    )
    logger.info(f"Target file: {target_file}")

    return 0


# =============================================================================
# Main CLI
# =============================================================================


def main():
    """Main entry point for consolidation hook."""
    parser = argparse.ArgumentParser(
        description="Consolidate Intention Anchor artifacts (report/plan/apply modes)"
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # Report subcommand
    report_parser = subparsers.add_parser(
        "report",
        help="Generate report of all runs with intention anchors (read-only)",
    )
    report_parser.add_argument(
        "--run-id",
        type=str,
        help="Analyze specific run ID (default: all runs)",
    )
    report_parser.add_argument(
        "--base-dir",
        type=str,
        default=".",
        help="Base directory (default: current directory)",
    )
    report_parser.add_argument(
        "--output-md",
        type=str,
        help="Write markdown report to file (default: stdout)",
    )
    report_parser.add_argument(
        "--output-json",
        type=str,
        help="Write JSON report to file (optional)",
    )

    # Plan subcommand
    plan_parser = subparsers.add_parser(
        "plan",
        help="Generate consolidation plan with idempotency hashes (no SOT writes)",
    )
    plan_parser.add_argument(
        "--project-id",
        type=str,
        required=True,
        help="Project ID (e.g., 'autopack')",
    )
    plan_parser.add_argument(
        "--base-dir",
        type=str,
        default=".",
        help="Base directory (default: current directory)",
    )
    plan_parser.add_argument(
        "--out",
        type=str,
        required=True,
        help="Output path for plan JSON",
    )
    plan_parser.add_argument(
        "--max-runs",
        type=int,
        default=10,
        help="Maximum runs to include in plan (default: 10)",
    )

    # Apply subcommand
    apply_parser = subparsers.add_parser(
        "apply",
        help="Apply consolidation (gated, requires --execute flag for SOT writes)",
    )
    apply_parser.add_argument(
        "--project-id",
        type=str,
        required=True,
        help="Project ID (e.g., 'autopack')",
    )
    apply_parser.add_argument(
        "--base-dir",
        type=str,
        default=".",
        help="Base directory (default: current directory)",
    )
    apply_parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually perform SOT writes (required, double opt-in)",
    )
    apply_parser.add_argument(
        "--max-runs",
        type=int,
        default=10,
        help="Maximum runs to consolidate (default: 10)",
    )
    apply_parser.add_argument(
        "--include-unknown-project",
        action="store_true",
        help="Include runs where project_id cannot be derived (not recommended)",
    )

    # Plan subcommand extra flags
    plan_parser.add_argument(
        "--include-unknown-project",
        action="store_true",
        help="Include runs where project_id cannot be derived (not recommended)",
    )

    args = parser.parse_args()

    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    # Dispatch to subcommand
    if args.command == "report":
        return run_report_mode(
            run_id=args.run_id,
            base_dir=Path(args.base_dir),
            output_md=Path(args.output_md) if args.output_md else None,
            output_json=Path(args.output_json) if args.output_json else None,
        )
    elif args.command == "plan":
        return run_plan_mode(
            project_id=args.project_id,
            base_dir=Path(args.base_dir),
            out=Path(args.out),
            max_runs=args.max_runs,
            include_unknown_project=args.include_unknown_project,
        )
    elif args.command == "apply":
        return run_apply_mode(
            project_id=args.project_id,
            base_dir=Path(args.base_dir),
            execute=args.execute,
            max_runs=args.max_runs,
            include_unknown_project=args.include_unknown_project,
        )
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
