"""Debug Journal System for Autopack

Provides persistent error tracking and fix documentation to prevent
re-trying failed approaches across sessions.

This module implements the system described in ref5.md to solve the
"regression" problem where resolved issues keep reappearing.
"""

import os
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any
from enum import Enum


class IssueStatus(Enum):
    """Status of a debug journal issue"""
    OPEN = "open"
    RESOLVED = "resolved"
    SUPERSEDED = "superseded"


class DebugJournal:
    """
    Manages the persistent debug journal for a project.

    The journal is stored as a Markdown file that tracks:
    - Error signatures and symptoms
    - Root causes and investigations
    - Actions taken and results
    - Status (open/resolved/superseded)
    """

    def __init__(self, project_slug: str, workspace_root: Optional[Path] = None):
        """
        Initialize the debug journal.

        Args:
            project_slug: Project identifier (e.g. 'file-organizer-app-v1')
            workspace_root: Root directory for autonomous runs
                           (defaults to .autonomous_runs)
        """
        if workspace_root is None:
            workspace_root = Path.cwd() / ".autonomous_runs"

        self.project_slug = project_slug
        self.journal_dir = workspace_root / project_slug
        self.journal_path = self.journal_dir / "DEBUG_JOURNAL.md"

        # Ensure directory exists
        self.journal_dir.mkdir(parents=True, exist_ok=True)

        # Create journal if it doesn't exist
        if not self.journal_path.exists():
            self._initialize_journal()

    def _initialize_journal(self):
        """Create the initial journal file with instructions"""
        header = """# Debug Journal - {project_slug}

**Purpose**: This journal tracks all errors, fixes, and testing results for {project_slug} autonomous runs. It prevents repetitive debugging by maintaining a single source of truth for what has been tried and what worked.

## HOW TO USE THIS JOURNAL

**For Cursor/Autopack agents starting a new debugging session:**

1. **READ THIS FILE FIRST** before attempting any fixes
2. Check the "Current Open Issues" section to see what's unresolved
3. Check the "Resolved Issues" section to avoid re-trying failed approaches
4. Pick the highest-priority open issue to work on
5. **UPDATE THIS JOURNAL** with new findings before ending the session
6. When testing a fix, **ALWAYS CREATE A NEW RUN** - never reuse old runs with stale state

---

## Current Open Issues

_(No open issues yet)_

---

## Resolved Issues

_(No resolved issues yet)_

---

## Critical Lessons

### Never Reuse Old Runs for Testing New Fixes

**Why This Matters**:

When you fix a bug in the code and then test it on an **old run** (one created before the fix), you're often testing against:
- Old phase definitions that may not exercise the new code path
- Stale phase states (EXECUTING phases that block new work)
- Cached or pre-computed results
- Old configuration that doesn't match current code

**Result**: The fix appears not to work, leading to wasted debugging cycles.

**Protocol Going Forward**:

1. **After implementing a fix**: Create a NEW run with a new run_id
2. **Fresh workspace**: Use a clean checkout or ensure workspace reflects latest code
3. **Clear state**: No phases in EXECUTING, all start from QUEUED
4. **Document the test**: Record in this journal which run_id was used to verify which fix

**Example**:
- ❌ BAD: Fix slice error, test on `fileorg-phase2-beta` (created days ago)
- ✅ GOOD: Fix slice error, create `fileorg-test-slice-fix-2025-11-29`, test on fresh run

---

## Run History

_(Run history will be recorded here as runs are executed)_

---

## Next Session Checklist

When starting a new debugging session:

- [ ] Read this DEBUG_JOURNAL.md file completely
- [ ] Check "Current Open Issues" for highest priority
- [ ] Review "Resolved Issues" to avoid repeating fixes
- [ ] If testing a fix: CREATE A NEW RUN (don't reuse old ones)
- [ ] Update this journal with findings before ending session
- [ ] Mark issues as RESOLVED only after verification on a FRESH run

---

## References

- **System Design**: `ref5.md` (Debug Journal System specification)

""".format(project_slug=self.project_slug)

        self.journal_path.write_text(header, encoding='utf-8')

    def log_error_event(
        self,
        error_signature: str,
        symptom: str,
        run_id: Optional[str] = None,
        phase_id: Optional[str] = None,
        suspected_cause: Optional[str] = None,
        priority: str = "MEDIUM"
    ):
        """
        Log a new error event to the journal.

        Args:
            error_signature: Short title for the error (e.g. "Unicode emoji crash")
            symptom: Log snippet or error message
            run_id: Run identifier where error occurred
            phase_id: Phase identifier where error occurred
            suspected_cause: Initial hypothesis about root cause
            priority: CRITICAL, HIGH, MEDIUM, or LOW
        """
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        entry = f"""
### {error_signature}
**Status**: OPEN
**Priority**: {priority}
**First Observed**: {datetime.now().strftime("%Y-%m-%d")}
**Run ID**: {run_id or "N/A"}
**Phase ID**: {phase_id or "N/A"}

**Symptom**:
```
{symptom}
```

**Suspected Root Cause**:
{suspected_cause or "_To be investigated_"}

**Actions Taken**:
- None yet - just discovered

**Next Steps**:
1. Investigate root cause
2. Implement fix
3. Test on a FRESH run (not reusing old run)

---
"""

        self._append_to_section("Current Open Issues", entry)
        print(f"[DEBUG_JOURNAL] Logged new error: {error_signature}")

    def log_fix_applied(
        self,
        error_signature: str,
        fix_description: str,
        files_changed: list,
        test_run_id: Optional[str] = None,
        result: str = "success"
    ):
        """
        Log a fix that was applied for an error.

        Args:
            error_signature: Error title (must match existing entry)
            fix_description: Description of what was fixed
            files_changed: List of files that were modified
            test_run_id: Run ID used to verify the fix
            result: "success", "partial", or "failed"
        """
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        fix_entry = f"""
**Fix Applied** ({timestamp}):
{fix_description}

**Files Changed**:
{chr(10).join(f"- {f}" for f in files_changed)}

**Test Run**: {test_run_id or "Not tested yet"}
**Result**: {result}
"""

        self._append_to_issue(error_signature, fix_entry)
        print(f"[DEBUG_JOURNAL] Logged fix for: {error_signature}")

    def mark_issue_resolved(
        self,
        error_signature: str,
        resolution_summary: str,
        verified_run_id: Optional[str] = None
    ):
        """
        Mark an issue as resolved and move it to the Resolved Issues section.

        Args:
            error_signature: Error title (must match existing entry)
            resolution_summary: Summary of how it was fixed
            verified_run_id: Run ID that confirmed the fix works
        """
        # Move from Open to Resolved
        # (Implementation would parse MD, find issue, move sections)
        # For now, just append a resolution note

        resolution = f"""
**Resolution** ({datetime.now().strftime("%Y-%m-%d")}):
{resolution_summary}

**Verified On Run**: {verified_run_id or "Not verified"}
**Status**: ✅ RESOLVED
"""

        self._append_to_issue(error_signature, resolution)
        print(f"[DEBUG_JOURNAL] Marked as RESOLVED: {error_signature}")

    def _append_to_section(self, section_name: str, content: str):
        """Append content to a specific section of the journal"""
        # Read current journal
        if not self.journal_path.exists():
            self._initialize_journal()

        journal_text = self.journal_path.read_text(encoding='utf-8')

        # Find the section and append
        section_marker = f"## {section_name}"
        if section_marker in journal_text:
            # Find the next section or end of file
            parts = journal_text.split(section_marker)
            if len(parts) >= 2:
                # Find next section
                next_section_idx = parts[1].find("\n## ")
                if next_section_idx != -1:
                    # Insert before next section
                    updated = (
                        parts[0] + section_marker +
                        parts[1][:next_section_idx] + "\n" + content +
                        parts[1][next_section_idx:]
                    )
                else:
                    # Append at end
                    updated = parts[0] + section_marker + parts[1] + "\n" + content

                self.journal_path.write_text(updated, encoding='utf-8')

    def _append_to_issue(self, error_signature: str, content: str):
        """Append content to a specific issue entry"""
        if not self.journal_path.exists():
            return

        journal_text = self.journal_path.read_text(encoding='utf-8')

        # Find the issue header
        issue_marker = f"### {error_signature}"
        if issue_marker in journal_text:
            # Find the next issue or section
            parts = journal_text.split(issue_marker)
            if len(parts) >= 2:
                # Find next issue/section
                next_marker_idx = parts[1].find("\n###")
                if next_marker_idx == -1:
                    next_marker_idx = parts[1].find("\n---")

                if next_marker_idx != -1:
                    updated = (
                        parts[0] + issue_marker +
                        parts[1][:next_marker_idx] + "\n" + content +
                        parts[1][next_marker_idx:]
                    )
                else:
                    updated = parts[0] + issue_marker + parts[1] + "\n" + content

                self.journal_path.write_text(updated, encoding='utf-8')


# Global singleton for easy access
_journal_instance: Optional[DebugJournal] = None


def get_journal(project_slug: str = "file-organizer-app-v1") -> DebugJournal:
    """Get or create the global debug journal instance"""
    global _journal_instance
    if _journal_instance is None or _journal_instance.project_slug != project_slug:
        _journal_instance = DebugJournal(project_slug)
    return _journal_instance


# Convenience functions for easy use
def log_error(
    error_signature: str,
    symptom: str,
    run_id: Optional[str] = None,
    phase_id: Optional[str] = None,
    suspected_cause: Optional[str] = None,
    priority: str = "MEDIUM",
    project_slug: str = "file-organizer-app-v1"
):
    """
    Log a new error to the debug journal.

    Convenience wrapper around DebugJournal.log_error_event()
    """
    journal = get_journal(project_slug)
    journal.log_error_event(
        error_signature=error_signature,
        symptom=symptom,
        run_id=run_id,
        phase_id=phase_id,
        suspected_cause=suspected_cause,
        priority=priority
    )


def log_fix(
    error_signature: str,
    fix_description: str,
    files_changed: list,
    test_run_id: Optional[str] = None,
    result: str = "success",
    project_slug: str = "file-organizer-app-v1"
):
    """
    Log a fix that was applied.

    Convenience wrapper around DebugJournal.log_fix_applied()
    """
    journal = get_journal(project_slug)
    journal.log_fix_applied(
        error_signature=error_signature,
        fix_description=fix_description,
        files_changed=files_changed,
        test_run_id=test_run_id,
        result=result
    )


def mark_resolved(
    error_signature: str,
    resolution_summary: str,
    verified_run_id: Optional[str] = None,
    project_slug: str = "file-organizer-app-v1"
):
    """
    Mark an issue as resolved.

    Convenience wrapper around DebugJournal.mark_issue_resolved()
    """
    journal = get_journal(project_slug)
    journal.mark_issue_resolved(
        error_signature=error_signature,
        resolution_summary=resolution_summary,
        verified_run_id=verified_run_id
    )
