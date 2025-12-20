"""Learned rules system for Autopack (Stage 0A + 0B)

Stage 0A: Within-run hints - help later phases in same run
Stage 0B: Cross-run persistent rules - help future runs

Per GPT architect + user consensus on learned rules design.
"""

import json
import os
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional, Dict, Set, Tuple
from collections import defaultdict
from enum import Enum


class DiscoveryStage(Enum):
    """Promotion stages for learned rules
    
    NEW: Fix discovered during troubleshooting
    APPLIED: Fix was attempted in a run
    CANDIDATE_RULE: Same pattern seen in >= 3 runs within 30 days
    RULE: Confirmed via recurrence, no regressions, human approved
    """
    NEW = "new"
    APPLIED = "applied"
    CANDIDATE_RULE = "candidate_rule"
    RULE = "rule"


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
    stage: str  # DiscoveryStage value ("new", "applied", "candidate_rule", "rule")

    def to_dict(self) -> Dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict) -> 'LearnedRule':
        # Handle legacy rules without stage field
        if 'stage' not in data:
            data['stage'] = DiscoveryStage.RULE.value
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
        created_at=datetime.now(timezone.utc).isoformat()
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

    Called at: End of run
    Looks for: Hints that match existing rules or appear frequently

    Args:
        run_id: Run ID
        project_id: Project ID

    Returns:
        Number of rules promoted
    """
    hints = load_run_rule_hints(run_id)
    if not hints:
        return 0

    rules = load_project_rules(project_id)
    rules_by_category = defaultdict(list)
    for rule in rules:
        rules_by_category[rule.task_category].append(rule)

    promoted_count = 0

    for hint in hints:
        # Check if hint matches existing rule
        matching_rule = _find_matching_rule(hint, rules_by_category.get(hint.task_category, []))

        if matching_rule:
            # Increment promotion count
            matching_rule.promotion_count += 1
            matching_rule.last_seen = datetime.now(timezone.utc).isoformat()
            matching_rule.source_hint_ids.append(f"{run_id}:{hint.phase_id}")
            promoted_count += 1
        else:
            # Create new rule with NEW stage
            new_rule = LearnedRule(
                rule_id=_generate_rule_id(hint),
                task_category=hint.task_category or "general",
                scope_pattern=_infer_scope_pattern(hint.scope_paths),
                constraint=hint.hint_text,
                source_hint_ids=[f"{run_id}:{hint.phase_id}"],
                promotion_count=1,
                first_seen=hint.created_at,
                last_seen=datetime.now(timezone.utc).isoformat(),
                status="active",
                stage=DiscoveryStage.NEW.value
            )
            rules.append(new_rule)
            promoted_count += 1

    # Save updated rules
    _save_project_rules(project_id, rules)

    return promoted_count


def load_project_rules(project_id: str) -> List[LearnedRule]:
    """Load all project rules

    Args:
        project_id: Project ID

    Returns:
        List of LearnedRule objects
    """
    rules_file = _get_project_rules_file(project_id)
    if not rules_file.exists():
        return []

    try:
        with open(rules_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return [LearnedRule.from_dict(r) for r in data.get("rules", [])]
    except (json.JSONDecodeError, KeyError, TypeError):
        return []


def get_active_rules_for_phase(
    project_id: str,
    phase: Dict,
    max_rules: int = 10
) -> List[LearnedRule]:
    """Get active rules relevant to this phase

    Filters by:
    - status == "active"
    - stage == "rule" (only fully promoted rules)
    - task_category match
    - scope_pattern match

    Args:
        project_id: Project ID
        phase: Phase dict
        max_rules: Maximum number of rules to return

    Returns:
        List of relevant rules (most promoted first)
    """
    all_rules = load_project_rules(project_id)
    if not all_rules:
        return []

    task_category = phase.get("task_category")

    # Filter relevant rules
    relevant = []
    for rule in all_rules:
        # Only active rules at RULE stage
        if rule.status != "active" or rule.stage != DiscoveryStage.RULE.value:
            continue

        # Match task_category if both have it
        if task_category and rule.task_category:
            if rule.task_category != task_category:
                continue

        # TODO: Could add scope_pattern matching here

        relevant.append(rule)

    # Return most promoted first, limited
    relevant.sort(key=lambda r: r.promotion_count, reverse=True)
    return relevant[:max_rules]


# ============================================================================
# Promotion Pipeline Functions
# ============================================================================

def promote_rule(rule_id: str, project_id: str) -> bool:
    """Move rule to next stage in promotion pipeline
    
    Stages: NEW → APPLIED → CANDIDATE_RULE → RULE
    
    Args:
        rule_id: Rule identifier
        project_id: Project identifier
        
    Returns:
        True if promoted, False if already at final stage or not found
    """
    rules = load_project_rules(project_id)
    rule = next((r for r in rules if r.rule_id == rule_id), None)
    
    if not rule:
        return False
    
    # Define stage progression
    stage_order = [
        DiscoveryStage.NEW,
        DiscoveryStage.APPLIED,
        DiscoveryStage.CANDIDATE_RULE,
        DiscoveryStage.RULE
    ]
    
    current_stage = DiscoveryStage(rule.stage)
    current_index = stage_order.index(current_stage)
    
    # Already at final stage
    if current_index >= len(stage_order) - 1:
        return False
    
    # Promote to next stage
    next_stage = stage_order[current_index + 1]
    rule.stage = next_stage.value
    rule.last_seen = datetime.now(timezone.utc).isoformat()
    
    # Save updated rules
    _save_project_rules(project_id, rules)
    
    return True


def get_candidates_for_promotion(project_id: str) -> List[LearnedRule]:
    """Get rules ready for human review and promotion
    
    Returns rules at CANDIDATE_RULE stage that meet promotion criteria.
    
    Args:
        project_id: Project identifier
        
    Returns:
        List of rules ready for promotion to RULE stage
    """
    rules = load_project_rules(project_id)
    candidates = []
    
    for rule in rules:
        if rule.stage != DiscoveryStage.CANDIDATE_RULE.value:
            continue
            
        eligible, reason = is_promotion_eligible(rule, project_id)
        if eligible:
            candidates.append(rule)
    
    # Sort by promotion_count (most frequent first)
    candidates.sort(key=lambda r: r.promotion_count, reverse=True)
    return candidates


def count_rule_applications(rule_id: str, project_id: str, days: int = 30) -> int:
    """Count how many times a rule pattern was applied in recent runs
    
    Args:
        rule_id: Rule identifier
        project_id: Project identifier
        days: Time window in days
        
    Returns:
        Number of applications within time window
    """
    rules = load_project_rules(project_id)
    rule = next((r for r in rules if r.rule_id == rule_id), None)
    
    if not rule:
        return 0
    
    # Parse last_seen timestamp
    try:
        last_seen = datetime.fromisoformat(rule.last_seen)
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        
        # Count source hints within window
        # This is a simplified implementation - in production, you'd track
        # individual application timestamps
        if last_seen >= cutoff:
            return rule.promotion_count
        else:
            return 0
    except (ValueError, AttributeError):
        return 0


def check_rule_regressions(rule_id: str, project_id: str) -> bool:
    """Check if rule has caused any regressions
    
    Args:
        rule_id: Rule identifier
        project_id: Project identifier
        
    Returns:
        True if regressions detected, False otherwise
    """
    # Simplified implementation - in production, you'd track:
    # - Phases that failed after applying this rule
    # - CI failures correlated with rule application
    # - Manual regression reports
    
    # For now, assume no regressions (optimistic)
    # Real implementation would query run history and failure logs
    return False


def is_promotion_eligible(rule: LearnedRule, project_id: str) -> Tuple[bool, str]:
    """Check if rule meets criteria for promotion to next stage
    
    Args:
        rule: LearnedRule to check
        project_id: Project identifier
        
    Returns:
        Tuple of (eligible: bool, reason: str)
    """
    # Load config
    config = _load_promotion_config()
    
    current_stage = DiscoveryStage(rule.stage)
    
    # NEW → APPLIED: Just needs to be attempted once
    if current_stage == DiscoveryStage.NEW:
        if rule.promotion_count >= 1:
            return True, "Rule has been applied at least once"
        return False, "Rule has not been applied yet"
    
    # APPLIED → CANDIDATE_RULE: Needs min_runs_for_candidate within window
    elif current_stage == DiscoveryStage.APPLIED:
        min_runs = config.get("min_runs_for_candidate", 3)
        window_days = config.get("window_days", 30)
        
        applications = count_rule_applications(rule.rule_id, project_id, window_days)
        
        if applications >= min_runs:
            return True, f"Rule applied {applications} times in {window_days} days"
        return False, f"Rule only applied {applications} times (need {min_runs})"
    
    # CANDIDATE_RULE → RULE: Needs no regressions + human approval
    elif current_stage == DiscoveryStage.CANDIDATE_RULE:
        has_regressions = check_rule_regressions(rule.rule_id, project_id)
        
        if has_regressions:
            return False, "Rule has caused regressions"
        
        require_approval = config.get("require_human_approval", True)
        if require_approval:
            return False, "Awaiting human approval (use promote_rule() after review)"
        
        return True, "No regressions detected, ready for promotion"
    
    # Already at RULE stage
    else:
        return False, "Rule already at final stage"


def _load_promotion_config() -> Dict:
    """Load promotion configuration from models.yaml
    
    Returns:
        Dict with promotion settings
    """
    try:
        import yaml
        config_path = Path("config/models.yaml")
        
        if not config_path.exists():
            # Return defaults if config not found
            return {
                "enabled": False,
                "min_runs_for_candidate": 3,
                "window_days": 30,
                "min_severity_for_candidate": "medium",
                "require_human_approval": True
            }
        
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
        
        return config.get("discovery_promotion", {
            "enabled": False,
            "min_runs_for_candidate": 3,
            "window_days": 30,
            "min_severity_for_candidate": "medium",
            "require_human_approval": True
        })
    except Exception:
        # Return defaults on any error
        return {
            "enabled": False,
            "min_runs_for_candidate": 3,
            "window_days": 30,
            "min_severity_for_candidate": "medium",
            "require_human_approval": True
        }


# ============================================================================
# Helper Functions
# ============================================================================

def _detect_resolved_issues(issues_before: List, issues_after: List) -> List:
    """Detect issues that were resolved"""
    before_keys = {issue.get("issue_key") for issue in issues_before}
    after_keys = {issue.get("issue_key") for issue in issues_after}
    resolved_keys = before_keys - after_keys
    return [issue for issue in issues_before if issue.get("issue_key") in resolved_keys]


def _extract_scope_paths(phase: Dict, context: Optional[Dict]) -> List[str]:
    """Extract file paths from phase or context"""
    paths = []

    # From context
    if context:
        if "files" in context:
            paths.extend(context["files"])
        if "scope_paths" in context:
            paths.extend(context["scope_paths"])

    # From phase
    if "files_to_modify" in phase:
        paths.extend(phase["files_to_modify"])

    return list(set(paths))  # Deduplicate


def _generate_hint_text(resolved: List, scope_paths: List[str], phase: Dict) -> str:
    """Generate human-readable hint text"""
    issue_types = [issue.get("issue_type", "unknown") for issue in resolved]
    unique_types = list(set(issue_types))

    if len(unique_types) == 1:
        hint = f"When working on {phase.get('task_category', 'tasks')}, "
        hint += f"watch out for {unique_types[0]} issues in {', '.join(scope_paths[:3])}"
    else:
        hint = f"When working on {phase.get('task_category', 'tasks')}, "
        hint += f"watch out for {', '.join(unique_types[:3])} issues"

    return hint


def _find_matching_rule(hint: RunRuleHint, rules: List[LearnedRule]) -> Optional[LearnedRule]:
    """Find rule that matches hint pattern"""
    # Simple text similarity for now
    # In production, use more sophisticated matching (embeddings, etc.)
    hint_lower = hint.hint_text.lower()

    for rule in rules:
        rule_lower = rule.constraint.lower()
        # Check for significant word overlap
        hint_words = set(hint_lower.split())
        rule_words = set(rule_lower.split())
        overlap = len(hint_words & rule_words)
        if overlap >= 3:  # At least 3 words in common
            return rule

    return None


def _infer_scope_pattern(scope_paths: List[str]) -> Optional[str]:
    """Infer scope pattern from paths"""
    if not scope_paths:
        return None

    # Check for common extensions
    extensions = [Path(p).suffix for p in scope_paths]
    unique_extensions = list(set(extensions))

    if len(unique_extensions) == 1 and unique_extensions[0]:
        return f"*{unique_extensions[0]}"

    # Check for common directory
    dirs = [str(Path(p).parent) for p in scope_paths]
    unique_dirs = list(set(dirs))

    if len(unique_dirs) == 1 and unique_dirs[0] != ".":
        return f"{unique_dirs[0]}/*"

    return None


def _generate_rule_id(hint: RunRuleHint) -> str:
    """Generate unique rule ID from hint"""
    import hashlib

    # Use hint text + category for ID
    text = f"{hint.task_category}:{hint.hint_text}"
    text_hash = hashlib.md5(text.encode()).hexdigest()[:8]

    category = hint.task_category or "general"
    return f"{category}.rule_{text_hash}"


def _get_run_hints_file(run_id: str) -> Path:
    """Get path to run hints file"""
    return Path(".autonomous_runs") / run_id / "run_rule_hints.json"


def _get_project_rules_file(project_id: str) -> Path:
    """Get path to project rules file

    Returns the SOT location for learned rules in docs/ directory.
    For main Autopack project: docs/LEARNED_RULES.json
    For sub-projects: .autonomous_runs/{project}/docs/LEARNED_RULES.json
    """
    if project_id == "autopack":
        return Path("docs") / "LEARNED_RULES.json"
    else:
        return Path(".autonomous_runs") / project_id / "docs" / "LEARNED_RULES.json"


def _save_run_rule_hint(run_id: str, hint: RunRuleHint):
    """Save hint to run hints file"""
    hints_file = _get_run_hints_file(run_id)
    hints_file.parent.mkdir(parents=True, exist_ok=True)

    # Load existing hints
    hints = load_run_rule_hints(run_id)
    hints.append(hint)

    # Save
    with open(hints_file, 'w', encoding='utf-8') as f:
        json.dump(
            {"hints": [h.to_dict() for h in hints]},
            f,
            indent=2
        )


def _save_project_rules(project_id: str, rules: List[LearnedRule]):
    """Save rules to project rules file"""
    rules_file = _get_project_rules_file(project_id)
    rules_file.parent.mkdir(parents=True, exist_ok=True)

    with open(rules_file, 'w', encoding='utf-8') as f:
        json.dump(
            {"rules": [r.to_dict() for r in rules]},
            f,
            indent=2
        )


# ============================================================================
# Debug Journal Integration
# ============================================================================

def _generate_debug_rule_id(rule_text: str) -> str:
    """Generate rule ID for debug journal rules
    
    Uses semantic prefixes based on rule content.
    """
    import hashlib
    
    rule_lower = rule_text.lower()
    text_hash = hashlib.md5(rule_text.encode()).hexdigest()[:8]
    
    # Semantic prefix detection
    if "import" in rule_lower or "module" in rule_lower:
        prefix = "import"
    elif "type" in rule_lower or "hint" in rule_lower:
        prefix = "typing"
    elif "test" in rule_lower:
        prefix = "testing"
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
        created_at=datetime.now(timezone.utc).isoformat()
    )

    _save_run_rule_hint(run_id, hint)
    return hint


# ============================================================================
# Formatting Helpers (for LLM clients)
# ============================================================================

def format_rules_for_prompt(rules: List[LearnedRule]) -> str:
    """Format learned rules for inclusion in LLM prompts.

    Args:
        rules: List of learned rules

    Returns:
        Formatted string for prompt injection
    """
    if not rules:
        return ""

    sections = []
    for rule in rules:
        scope_info = f" (scope: {rule.scope_pattern})" if rule.scope_pattern else ""
        sections.append(f"- {rule.rule_text}{scope_info}")

    return "\n".join(sections)


def format_hints_for_prompt(hints: List[RunRuleHint]) -> str:
    """Format run hints for inclusion in LLM prompts.

    Args:
        hints: List of run hints

    Returns:
        Formatted string for prompt injection
    """
    if not hints:
        return ""

    sections = []
    for hint in hints:
        scope_info = f" (scope: {', '.join(hint.scope_paths[:3])})" if hint.scope_paths else ""
        sections.append(f"- {hint.hint_text}{scope_info}")

    return "\n".join(sections)
