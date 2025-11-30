"""Debug Journal System for Autopack

Legacy module that now redirects to archive_consolidator.py.
Maintains backward compatibility for imports while using the new consolidated documentation system.
"""

from typing import Optional, List
from autopack.archive_consolidator import (
    log_error as _log_error,
    log_fix as _log_fix,
    mark_resolved as _mark_resolved,
    get_consolidator
)

# Re-export functions for backward compatibility
def log_error(
    error_signature: str,
    symptom: str,
    run_id: Optional[str] = None,
    phase_id: Optional[str] = None,
    suspected_cause: Optional[str] = None,
    priority: str = "MEDIUM",
    project_slug: str = "file-organizer-app-v1"
):
    """Log a new error to CONSOLIDATED_DEBUG.md (via archive_consolidator)"""
    _log_error(
        error_signature=error_signature,
        symptom=symptom,
        run_id=run_id,
        phase_id=phase_id,
        suspected_cause=suspected_cause,
        priority=priority,
        project_slug=project_slug
    )

def log_fix(
    error_signature: str,
    fix_description: str,
    files_changed: List[str],
    test_run_id: Optional[str] = None,
    result: str = "success",
    project_slug: str = "file-organizer-app-v1"
):
    """Log a fix to CONSOLIDATED_DEBUG.md (via archive_consolidator)"""
    _log_fix(
        error_signature=error_signature,
        fix_description=fix_description,
        files_changed=files_changed,
        test_run_id=test_run_id,
        result=result,
        project_slug=project_slug
    )

def mark_resolved(
    error_signature: str,
    resolution_summary: str,
    verified_run_id: Optional[str] = None,
    prevention_rule: Optional[str] = None,
    project_slug: str = "file-organizer-app-v1"
):
    """Mark an issue as resolved in CONSOLIDATED_DEBUG.md (via archive_consolidator)"""
    _mark_resolved(
        error_signature=error_signature,
        resolution_summary=resolution_summary,
        verified_run_id=verified_run_id,
        prevention_rule=prevention_rule,
        project_slug=project_slug
    )

class DebugJournal:
    """Legacy DebugJournal class - wrapper around ArchiveConsolidator"""
    
    def __init__(self, project_slug: str, workspace_root=None):
        self.consolidator = get_consolidator(project_slug)
        self.project_slug = project_slug
    
    def log_error(self, *args, **kwargs):
        self.consolidator.log_error_event(*args, **kwargs)
        
    # Add other methods if needed, but functions are primary interface
