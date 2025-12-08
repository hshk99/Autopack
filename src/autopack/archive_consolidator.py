"""Archive Consolidator System for Autopack

Automatically maintains consolidated reference documents in the archive folder:
- CONSOLIDATED_DEBUG_AND_ERRORS.md
- CONSOLIDATED_BUILD_HISTORY.md
- CONSOLIDATED_STRATEGIC_ANALYSIS.md
- ARCHIVE_INDEX.md

This module monitors archive files and automatically updates the consolidated
documents when relevant information changes.
"""

import os
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List, Any
import logging

logger = logging.getLogger(__name__)


class ArchiveConsolidator:
    """
    Manages automatic consolidation of archive files.

    Monitors source files and updates consolidated documents when changes occur.
    Similar to DebugJournal but for historical/strategic documentation.
    """

    def __init__(self, project_slug: str = "file-organizer-app-v1", workspace_root: Optional[Path] = None):
        """
        Initialize the archive consolidator.

        Args:
            project_slug: Project identifier (e.g. 'file-organizer-app-v1')
            workspace_root: Root directory for autonomous runs
                           (defaults to .autonomous_runs)
        """
        if workspace_root is None:
            workspace_root = Path.cwd() / ".autonomous_runs"

        self.project_slug = project_slug
        
        if project_slug == "autopack-framework":
            # Special case for framework root
            # Assumes workspace_root is inside the project root (e.g. .autonomous_runs)
            self.project_dir = workspace_root.parent
            self.archive_dir = self.project_dir / "archive"
        else:
            # Standard project in .autonomous_runs
            self.project_dir = workspace_root / project_slug
            self.archive_dir = self.project_dir / "archive"

        # Consolidated files
        self.debug_errors_file = self.archive_dir / "CONSOLIDATED_DEBUG.md"
        self.build_history_file = self.archive_dir / "CONSOLIDATED_BUILD.md"
        self.strategic_analysis_file = self.archive_dir / "CONSOLIDATED_STRATEGY.md"
        self.archive_index_file = self.archive_dir / "ARCHIVE_INDEX.md"

        # Project-level files
        self.readme_file = self.project_dir / "README.md"
        self.learned_rules_file = self.project_dir / "LEARNED_RULES_README.md"

        # Source files to monitor
        self.debug_sources = [
            "DEBUG_JOURNAL.md",
            "ERROR_RECOVERY_INTEGRATION_SUMMARY.md",
            "BUILD_PROGRESS.md",
            "AUTOPACK_DEBUG_HISTORY_AND_PROMPT.md"
        ]

        self.build_sources = [
            "BUILD_PROGRESS.md",
            "FINAL_BUILD_REPORT.md",
            "IMPLEMENTATION_SUMMARY.md",
            "DELEGATION_TO_GPT4O.md"
        ]

        self.strategy_sources = [
            "fileorganizer_final_strategic_review.md",
            "fileorganizer_product_intent_and_features.md",
            "GPT_STRATEGIC_ANALYSIS_PROMPT_V2.md"
        ]

        # Ensure directory exists
        self.archive_dir.mkdir(parents=True, exist_ok=True)

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
        Log a new error to CONSOLIDATED_DEBUG_AND_ERRORS.md.

        This automatically appends to the "Open Issues" section.
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

        self._append_to_section(
            self.debug_errors_file,
            "Open Issues",
            entry
        )
        logger.info(f"[ARCHIVE_CONSOLIDATOR] Logged new error: {error_signature}")

    def log_fix_applied(
        self,
        error_signature: str,
        fix_description: str,
        files_changed: List[str],
        test_run_id: Optional[str] = None,
        result: str = "success"
    ):
        """
        Log a fix that was applied for an error.

        Appends to the existing issue in CONSOLIDATED_DEBUG_AND_ERRORS.md.
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

        self._append_to_issue(
            self.debug_errors_file,
            error_signature,
            fix_entry
        )
        logger.info(f"[ARCHIVE_CONSOLIDATOR] Logged fix for: {error_signature}")

    def mark_issue_resolved(
        self,
        error_signature: str,
        resolution_summary: str,
        verified_run_id: Optional[str] = None,
        prevention_rule: Optional[str] = None
    ):
        """
        Mark an issue as resolved in CONSOLIDATED_DEBUG_AND_ERRORS.md.

        If prevention_rule is provided, adds it to the Prevention Rules section.
        """
        resolution = f"""
**Resolution** ({datetime.now().strftime("%Y-%m-%d")}):
{resolution_summary}

**Verified On Run**: {verified_run_id or "Not verified"}
**Status**: ✅ RESOLVED
"""

        self._append_to_issue(
            self.debug_errors_file,
            error_signature,
            resolution
        )

        # If prevention rule provided, add to Prevention Rules section
        if prevention_rule:
            self._add_prevention_rule(prevention_rule)

        logger.info(f"[ARCHIVE_CONSOLIDATOR] Marked as RESOLVED: {error_signature}")

    def log_build_event(
        self,
        event_type: str,
        week_number: Optional[int] = None,
        description: str = "",
        deliverables: Optional[List[str]] = None,
        token_usage: Optional[Dict[str, int]] = None
    ):
        """
        Log a build event to CONSOLIDATED_BUILD_HISTORY.md.

        Args:
            event_type: "week_complete", "intervention", "escalation", "incident"
            week_number: Week number (for week_complete events)
            description: Event description
            deliverables: List of deliverables (for week_complete)
            token_usage: Dict with builder/auditor/total tokens
        """
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        entry = f"""
### {event_type.replace('_', ' ').title()} - {timestamp}
{description}
"""

        if deliverables:
            entry += "\n**Deliverables**:\n"
            entry += "\n".join(f"- {d}" for d in deliverables)

        if token_usage:
            entry += f"\n**Token Usage**: Builder: {token_usage.get('builder', 0)}, "
            entry += f"Auditor: {token_usage.get('auditor', 0)}, "
            entry += f"Total: {token_usage.get('total', 0)}"

        entry += "\n\n---\n"

        # Append to appropriate section based on event type
        section_map = {
            "week_complete": "Week-by-Week Build Timeline",
            "intervention": "Manual Interventions Log",
            "escalation": "Auditor Escalations",
            "incident": "Critical Incidents and Resolutions"
        }

        section = section_map.get(event_type, "Run History")
        self._append_to_section(
            self.build_history_file,
            section,
            entry
        )
        logger.info(f"[ARCHIVE_CONSOLIDATOR] Logged build event: {event_type}")

    def log_strategic_update(
        self,
        update_type: str,
        content: str
    ):
        """
        Log a strategic update to CONSOLIDATED_STRATEGIC_ANALYSIS.md.

        Args:
            update_type: "market_analysis", "competitive_landscape", "go_no_go", etc.
            content: Update content
        """
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        entry = f"""
### Update - {timestamp}
**Type**: {update_type}

{content}

---
"""

        # Map update type to section
        section_map = {
            "market_analysis": "Market Analysis",
            "competitive_landscape": "Competitive Landscape",
            "go_no_go": "GO/NO-GO Decision Framework",
            "pricing": "Pricing Strategy",
            "risk": "Risk Analysis and Mitigation"
        }

        section = section_map.get(update_type, "Strategic Updates")
        self._append_to_section(
            self.strategic_analysis_file,
            section,
            entry
        )
        logger.info(f"[ARCHIVE_CONSOLIDATOR] Logged strategic update: {update_type}")

    def update_archive_index(self):
        """
        Refresh the ARCHIVE_INDEX.md with current file mapping.

        This scans the archive directory and updates the index to reflect
        what files have been consolidated and where information can be found.
        """
        if not self.archive_index_file.exists():
            logger.warning(f"ARCHIVE_INDEX.md not found at {self.archive_index_file}")
            return

        # Get list of all archive files
        archive_files = sorted([f.name for f in self.archive_dir.glob("*.md")
                               if f.name != "ARCHIVE_INDEX.md" and not f.name.startswith("CONSOLIDATED_")])

        # Update the "Remaining Archive Files" section
        remaining_section = f"""
### Still Relevant (Not Consolidated)
These files contain unique information not yet merged:

"""
        for fname in archive_files:
            remaining_section += f"- {fname}\n"

        remaining_section += f"""
**Last Updated**: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

---
"""

        # Replace the section in ARCHIVE_INDEX.md
        if self.archive_index_file.exists():
            content = self.archive_index_file.read_text(encoding='utf-8')

            # Find and replace "Remaining Archive Files" section
            section_pattern = r"## Remaining Archive Files\n(.*?)(?=\n##|$)"
            import re
            if re.search(section_pattern, content, re.DOTALL):
                updated = re.sub(
                    section_pattern,
                    f"## Remaining Archive Files\n{remaining_section}",
                    content,
                    flags=re.DOTALL
                )
                self.archive_index_file.write_text(updated, encoding='utf-8')
                logger.info("[ARCHIVE_CONSOLIDATOR] Updated ARCHIVE_INDEX.md")

    def add_learned_rule(
        self,
        rule: str,
        category: str = "General",
        context: Optional[str] = None
    ):
        """
        Add a learned rule/best practice to LEARNED_RULES_README.md.

        This is for NEVER/ALWAYS guidelines, prevention rules, and best practices
        learned from past bugs or successful patterns.

        Args:
            rule: The rule text (e.g., "NEVER reuse old runs for testing fixes")
            category: Rule category (e.g., "Testing", "Coding", "Architecture")
            context: Optional context explaining why this rule exists
        """
        if not self.learned_rules_file.exists():
            self._initialize_learned_rules()

        timestamp = datetime.now().strftime("%Y-%m-%d")

        entry = f"""
#### {rule}
**Category**: {category}
**Added**: {timestamp}

"""
        if context:
            entry += f"""**Context**: {context}

"""

        entry += "---\n"

        # Add to the appropriate category section
        self._append_to_section(
            self.learned_rules_file,
            f"{category} Rules",
            entry
        )
        logger.info(f"[ARCHIVE_CONSOLIDATOR] Added learned rule: {rule[:50]}...")

    def update_readme_section(
        self,
        section_name: str,
        content: str,
        mode: str = "append"
    ):
        """
        Update a section in README.md.

        This is for project overview, setup instructions, architecture, etc.

        Args:
            section_name: Section to update (e.g., "Features", "Installation")
            content: Content to add or replace
            mode: "append" to add to section, "replace" to replace entire section
        """
        if not self.readme_file.exists():
            logger.warning(f"README.md not found at {self.readme_file}")
            return

        if mode == "append":
            self._append_to_section(
                self.readme_file,
                section_name,
                content
            )
        elif mode == "replace":
            self._replace_section(
                self.readme_file,
                section_name,
                content
            )

        logger.info(f"[ARCHIVE_CONSOLIDATOR] Updated README.md section: {section_name}")

    def log_feature_completion(
        self,
        feature_name: str,
        description: str,
        files_added: Optional[List[str]] = None
    ):
        """
        Log a completed feature to README.md (Features section).

        Intelligently routes to README.md instead of build history when it's
        a user-facing feature description.

        Args:
            feature_name: Feature name
            description: Brief description
            files_added: Optional list of files implementing this feature
        """
        entry = f"""
- **{feature_name}**: {description}
"""
        if files_added:
            entry += f"  (Files: {', '.join(files_added)})\n"

        self._append_to_section(
            self.readme_file,
            "Features",
            entry
        )
        logger.info(f"[ARCHIVE_CONSOLIDATOR] Logged feature: {feature_name}")

    def _add_prevention_rule(self, rule: str):
        """Add a new prevention rule to CONSOLIDATED_DEBUG_AND_ERRORS.md"""
        if not self.debug_errors_file.exists():
            return

        content = self.debug_errors_file.read_text(encoding='utf-8')

        # Find Prevention Rules section
        section_marker = "## Prevention Rules"
        if section_marker in content:
            # Count existing rules
            import re
            existing_rules = re.findall(r'^\d+\.', content, re.MULTILINE)
            next_number = len(existing_rules) + 1

            new_rule = f"{next_number}. {rule}\n"

            # Insert after section header
            parts = content.split(section_marker)
            if len(parts) >= 2:
                # Find the first line after section header
                lines = parts[1].split('\n')
                # Insert after first blank line
                for i, line in enumerate(lines):
                    if line.strip() == "" and i > 0:
                        lines.insert(i + 1, new_rule)
                        break

                updated = parts[0] + section_marker + '\n'.join(lines)
                self.debug_errors_file.write_text(updated, encoding='utf-8')
                logger.info(f"[ARCHIVE_CONSOLIDATOR] Added prevention rule #{next_number}")

    def _append_to_section(self, file_path: Path, section_name: str, content: str):
        """Append content to a specific section of a markdown file"""
        if not file_path.exists():
            logger.warning(f"File not found: {file_path}")
            return

        file_content = file_path.read_text(encoding='utf-8')

        # Find the section and append
        section_marker = f"## {section_name}"
        if section_marker in file_content:
            # Find the next section or end of file
            parts = file_content.split(section_marker)
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

                file_path.write_text(updated, encoding='utf-8')
                logger.debug(f"Appended to section '{section_name}' in {file_path.name}")

    def _append_to_issue(self, file_path: Path, error_signature: str, content: str):
        """Append content to a specific issue entry"""
        if not file_path.exists():
            logger.warning(f"File not found: {file_path}")
            return

        file_content = file_path.read_text(encoding='utf-8')

        # Find the issue header
        issue_marker = f"### {error_signature}"
        if issue_marker in file_content:
            # Find the next issue or section
            parts = file_content.split(issue_marker)
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

                file_path.write_text(updated, encoding='utf-8')
                logger.debug(f"Appended to issue '{error_signature}' in {file_path.name}")

    def _replace_section(self, file_path: Path, section_name: str, content: str):
        """Replace an entire section with new content"""
        if not file_path.exists():
            logger.warning(f"File not found: {file_path}")
            return

        file_content = file_path.read_text(encoding='utf-8')

        # Find and replace the section
        section_marker = f"## {section_name}"
        if section_marker in file_content:
            parts = file_content.split(section_marker)
            if len(parts) >= 2:
                # Find next section
                next_section_idx = parts[1].find("\n## ")
                if next_section_idx != -1:
                    # Replace section content, keep next section
                    updated = (
                        parts[0] + section_marker + "\n" + content +
                        parts[1][next_section_idx:]
                    )
                else:
                    # Replace section content to end of file
                    updated = parts[0] + section_marker + "\n" + content

                file_path.write_text(updated, encoding='utf-8')
                logger.debug(f"Replaced section '{section_name}' in {file_path.name}")

    def _initialize_learned_rules(self):
        """Create the initial LEARNED_RULES_README.md file"""
        header = f"""# Learned Rules and Best Practices - {self.project_slug}

**Purpose**: This document tracks NEVER/ALWAYS guidelines, prevention rules, and best practices learned from past bugs, successes, and failures.

These rules are extracted from real experience and should be treated as **mandatory guidelines** for all future work.

---

## How to Use This Document

**Before starting any task:**
1. Read relevant rules in the category you're working on
2. Check for NEVER/ALWAYS patterns that apply
3. Follow these rules strictly - they prevent known pitfalls

**When you discover a new pattern:**
1. Add it immediately using `add_learned_rule()`
2. Include context explaining WHY this rule exists
3. Categorize appropriately (Testing, Coding, Architecture, etc.)

---

## Testing Rules

_(Rules about testing practices and patterns)_

---

## Coding Rules

_(Rules about coding patterns and anti-patterns)_

---

## Architecture Rules

_(Rules about architectural decisions and patterns)_

---

## Deployment Rules

_(Rules about deployment and operations)_

---

## General Rules

_(Cross-cutting rules that don't fit other categories)_

---

**Last Updated**: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
**Maintained by**: Autopack Archive Consolidator
"""

        self.learned_rules_file.write_text(header, encoding='utf-8')
        logger.info(f"[ARCHIVE_CONSOLIDATOR] Created LEARNED_RULES_README.md at {self.learned_rules_file}")


# Global singleton for easy access
_consolidator_instance: Optional[ArchiveConsolidator] = None


def get_consolidator(project_slug: str = "file-organizer-app-v1") -> ArchiveConsolidator:
    """Get or create the global archive consolidator instance"""
    global _consolidator_instance
    if _consolidator_instance is None or _consolidator_instance.project_slug != project_slug:
        _consolidator_instance = ArchiveConsolidator(project_slug)
    return _consolidator_instance


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
    """Log a new error to consolidated debug file"""
    consolidator = get_consolidator(project_slug)
    consolidator.log_error_event(
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
    files_changed: List[str],
    test_run_id: Optional[str] = None,
    result: str = "success",
    project_slug: str = "file-organizer-app-v1",
    run_id: Optional[str] = None,
    phase_id: Optional[str] = None,
    outcome: Optional[str] = None,
):
    """Log a fix that was applied"""
    consolidator = get_consolidator(project_slug)
    consolidator.log_fix_applied(
        error_signature=error_signature,
        fix_description=fix_description,
        files_changed=files_changed or [],
        test_run_id=test_run_id,
        result=result,
    )


def mark_resolved(
    error_signature: str,
    resolution_summary: str,
    verified_run_id: Optional[str] = None,
    prevention_rule: Optional[str] = None,
    project_slug: str = "file-organizer-app-v1"
):
    """Mark an issue as resolved"""
    consolidator = get_consolidator(project_slug)
    consolidator.mark_issue_resolved(
        error_signature=error_signature,
        resolution_summary=resolution_summary,
        verified_run_id=verified_run_id,
        prevention_rule=prevention_rule
    )


def log_build_event(
    event_type: str,
    week_number: Optional[int] = None,
    description: str = "",
    deliverables: Optional[List[str]] = None,
    token_usage: Optional[Dict[str, int]] = None,
    project_slug: str = "file-organizer-app-v1"
):
    """Log a build event to consolidated build history"""
    consolidator = get_consolidator(project_slug)
    consolidator.log_build_event(
        event_type=event_type,
        week_number=week_number,
        description=description,
        deliverables=deliverables,
        token_usage=token_usage
    )


def log_strategic_update(
    update_type: str,
    content: str,
    project_slug: str = "file-organizer-app-v1"
):
    """Log a strategic update"""
    consolidator = get_consolidator(project_slug)
    consolidator.log_strategic_update(
        update_type=update_type,
        content=content
    )


def update_archive_index(project_slug: str = "file-organizer-app-v1"):
    """Update the archive index file"""
    consolidator = get_consolidator(project_slug)
    consolidator.update_archive_index()


def add_learned_rule(
    rule: str,
    category: str = "General",
    context: Optional[str] = None,
    project_slug: str = "file-organizer-app-v1"
):
    """Add a learned rule/best practice to LEARNED_RULES_README.md"""
    consolidator = get_consolidator(project_slug)
    consolidator.add_learned_rule(
        rule=rule,
        category=category,
        context=context
    )


def update_readme(
    section_name: str,
    content: str,
    mode: str = "append",
    project_slug: str = "file-organizer-app-v1"
):
    """Update a section in README.md"""
    consolidator = get_consolidator(project_slug)
    consolidator.update_readme_section(
        section_name=section_name,
        content=content,
        mode=mode
    )


def log_feature(
    feature_name: str,
    description: str,
    files_added: Optional[List[str]] = None,
    project_slug: str = "file-organizer-app-v1"
):
    """Log a completed feature to README.md"""
    consolidator = get_consolidator(project_slug)
    consolidator.log_feature_completion(
        feature_name=feature_name,
        description=description,
        files_added=files_added
    )
