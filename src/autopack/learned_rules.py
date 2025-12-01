"""Learned rules system for Autopack (Stage 0A + 0B)

Stage 0A: Within-run hints - help later phases in same run
Stage 0B: Cross-run persistent rules - help future runs

Per GPT architect + user consensus on learned rules design.
"""

import json
import os
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Set
from collections import defaultdict


@dataclass
class RunRuleHint:
    """Stage 0A: Run-local hint from resolved issue

    Stored in: .autonomous_runs/{run_id}/run_rule_hints.json
    Used for: Later phases in same run
    """
    run_id: str
    phase_index: int
    phase_id: str
    tier_id: Optional[str]
    task_category: Optional[str]
    scope_paths: List[str]  # Files/modules affected
    source_issue_keys: List[str]
    hint_text: str  # Human-readable lesson
    created_at: str  # ISO format datetime

    def to_dict(self) -> Dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict) -> 'RunRuleHint':
        return cls(**data)


@dataclass
class LearnedRule:
    """Stage 0B: Persistent project-level rule

    Stored in: .autonomous_runs/{project_id}/project_learned_rules.json
    Used for: All phases in all future runs
    """
    rule_id: str  # e.g., "python.type_hints_required"
    task_category: str
    scope_pattern: Optional[str]  # e.g., "*.py", "auth/*.py", None for global
    constraint: str  # Human-readable rule text
    source_hint_ids: List[str]  # Traceability to original hints
    promotion_count: int  # Number of times promoted across runs
    first_seen: str  # ISO format datetime
    last_seen: str  # ISO format datetime
    status: str  # "active" | "deprecated"

    def to_dict(self) -> Dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict) -> 'LearnedRule':
        return cls(**data)


# ============================================================================
# Stage 0A: Run-Local Hints
# ============================================================================

def record_run_rule_hint(
    run_id: str,
    phase: Dict,
    issues_before: List,
    issues_after: List,
    context: Optional[Dict] = None
) -> Optional[RunRuleHint]:
    """Record a hint when phase resolves issues

    Called when: Phase transitions to complete + CI green
    Only creates hint if: Issues were resolved

    Args:
        run_id: Run ID
        phase: Phase dict with phase_id, task_category, etc.
        issues_before: Issues at phase start
        issues_after: Issues at phase end
        context: Optional context (file paths, etc.)

    Returns:
        RunRuleHint if created, None otherwise
    """
    # Detect resolved issues
    resolved = _detect_resolved_issues(issues_before, issues_after)
    if not resolved:
        return None

    # Extract scope paths from context or phase
    scope_paths = _extract_scope_paths(phase, context)
    if not scope_paths:
        return None  # Need scope to make hint useful

    # Generate hint text
    hint_text = _generate_hint_text(resolved, scope_paths, phase)

    # Create hint
    hint = RunRuleHint(
        run_id=run_id,
        phase_index=phase.get("phase_index", 0),
        phase_id=phase["phase_id"],
        tier_id=phase.get("tier_id"),
        task_category=phase.get("task_category"),
        scope_paths=scope_paths[:5],  # Limit to 5 paths
        source_issue_keys=[issue.get("issue_key", "") for issue in resolved],
        hint_text=hint_text,
        created_at=datetime.utcnow().isoformat()
    )

    # Save to file
    _save_run_rule_hint(run_id, hint)

    return hint


def load_run_rule_hints(run_id: str) -> List[RunRuleHint]:
    """Load all hints for a run

    Args:
        run_id: Run ID

    Returns:
        List of RunRuleHint objects
    """
    hints_file = _get_run_hints_file(run_id)
    if not hints_file.exists():
        return []

    try:
        with open(hints_file, 'r') as f:
            data = json.load(f)
        return [RunRuleHint.from_dict(h) for h in data.get("hints", [])]
    except (json.JSONDecodeError, KeyError, TypeError):
        return []


def get_relevant_hints_for_phase(
    run_id: str,
    phase: Dict,
    max_hints: int = 5
) -> List[RunRuleHint]:
    """Get hints relevant to this phase

    Filters by:
    - Same task_category
    - Intersecting scope_paths
    - Only hints from earlier phases

    Args:
        run_id: Run ID
        phase: Phase dict
        max_hints: Maximum number of hints to return

    Returns:
        List of relevant hints (most recent first)
    """
    all_hints = load_run_rule_hints(run_id)
    if not all_hints:
        return []

    phase_index = phase.get("phase_index", 999)
    task_category = phase.get("task_category")

    # Filter relevant hints
    relevant = []
    for hint in all_hints:
        # Only hints from earlier phases
        if hint.phase_index >= phase_index:
            continue

        # Match task_category if both have it
        if task_category and hint.task_category:
            if hint.task_category != task_category:
                continue

        # TODO: Could add scope_paths intersection check here

        relevant.append(hint)

    # Return most recent first, limited
    relevant.sort(key=lambda h: h.phase_index, reverse=True)
    return relevant[:max_hints]


# ============================================================================
# Stage 0B: Cross-Run Persistent Rules
# ============================================================================

def promote_hints_to_rules(run_id: str, project_id: str) -> int:
    """Promote frequent hints to persistent project rules

    Called when: Run completes
    Logic: If hint pattern appears 2+ times in this run, promote

    Args:
        run_id: Run ID
        project_id: Project ID

    Returns:
        Number of rules promoted
    """
    hints = load_run_rule_hints(run_id)
    if not hints:
        return 0

    # Group hints by pattern (issue_key + task_category)
    patterns = _group_hints_by_pattern(hints)

    # Load existing rules
    existing_rules = load_project_learned_rules(project_id)
    rules_dict = {r.rule_id: r for r in existing_rules}

    promoted_count = 0

    # Promote patterns that appear 2+ times
    for pattern_key, hint_group in patterns.items():
        if len(hint_group) < 2:
            continue  # Need 2+ occurrences to promote

        rule_id = _generate_rule_id(hint_group[0])

        if rule_id in rules_dict:
            # Update existing rule
            rule = rules_dict[rule_id]
            rule.promotion_count += 1
            rule.last_seen = datetime.utcnow().isoformat()
            rule.source_hint_ids.extend([f"{h.run_id}:{h.phase_id}" for h in hint_group])
        else:
            # Create new rule
            rule = _create_rule_from_hints(rule_id, hint_group, project_id)
            rules_dict[rule_id] = rule
            promoted_count += 1

    # Save updated rules
    _save_project_learned_rules(project_id, list(rules_dict.values()))

    return promoted_count


def load_project_learned_rules(project_id: str) -> List[LearnedRule]:
    """Load persistent project rules

    Args:
        project_id: Project ID

    Returns:
        List of LearnedRule objects (active only)
    """
    rules_file = _get_project_rules_file(project_id)
    if not rules_file.exists():
        return []

    try:
        with open(rules_file, 'r') as f:
            data = json.load(f)
        rules = [LearnedRule.from_dict(r) for r in data.get("rules", [])]
        # Return only active rules
        return [r for r in rules if r.status == "active"]
    except (json.JSONDecodeError, KeyError, TypeError):
        return []


def get_relevant_rules_for_phase(
    project_rules: List[LearnedRule],
    phase: Dict,
    max_rules: int = 10
) -> List[LearnedRule]:
    """Get rules relevant to this phase

    Filters by:
    - task_category match
    - scope_pattern match (if specified)

    Args:
        project_rules: All project rules
        phase: Phase dict
        max_rules: Maximum number of rules to return

    Returns:
        List of relevant rules (most promoted first)
    """
    if not project_rules:
        return []

    task_category = phase.get("task_category")

    # Filter relevant rules
    relevant = []
    for rule in project_rules:
        # Match task_category
        if task_category and rule.task_category != task_category:
            continue

        # TODO: Could add scope_pattern matching here

        relevant.append(rule)

    # Return most promoted first (highest confidence), limited
    relevant.sort(key=lambda r: r.promotion_count, reverse=True)
    return relevant[:max_rules]


# ============================================================================
# Helper Functions
# ============================================================================

def _detect_resolved_issues(issues_before: List, issues_after: List) -> List:
    """Detect which issues were resolved"""
    if not issues_before:
        return []

    # Simple heuristic: issues in before but not in after
    before_keys = {issue.get("issue_key") for issue in issues_before if issue.get("issue_key")}
    after_keys = {issue.get("issue_key") for issue in issues_after if issue.get("issue_key")}
    resolved_keys = before_keys - after_keys

    return [issue for issue in issues_before if issue.get("issue_key") in resolved_keys]


def _extract_scope_paths(phase: Dict, context: Optional[Dict]) -> List[str]:
    """Extract file/module paths from phase or context"""
    paths = []

    # Try context first
    if context and "file_paths" in context:
        paths.extend(context["file_paths"])

    # Try phase description parsing (future enhancement)
    # For now, return what we have

    return list(set(paths))[:5]  # Unique, max 5


def _generate_hint_text(resolved: List, scope_paths: List[str], phase: Dict) -> str:
    """Generate hint text from resolved issues

    Template-based for now (no LLM)
    """
    if not resolved:
        return "Issue resolved in this phase"

    issue = resolved[0]  # Use first issue for template
    issue_key = issue.get("issue_key", "unknown_issue")

    # Pattern detection
    templates = {
        "missing_type_hints": "Resolved {issue_key} in {files} - ensure all functions have type annotations",
        "placeholder": "Resolved {issue_key} - removed placeholder code in {files}",
        "missing_tests": "Resolved {issue_key} - added tests for {files}",
        "import_error": "Resolved {issue_key} - fixed imports in {files}",
        "syntax_error": "Resolved {issue_key} - fixed syntax in {files}",
    }

    # Detect pattern
    pattern = None
    for key in templates.keys():
        if key in issue_key.lower():
            pattern = key
            break

    template = templates.get(pattern, "Resolved {issue_key} in {files}")

    files_str = ", ".join(scope_paths[:3]) if scope_paths else "affected files"

    return template.format(issue_key=issue_key, files=files_str)


def _group_hints_by_pattern(hints: List[RunRuleHint]) -> Dict[str, List[RunRuleHint]]:
    """Group hints by pattern for promotion detection"""
    patterns = defaultdict(list)

    for hint in hints:
        # Pattern key: first issue_key + task_category
        issue_key = hint.source_issue_keys[0] if hint.source_issue_keys else "unknown"
        # Extract pattern from issue_key (e.g., "missing_type_hints" from "missing_type_hints_auth_py")
        pattern_key = _extract_pattern(issue_key)
        key = f"{pattern_key}:{hint.task_category or 'any'}"
        patterns[key].append(hint)

    return dict(patterns)


def _extract_pattern(issue_key: str) -> str:
    """Extract base pattern from issue key"""
    # Simple heuristic: take first 2-3 words before underscore + digits/file
    parts = issue_key.split("_")
    # Take up to 3 parts, stop at file extensions or numbers
    pattern_parts = []
    for part in parts[:3]:
        if part.isdigit() or "." in part:
            break
        pattern_parts.append(part)
    return "_".join(pattern_parts) if pattern_parts else issue_key


def _generate_rule_id(hint: RunRuleHint) -> str:
    """Generate rule ID from hint"""
    issue_key = hint.source_issue_keys[0] if hint.source_issue_keys else "unknown"
    pattern = _extract_pattern(issue_key)
    category = hint.task_category or "general"
    return f"{category}.{pattern}"


def _create_rule_from_hints(rule_id: str, hints: List[RunRuleHint], project_id: str) -> LearnedRule:
    """Create new rule from hint group"""
    first_hint = hints[0]

    # Generate constraint from hint text (generalize it)
    constraint = _generalize_constraint(first_hint.hint_text)

    return LearnedRule(
        rule_id=rule_id,
        task_category=first_hint.task_category or "general",
        scope_pattern=None,  # Global for now
        constraint=constraint,
        source_hint_ids=[f"{h.run_id}:{h.phase_id}" for h in hints],
        promotion_count=1,
        first_seen=datetime.utcnow().isoformat(),
        last_seen=datetime.utcnow().isoformat(),
        status="active"
    )


def _generalize_constraint(hint_text: str) -> str:
    """Generalize hint text to constraint

    Remove specific file names, make it more general
    """
    # Simple generalization: remove "in file_name.py" parts
    constraint = hint_text
    # Replace specific files with "affected files"
    import re
    constraint = re.sub(r' in [a-zA-Z0-9_./]+\.(py|js|ts|tsx|jsx)', ' in affected files', constraint)
    constraint = re.sub(r' - [a-zA-Z0-9_./]+\.(py|js|ts|tsx|jsx)', '', constraint)
    return constraint


# ============================================================================
# File I/O
# ============================================================================

def _get_run_hints_file(run_id: str) -> Path:
    """Get path to run hints file"""
    base_dir = Path(".autonomous_runs") / "runs" / run_id
    base_dir.mkdir(parents=True, exist_ok=True)
    return base_dir / "run_rule_hints.json"


def _get_project_rules_file(project_id: str) -> Path:
    """Get path to project rules file"""
    base_dir = Path(".autonomous_runs") / project_id
    base_dir.mkdir(parents=True, exist_ok=True)
    return base_dir / "project_learned_rules.json"


def _save_run_rule_hint(run_id: str, hint: RunRuleHint):
    """Save hint to run hints file (append)"""
    hints_file = _get_run_hints_file(run_id)

    # Load existing
    existing_hints = []
    if hints_file.exists():
        try:
            with open(hints_file, 'r') as f:
                data = json.load(f)
            existing_hints = data.get("hints", [])
        except (json.JSONDecodeError, KeyError):
            pass

    # Append new hint
    existing_hints.append(hint.to_dict())

    # Save
    with open(hints_file, 'w') as f:
        json.dump({
            "run_id": run_id,
            "hints": existing_hints
        }, f, indent=2)


def _save_project_learned_rules(project_id: str, rules: List[LearnedRule]):
    """Save project rules file (overwrite)"""
    rules_file = _get_project_rules_file(project_id)

    with open(rules_file, 'w') as f:
        json.dump({
            "project_id": project_id,
            "version": "1.0",
            "last_updated": datetime.utcnow().isoformat(),
            "rule_count": len(rules),
            "rules": [r.to_dict() for r in rules]
        }, f, indent=2)


# ============================================================================
# Formatting for Prompts
# ============================================================================

def format_hints_for_prompt(hints: List[RunRuleHint]) -> str:
    """Format hints for Builder/Auditor prompt injection"""
    if not hints:
        return ""

    output = "## Lessons from Earlier Phases (this run only)\n\n"
    output += "Do not repeat these mistakes:\n"
    for i, hint in enumerate(hints, 1):
        output += f"{i}. {hint.hint_text}\n"

    return output


def format_rules_for_prompt(rules: List[LearnedRule]) -> str:
    """Format rules for Builder/Auditor prompt injection"""
    if not rules:
        return ""

    output = "## Project Learned Rules (from past runs)\n\n"
    output += "IMPORTANT: Follow these rules learned from past experience:\n\n"

    for i, rule in enumerate(rules, 1):
        output += f"{i}. **{rule.rule_id}**: {rule.constraint}\n"

    return output


# ============================================================================
# Debug History Integration (CONSOLIDATED_DEBUG.md -> project_learned_rules.json)
# ============================================================================

def sync_rules_from_debug_history(project_id: str) -> int:
    """
    Extract prevention rules from CONSOLIDATED_DEBUG.md and sync to project_learned_rules.json.

    This bridges the gap between the debug journal system (manual debugging documentation)
    and the learned rules system (automated rule injection into prompts).

    Called at: Run start, to ensure any manually documented fixes are available as rules.

    Args:
        project_id: Project ID (e.g., "file-organizer-app-v1" or "Autopack")

    Returns:
        Number of new rules synced from debug history
    """
    from autopack.journal_reader import get_prevention_rules

    # Get prevention rules from CONSOLIDATED_DEBUG.md
    prevention_rules = get_prevention_rules(project_id)
    if not prevention_rules:
        return 0

    # Load existing learned rules
    existing_rules = load_project_learned_rules(project_id)
    rules_dict = {r.rule_id: r for r in existing_rules}

    synced_count = 0

    for i, rule_text in enumerate(prevention_rules):
        # Generate rule ID from rule text
        rule_id = _generate_rule_id_from_text(rule_text, i)

        if rule_id in rules_dict:
            # Rule already exists, update last_seen
            rules_dict[rule_id].last_seen = datetime.utcnow().isoformat()
        else:
            # Create new rule from prevention rule
            new_rule = LearnedRule(
                rule_id=rule_id,
                task_category="debug_journal",  # Special category for debug-sourced rules
                scope_pattern=None,  # Global
                constraint=rule_text,
                source_hint_ids=[f"debug_journal:{project_id}"],
                promotion_count=10,  # High confidence since manually documented
                first_seen=datetime.utcnow().isoformat(),
                last_seen=datetime.utcnow().isoformat(),
                status="active"
            )
            rules_dict[rule_id] = new_rule
            synced_count += 1

    # Save updated rules
    if synced_count > 0 or existing_rules:
        _save_project_learned_rules(project_id, list(rules_dict.values()))

    return synced_count


def _generate_rule_id_from_text(rule_text: str, index: int) -> str:
    """Generate a stable rule ID from rule text"""
    import hashlib
    # Create hash from rule text for stability
    text_hash = hashlib.md5(rule_text.encode()).hexdigest()[:8]

    # Try to extract meaningful prefix from rule text
    rule_lower = rule_text.lower()
    if "never" in rule_lower:
        prefix = "never"
    elif "always" in rule_lower:
        prefix = "always"
    elif "import" in rule_lower:
        prefix = "import"
    elif "test" in rule_lower:
        prefix = "test"
    elif "file" in rule_lower or "path" in rule_lower:
        prefix = "file"
    elif "api" in rule_lower or "key" in rule_lower:
        prefix = "api"
    elif "unicode" in rule_lower or "encoding" in rule_lower:
        prefix = "encoding"
    elif "sqlite" in rule_lower or "database" in rule_lower:
        prefix = "database"
    else:
        prefix = "rule"

    return f"debug_journal.{prefix}_{text_hash}"


def save_run_hint(
    run_id: str,
    phase: Dict,
    hint_text: str,
    scope_paths: Optional[List[str]] = None,
    source_issue_keys: Optional[List[str]] = None
) -> RunRuleHint:
    """
    Save a run hint directly (convenience function for autonomous_executor).

    Unlike record_run_rule_hint which requires issues_before/after,
    this function allows direct hint creation.

    Args:
        run_id: Run ID
        phase: Phase dict
        hint_text: Human-readable lesson learned
        scope_paths: Files affected (optional)
        source_issue_keys: Issue keys (optional)

    Returns:
        Created RunRuleHint
    """
    hint = RunRuleHint(
        run_id=run_id,
        phase_index=phase.get("phase_index", 0),
        phase_id=phase.get("phase_id", "unknown"),
        tier_id=phase.get("tier_id"),
        task_category=phase.get("task_category"),
        scope_paths=scope_paths or [],
        source_issue_keys=source_issue_keys or [],
        hint_text=hint_text,
        created_at=datetime.utcnow().isoformat()
    )

    _save_run_rule_hint(run_id, hint)
    return hint
