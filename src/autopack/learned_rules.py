"""Learned rules system for Autopack (Stage 0A + 0B)

Stage 0A: Within-run hints - help later phases in same run
Stage 0B: Cross-run persistent rules - help future runs

Per GPT architect + user consensus on learned rules design.
"""

import json
import logging
import os
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ============================================================================
# IMP-PERF-003: Process-level cache for project rules loading
# ============================================================================

# Cache for project rules keyed by project_id
_project_rules_cache: Dict[str, List["LearnedRule"]] = {}

# Track file modification times for cache invalidation
_project_rules_mtime: Dict[str, float] = {}


# ============================================================================
# IMP-PERF-006: Run-level cache for hint loading
# ============================================================================

# Cache for run hints keyed by run_id
_run_hints_cache: Dict[str, List["RunRuleHint"]] = {}


def clear_run_hints_cache(run_id: Optional[str] = None) -> None:
    """Clear the run hints cache.

    Call this between runs or when hints are modified externally.

    Args:
        run_id: Optional specific run_id to clear. If None, clears all cached hints.
    """
    if run_id is not None:
        _run_hints_cache.pop(run_id, None)
    else:
        _run_hints_cache.clear()


def clear_project_rules_cache() -> None:
    """Clear the project rules cache.

    Call this when rules are modified externally or between test runs.
    """
    _project_rules_cache.clear()
    _project_rules_mtime.clear()


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
    def from_dict(cls, data: Dict) -> "RunRuleHint":
        return cls(**data)


@dataclass
class LearnedRule:
    """Stage 0B: Persistent project-level rule

    Stored in: .autonomous_runs/{project_id}/project_learned_rules.json
    Used for: All phases in all future runs

    IMP-LOOP-034: Added effectiveness tracking fields for rule deprecation:
    - effectiveness_score: Tracks how well the rule works (0.0-1.0)
    - last_validated_at: When the rule was last validated
    - deprecated: Whether the rule has been deprecated due to low effectiveness
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
    # IMP-LOOP-034: Effectiveness tracking fields
    effectiveness_score: float = 1.0  # 0.0-1.0, starts at 1.0 (fully effective)
    last_validated_at: Optional[str] = None  # ISO format datetime
    deprecated: bool = False  # Explicit deprecation flag

    def to_dict(self) -> Dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict) -> "LearnedRule":
        # Handle legacy rules without stage field
        if "stage" not in data:
            data["stage"] = DiscoveryStage.RULE.value
        # IMP-LOOP-034: Handle legacy rules without effectiveness fields
        if "effectiveness_score" not in data:
            data["effectiveness_score"] = 1.0
        if "last_validated_at" not in data:
            data["last_validated_at"] = None
        if "deprecated" not in data:
            data["deprecated"] = False
        return cls(**data)


@dataclass
class LearnedRuleAging:
    """Tracks aging and decay of learned rules.

    Monitors how outdated learned rules become over time and triggers
    automatic deprecation when decay exceeds threshold.

    Attributes:
        rule_id: Unique identifier of the rule being tracked
        creation_date: When the rule was first created
        last_validation_date: When the rule was last validated as still useful
        age_days: Number of days since creation
        validation_failures: Count of times rule failed to prevent issues
        decay_score: 0.0 = fresh, 1.0 = fully decayed
    """

    rule_id: str
    creation_date: datetime
    last_validation_date: datetime
    age_days: int
    validation_failures: int
    decay_score: float  # 0.0 = fresh, 1.0 = fully decayed

    def should_deprecate(self) -> bool:
        """Check if rule should be deprecated (decay > 0.7).

        Returns:
            True if decay_score exceeds 0.7 threshold
        """
        return self.decay_score > 0.7

    def calculate_decay(self) -> float:
        """Calculate decay score based on age and validation failures.

        Decay formula:
        - Age factor: age_days / 365, capped at 0.5 (min 0.0)
        - Failure factor: validation_failures * 0.1, capped at 0.5 (min 0.0)
        - Total decay: age_factor + failure_factor, capped at 1.0

        Returns:
            Decay score between 0.0 and 1.0
        """
        age_factor = max(0.0, min(self.age_days / 365, 0.5))  # 0.0 to 0.5 from age
        failure_factor = max(
            0.0, min(self.validation_failures * 0.1, 0.5)
        )  # 0.0 to 0.5 from failures
        return min(age_factor + failure_factor, 1.0)

    @classmethod
    def from_rule(cls, rule: LearnedRule) -> "LearnedRuleAging":
        """Create aging tracker from an existing LearnedRule.

        Args:
            rule: The LearnedRule to track

        Returns:
            LearnedRuleAging instance with calculated age and initial decay
        """
        creation_date = datetime.fromisoformat(rule.first_seen)
        last_validation_date = datetime.fromisoformat(rule.last_seen)
        now = datetime.now(timezone.utc)
        age_days = (now - creation_date).days

        aging = cls(
            rule_id=rule.rule_id,
            creation_date=creation_date,
            last_validation_date=last_validation_date,
            age_days=age_days,
            validation_failures=0,  # Start with no failures
            decay_score=0.0,
        )
        # Calculate initial decay based on age
        aging.decay_score = aging.calculate_decay()
        return aging

    def record_validation_failure(self) -> None:
        """Record a validation failure and recalculate decay."""
        self.validation_failures += 1
        self.decay_score = self.calculate_decay()

    def record_validation_success(self) -> None:
        """Record a successful validation, updating last validation date."""
        self.last_validation_date = datetime.now(timezone.utc)
        # Successful validations can reduce failure impact over time
        # but age factor still applies
        self.decay_score = self.calculate_decay()


# ============================================================================
# IMP-LOOP-034: Rule Effectiveness Tracking
# ============================================================================


@dataclass
class RuleApplication:
    """Tracks a single application of a learned rule.

    IMP-LOOP-034: Used to measure rule effectiveness over time.

    Attributes:
        rule_id: The rule that was applied
        phase_id: The phase where the rule was applied
        applied_at: When the rule was applied (ISO format)
        successful: Whether the phase succeeded with this rule
        context: Optional additional context about the application
    """

    rule_id: str
    phase_id: str
    applied_at: str  # ISO format datetime
    successful: bool
    context: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict) -> "RuleApplication":
        return cls(**data)


@dataclass
class RuleEffectivenessReport:
    """Report on a rule's effectiveness based on recent applications.

    IMP-LOOP-034: Used to evaluate whether rules are still working
    and should be deprecated if effectiveness falls below threshold.

    Attributes:
        rule_id: The rule being evaluated
        effectiveness_score: Success rate from 0.0 to 1.0
        total_applications: Number of times the rule was applied
        successful_applications: Number of successful applications
        evaluation_period_days: The time period over which effectiveness was measured
        recommendation: Suggested action ("keep", "monitor", "deprecate")
    """

    rule_id: str
    effectiveness_score: float
    total_applications: int
    successful_applications: int
    evaluation_period_days: int
    recommendation: str  # "keep", "monitor", "deprecate"

    def to_dict(self) -> Dict:
        return asdict(self)


# ============================================================================
# IMP-LOOP-018: Rule Aging Tracker (Persistence Layer)
# ============================================================================


class RuleAgingTracker:
    """Manages persistence and tracking of rule aging data.

    IMP-LOOP-018: Activates LearnedRuleAging by persisting validation
    outcomes and providing rule deprecation filtering.

    Aging data is stored alongside project rules in a separate file:
    - docs/RULE_AGING.json (for autopack project)
    - {autonomous_runs_dir}/{project}/docs/RULE_AGING.json (for sub-projects)
    """

    def __init__(self, project_id: str = "autopack"):
        """Initialize tracker for a project.

        Args:
            project_id: Project identifier for rule isolation
        """
        self.project_id = project_id
        self._aging_data: Dict[str, Dict] = {}
        self._load_aging_data()

    def _get_aging_file(self) -> Path:
        """Get path to rule aging data file."""
        if self.project_id == "autopack":
            return Path("docs") / "RULE_AGING.json"
        else:
            from .config import settings

            return Path(settings.autonomous_runs_dir) / self.project_id / "docs" / "RULE_AGING.json"

    def _load_aging_data(self) -> None:
        """Load aging data from file."""
        aging_file = self._get_aging_file()
        if not aging_file.exists():
            self._aging_data = {}
            return

        try:
            with open(aging_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._aging_data = data.get("aging", {})
        except (json.JSONDecodeError, KeyError, TypeError):
            self._aging_data = {}

    def _save_aging_data(self) -> None:
        """Persist aging data to file."""
        aging_file = self._get_aging_file()
        aging_file.parent.mkdir(parents=True, exist_ok=True)

        with open(aging_file, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "aging": self._aging_data,
                    "last_updated": datetime.now(timezone.utc).isoformat(),
                },
                f,
                indent=2,
            )

    def get_aging(self, rule_id: str) -> Optional[LearnedRuleAging]:
        """Get aging data for a rule.

        Args:
            rule_id: Rule identifier

        Returns:
            LearnedRuleAging instance or None if not tracked
        """
        if rule_id not in self._aging_data:
            return None

        data = self._aging_data[rule_id]
        return LearnedRuleAging(
            rule_id=rule_id,
            creation_date=datetime.fromisoformat(data["creation_date"]),
            last_validation_date=datetime.fromisoformat(data["last_validation_date"]),
            age_days=data["age_days"],
            validation_failures=data["validation_failures"],
            decay_score=data["decay_score"],
        )

    def get_or_create_aging(self, rule: LearnedRule) -> LearnedRuleAging:
        """Get or create aging tracker for a rule.

        Args:
            rule: LearnedRule to track

        Returns:
            LearnedRuleAging instance (creates new if not tracked)
        """
        existing = self.get_aging(rule.rule_id)
        if existing:
            # Update age_days based on current time
            now = datetime.now(timezone.utc)
            existing.age_days = (now - existing.creation_date).days
            existing.decay_score = existing.calculate_decay()
            return existing

        # Create new aging tracker from rule
        return LearnedRuleAging.from_rule(rule)

    def record_validation_success(self, rule_id: str) -> None:
        """Record a successful rule application.

        Args:
            rule_id: Rule identifier
        """
        now = datetime.now(timezone.utc)

        if rule_id not in self._aging_data:
            # Initialize aging data for new rule
            self._aging_data[rule_id] = {
                "creation_date": now.isoformat(),
                "last_validation_date": now.isoformat(),
                "age_days": 0,
                "validation_failures": 0,
                "decay_score": 0.0,
            }
        else:
            # Update existing aging data
            data = self._aging_data[rule_id]
            data["last_validation_date"] = now.isoformat()
            creation = datetime.fromisoformat(data["creation_date"])
            age_days = (now - creation).days
            data["age_days"] = age_days

            # Recalculate decay directly
            # Calculate decay: age_factor (max 0.5) + failure_factor (max 0.5)
            age_factor = max(0.0, min(age_days / 365, 0.5))
            failure_factor = max(0.0, min(data.get("validation_failures", 0) * 0.1, 0.5))
            data["decay_score"] = min(age_factor + failure_factor, 1.0)

        self._save_aging_data()

    def record_validation_failure(self, rule_id: str) -> None:
        """Record a failed rule application.

        Args:
            rule_id: Rule identifier
        """
        now = datetime.now(timezone.utc)

        if rule_id not in self._aging_data:
            # Initialize aging data for new rule with one failure
            self._aging_data[rule_id] = {
                "creation_date": now.isoformat(),
                "last_validation_date": now.isoformat(),
                "age_days": 0,
                "validation_failures": 1,
                "decay_score": 0.1,  # 1 failure * 0.1
            }
        else:
            # Update existing aging data
            data = self._aging_data[rule_id]
            data["validation_failures"] = data.get("validation_failures", 0) + 1

            # Recalculate decay directly (don't use aging.record_validation_failure()
            # as that would double-increment the failures)
            creation = datetime.fromisoformat(data["creation_date"])
            age_days = (now - creation).days
            data["age_days"] = age_days

            # Calculate decay: age_factor (max 0.5) + failure_factor (max 0.5)
            age_factor = max(0.0, min(age_days / 365, 0.5))
            failure_factor = max(0.0, min(data["validation_failures"] * 0.1, 0.5))
            data["decay_score"] = min(age_factor + failure_factor, 1.0)

        self._save_aging_data()

    def should_deprecate(self, rule_id: str) -> bool:
        """Check if a rule should be deprecated based on aging.

        Args:
            rule_id: Rule identifier

        Returns:
            True if rule decay exceeds 0.7 threshold
        """
        aging = self.get_aging(rule_id)
        if not aging:
            return False  # Unknown rules are not deprecated
        return aging.should_deprecate()


def record_rule_validation_outcome(project_id: str, rule_ids: List[str], success: bool) -> None:
    """Record validation outcome for rules applied during phase execution.

    IMP-LOOP-018: Called after phase execution to track rule effectiveness.

    Args:
        project_id: Project identifier
        rule_ids: List of rule IDs that were applied
        success: True if phase succeeded, False otherwise
    """
    if not rule_ids:
        return

    tracker = RuleAgingTracker(project_id)

    for rule_id in rule_ids:
        if success:
            tracker.record_validation_success(rule_id)
        else:
            tracker.record_validation_failure(rule_id)


# ============================================================================
# IMP-LOOP-034: Rule Effectiveness Manager
# ============================================================================


class RuleEffectivenessManager:
    """Manages rule effectiveness evaluation and deprecation.

    IMP-LOOP-034: Provides methods to:
    - Track rule applications and their outcomes
    - Evaluate rule effectiveness based on recent applications
    - Deprecate rules that fall below effectiveness threshold

    Rule applications are stored in a separate file:
    - docs/RULE_APPLICATIONS.json (for autopack project)
    - {autonomous_runs_dir}/{project}/docs/RULE_APPLICATIONS.json (for sub-projects)
    """

    def __init__(self, project_id: str = "autopack"):
        """Initialize effectiveness manager for a project.

        Args:
            project_id: Project identifier for rule isolation
        """
        self.project_id = project_id
        self._applications: List[RuleApplication] = []
        self._load_applications()

    def _get_applications_file(self) -> Path:
        """Get path to rule applications data file."""
        if self.project_id == "autopack":
            return Path("docs") / "RULE_APPLICATIONS.json"
        else:
            from .config import settings

            return (
                Path(settings.autonomous_runs_dir)
                / self.project_id
                / "docs"
                / "RULE_APPLICATIONS.json"
            )

    def _load_applications(self) -> None:
        """Load rule applications from file."""
        applications_file = self._get_applications_file()
        if not applications_file.exists():
            self._applications = []
            return

        try:
            with open(applications_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._applications = [
                RuleApplication.from_dict(a) for a in data.get("applications", [])
            ]
        except (json.JSONDecodeError, KeyError, TypeError):
            self._applications = []

    def _save_applications(self) -> None:
        """Persist rule applications to file."""
        applications_file = self._get_applications_file()
        applications_file.parent.mkdir(parents=True, exist_ok=True)

        with open(applications_file, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "applications": [a.to_dict() for a in self._applications],
                    "last_updated": datetime.now(timezone.utc).isoformat(),
                },
                f,
                indent=2,
            )

    def record_application(
        self,
        rule_id: str,
        phase_id: str,
        successful: bool,
        context: Optional[Dict[str, Any]] = None,
    ) -> RuleApplication:
        """Record a rule application.

        Args:
            rule_id: The rule that was applied
            phase_id: The phase where the rule was applied
            successful: Whether the phase succeeded
            context: Optional additional context

        Returns:
            The created RuleApplication
        """
        application = RuleApplication(
            rule_id=rule_id,
            phase_id=phase_id,
            applied_at=datetime.now(timezone.utc).isoformat(),
            successful=successful,
            context=context,
        )
        self._applications.append(application)
        self._save_applications()
        return application

    def get_recent_applications(
        self,
        rule_id: str,
        days: int = 30,
    ) -> List[RuleApplication]:
        """Get recent applications of a rule.

        Args:
            rule_id: The rule to get applications for
            days: Number of days to look back (default 30)

        Returns:
            List of RuleApplication objects within the time window
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        recent = []

        for app in self._applications:
            if app.rule_id != rule_id:
                continue

            try:
                app_date = datetime.fromisoformat(app.applied_at)
                # Handle timezone-naive datetimes
                if app_date.tzinfo is None:
                    app_date = app_date.replace(tzinfo=timezone.utc)
                if app_date >= cutoff:
                    recent.append(app)
            except (ValueError, AttributeError):
                continue

        return recent

    def evaluate_rule_effectiveness(
        self,
        rule_id: str,
        days: int = 30,
    ) -> RuleEffectivenessReport:
        """Evaluate rule's current effectiveness based on recent outcomes.

        IMP-LOOP-034: Calculates effectiveness score as the success rate
        of recent rule applications and provides a recommendation.

        Args:
            rule_id: The rule to evaluate
            days: Evaluation period in days (default 30)

        Returns:
            RuleEffectivenessReport with effectiveness metrics and recommendation
        """
        recent_applications = self.get_recent_applications(rule_id, days)
        total = len(recent_applications)

        if total == 0:
            # No recent applications - maintain current effectiveness
            return RuleEffectivenessReport(
                rule_id=rule_id,
                effectiveness_score=1.0,  # Assume effective if not tested
                total_applications=0,
                successful_applications=0,
                evaluation_period_days=days,
                recommendation="monitor",  # Need more data
            )

        successful = sum(1 for a in recent_applications if a.successful)
        effectiveness_score = successful / total

        # Determine recommendation based on effectiveness
        if effectiveness_score >= 0.7:
            recommendation = "keep"
        elif effectiveness_score >= 0.3:
            recommendation = "monitor"
        else:
            recommendation = "deprecate"

        return RuleEffectivenessReport(
            rule_id=rule_id,
            effectiveness_score=effectiveness_score,
            total_applications=total,
            successful_applications=successful,
            evaluation_period_days=days,
            recommendation=recommendation,
        )

    def deprecate_ineffective_rules(
        self,
        min_effectiveness: float = 0.3,
        min_applications: int = 3,
        days: int = 30,
    ) -> List[str]:
        """Deprecate rules below effectiveness threshold.

        IMP-LOOP-034: Evaluates all active rules and deprecates those
        that fall below the minimum effectiveness threshold, provided
        they have enough applications for a meaningful evaluation.

        Args:
            min_effectiveness: Minimum effectiveness score to remain active (default 0.3)
            min_applications: Minimum applications required for evaluation (default 3)
            days: Evaluation period in days (default 30)

        Returns:
            List of rule IDs that were deprecated
        """
        rules = load_project_rules(self.project_id)
        deprecated_ids: List[str] = []

        for rule in rules:
            # Skip already deprecated rules
            if rule.deprecated or rule.status == "deprecated":
                continue

            # Evaluate effectiveness
            report = self.evaluate_rule_effectiveness(rule.rule_id, days)

            # Skip rules with insufficient data
            if report.total_applications < min_applications:
                continue

            # Deprecate if below threshold
            if report.effectiveness_score < min_effectiveness:
                rule.deprecated = True
                rule.status = "deprecated"
                rule.effectiveness_score = report.effectiveness_score
                rule.last_validated_at = datetime.now(timezone.utc).isoformat()
                deprecated_ids.append(rule.rule_id)
                logger.info(
                    f"Deprecated rule {rule.rule_id}: effectiveness "
                    f"{report.effectiveness_score:.2f} < {min_effectiveness}"
                )
            else:
                # Update effectiveness score for active rules
                rule.effectiveness_score = report.effectiveness_score
                rule.last_validated_at = datetime.now(timezone.utc).isoformat()

        # Save updated rules
        if deprecated_ids or rules:
            _save_project_rules(self.project_id, rules)

        return deprecated_ids

    def get_all_effectiveness_reports(self, days: int = 30) -> List[RuleEffectivenessReport]:
        """Get effectiveness reports for all rules.

        Args:
            days: Evaluation period in days

        Returns:
            List of RuleEffectivenessReport for each rule
        """
        rules = load_project_rules(self.project_id)
        reports = []

        for rule in rules:
            report = self.evaluate_rule_effectiveness(rule.rule_id, days)
            reports.append(report)

        return reports


def evaluate_rule_effectiveness(
    rule_id: str, project_id: str = "autopack", days: int = 30
) -> RuleEffectivenessReport:
    """Convenience function to evaluate a single rule's effectiveness.

    IMP-LOOP-034: Wrapper around RuleEffectivenessManager for simple use cases.

    Args:
        rule_id: The rule to evaluate
        project_id: Project identifier
        days: Evaluation period in days

    Returns:
        RuleEffectivenessReport with effectiveness metrics
    """
    manager = RuleEffectivenessManager(project_id)
    return manager.evaluate_rule_effectiveness(rule_id, days)


def deprecate_ineffective_rules(
    project_id: str = "autopack",
    min_effectiveness: float = 0.3,
    min_applications: int = 3,
    days: int = 30,
) -> List[str]:
    """Convenience function to deprecate ineffective rules.

    IMP-LOOP-034: Wrapper around RuleEffectivenessManager for simple use cases.

    Args:
        project_id: Project identifier
        min_effectiveness: Minimum effectiveness threshold
        min_applications: Minimum applications for evaluation
        days: Evaluation period in days

    Returns:
        List of deprecated rule IDs
    """
    manager = RuleEffectivenessManager(project_id)
    return manager.deprecate_ineffective_rules(min_effectiveness, min_applications, days)


# ============================================================================
# Stage 0A: Run-Local Hints
# ============================================================================


def record_run_rule_hint(
    run_id: str,
    phase: Dict,
    issues_before: List,
    issues_after: List,
    context: Optional[Dict] = None,
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
        created_at=datetime.now(timezone.utc).isoformat(),
    )

    # Save to file
    _save_run_rule_hint(run_id, hint)

    return hint


def load_run_rule_hints(run_id: str) -> List[RunRuleHint]:
    """Load all hints for a run with caching.

    IMP-PERF-006: Uses run-level cache to avoid redundant file reads
    within the same run. Hints are cached per run_id and only read
    from disk once per run.

    Args:
        run_id: Run ID

    Returns:
        List of RunRuleHint objects
    """
    # Check cache first
    if run_id in _run_hints_cache:
        return _run_hints_cache[run_id]

    hints_file = _get_run_hints_file(run_id)
    if not hints_file.exists():
        # Cache empty result to avoid repeated file existence checks
        _run_hints_cache[run_id] = []
        return _run_hints_cache[run_id]

    try:
        with open(hints_file, "r") as f:
            data = json.load(f)
        hints = [RunRuleHint.from_dict(h) for h in data.get("hints", [])]
        # Cache the result
        _run_hints_cache[run_id] = hints
        return hints
    except (json.JSONDecodeError, KeyError, TypeError):
        # Cache empty result on parse errors
        _run_hints_cache[run_id] = []
        return _run_hints_cache[run_id]


def get_relevant_hints_for_phase(run_id: str, phase: Dict, max_hints: int = 5) -> List[RunRuleHint]:
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

    # Extract phase scope_paths for intersection check
    phase_scope_paths = set(_extract_scope_paths(phase, None))

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

        # P1.4: scope_paths intersection check
        # If phase has scope paths and hint has scope paths, require intersection
        if phase_scope_paths and hint.scope_paths:
            hint_paths = set(hint.scope_paths)
            if not phase_scope_paths.intersection(hint_paths):
                # No direct path match, check for directory overlap
                phase_dirs = {str(Path(p).parent) for p in phase_scope_paths}
                hint_dirs = {str(Path(p).parent) for p in hint_paths}
                if not phase_dirs.intersection(hint_dirs):
                    continue

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
                stage=DiscoveryStage.NEW.value,
            )
            rules.append(new_rule)
            promoted_count += 1

    # Save updated rules
    _save_project_rules(project_id, rules)

    return promoted_count


# ============================================================================
# IMP-LOOP-020: Cross-Run Hint/Rule Conflict Detection
# ============================================================================


# Opposing keyword pairs for semantic conflict detection
_OPPOSING_KEYWORDS = [
    (
        {"always", "require", "must", "enforce", "add", "include", "enable"},
        {"never", "avoid", "skip", "disable", "remove", "exclude", "omit"},
    ),
    ({"strict", "mandatory"}, {"optional", "flexible", "relaxed"}),
    ({"all", "every"}, {"none", "no"}),
    ({"with"}, {"without"}),
]


def detect_rule_conflicts(
    rules: List[LearnedRule],
) -> List[Tuple[LearnedRule, LearnedRule, str]]:
    """Detect potentially conflicting rules based on scope overlap and semantic analysis.

    IMP-LOOP-020: Identifies contradicting rules/hints that could cause confusion
    or inconsistent guidance during phase execution.

    Conflict detection checks:
    1. Scope overlap - both rules affect the same files/patterns
    2. Semantic contradiction - directives contain opposing keywords

    Args:
        rules: List of LearnedRule objects to check for conflicts

    Returns:
        List of (rule1, rule2, conflict_reason) tuples for each detected conflict
    """
    conflicts: List[Tuple[LearnedRule, LearnedRule, str]] = []

    # Only check active rules
    active_rules = [r for r in rules if r.status == "active"]

    for i, rule1 in enumerate(active_rules):
        for rule2 in active_rules[i + 1 :]:
            # Skip rules in different task categories (unlikely to conflict)
            if rule1.task_category != rule2.task_category:
                continue

            if _scopes_overlap(rule1, rule2):
                if _directives_conflict(rule1, rule2):
                    conflicts.append(
                        (
                            rule1,
                            rule2,
                            f"Scope overlap ({_describe_scope_overlap(rule1, rule2)}) "
                            f"with conflicting directives",
                        )
                    )

    return conflicts


def detect_hint_conflicts(
    hints: List[RunRuleHint],
) -> List[Tuple[RunRuleHint, RunRuleHint, str]]:
    """Detect potentially conflicting hints within the same run.

    Similar to detect_rule_conflicts but for run-local hints.

    Args:
        hints: List of RunRuleHint objects to check for conflicts

    Returns:
        List of (hint1, hint2, conflict_reason) tuples for each detected conflict
    """
    conflicts: List[Tuple[RunRuleHint, RunRuleHint, str]] = []

    for i, hint1 in enumerate(hints):
        for hint2 in hints[i + 1 :]:
            # Skip hints in different task categories
            if hint1.task_category != hint2.task_category:
                continue

            if _hint_scopes_overlap(hint1, hint2):
                if _hint_directives_conflict(hint1, hint2):
                    conflicts.append(
                        (
                            hint1,
                            hint2,
                            "Scope overlap with conflicting directives",
                        )
                    )

    return conflicts


def _scopes_overlap(rule1: LearnedRule, rule2: LearnedRule) -> bool:
    """Check if two rules affect overlapping file patterns.

    Two rules overlap if their scope_patterns could match the same files.

    Rules:
    - If both have no scope_pattern (None/global), they overlap
    - If one is global and the other isn't, they overlap (global affects all)
    - If both have patterns, check for pattern intersection

    Args:
        rule1: First rule to compare
        rule2: Second rule to compare

    Returns:
        True if scopes overlap, False otherwise
    """
    pattern1 = rule1.scope_pattern
    pattern2 = rule2.scope_pattern

    # Both global = overlap
    if pattern1 is None and pattern2 is None:
        return True

    # One global = overlap (global affects everything)
    if pattern1 is None or pattern2 is None:
        return True

    # Both have patterns - check for intersection
    return _patterns_can_intersect(pattern1, pattern2)


def _patterns_can_intersect(pattern1: str, pattern2: str) -> bool:
    """Check if two glob patterns could match the same files.

    Uses heuristic matching:
    - Same pattern = intersect
    - Same extension (*.py, *.py) = intersect
    - One contains the other (auth/*.py, *.py) = intersect
    - Same directory prefix = intersect

    Args:
        pattern1: First glob pattern
        pattern2: Second glob pattern

    Returns:
        True if patterns could match same files
    """
    import fnmatch

    # Normalize patterns
    p1 = pattern1.replace("\\", "/").lower()
    p2 = pattern2.replace("\\", "/").lower()

    # Exact match
    if p1 == p2:
        return True

    # Extract extensions
    ext1 = _extract_extension(p1)
    ext2 = _extract_extension(p2)

    # Different extensions = no overlap (*.py and *.js won't match same files)
    if ext1 and ext2 and ext1 != ext2:
        return False

    # Same extension with wildcards = likely overlap
    if ext1 and ext1 == ext2:
        return True

    # Check if one pattern is more general than the other
    # e.g., "*.py" matches anything "auth/*.py" matches
    if fnmatch.fnmatch(p1, p2) or fnmatch.fnmatch(p2, p1):
        return True

    # Check directory overlap
    dir1 = _extract_directory(p1)
    dir2 = _extract_directory(p2)

    if dir1 and dir2:
        # Same directory or one contains the other
        if dir1 == dir2 or dir1.startswith(dir2) or dir2.startswith(dir1):
            return True

    # Default: assume no overlap for distinct patterns
    return False


def _extract_extension(pattern: str) -> Optional[str]:
    """Extract file extension from a glob pattern."""
    if "*." in pattern:
        # Find the extension after the last *.
        parts = pattern.split("*.")
        if len(parts) > 1:
            ext = parts[-1]
            # Handle patterns like "*.py" or "src/*.py"
            if "/" not in ext and "\\" not in ext:
                return f".{ext}"
    return None


def _extract_directory(pattern: str) -> Optional[str]:
    """Extract directory prefix from a glob pattern."""
    if "/" in pattern:
        parts = pattern.rsplit("/", 1)
        if parts[0] and not parts[0].startswith("*"):
            return parts[0]
    return None


def _directives_conflict(rule1: LearnedRule, rule2: LearnedRule) -> bool:
    """Check if rule constraints/directives are semantically contradictory.

    Uses keyword matching to detect opposing directives like:
    - "always add type hints" vs "skip type hints for tests"
    - "require docstrings" vs "avoid docstrings"

    Args:
        rule1: First rule to compare
        rule2: Second rule to compare

    Returns:
        True if directives appear to conflict
    """
    text1 = rule1.constraint.lower()
    text2 = rule2.constraint.lower()

    # Tokenize
    words1 = set(text1.split())
    words2 = set(text2.split())

    # Check for opposing keyword pairs
    for positive_set, negative_set in _OPPOSING_KEYWORDS:
        has_positive_1 = bool(words1 & positive_set)
        has_negative_1 = bool(words1 & negative_set)
        has_positive_2 = bool(words2 & positive_set)
        has_negative_2 = bool(words2 & negative_set)

        # Rule1 positive + Rule2 negative = conflict
        if has_positive_1 and has_negative_2:
            # Verify they're discussing the same topic
            if _share_topic_keywords(words1, words2):
                return True

        # Rule1 negative + Rule2 positive = conflict
        if has_negative_1 and has_positive_2:
            if _share_topic_keywords(words1, words2):
                return True

    return False


def _share_topic_keywords(words1: set, words2: set) -> bool:
    """Check if two word sets share topic-related keywords.

    Filters out common words to focus on topic-specific terms.

    Args:
        words1: First set of words
        words2: Second set of words

    Returns:
        True if they share meaningful topic words
    """
    # Common words to ignore
    stop_words = {
        "the",
        "a",
        "an",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "have",
        "has",
        "had",
        "do",
        "does",
        "did",
        "will",
        "would",
        "could",
        "should",
        "may",
        "might",
        "must",
        "shall",
        "can",
        "need",
        "to",
        "of",
        "in",
        "for",
        "on",
        "with",
        "at",
        "by",
        "from",
        "as",
        "into",
        "through",
        "during",
        "before",
        "after",
        "above",
        "below",
        "between",
        "under",
        "again",
        "further",
        "then",
        "once",
        "here",
        "there",
        "when",
        "where",
        "why",
        "how",
        "all",
        "each",
        "few",
        "more",
        "most",
        "other",
        "some",
        "such",
        "no",
        "nor",
        "not",
        "only",
        "own",
        "same",
        "so",
        "than",
        "too",
        "very",
        "just",
        "and",
        "but",
        "if",
        "or",
        "because",
        "until",
        "while",
        "this",
        "that",
        "these",
        "those",
        "always",
        "never",
        "require",
        "avoid",
        "add",
        "skip",
        "include",
        "exclude",
        "enable",
        "disable",
        "watch",
        "out",
        "working",
        "tasks",
        "issues",
    }

    # Get meaningful words
    meaningful1 = words1 - stop_words
    meaningful2 = words2 - stop_words

    # Need at least 1 shared meaningful word to consider same topic
    shared = meaningful1 & meaningful2
    return len(shared) >= 1


def _hint_scopes_overlap(hint1: RunRuleHint, hint2: RunRuleHint) -> bool:
    """Check if two hints affect overlapping file paths."""
    if not hint1.scope_paths and not hint2.scope_paths:
        return True  # Both global

    if not hint1.scope_paths or not hint2.scope_paths:
        return True  # One is global

    # Check for direct path overlap or directory overlap
    paths1 = set(hint1.scope_paths)
    paths2 = set(hint2.scope_paths)

    if paths1 & paths2:
        return True  # Direct path overlap

    # Check directory overlap
    dirs1 = {str(Path(p).parent) for p in paths1}
    dirs2 = {str(Path(p).parent) for p in paths2}

    return bool(dirs1 & dirs2)


def _hint_directives_conflict(hint1: RunRuleHint, hint2: RunRuleHint) -> bool:
    """Check if hint texts are semantically contradictory."""
    text1 = hint1.hint_text.lower()
    text2 = hint2.hint_text.lower()

    words1 = set(text1.split())
    words2 = set(text2.split())

    for positive_set, negative_set in _OPPOSING_KEYWORDS:
        has_positive_1 = bool(words1 & positive_set)
        has_negative_1 = bool(words1 & negative_set)
        has_positive_2 = bool(words2 & positive_set)
        has_negative_2 = bool(words2 & negative_set)

        if (has_positive_1 and has_negative_2) or (has_negative_1 and has_positive_2):
            if _share_topic_keywords(words1, words2):
                return True

    return False


def _describe_scope_overlap(rule1: LearnedRule, rule2: LearnedRule) -> str:
    """Generate a human-readable description of the scope overlap."""
    p1 = rule1.scope_pattern or "global"
    p2 = rule2.scope_pattern or "global"

    if p1 == "global" and p2 == "global":
        return "both global"
    elif p1 == "global":
        return f"global vs {p2}"
    elif p2 == "global":
        return f"{p1} vs global"
    else:
        return f"{p1} vs {p2}"


def get_conflicts_for_project(project_id: str) -> List[Tuple[LearnedRule, LearnedRule, str]]:
    """Get all rule conflicts for a project.

    Convenience function that loads project rules and detects conflicts.

    Args:
        project_id: Project identifier

    Returns:
        List of (rule1, rule2, conflict_reason) tuples
    """
    rules = load_project_rules(project_id)
    return detect_rule_conflicts(rules)


def format_conflicts_report(
    conflicts: List[Tuple[LearnedRule, LearnedRule, str]],
) -> str:
    """Format conflicts into a human-readable report.

    Args:
        conflicts: List of conflict tuples from detect_rule_conflicts

    Returns:
        Formatted string report
    """
    if not conflicts:
        return "No conflicts detected."

    lines = [f"Detected {len(conflicts)} potential rule conflict(s):\n"]

    for i, (rule1, rule2, reason) in enumerate(conflicts, 1):
        lines.append(f"--- Conflict {i} ---")
        lines.append(f"Rule A: [{rule1.rule_id}] {rule1.constraint}")
        lines.append(f"Rule B: [{rule2.rule_id}] {rule2.constraint}")
        lines.append(f"Reason: {reason}")
        lines.append("")

    return "\n".join(lines)


def promote_hints_with_conflict_check(
    run_id: str, project_id: str
) -> Tuple[int, List[Tuple[LearnedRule, LearnedRule, str]]]:
    """Promote hints to rules and check for conflicts.

    IMP-LOOP-020: Extended version of promote_hints_to_rules that also
    detects and returns any conflicts among the resulting rules.

    Args:
        run_id: Run ID
        project_id: Project ID

    Returns:
        Tuple of (promoted_count, conflicts) where:
        - promoted_count: Number of rules promoted
        - conflicts: List of (rule1, rule2, reason) tuples for detected conflicts
    """
    promoted_count = promote_hints_to_rules(run_id, project_id)

    # After promotion, check for conflicts
    rules = load_project_rules(project_id)
    conflicts = detect_rule_conflicts(rules)

    # Log warnings for any detected conflicts
    if conflicts:
        logger.warning(
            f"Detected {len(conflicts)} potential rule conflict(s) in project '{project_id}'"
        )
        for rule1, rule2, reason in conflicts:
            logger.warning(f"  Conflict: [{rule1.rule_id}] vs [{rule2.rule_id}]: {reason}")

    return promoted_count, conflicts


def load_project_rules(project_id: str) -> List[LearnedRule]:
    """Load all project rules with mtime-based caching.

    IMP-PERF-003: Uses process-level cache with mtime checking to avoid
    redundant file reads. Cache is invalidated when file modification
    time changes.

    Args:
        project_id: Project ID

    Returns:
        List of LearnedRule objects
    """
    rules_file = _get_project_rules_file(project_id)
    if not rules_file.exists():
        # Clear any stale cache entry if file was deleted
        _project_rules_cache.pop(project_id, None)
        _project_rules_mtime.pop(project_id, None)
        return []

    try:
        # Get current file modification time
        current_mtime = os.path.getmtime(rules_file)

        # Check cache: return cached data if mtime unchanged
        if project_id in _project_rules_cache:
            cached_mtime = _project_rules_mtime.get(project_id)
            if cached_mtime == current_mtime:
                return _project_rules_cache[project_id]

        # Cache miss or stale: read from file
        with open(rules_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        rules = [LearnedRule.from_dict(r) for r in data.get("rules", [])]

        # Update cache
        _project_rules_cache[project_id] = rules
        _project_rules_mtime[project_id] = current_mtime

        return rules
    except (json.JSONDecodeError, KeyError, TypeError):
        return []
    except OSError:
        # Handle file system errors gracefully
        return []


def get_active_rules_for_phase(
    project_id: str, phase: Dict, max_rules: int = 10
) -> List[LearnedRule]:
    """Get active rules relevant to this phase

    Filters by:
    - status == "active"
    - stage == "rule" (only fully promoted rules)
    - task_category match
    - scope_pattern match
    - IMP-LOOP-018: Not deprecated by aging (decay_score <= 0.7)

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

    # Extract phase scope_paths for pattern matching
    phase_scope_paths = _extract_scope_paths(phase, None)

    # IMP-LOOP-018: Initialize aging tracker for deprecation filtering
    aging_tracker = RuleAgingTracker(project_id)

    # Filter relevant rules
    relevant = []
    for rule in all_rules:
        # Only active rules at RULE stage
        if rule.status != "active" or rule.stage != DiscoveryStage.RULE.value:
            continue

        # IMP-LOOP-018: Filter out deprecated rules based on aging
        if aging_tracker.should_deprecate(rule.rule_id):
            continue

        # Match task_category if both have it
        if task_category and rule.task_category:
            if rule.task_category != task_category:
                continue

        # P1.4: scope_pattern matching
        if rule.scope_pattern and phase_scope_paths:
            if not _matches_scope_pattern(rule.scope_pattern, phase_scope_paths):
                continue

        relevant.append(rule)

    # Return most promoted first, limited
    relevant.sort(key=lambda r: r.promotion_count, reverse=True)
    return relevant[:max_rules]


def get_active_rules_with_conflicts(
    project_id: str, phase: Dict, max_rules: int = 10
) -> Tuple[List[LearnedRule], List[Tuple[LearnedRule, LearnedRule, str]]]:
    """Get active rules for phase along with any detected conflicts.

    IMP-LOOP-020: Extended version of get_active_rules_for_phase that also
    returns detected conflicts among the returned rules.

    Args:
        project_id: Project ID
        phase: Phase dict
        max_rules: Maximum number of rules to return

    Returns:
        Tuple of (rules, conflicts) where:
        - rules: List of relevant LearnedRule objects
        - conflicts: List of (rule1, rule2, reason) tuples for any conflicts
    """
    rules = get_active_rules_for_phase(project_id, phase, max_rules)

    # Detect conflicts among returned rules
    conflicts = detect_rule_conflicts(rules)

    return rules, conflicts


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
        DiscoveryStage.RULE,
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
                "require_human_approval": True,
            }

        with open(config_path, "r") as f:
            config = yaml.safe_load(f)

        return config.get(
            "discovery_promotion",
            {
                "enabled": False,
                "min_runs_for_candidate": 3,
                "window_days": 30,
                "min_severity_for_candidate": "medium",
                "require_human_approval": True,
            },
        )
    except Exception:
        # Return defaults on any error
        return {
            "enabled": False,
            "min_runs_for_candidate": 3,
            "window_days": 30,
            "min_severity_for_candidate": "medium",
            "require_human_approval": True,
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


def _matches_scope_pattern(scope_pattern: str, phase_scope_paths: List[str]) -> bool:
    """Check if any phase path matches the rule's scope pattern

    Supports glob-style patterns:
    - "*.py" matches any .py file
    - "auth/*.py" matches .py files in auth/ directory
    - "src/autopack/*" matches anything in src/autopack/

    Args:
        scope_pattern: Glob-style pattern (e.g., "*.py", "auth/*.py")
        phase_scope_paths: List of file paths from the phase

    Returns:
        True if any path matches the pattern
    """
    import fnmatch

    if not scope_pattern or not phase_scope_paths:
        return False

    # Normalize pattern for cross-platform matching
    pattern = scope_pattern.replace("\\", "/")

    for path in phase_scope_paths:
        # Normalize path for matching
        normalized_path = str(path).replace("\\", "/")

        # Try direct match
        if fnmatch.fnmatch(normalized_path, pattern):
            return True

        # Try matching just the filename for patterns like "*.py"
        if "/" not in pattern:
            filename = Path(normalized_path).name
            if fnmatch.fnmatch(filename, pattern):
                return True

        # Try matching from the end for patterns like "auth/*.py"
        # This handles cases where phase path is "src/autopack/auth/login.py"
        # and pattern is "auth/*.py"
        if fnmatch.fnmatch(normalized_path, f"*/{pattern}"):
            return True

    return False


def _generate_rule_id(hint: RunRuleHint) -> str:
    """Generate unique rule ID from hint"""
    import hashlib

    # Use hint text + category for ID
    text = f"{hint.task_category}:{hint.hint_text}"
    text_hash = hashlib.md5(text.encode()).hexdigest()[:8]

    category = hint.task_category or "general"
    return f"{category}.rule_{text_hash}"


def _get_run_hints_file(run_id: str) -> Path:
    """Get path to run hints file (P2.2: respects autonomous_runs_dir)"""
    from .config import settings

    return Path(settings.autonomous_runs_dir) / run_id / "run_rule_hints.json"


def _get_project_rules_file(project_id: str) -> Path:
    """Get path to project rules file

    Returns the SOT location for learned rules in docs/ directory.
    For main Autopack project: docs/LEARNED_RULES.json
    For sub-projects: {autonomous_runs_dir}/{project}/docs/LEARNED_RULES.json (P2.2)
    """
    if project_id == "autopack":
        return Path("docs") / "LEARNED_RULES.json"
    else:
        from .config import settings

        return Path(settings.autonomous_runs_dir) / project_id / "docs" / "LEARNED_RULES.json"


def _save_run_rule_hint(run_id: str, hint: RunRuleHint):
    """Save hint to run hints file.

    IMP-PERF-006: Invalidates the cache for this run_id to ensure
    subsequent loads reflect the saved changes.
    """
    hints_file = _get_run_hints_file(run_id)
    hints_file.parent.mkdir(parents=True, exist_ok=True)

    # Load existing hints (may come from cache)
    hints = load_run_rule_hints(run_id)
    hints.append(hint)

    # Save
    with open(hints_file, "w", encoding="utf-8") as f:
        json.dump({"hints": [h.to_dict() for h in hints]}, f, indent=2)

    # Invalidate cache after save to ensure fresh read on next load
    clear_run_hints_cache(run_id)


def _save_project_rules(project_id: str, rules: List[LearnedRule]):
    """Save rules to project rules file.

    IMP-PERF-003: Invalidates the cache for this project to ensure
    subsequent loads reflect the saved changes.
    """
    rules_file = _get_project_rules_file(project_id)
    rules_file.parent.mkdir(parents=True, exist_ok=True)

    with open(rules_file, "w", encoding="utf-8") as f:
        json.dump({"rules": [r.to_dict() for r in rules]}, f, indent=2)

    # Invalidate cache after save to ensure fresh read on next load
    _project_rules_cache.pop(project_id, None)
    _project_rules_mtime.pop(project_id, None)


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
    source_issue_keys: Optional[List[str]] = None,
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
        created_at=datetime.now(timezone.utc).isoformat(),
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
