"""Debug Journal System for Autopack

Legacy module that now redirects to archive_consolidator.py.
Maintains backward compatibility for imports while using the new consolidated documentation system.
"""

from typing import List, Optional

from autopack.archive_consolidator import get_consolidator
from autopack.archive_consolidator import log_error as _log_error
from autopack.archive_consolidator import log_fix as _log_fix
from autopack.archive_consolidator import mark_resolved as _mark_resolved


# Re-export functions for backward compatibility
def log_error(
    error_signature: str,
    symptom: str,
    run_id: Optional[str] = None,
    phase_id: Optional[str] = None,
    suspected_cause: Optional[str] = None,
    priority: str = "MEDIUM",
    project_slug: str = "file-organizer-app-v1",
):
    """Log a new error to CONSOLIDATED_DEBUG.md (via archive_consolidator)"""
    _log_error(
        error_signature=error_signature,
        symptom=symptom,
        run_id=run_id,
        phase_id=phase_id,
        suspected_cause=suspected_cause,
        priority=priority,
        project_slug=project_slug,
    )


def log_fix(
    error_signature: str,
    fix_description: str,
    files_changed: Optional[List[str]] = None,
    test_run_id: Optional[str] = None,
    result: str = "success",
    project_slug: str = "file-organizer-app-v1",
    run_id: Optional[str] = None,
    phase_id: Optional[str] = None,
    outcome: Optional[str] = None,
):
    """Log a fix to CONSOLIDATED_DEBUG.md (via archive_consolidator)"""
    _log_fix(
        error_signature=error_signature,
        fix_description=fix_description,
        files_changed=files_changed or [],
        test_run_id=test_run_id,
        result=result,
        project_slug=project_slug,
        run_id=run_id,
        phase_id=phase_id,
        outcome=outcome,
    )


def mark_resolved(
    error_signature: str,
    resolution_summary: str,
    verified_run_id: Optional[str] = None,
    prevention_rule: Optional[str] = None,
    project_slug: str = "file-organizer-app-v1",
):
    """Mark an issue as resolved in CONSOLIDATED_DEBUG.md (via archive_consolidator)"""
    _mark_resolved(
        error_signature=error_signature,
        resolution_summary=resolution_summary,
        verified_run_id=verified_run_id,
        prevention_rule=prevention_rule,
        project_slug=project_slug,
    )


def log_escalation(
    error_category: str,
    error_count: int,
    threshold: int,
    reason: str,
    run_id: Optional[str] = None,
    phase_id: Optional[str] = None,
    project_slug: str = "file-organizer-app-v1",
):
    """
    Log an escalation event when error threshold is exceeded.

    This indicates the self-troubleshoot system has determined manual
    intervention is needed.
    """
    consolidator = get_consolidator(project_slug)
    escalation_signature = f"ESCALATION: {error_category} ({error_count}/{threshold})"

    # Log as a high-priority error that requires human attention
    consolidator.log_error_event(
        error_signature=escalation_signature,
        symptom=f"Self-troubleshoot escalation: {reason}",
        run_id=run_id,
        phase_id=phase_id,
        suspected_cause=f"Error '{error_category}' occurred {error_count} times (threshold: {threshold})",
        priority="CRITICAL",
    )

    # Also log to standard logger for immediate visibility
    import logging

    logger = logging.getLogger(__name__)
    logger.critical(
        f"[ESCALATION] {error_category} - {reason} "
        f"(occurred {error_count} times, threshold: {threshold})"
    )


class DebugJournal:
    """Legacy DebugJournal class - wrapper around ArchiveConsolidator"""

    def __init__(self, project_slug: str, workspace_root=None):
        self.consolidator = get_consolidator(project_slug)
        self.project_slug = project_slug

    def log_error(self, *args, **kwargs):
        self.consolidator.log_error_event(*args, **kwargs)

    # Add other methods if needed, but functions are primary interface
