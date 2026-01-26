"""Telemetry Analysis Module for Self-Improvement Loop.

Analyzes operational telemetry to identify patterns and generate improvements.
Reads from nudge_state.json, ci_retry_state.json, and slot_history.json to
detect recurring issues and suggest actionable improvements.
"""

from __future__ import annotations

import json
import logging
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.improvement_generator import ImprovementGenerator

logger = logging.getLogger(__name__)


class TelemetryAnalyzer:
    """Analyzes telemetry files to detect patterns and generate improvement suggestions.

    This class provides methods to analyze operational telemetry from three sources:
    - nudge_state.json: Tracks nudge events and escalations
    - ci_retry_state.json: Records CI retry patterns and outcomes
    - slot_history.json: Contains slot allocation and event history

    The analysis identifies patterns that indicate systemic issues and generates
    improvement suggestions that can be fed back into the self-improvement loop.
    """

    # Minimum occurrences to consider a pattern significant
    MIN_PATTERN_THRESHOLD = 2
    # Minimum failure rate to flag as concerning
    FAILURE_RATE_THRESHOLD = 0.3
    # Minimum retries to consider a test flaky
    FLAKY_TEST_RETRY_THRESHOLD = 2

    def __init__(self, base_path: str | Path) -> None:
        """Initialize the TelemetryAnalyzer with paths to telemetry files.

        Args:
            base_path: Directory containing the telemetry JSON files.
        """
        self.base_path = Path(base_path)
        self.nudge_state_file = self.base_path / "nudge_state.json"
        self.ci_retry_file = self.base_path / "ci_retry_state.json"
        self.slot_history_file = self.base_path / "slot_history.json"

        # Cache for loaded data
        self._nudge_data: dict[str, Any] | None = None
        self._ci_retry_data: dict[str, Any] | None = None
        self._slot_history_data: dict[str, Any] | None = None

    def _load_json_file(self, file_path: Path) -> dict[str, Any]:
        """Load and parse a JSON file.

        Args:
            file_path: Path to the JSON file.

        Returns:
            Parsed JSON data or empty dict if file doesn't exist or is invalid.
        """
        if not file_path.exists():
            logger.debug("Telemetry file not found: %s", file_path)
            return {}

        try:
            with open(file_path, encoding="utf-8") as f:
                data = json.load(f)
                logger.debug("Loaded %s with %d entries", file_path.name, len(data))
                return data
        except json.JSONDecodeError as e:
            logger.warning("Failed to parse %s: %s", file_path.name, e)
            return {}
        except OSError as e:
            logger.warning("Failed to read %s: %s", file_path.name, e)
            return {}

    def _get_nudge_data(self) -> dict[str, Any]:
        """Get nudge state data, loading from file if not cached."""
        if self._nudge_data is None:
            self._nudge_data = self._load_json_file(self.nudge_state_file)
        return self._nudge_data

    def _get_ci_retry_data(self) -> dict[str, Any]:
        """Get CI retry state data, loading from file if not cached."""
        if self._ci_retry_data is None:
            self._ci_retry_data = self._load_json_file(self.ci_retry_file)
        return self._ci_retry_data

    def _get_slot_history_data(self) -> dict[str, Any]:
        """Get slot history data, loading from file if not cached."""
        if self._slot_history_data is None:
            self._slot_history_data = self._load_json_file(self.slot_history_file)
        return self._slot_history_data

    def analyze_failure_patterns(self) -> list[dict[str, Any]]:
        """Analyze nudge_state.json for recurring failure patterns.

        Examines nudge events to identify:
        - Repeated failure types
        - Phase types that frequently fail
        - Escalation patterns

        Returns:
            List of detected failure patterns with metadata.
        """
        patterns: list[dict[str, Any]] = []
        nudge_data = self._get_nudge_data()

        if not nudge_data:
            logger.info("No nudge state data available for failure pattern analysis")
            return patterns

        # Count failure reasons
        failure_reasons: Counter[str] = Counter()
        phase_failures: Counter[str] = Counter()
        escalation_triggers: Counter[str] = Counter()

        # Process nudges list if present
        nudges = nudge_data.get("nudges", [])
        if isinstance(nudges, list):
            for nudge in nudges:
                if not isinstance(nudge, dict):
                    continue

                # Track failure reasons
                reason = nudge.get("failure_reason", nudge.get("reason"))
                if reason:
                    failure_reasons[reason] += 1

                # Track phase failures
                phase_type = nudge.get("phase_type", nudge.get("phase"))
                status = nudge.get("status", "").lower()
                if phase_type and status in ("failed", "error", "timeout"):
                    phase_failures[phase_type] += 1

                # Track escalation triggers
                if nudge.get("escalated", False):
                    trigger = nudge.get("escalation_trigger", "unknown")
                    escalation_triggers[trigger] += 1

        # Also check top-level fields for flat structure
        if nudge_data.get("failure_reason"):
            failure_reasons[nudge_data["failure_reason"]] += 1
        if nudge_data.get("phase_type") and nudge_data.get("status", "").lower() in (
            "failed",
            "error",
        ):
            phase_failures[nudge_data["phase_type"]] += 1

        # Generate patterns from failure reasons
        for reason, count in failure_reasons.most_common():
            if count >= self.MIN_PATTERN_THRESHOLD:
                patterns.append(
                    {
                        "pattern_type": "repeated_failure",
                        "failure_reason": reason,
                        "occurrence_count": count,
                        "severity": "high" if count >= 5 else "medium",
                        "description": f"Failure reason '{reason}' occurred {count} times",
                        "source": "nudge_state",
                    }
                )

        # Generate patterns from phase failures
        for phase_type, count in phase_failures.most_common():
            if count >= self.MIN_PATTERN_THRESHOLD:
                patterns.append(
                    {
                        "pattern_type": "phase_failure",
                        "phase_type": phase_type,
                        "occurrence_count": count,
                        "severity": "high" if count >= 3 else "medium",
                        "description": f"Phase type '{phase_type}' failed {count} times",
                        "source": "nudge_state",
                    }
                )

        # Generate patterns from escalations
        for trigger, count in escalation_triggers.most_common():
            if count >= self.MIN_PATTERN_THRESHOLD:
                patterns.append(
                    {
                        "pattern_type": "escalation_pattern",
                        "trigger": trigger,
                        "occurrence_count": count,
                        "severity": "medium",
                        "description": f"Escalation triggered by '{trigger}' occurred {count} times",
                        "source": "nudge_state",
                    }
                )

        logger.info(
            "Analyzed nudge state: found %d failure patterns from %d nudges",
            len(patterns),
            len(nudges),
        )
        return patterns

    def analyze_ci_patterns(self) -> list[dict[str, Any]]:
        """Analyze CI retry patterns to identify flaky tests vs code issues.

        Examines ci_retry_state.json to detect:
        - Flaky tests (succeed on retry without code changes)
        - Consistent failures (same tests failing repeatedly)
        - CI infrastructure issues

        Returns:
            List of detected CI patterns with metadata.
        """
        patterns: list[dict[str, Any]] = []
        ci_data = self._get_ci_retry_data()

        if not ci_data:
            logger.info("No CI retry data available for pattern analysis")
            return patterns

        # Track retries by test/workflow
        test_retries: dict[str, list[dict[str, Any]]] = {}
        workflow_failures: Counter[str] = Counter()
        failure_reasons: Counter[str] = Counter()

        retries = ci_data.get("retries", [])
        if isinstance(retries, list):
            for retry in retries:
                if not isinstance(retry, dict):
                    continue

                # Group by test or workflow identifier
                test_id = retry.get(
                    "test_name", retry.get("workflow", retry.get("run_id", "unknown"))
                )
                if test_id not in test_retries:
                    test_retries[test_id] = []
                test_retries[test_id].append(retry)

                # Track failure reasons
                outcome = retry.get("outcome", "").lower()
                if outcome in ("failed", "error"):
                    reason = retry.get("failure_reason", "unknown")
                    failure_reasons[reason] += 1

                    workflow = retry.get("workflow", "unknown")
                    workflow_failures[workflow] += 1

        # Identify flaky tests (multiple retries, eventually succeed)
        for test_id, retry_list in test_retries.items():
            if len(retry_list) < self.FLAKY_TEST_RETRY_THRESHOLD:
                continue

            # Check if any retry succeeded
            outcomes = [r.get("outcome", "").lower() for r in retry_list]
            has_success = any(o in ("success", "passed") for o in outcomes)
            has_failure = any(o in ("failed", "error") for o in outcomes)

            if has_success and has_failure:
                # Flaky test pattern
                patterns.append(
                    {
                        "pattern_type": "flaky_test",
                        "test_id": test_id,
                        "retry_count": len(retry_list),
                        "success_rate": outcomes.count("success") / len(outcomes),
                        "severity": "high",
                        "description": f"Test '{test_id}' is flaky - {len(retry_list)} retries with mixed outcomes",
                        "source": "ci_retry_state",
                    }
                )
            elif not has_success and len(retry_list) >= 3:
                # Consistent failure pattern
                patterns.append(
                    {
                        "pattern_type": "consistent_ci_failure",
                        "test_id": test_id,
                        "failure_count": len(retry_list),
                        "severity": "critical",
                        "description": f"Test '{test_id}' consistently fails - {len(retry_list)} failures",
                        "source": "ci_retry_state",
                    }
                )

        # Identify workflows with high failure rates
        for workflow, count in workflow_failures.most_common():
            if count >= self.MIN_PATTERN_THRESHOLD:
                patterns.append(
                    {
                        "pattern_type": "workflow_failure",
                        "workflow": workflow,
                        "failure_count": count,
                        "severity": "medium" if count < 5 else "high",
                        "description": f"Workflow '{workflow}' failed {count} times",
                        "source": "ci_retry_state",
                    }
                )

        # Common failure reasons
        for reason, count in failure_reasons.most_common(5):
            if count >= self.MIN_PATTERN_THRESHOLD:
                patterns.append(
                    {
                        "pattern_type": "ci_failure_reason",
                        "failure_reason": reason,
                        "occurrence_count": count,
                        "severity": "medium",
                        "description": f"CI failure reason '{reason}' occurred {count} times",
                        "source": "ci_retry_state",
                    }
                )

        logger.info(
            "Analyzed CI patterns: found %d patterns from %d retries",
            len(patterns),
            len(retries),
        )
        return patterns

    def analyze_slot_behavior(self) -> list[dict[str, Any]]:
        """Analyze slot history for problematic behavior patterns.

        Examines slot_history.json to detect:
        - Slots with high failure rates
        - Connection error patterns
        - Stagnation events
        - Unusual event sequences

        Returns:
            List of detected slot behavior patterns with metadata.
        """
        patterns: list[dict[str, Any]] = []
        slot_data = self._get_slot_history_data()

        if not slot_data:
            logger.info("No slot history data available for behavior analysis")
            return patterns

        # Track per-slot statistics
        slot_stats: dict[int, dict[str, Any]] = {}
        event_type_counts: Counter[str] = Counter()
        error_types: Counter[str] = Counter()

        # Process slots array
        slots = slot_data.get("slots", [])
        if isinstance(slots, list):
            for slot in slots:
                if not isinstance(slot, dict):
                    continue

                slot_id = slot.get("slot_id", slot.get("slot", 0))
                if slot_id not in slot_stats:
                    slot_stats[slot_id] = {"total": 0, "failed": 0, "events": []}

                slot_stats[slot_id]["total"] += 1
                status = slot.get("status", "").lower()
                if status in ("failed", "error", "timeout"):
                    slot_stats[slot_id]["failed"] += 1

                # Track event types
                event_type = slot.get("event_type", slot.get("type"))
                if event_type:
                    event_type_counts[event_type] += 1
                    slot_stats[slot_id]["events"].append(event_type)

                # Track error types
                error_type = slot.get("error_type", slot.get("failure_category"))
                if error_type:
                    error_types[error_type] += 1

        # Process events array if present
        events = slot_data.get("events", [])
        if isinstance(events, list):
            for event in events:
                if not isinstance(event, dict):
                    continue

                event_type = event.get("event_type", event.get("type"))
                if event_type:
                    event_type_counts[event_type] += 1

                slot_id = event.get("slot", event.get("slot_id", 0))
                if slot_id not in slot_stats:
                    slot_stats[slot_id] = {"total": 0, "failed": 0, "events": []}
                slot_stats[slot_id]["events"].append(event_type)

        # Identify problematic slots
        for slot_id, stats in slot_stats.items():
            if stats["total"] > 0:
                failure_rate = stats["failed"] / stats["total"]
                if failure_rate >= self.FAILURE_RATE_THRESHOLD:
                    patterns.append(
                        {
                            "pattern_type": "slot_high_failure_rate",
                            "slot_id": slot_id,
                            "failure_rate": round(failure_rate, 2),
                            "total_events": stats["total"],
                            "failed_events": stats["failed"],
                            "severity": "high" if failure_rate >= 0.5 else "medium",
                            "description": f"Slot {slot_id} has {failure_rate:.0%} failure rate",
                            "source": "slot_history",
                        }
                    )

        # Identify concerning event patterns
        problematic_events = [
            "connection_error_detected",
            "stagnation_detected",
            "escalation_level_change",
            "error_recovery_success",
        ]
        for event_type in problematic_events:
            count = event_type_counts.get(event_type, 0)
            if count >= self.MIN_PATTERN_THRESHOLD:
                patterns.append(
                    {
                        "pattern_type": "frequent_event",
                        "event_type": event_type,
                        "occurrence_count": count,
                        "severity": "medium" if count < 5 else "high",
                        "description": f"Event '{event_type}' occurred {count} times",
                        "source": "slot_history",
                    }
                )

        # Track common error types
        for error_type, count in error_types.most_common(5):
            if count >= self.MIN_PATTERN_THRESHOLD:
                patterns.append(
                    {
                        "pattern_type": "slot_error_type",
                        "error_type": error_type,
                        "occurrence_count": count,
                        "severity": "medium",
                        "description": f"Error type '{error_type}' occurred {count} times in slots",
                        "source": "slot_history",
                    }
                )

        logger.info(
            "Analyzed slot behavior: found %d patterns from %d slots, %d events",
            len(patterns),
            len(slots),
            len(events),
        )
        return patterns

    def generate_improvement_suggestions(self) -> list[dict[str, Any]]:
        """Generate improvement suggestions based on all telemetry analysis.

        Aggregates patterns from all analysis methods and converts them into
        actionable improvement suggestions formatted for the self-improvement loop.

        Returns:
            List of improvement suggestions in IMP-compatible format.
        """
        suggestions: list[dict[str, Any]] = []

        # Gather all patterns
        failure_patterns = self.analyze_failure_patterns()
        ci_patterns = self.analyze_ci_patterns()
        slot_patterns = self.analyze_slot_behavior()

        all_patterns = failure_patterns + ci_patterns + slot_patterns

        # Map pattern types to improvement categories
        pattern_to_category = {
            "repeated_failure": "reliability",
            "phase_failure": "automation",
            "escalation_pattern": "automation",
            "flaky_test": "testing",
            "consistent_ci_failure": "testing",
            "workflow_failure": "ci_cd",
            "ci_failure_reason": "ci_cd",
            "slot_high_failure_rate": "reliability",
            "frequent_event": "monitoring",
            "slot_error_type": "reliability",
        }

        # Map severity to priority
        severity_to_priority = {
            "critical": "critical",
            "high": "high",
            "medium": "medium",
            "low": "low",
        }

        # Generate suggestions from patterns
        for pattern in all_patterns:
            pattern_type = pattern.get("pattern_type", "unknown")
            severity = pattern.get("severity", "medium")
            description = pattern.get("description", "")

            # Generate title based on pattern type
            title = self._generate_suggestion_title(pattern)

            # Generate recommended action
            action = self._generate_recommended_action(pattern)

            suggestion = {
                "id": f"AUTO-{pattern_type.upper()}-{hash(description) % 10000:04d}",
                "title": title,
                "category": pattern_to_category.get(pattern_type, "general"),
                "priority": severity_to_priority.get(severity, "medium"),
                "description": description,
                "recommended_action": action,
                "source_pattern": pattern_type,
                "occurrence_count": pattern.get("occurrence_count", 1),
                "telemetry_source": pattern.get("source", "unknown"),
                "detected_at": datetime.now().isoformat(),
                "auto_generated": True,
            }
            suggestions.append(suggestion)

        # Sort by priority
        priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        suggestions.sort(key=lambda s: priority_order.get(s["priority"], 4))

        logger.info(
            "Generated %d improvement suggestions from %d total patterns",
            len(suggestions),
            len(all_patterns),
        )
        return suggestions

    def _generate_suggestion_title(self, pattern: dict[str, Any]) -> str:
        """Generate a descriptive title for an improvement suggestion.

        Args:
            pattern: The detected pattern dictionary.

        Returns:
            Human-readable title for the improvement.
        """
        pattern_type = pattern.get("pattern_type", "")

        if pattern_type == "flaky_test":
            test_id = pattern.get("test_id", "unknown")
            return f"Fix flaky test: {test_id}"
        elif pattern_type == "consistent_ci_failure":
            test_id = pattern.get("test_id", "unknown")
            return f"Investigate consistent CI failure: {test_id}"
        elif pattern_type == "repeated_failure":
            reason = pattern.get("failure_reason", "unknown")
            return f"Address repeated failure: {reason}"
        elif pattern_type == "phase_failure":
            phase_type = pattern.get("phase_type", "unknown")
            return f"Improve reliability of phase: {phase_type}"
        elif pattern_type == "slot_high_failure_rate":
            slot_id = pattern.get("slot_id", "unknown")
            return f"Investigate high failure rate in slot {slot_id}"
        elif pattern_type == "workflow_failure":
            workflow = pattern.get("workflow", "unknown")
            return f"Fix workflow failures: {workflow}"
        elif pattern_type == "frequent_event":
            event_type = pattern.get("event_type", "unknown")
            return f"Reduce frequency of: {event_type}"
        else:
            return f"Address pattern: {pattern_type}"

    def _generate_recommended_action(self, pattern: dict[str, Any]) -> str:
        """Generate a recommended action for addressing a pattern.

        Args:
            pattern: The detected pattern dictionary.

        Returns:
            Actionable recommendation string.
        """
        pattern_type = pattern.get("pattern_type", "")

        if pattern_type == "flaky_test":
            return (
                "Review test for race conditions, timing issues, or external dependencies. "
                "Consider adding retries or stabilizing the test environment."
            )
        elif pattern_type == "consistent_ci_failure":
            return (
                "Investigate the root cause of consistent failures. "
                "Check for environment issues, missing dependencies, or code changes."
            )
        elif pattern_type == "repeated_failure":
            reason = pattern.get("failure_reason", "")
            return (
                f"Analyze occurrences of '{reason}' failures and implement mitigation strategies."
            )
        elif pattern_type == "phase_failure":
            return (
                "Review phase implementation for robustness. "
                "Consider adding better error handling or validation."
            )
        elif pattern_type == "slot_high_failure_rate":
            return (
                "Investigate slot configuration and resource allocation. "
                "Check for capacity issues or conflicting operations."
            )
        elif pattern_type == "escalation_pattern":
            return (
                "Review escalation thresholds and automated resolution capabilities. "
                "Consider adding intermediate handling steps."
            )
        elif pattern_type == "frequent_event":
            event_type = pattern.get("event_type", "")
            return f"Investigate root cause of frequent '{event_type}' events and implement prevention."
        else:
            return "Review the pattern and implement appropriate improvements."

    def get_summary(self) -> dict[str, Any]:
        """Get a summary of all telemetry analysis.

        Returns:
            Dictionary containing analysis summary with pattern counts and suggestions.
        """
        failure_patterns = self.analyze_failure_patterns()
        ci_patterns = self.analyze_ci_patterns()
        slot_patterns = self.analyze_slot_behavior()
        suggestions = self.generate_improvement_suggestions()

        return {
            "analysis_timestamp": datetime.now().isoformat(),
            "base_path": str(self.base_path),
            "pattern_counts": {
                "failure_patterns": len(failure_patterns),
                "ci_patterns": len(ci_patterns),
                "slot_patterns": len(slot_patterns),
                "total_patterns": len(failure_patterns) + len(ci_patterns) + len(slot_patterns),
            },
            "suggestion_count": len(suggestions),
            "suggestions_by_priority": {
                "critical": sum(1 for s in suggestions if s["priority"] == "critical"),
                "high": sum(1 for s in suggestions if s["priority"] == "high"),
                "medium": sum(1 for s in suggestions if s["priority"] == "medium"),
                "low": sum(1 for s in suggestions if s["priority"] == "low"),
            },
            "suggestions_by_category": self._count_by_key(suggestions, "category"),
            "patterns": {
                "failure_patterns": failure_patterns,
                "ci_patterns": ci_patterns,
                "slot_patterns": slot_patterns,
            },
            "suggestions": suggestions,
        }

    def _count_by_key(self, items: list[dict[str, Any]], key: str) -> dict[str, int]:
        """Count items grouped by a key.

        Args:
            items: List of dictionaries.
            key: Key to group by.

        Returns:
            Dictionary mapping key values to counts.
        """
        counts: Counter[str] = Counter()
        for item in items:
            value = item.get(key, "unknown")
            counts[value] += 1
        return dict(counts)

    def clear_cache(self) -> None:
        """Clear cached telemetry data to force reload on next analysis."""
        self._nudge_data = None
        self._ci_retry_data = None
        self._slot_history_data = None
        logger.debug("Cleared telemetry data cache")

    def get_all_patterns(self) -> list[dict[str, Any]]:
        """Get all detected patterns from all telemetry sources.

        Convenience method that aggregates patterns from all analysis methods.

        Returns:
            Combined list of patterns from failure, CI, and slot analysis.
        """
        failure_patterns = self.analyze_failure_patterns()
        ci_patterns = self.analyze_ci_patterns()
        slot_patterns = self.analyze_slot_behavior()

        all_patterns = failure_patterns + ci_patterns + slot_patterns
        logger.info(
            "Collected %d total patterns: %d failure, %d CI, %d slot",
            len(all_patterns),
            len(failure_patterns),
            len(ci_patterns),
            len(slot_patterns),
        )
        return all_patterns

    def generate_improvements_to_master(
        self,
        master_file_path: str | Path,
    ) -> int:
        """Generate improvements from patterns and append to master file.

        This method bridges pattern detection with the ImprovementGenerator,
        creating a complete pipeline from telemetry analysis to IMP entries.

        Args:
            master_file_path: Path to AUTOPACK_IMPS_MASTER.json file.

        Returns:
            Number of new improvements added to the master file.
        """
        # Import here to avoid circular dependency
        from src.improvement_generator import ImprovementGenerator

        # Get all detected patterns
        patterns = self.get_all_patterns()

        if not patterns:
            logger.info("No patterns detected, no improvements to generate")
            return 0

        # Create generator and convert patterns to improvements
        generator = ImprovementGenerator(master_file_path)
        improvements = generator.generate_from_patterns(patterns)

        # Append to master file
        added_count = generator.append_to_master(improvements)

        logger.info(
            "Generated %d improvements from %d patterns, added %d to master file",
            len(improvements),
            len(patterns),
            added_count,
        )
        return added_count

    def create_improvement_generator(
        self,
        master_file_path: str | Path,
    ) -> "ImprovementGenerator":
        """Create an ImprovementGenerator instance for manual control.

        Use this when you need more control over the improvement generation
        process, such as filtering patterns before conversion.

        Args:
            master_file_path: Path to AUTOPACK_IMPS_MASTER.json file.

        Returns:
            Configured ImprovementGenerator instance.
        """
        from src.improvement_generator import ImprovementGenerator

        return ImprovementGenerator(master_file_path)

    def generate_discovery_input(self) -> list[dict[str, Any]]:
        """Generate discovery input formatted for Phase 1 consumption.

        This method bridges the telemetry-to-discovery feedback loop by converting
        detected patterns into a format suitable for Phase 1 discovery to ingest.
        The output includes recurring issues, high-value categories, and
        recommendations based on telemetry analysis.

        Returns:
            List of discovery input items with the following structure:
            - recurring_issues: Issues that keep appearing and need attention
            - high_value_categories: Categories where improvements have high impact
            - failed_approaches: Approaches that have historically failed
            - recommendations: Actionable suggestions for discovery focus
        """
        all_patterns = self.get_all_patterns()

        if not all_patterns:
            logger.info("No patterns detected for discovery input")
            return []

        discovery_items: list[dict[str, Any]] = []

        # Group patterns by type for analysis
        patterns_by_type: dict[str, list[dict[str, Any]]] = {}
        for pattern in all_patterns:
            pattern_type = pattern.get("pattern_type", "unknown")
            if pattern_type not in patterns_by_type:
                patterns_by_type[pattern_type] = []
            patterns_by_type[pattern_type].append(pattern)

        # Identify recurring issues (patterns that appear multiple times or have high counts)
        recurring_issues: list[dict[str, Any]] = []
        for pattern in all_patterns:
            occurrence_count = pattern.get("occurrence_count", pattern.get("failure_count", 1))
            if occurrence_count >= self.MIN_PATTERN_THRESHOLD:
                recurring_issues.append(
                    {
                        "issue_type": pattern.get("pattern_type"),
                        "description": pattern.get("description", ""),
                        "occurrence_count": occurrence_count,
                        "severity": pattern.get("severity", "medium"),
                        "source": pattern.get("source", "unknown"),
                        "details": self._extract_pattern_details(pattern),
                    }
                )

        # Identify high-value categories based on pattern frequency and severity
        category_scores: dict[str, int] = {}
        severity_weights = {"critical": 4, "high": 3, "medium": 2, "low": 1}
        category_map = {
            "flaky_test": "testing",
            "consistent_ci_failure": "testing",
            "repeated_failure": "reliability",
            "phase_failure": "automation",
            "escalation_pattern": "automation",
            "workflow_failure": "ci_cd",
            "slot_high_failure_rate": "reliability",
            "frequent_event": "monitoring",
        }

        for pattern in all_patterns:
            pattern_type = pattern.get("pattern_type", "unknown")
            category = category_map.get(pattern_type, "general")
            severity = pattern.get("severity", "medium")
            weight = severity_weights.get(severity, 2)
            occurrence_count = pattern.get("occurrence_count", pattern.get("failure_count", 1))
            category_scores[category] = category_scores.get(category, 0) + (
                weight * occurrence_count
            )

        # Sort categories by score and identify high-value ones
        high_value_categories = sorted(category_scores.items(), key=lambda x: x[1], reverse=True)[
            :5
        ]

        # Generate recommendations based on patterns
        recommendations: list[dict[str, Any]] = []

        # Check for testing issues
        testing_patterns = patterns_by_type.get("flaky_test", []) + patterns_by_type.get(
            "consistent_ci_failure", []
        )
        if testing_patterns:
            recommendations.append(
                {
                    "focus_area": "testing",
                    "priority": "high",
                    "recommendation": (
                        f"Address {len(testing_patterns)} testing issues. "
                        "Consider implementing test stabilization improvements."
                    ),
                    "related_pattern_count": len(testing_patterns),
                }
            )

        # Check for reliability issues
        reliability_patterns = patterns_by_type.get("repeated_failure", []) + patterns_by_type.get(
            "slot_high_failure_rate", []
        )
        if reliability_patterns:
            recommendations.append(
                {
                    "focus_area": "reliability",
                    "priority": "high",
                    "recommendation": (
                        f"Improve system reliability to address {len(reliability_patterns)} "
                        "recurring failure patterns."
                    ),
                    "related_pattern_count": len(reliability_patterns),
                }
            )

        # Check for automation/escalation issues
        automation_patterns = patterns_by_type.get("escalation_pattern", []) + patterns_by_type.get(
            "phase_failure", []
        )
        if automation_patterns:
            recommendations.append(
                {
                    "focus_area": "automation",
                    "priority": "medium",
                    "recommendation": (
                        f"Enhance automation to reduce {len(automation_patterns)} "
                        "escalation and phase failure patterns."
                    ),
                    "related_pattern_count": len(automation_patterns),
                }
            )

        # Build the discovery input structure
        discovery_input = {
            "generated_at": datetime.now().isoformat(),
            "telemetry_source": str(self.base_path),
            "total_patterns_analyzed": len(all_patterns),
            "recurring_issues": recurring_issues,
            "high_value_categories": [
                {"category": cat, "score": score} for cat, score in high_value_categories
            ],
            "recommendations": recommendations,
            "pattern_summary": {
                pattern_type: len(patterns) for pattern_type, patterns in patterns_by_type.items()
            },
        }

        discovery_items.append(discovery_input)

        logger.info(
            "Generated discovery input: %d recurring issues, %d high-value categories, "
            "%d recommendations",
            len(recurring_issues),
            len(high_value_categories),
            len(recommendations),
        )

        return discovery_items

    def _extract_pattern_details(self, pattern: dict[str, Any]) -> dict[str, Any]:
        """Extract relevant details from a pattern for discovery input.

        Args:
            pattern: The detected pattern dictionary.

        Returns:
            Dictionary containing pattern-specific details.
        """
        pattern_type = pattern.get("pattern_type", "")
        details: dict[str, Any] = {}

        if pattern_type == "flaky_test":
            details["test_id"] = pattern.get("test_id")
            details["retry_count"] = pattern.get("retry_count")
            details["success_rate"] = pattern.get("success_rate")
        elif pattern_type == "consistent_ci_failure":
            details["test_id"] = pattern.get("test_id")
            details["failure_count"] = pattern.get("failure_count")
        elif pattern_type == "slot_high_failure_rate":
            details["slot_id"] = pattern.get("slot_id")
            details["failure_rate"] = pattern.get("failure_rate")
        elif pattern_type in ("repeated_failure", "ci_failure_reason"):
            details["failure_reason"] = pattern.get("failure_reason")
        elif pattern_type == "phase_failure":
            details["phase_type"] = pattern.get("phase_type")
        elif pattern_type == "workflow_failure":
            details["workflow"] = pattern.get("workflow")
        elif pattern_type == "frequent_event":
            details["event_type"] = pattern.get("event_type")
        elif pattern_type == "escalation_pattern":
            details["trigger"] = pattern.get("trigger")

        return details

    def export_discovery_input(self, output_path: str | Path) -> bool:
        """Export discovery input to a JSON file for Phase 1 consumption.

        Args:
            output_path: Path where the discovery input JSON will be written.

        Returns:
            True if export was successful, False otherwise.
        """
        output_path = Path(output_path)

        try:
            discovery_input = self.generate_discovery_input()

            if not discovery_input:
                logger.warning("No discovery input generated, creating empty structure")
                discovery_input = [
                    {
                        "generated_at": datetime.now().isoformat(),
                        "telemetry_source": str(self.base_path),
                        "total_patterns_analyzed": 0,
                        "recurring_issues": [],
                        "high_value_categories": [],
                        "recommendations": [],
                        "pattern_summary": {},
                    }
                ]

            # Ensure parent directory exists
            output_path.parent.mkdir(parents=True, exist_ok=True)

            # Write the discovery input
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(
                    {"discovery_input": discovery_input[0] if discovery_input else {}},
                    f,
                    indent=2,
                    ensure_ascii=False,
                )
                f.write("\n")

            logger.info("Exported discovery input to: %s", output_path)
            return True

        except OSError as e:
            logger.error("Failed to export discovery input to %s: %s", output_path, e)
            return False
