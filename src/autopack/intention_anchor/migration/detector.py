"""IMP-INTENT-003: Migration detector for intention systems.

Detects usage of old (v1) vs new (v2) intention systems across the codebase.

Old System (v1):
- ProjectIntentionManager (project_intention.py)
- IntentionContextInjector (intention_wiring.py)
- Uses v1 schema with intent_anchor, intent_facts, non_goals

New System (v2):
- IntentionAnchorV2 (intention_anchor/v2.py)
- Universal pivot intentions model
- Uses v2 schema with north_star, safety_risk, evidence_verification sections
"""

import logging
from pathlib import Path
from typing import Dict, List

logger = logging.getLogger(__name__)

# Old system markers (v1)
OLD_SYSTEM_MARKERS = [
    "ProjectIntentionManager",
    "IntentionContextInjector",
    "from autopack.project_intention import",
    "from autopack.intention_wiring import",
    "intent_anchor",  # v1 schema field
    "intent_facts",  # v1 schema field
]

# New system markers (v2)
NEW_SYSTEM_MARKERS = [
    "IntentionAnchorV2",
    "from autopack.intention_anchor.v2 import",
    "from autopack.intention_anchor import IntentionAnchorV2",
    "north_star",  # v2 schema section
    "safety_risk",  # v2 schema section
    "NorthStarIntention",
    "SafetyRiskIntention",
]


def detect_intention_system_usage(workspace_root: str) -> Dict[str, List[str]]:
    """Detect which intention system is used in each Python file.

    IMP-INTENT-003: Scans workspace for old vs new intention system usage.

    Args:
        workspace_root: Root directory to scan

    Returns:
        Dict with keys:
        - "old_system": List of files using only old (v1) system
        - "new_system": List of files using only new (v2) system
        - "both_systems": List of files using both (needs immediate migration)
        - "neither": List of files using neither (no action needed)

    Example:
        >>> usage = detect_intention_system_usage("/workspace")
        >>> print(f"Files needing migration: {len(usage['old_system'])}")
        >>> print(f"Mixed usage (critical): {len(usage['both_systems'])}")
    """
    workspace = Path(workspace_root).resolve()

    old_system_files: List[str] = []
    new_system_files: List[str] = []
    both_system_files: List[str] = []
    neither_files: List[str] = []

    logger.info(f"[IMP-INTENT-003] Scanning workspace: {workspace}")

    # Scan all Python files in src/autopack
    src_autopack = workspace / "src" / "autopack"
    if not src_autopack.exists():
        logger.warning(f"[IMP-INTENT-003] Directory not found: {src_autopack}")
        return {
            "old_system": [],
            "new_system": [],
            "both_systems": [],
            "neither": [],
        }

    python_files = list(src_autopack.rglob("*.py"))
    logger.info(f"[IMP-INTENT-003] Found {len(python_files)} Python files to scan")

    for py_file in python_files:
        try:
            content = py_file.read_text(encoding="utf-8")
            rel_path = str(py_file.relative_to(workspace))

            # Check for old system markers
            has_old = any(marker in content for marker in OLD_SYSTEM_MARKERS)

            # Check for new system markers
            has_new = any(marker in content for marker in NEW_SYSTEM_MARKERS)

            # Categorize file
            if has_old and has_new:
                both_system_files.append(rel_path)
                logger.warning(
                    f"[IMP-INTENT-003] Mixed usage detected: {rel_path} "
                    f"(uses both v1 and v2 - needs immediate attention)"
                )
            elif has_old:
                old_system_files.append(rel_path)
                logger.debug(f"[IMP-INTENT-003] Old system (v1): {rel_path}")
            elif has_new:
                new_system_files.append(rel_path)
                logger.debug(f"[IMP-INTENT-003] New system (v2): {rel_path}")
            else:
                # File doesn't use intention system at all
                neither_files.append(rel_path)

        except Exception as e:
            logger.debug(f"[IMP-INTENT-003] Could not read {py_file}: {e}")
            continue

    # Log summary
    logger.info(
        f"[IMP-INTENT-003] Scan complete: "
        f"{len(old_system_files)} old system, "
        f"{len(new_system_files)} new system, "
        f"{len(both_system_files)} mixed usage, "
        f"{len(neither_files)} no intention usage"
    )

    if both_system_files:
        logger.warning(
            f"[IMP-INTENT-003] CRITICAL: {len(both_system_files)} files use both systems - "
            f"these need immediate migration!"
        )

    return {
        "old_system": sorted(old_system_files),
        "new_system": sorted(new_system_files),
        "both_systems": sorted(both_system_files),
        "neither": sorted(neither_files),
    }


def generate_migration_report(workspace_root: str, output_file: str | None = None) -> str:
    """Generate detailed migration report for intention systems.

    IMP-INTENT-003: Creates human-readable report with migration recommendations.

    Args:
        workspace_root: Root directory to scan
        output_file: Optional file path to write report (if None, returns string)

    Returns:
        Formatted migration report as string

    Example:
        >>> report = generate_migration_report("/workspace", "migration_report.md")
        >>> print("Report saved to migration_report.md")
    """
    usage = detect_intention_system_usage(workspace_root)

    # Build report
    lines = [
        "# Intention System Migration Report (IMP-INTENT-003)",
        "",
        "## Summary",
        "",
        f"- **Old System (v1)**: {len(usage['old_system'])} files",
        f"- **New System (v2)**: {len(usage['new_system'])} files",
        f"- **Mixed Usage**: {len(usage['both_systems'])} files ⚠️",
        f"- **No Intention Usage**: {len(usage['neither'])} files",
        "",
        "## Migration Priority",
        "",
    ]

    # Critical: Mixed usage files
    if usage["both_systems"]:
        lines.extend(
            [
                "### 🚨 CRITICAL: Mixed Usage (Immediate Action Required)",
                "",
                "These files import both v1 and v2 systems, which can cause conflicts:",
                "",
            ]
        )
        for filepath in usage["both_systems"]:
            lines.append(f"- `{filepath}`")
        lines.extend(
            [
                "",
                "**Action**: Migrate these files to v2 immediately to avoid conflicts.",
                "",
            ]
        )

    # High: Old system files
    if usage["old_system"]:
        lines.extend(
            [
                "### ⚠️ HIGH: Old System (v1) Usage",
                "",
                "These files use only the old intention system:",
                "",
            ]
        )
        for filepath in usage["old_system"]:
            lines.append(f"- `{filepath}`")
        lines.extend(
            [
                "",
                "**Action**: Migrate these files to v2 when convenient. "
                "Old system will be deprecated.",
                "",
            ]
        )

    # Info: New system files (already migrated)
    if usage["new_system"]:
        lines.extend(
            [
                "### ✅ New System (v2) Usage",
                "",
                f"{len(usage['new_system'])} files already using the new system (no action needed).",
                "",
            ]
        )

    # Migration guide
    lines.extend(
        [
            "## Migration Guide",
            "",
            "### Old System (v1) → New System (v2)",
            "",
            "**v1 Schema**:",
            "```python",
            "from autopack.project_intention import ProjectIntentionManager",
            "",
            "manager = ProjectIntentionManager(run_id=run_id)",
            "intention = manager.create_intention(",
            '    raw_input="Build a web scraper",',
            "    intent_facts=[...],",
            "    non_goals=[...],",
            ")",
            "```",
            "",
            "**v2 Schema**:",
            "```python",
            "from autopack.intention_anchor.v2 import IntentionAnchorV2, NorthStarIntention",
            "",
            "intention = IntentionAnchorV2(",
            "    project_id=project_id,",
            "    north_star=NorthStarIntention(",
            "        desired_outcomes=[...],",
            "        non_goals=[...],",
            "    ),",
            "    safety_risk=SafetyRiskIntention(...),",
            "    evidence_verification=EvidenceVerificationIntention(...),",
            ")",
            "```",
            "",
            "### Key Differences",
            "",
            "| v1 Field | v2 Equivalent |",
            "|----------|---------------|",
            "| `intent_anchor` | `north_star.desired_outcomes` |",
            "| `intent_facts` | `north_star.desired_outcomes` |",
            "| `non_goals` | `north_star.non_goals` |",
            "| `acceptance_criteria` | `evidence_verification.verification_gates` |",
            "| `constraints` | `scope_boundaries.*` |",
            "",
            "## Deprecation Timeline",
            "",
            "1. **Phase 1 (Current)**: Both systems coexist, deprecation warnings added",
            "2. **Phase 2 (Next Release)**: Old system marked deprecated, migration guide published",
            "3. **Phase 3 (Future)**: Old system removed after all internal usage migrated",
            "",
            "---",
            "",
            "*Generated by IMP-INTENT-003 migration detector*",
        ]
    )

    report = "\n".join(lines)

    # Write to file if specified
    if output_file:
        output_path = Path(output_file)
        output_path.write_text(report, encoding="utf-8")
        logger.info(f"[IMP-INTENT-003] Migration report written to: {output_file}")

    return report
