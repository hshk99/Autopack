"""Journal Reader Module

Reads the DEBUG_JOURNAL.md to extract prevention rules from resolved issues.
These rules are then injected into Builder/Auditor prompts to prevent recurring bugs.

This module implements Phase 1.1-1.3 of the Debug Journal System (ref5.md).
"""

import re
from pathlib import Path
from typing import List, Dict, Optional
import logging

logger = logging.getLogger(__name__)


def get_prevention_rules(project_slug: str = "file-organizer-app-v1") -> List[str]:
    """
    Extract prevention rules from resolved issues in DEBUG_JOURNAL.md.

    Prevention rules are patterns that the LLM should follow to avoid
    previously fixed bugs. They are extracted from RESOLVED issues marked
    with specific tags.

    Args:
        project_slug: Project identifier (default: "file-organizer-app-v1")

    Returns:
        List of prevention rule strings to inject into LLM prompts

    Example:
        rules = get_prevention_rules()
        for rule in rules:
            print(f"PREVENTION RULE: {rule}")
    """
    journal_path = Path.cwd() / ".autonomous_runs" / project_slug / "archive" / "CONSOLIDATED_DEBUG.md"

    if not journal_path.exists():
        # Fallback to old path if new one doesn't exist
        old_path = Path.cwd() / ".autonomous_runs" / project_slug / "DEBUG_JOURNAL.md"
        if old_path.exists():
            journal_path = old_path
        else:
            logger.warning(f"CONSOLIDATED_DEBUG.md not found at {journal_path}")
            return []

    try:
        journal_content = journal_path.read_text(encoding='utf-8')
    except Exception as e:
        logger.error(f"Failed to read DEBUG_JOURNAL.md: {e}")
        return []

    # Extract prevention rules from resolved issues
    rules = []

    # Parse resolved issues section
    resolved_section = _extract_section(journal_content, "Resolved Issues")
    if not resolved_section:
        logger.debug("No 'Resolved Issues' section found in DEBUG_JOURNAL.md")
        return []

    # Find all resolved issues
    issues = _parse_resolved_issues(resolved_section)

    for issue in issues:
        # Extract prevention rules from each issue
        issue_rules = _extract_prevention_rules_from_issue(issue)
        rules.extend(issue_rules)

    logger.info(f"Extracted {len(rules)} prevention rules from DEBUG_JOURNAL.md")
    return rules


def _extract_section(content: str, section_name: str) -> Optional[str]:
    """Extract a markdown section by name"""
    section_pattern = rf"## {re.escape(section_name)}\n(.*?)(?=\n##|$)"
    match = re.search(section_pattern, content, re.DOTALL)
    return match.group(1).strip() if match else None


def _parse_resolved_issues(resolved_section: str) -> List[Dict[str, str]]:
    """
    Parse resolved issues into structured data.

    Returns list of dicts with keys: title, status, root_cause, fix_applied, resolution
    """
    issues = []

    # Split by issue headers (### Issue Name)
    issue_blocks = re.split(r'\n### ', resolved_section)

    for block in issue_blocks:
        if not block.strip():
            continue

        # Extract issue title (first line)
        lines = block.split('\n')
        title = lines[0].strip()

        issue_data = {
            'title': title,
            'content': block
        }

        # Only include if marked as RESOLVED
        if '✅ RESOLVED' in block or 'Status**: ✅ RESOLVED' in block:
            issues.append(issue_data)

    return issues


def _extract_prevention_rules_from_issue(issue: Dict[str, str]) -> List[str]:
    """
    Extract prevention rules from a resolved issue.

    Prevention rules can be:
    1. Explicitly tagged with **Prevention Rule**: or **NEVER**:
    2. Derived from **Root Cause** and **Fix Applied** sections
    3. General patterns from **Resolution** summaries
    """
    rules = []
    content = issue['content']
    title = issue['title']

    # 1. Look for explicit prevention rules
    explicit_patterns = [
        r'\*\*Prevention Rule\*\*:?\s*(.+?)(?=\n\n|\*\*|$)',
        r'NEVER\s+(.+?)(?=\n|$)',
        r'ALWAYS\s+(.+?)(?=\n|$)',
    ]

    for pattern in explicit_patterns:
        matches = re.findall(pattern, content, re.DOTALL)
        for match in matches:
            rule = match.strip()
            if rule and len(rule) > 10:  # Filter out too-short matches
                rules.append(rule)

    # 2. Derive rules from Root Cause + Fix Applied
    root_cause = _extract_field(content, "Root Cause")
    fix_applied = _extract_field(content, "Fix Applied")

    if root_cause and fix_applied:
        # Create a prevention rule from the pattern
        rule = _synthesize_rule_from_fix(title, root_cause, fix_applied)
        if rule:
            rules.append(rule)

    # 3. Extract rules from Resolution summary
    resolution = _extract_field(content, "Resolution")
    if resolution and "NEVER" in resolution.upper():
        # Extract NEVER statements
        never_matches = re.findall(r'NEVER\s+(.+?)(?=\n|\.)', resolution, re.IGNORECASE)
        rules.extend([m.strip() for m in never_matches if len(m.strip()) > 10])

    return rules


def _extract_field(content: str, field_name: str) -> Optional[str]:
    """Extract a field like **Root Cause**: or **Fix Applied**:"""
    pattern = rf'\*\*{re.escape(field_name)}\*\*:?\s*(.+?)(?=\n\n|\*\*|$)'
    match = re.search(pattern, content, re.DOTALL)
    return match.group(1).strip() if match else None


def _synthesize_rule_from_fix(title: str, root_cause: str, fix_applied: str) -> Optional[str]:
    """
    Synthesize a prevention rule from issue title + root cause + fix.

    Example:
        Title: "Slice Error in Anthropic Builder"
        Root Cause: "file_context was wrapped in {'existing_files': {...}}"
        Fix: "files = file_context.get('existing_files', file_context)"

        Rule: "NEVER assume file_context is unwrapped - always use .get('existing_files', file_context)"
    """

    # Common patterns we can synthesize from
    synthesis_patterns = [
        # Pattern: Dict wrapping issues
        (r'wrapped in.*{.*existing_files',
         "NEVER assume file_context is a plain dict - always use .get('existing_files', file_context) to handle both wrapped and unwrapped formats"),

        # Pattern: API key dependency
        (r'unconditional import.*OpenAI',
         "NEVER import OpenAI clients unconditionally - wrap in try/except to support Anthropic-only, OpenAI-only, or both configurations"),

        # Pattern: Unicode encoding
        (r'charmap.*emoji|unicode.*encoding',
         "ALWAYS set PYTHONUTF8=1 environment variable on Windows to prevent Unicode encoding errors"),

        # Pattern: Patch truncation
        (r'patch.*truncat|patch.*corrupt|literal.*\.\.\.',
         "NEVER use literal `...` to skip code in patches - always include full file content or use explicit markers"),
    ]

    combined_text = f"{title} {root_cause} {fix_applied}".lower()

    for pattern, rule in synthesis_patterns:
        if re.search(pattern, combined_text, re.IGNORECASE):
            return rule

    return None


def get_startup_checks(project_slug: str = "file-organizer-app-v1") -> List[Dict[str, any]]:
    """
    Extract startup checks that should be performed proactively.

    Returns list of check configurations like:
    [
        {
            "name": "Windows Unicode Fix",
            "check": lambda: os.environ.get('PYTHONUTF8') == '1',
            "fix": lambda: os.environ.update({'PYTHONUTF8': '1'}),
            "priority": "HIGH"
        }
    ]
    """
    import os
    import platform

    checks = []

    # Check 1: Windows Unicode fix (from Issue #3)
    if platform.system() == "Windows":
        checks.append({
            "name": "Windows Unicode Fix (PYTHONUTF8)",
            "check": lambda: os.environ.get('PYTHONUTF8') == '1',
            "fix": lambda: os.environ.update({'PYTHONUTF8': '1'}),
            "priority": "HIGH",
            "reason": "Prevents UnicodeEncodeError with emoji characters in logs (Issue #3)"
        })

    # Check 2: Stale phase detection (from Gap #4 in ref5.md)
    # This check will be implemented in autonomous_executor.py
    # We just define the metadata here
    checks.append({
        "name": "Stale Phase Detection",
        "check": "implemented_in_executor",  # Placeholder
        "fix": "implemented_in_executor",
        "priority": "CRITICAL",
        "reason": "Automatically reset phases stuck in EXECUTING state >10 minutes"
    })

    return checks


def get_recent_prevention_rules(project_slug: str = "file-organizer-app-v1", limit: int = 20) -> List[str]:
    """
    Get recent prevention rules from CONSOLIDATED_DEBUG.md.

    This is a wrapper around get_prevention_rules that limits the number of rules
    returned to avoid overwhelming the LLM context.

    Args:
        project_slug: Project identifier
        limit: Maximum number of rules to return

    Returns:
        List of prevention rule strings (limited)
    """
    all_rules = get_prevention_rules(project_slug)
    return all_rules[:limit]


# Convenience function for direct use in prompts
def get_prevention_prompt_injection(project_slug: str = "file-organizer-app-v1") -> str:
    """
    Get a formatted prevention rules block to inject into LLM prompts.

    Returns:
        A markdown-formatted block with prevention rules, ready to inject
        into system prompts for Builder/Auditor agents.
    """
    rules = get_prevention_rules(project_slug)

    if not rules:
        return ""

    prompt_block = """
## CRITICAL PREVENTION RULES (from Debug Journal)

The following rules MUST be followed to prevent recurring bugs that have been
previously fixed and documented in the Debug Journal:

"""

    for i, rule in enumerate(rules, 1):
        prompt_block += f"{i}. {rule}\n"

    prompt_block += """
These rules are based on real errors that occurred in previous runs.
Violating these rules will likely result in the same errors reappearing.
"""

    return prompt_block
