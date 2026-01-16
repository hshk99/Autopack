"""Intention system migration utilities.

IMP-INTENT-003: Tools for detecting and migrating from v1 to v2 intention system.

Usage:
    from autopack.intention_anchor.migration import detect_intention_system_usage

    usage_report = detect_intention_system_usage("/path/to/workspace")
    print(f"Old system files: {len(usage_report['old_system'])}")
    print(f"New system files: {len(usage_report['new_system'])}")
    print(f"Mixed usage files: {len(usage_report['both_systems'])}")
"""

from .detector import detect_intention_system_usage, generate_migration_report

__all__ = [
    "detect_intention_system_usage",
    "generate_migration_report",
]
