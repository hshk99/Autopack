"""Telemetry Analytics Pipeline.

Analyzes operational state files to derive actionable insights:
- slot_history.json: Escalation patterns, slot reliability
- nudge_state.json: Nudge effectiveness, timing patterns
- ci_retry_state.json: Flaky test detection, failure correlation

This module bridges the telemetry->memory link in the self-improvement loop
by converting raw operational data into structured insights that can inform
task prioritization and improvement suggestions.
"""

from __future__ import annotations

import json
import logging
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class TelemetryAnalyzer:
    """Analyzes operational telemetry files to derive actionable insights.

    This class provides a high-level interface for analyzing the three main
    telemetry sources: slot_history.json, nudge_state.json, and ci_retry_state.json.
    It identifies patterns that indicate systemic issues and generates structured
    insights for the self-improvement loop.

    Attributes:
        state_dir: Directory containing the telemetry state files.
    """

    # Thresholds for pattern detection
    MIN_EVENTS_FOR_ANALYSIS = 3
    ESCALATION_RATE_THRESHOLD = 0.3  # 30% escalation rate is concerning
    FLAKY_TEST_THRESHOLD = 0.2  # 20% failure rate indicates flakiness
    RESOLUTION_WINDOW_HOURS = 24  # Time window for nudge->resolution correlation

    def __init__(self, state_dir: Path | str) -> None:
        """Initialize the TelemetryAnalyzer.

        Args:
            state_dir: Directory containing the telemetry state files
                (slot_history.json, nudge_state.json, ci_retry_state.json).
        """
        self.state_dir = Path(state_dir)
        self._slot_history: dict[str, Any] | None = None
        self._nudge_state: dict[str, Any] | None = None
        self._ci_retry_state: dict[str, Any] | None = None

    def _load_json_file(self, filename: str) -> dict[str, Any]:
        """Load and parse a JSON file from the state directory.

        Args:
            filename: Name of the JSON file to load.

        Returns:
            Parsed JSON data or empty dict if file doesn't exist or is invalid.
        """
        file_path = self.state_dir / filename
        if not file_path.exists():
            logger.debug("State file not found: %s", file_path)
            return {}

        try:
            with open(file_path, encoding="utf-8") as f:
                data = json.load(f)
                logger.debug("Loaded %s with %d top-level keys", filename, len(data))
                return data
        except json.JSONDecodeError as e:
            logger.warning("Failed to parse %s: %s", filename, e)
            return {}
        except OSError as e:
            logger.warning("Failed to read %s: %s", filename, e)
            return {}

    def _get_slot_history(self) -> dict[str, Any]:
        """Get slot history data, loading from file if not cached."""
        if self._slot_history is None:
            self._slot_history = self._load_json_file("slot_history.json")
        return self._slot_history

    def _get_nudge_state(self) -> dict[str, Any]:
        """Get nudge state data, loading from file if not cached."""
        if self._nudge_state is None:
            self._nudge_state = self._load_json_file("nudge_state.json")
        return self._nudge_state

    def _get_ci_retry_state(self) -> dict[str, Any]:
        """Get CI retry state data, loading from file if not cached."""
        if self._ci_retry_state is None:
            self._ci_retry_state = self._load_json_file("ci_retry_state.json")
        return self._ci_retry_state

    def analyze_slot_reliability(self) -> dict[str, Any]:
        """Identify which slots are most prone to escalation.

        Analyzes slot_history.json to calculate reliability metrics for each slot:
        - Total events per slot
        - Failure rate per slot
        - Escalation count and rate
        - Most common failure types per slot

        Returns:
            Dictionary containing:
            - slot_metrics: Per-slot reliability statistics
            - problematic_slots: List of slots with high escalation rates
            - overall_reliability: Aggregate reliability score
            - recommendations: Actionable suggestions based on analysis
        """
        slot_data = self._get_slot_history()

        if not slot_data:
            logger.info("No slot history data available for reliability analysis")
            return {
                "slot_metrics": {},
                "problematic_slots": [],
                "overall_reliability": 1.0,
                "recommendations": [],
            }

        # Aggregate statistics per slot
        slot_stats: dict[int, dict[str, Any]] = defaultdict(
            lambda: {
                "total_events": 0,
                "failed_events": 0,
                "escalated_events": 0,
                "error_types": Counter(),
                "event_types": Counter(),
            }
        )

        # Process slots array
        slots = slot_data.get("slots", [])
        for slot_entry in slots:
            if not isinstance(slot_entry, dict):
                continue

            slot_id = slot_entry.get("slot_id", slot_entry.get("slot", 0))
            stats = slot_stats[slot_id]
            stats["total_events"] += 1

            # Track failures
            status = str(slot_entry.get("status", "")).lower()
            if status in ("failed", "error", "timeout"):
                stats["failed_events"] += 1

            # Track escalations
            escalation_level = slot_entry.get("escalation_level", 0)
            if escalation_level > 0 or slot_entry.get("escalated", False):
                stats["escalated_events"] += 1

            # Track error types
            error_type = slot_entry.get("error_type", slot_entry.get("failure_category"))
            if error_type:
                stats["error_types"][error_type] += 1

            # Track event types
            event_type = slot_entry.get("event_type", slot_entry.get("type"))
            if event_type:
                stats["event_types"][event_type] += 1

        # Process events array
        events = slot_data.get("events", [])
        for event in events:
            if not isinstance(event, dict):
                continue

            slot_id = event.get("slot", event.get("slot_id", 0))
            stats = slot_stats[slot_id]

            event_type = event.get("event_type", event.get("type", ""))
            if event_type:
                stats["event_types"][event_type] += 1

            # Track escalation events
            if "escalation" in event_type.lower():
                stats["escalated_events"] += 1

        # Calculate metrics per slot
        slot_metrics: dict[int, dict[str, Any]] = {}
        problematic_slots: list[dict[str, Any]] = []
        total_events = 0
        total_failures = 0

        for slot_id, stats in slot_stats.items():
            if stats["total_events"] < self.MIN_EVENTS_FOR_ANALYSIS:
                continue

            failure_rate = stats["failed_events"] / stats["total_events"]
            escalation_rate = stats["escalated_events"] / stats["total_events"]

            metrics = {
                "slot_id": slot_id,
                "total_events": stats["total_events"],
                "failed_events": stats["failed_events"],
                "escalated_events": stats["escalated_events"],
                "failure_rate": round(failure_rate, 3),
                "escalation_rate": round(escalation_rate, 3),
                "top_error_types": dict(stats["error_types"].most_common(3)),
                "top_event_types": dict(stats["event_types"].most_common(3)),
            }
            slot_metrics[slot_id] = metrics

            total_events += stats["total_events"]
            total_failures += stats["failed_events"]

            # Flag problematic slots
            if escalation_rate >= self.ESCALATION_RATE_THRESHOLD:
                problematic_slots.append(
                    {
                        "slot_id": slot_id,
                        "escalation_rate": escalation_rate,
                        "failure_rate": failure_rate,
                        "severity": "high" if escalation_rate >= 0.5 else "medium",
                    }
                )

        # Sort problematic slots by escalation rate
        problematic_slots.sort(key=lambda x: x["escalation_rate"], reverse=True)

        # Calculate overall reliability
        overall_reliability = 1.0 - (total_failures / total_events) if total_events > 0 else 1.0

        # Generate recommendations
        recommendations: list[dict[str, Any]] = []
        for slot_info in problematic_slots[:3]:  # Top 3 problematic slots
            slot_id = slot_info["slot_id"]
            metrics = slot_metrics.get(slot_id, {})
            top_errors = metrics.get("top_error_types", {})

            recommendations.append(
                {
                    "slot_id": slot_id,
                    "priority": "high" if slot_info["escalation_rate"] >= 0.5 else "medium",
                    "action": f"Investigate slot {slot_id} with {slot_info['escalation_rate']:.0%} escalation rate",
                    "details": f"Top error types: {list(top_errors.keys())[:2]}",
                }
            )

        logger.info(
            "Analyzed slot reliability: %d slots, %d problematic, %.1f%% overall reliability",
            len(slot_metrics),
            len(problematic_slots),
            overall_reliability * 100,
        )

        return {
            "slot_metrics": slot_metrics,
            "problematic_slots": problematic_slots,
            "overall_reliability": round(overall_reliability, 3),
            "recommendations": recommendations,
        }

    def analyze_nudge_effectiveness(self) -> dict[str, Any]:
        """Track nudge->resolution correlation.

        Analyzes nudge_state.json to measure how effective nudges are at
        resolving issues:
        - Resolution rate after nudge
        - Average time to resolution
        - Nudge types with best/worst effectiveness
        - Escalation patterns

        Returns:
            Dictionary containing:
            - overall_effectiveness: Aggregate nudge effectiveness score
            - nudge_type_stats: Per-nudge-type statistics
            - timing_analysis: Analysis of nudge timing patterns
            - escalation_patterns: Patterns leading to escalation
            - recommendations: Suggestions for improving nudge effectiveness
        """
        nudge_data = self._get_nudge_state()

        if not nudge_data:
            logger.info("No nudge state data available for effectiveness analysis")
            return {
                "overall_effectiveness": 0.0,
                "nudge_type_stats": {},
                "timing_analysis": {},
                "escalation_patterns": [],
                "recommendations": [],
            }

        nudges = nudge_data.get("nudges", [])
        if not isinstance(nudges, list):
            nudges = []

        # Track statistics per nudge type/phase
        nudge_stats: dict[str, dict[str, Any]] = defaultdict(
            lambda: {
                "total": 0,
                "resolved": 0,
                "escalated": 0,
                "resolution_times": [],
                "failure_reasons": Counter(),
            }
        )

        # Track escalation patterns
        escalation_triggers: Counter[str] = Counter()
        failure_to_escalation: list[dict[str, Any]] = []

        for nudge in nudges:
            if not isinstance(nudge, dict):
                continue

            # Identify nudge type (by phase_type or nudge_type field)
            nudge_type = nudge.get("phase_type", nudge.get("nudge_type", "unknown"))
            stats = nudge_stats[nudge_type]
            stats["total"] += 1

            # Track resolution status
            status = str(nudge.get("status", "")).lower()
            if status in ("resolved", "completed", "success"):
                stats["resolved"] += 1

                # Track resolution time if available
                created_at = nudge.get("created_at", nudge.get("timestamp"))
                resolved_at = nudge.get("resolved_at", nudge.get("completed_at"))
                if created_at and resolved_at:
                    try:
                        start = datetime.fromisoformat(str(created_at).replace("Z", "+00:00"))
                        end = datetime.fromisoformat(str(resolved_at).replace("Z", "+00:00"))
                        resolution_time = (end - start).total_seconds() / 3600  # hours
                        stats["resolution_times"].append(resolution_time)
                    except (ValueError, TypeError):
                        pass

            # Track escalations
            if nudge.get("escalated", False):
                stats["escalated"] += 1
                trigger = nudge.get("escalation_trigger", "unknown")
                escalation_triggers[trigger] += 1

                # Record escalation pattern
                failure_reason = nudge.get("failure_reason", nudge.get("reason"))
                if failure_reason:
                    failure_to_escalation.append(
                        {
                            "nudge_type": nudge_type,
                            "failure_reason": failure_reason,
                            "trigger": trigger,
                        }
                    )

            # Track failure reasons
            failure_reason = nudge.get("failure_reason", nudge.get("reason"))
            if failure_reason:
                stats["failure_reasons"][failure_reason] += 1

        # Calculate effectiveness per nudge type
        nudge_type_stats: dict[str, dict[str, Any]] = {}
        total_nudges = 0
        total_resolved = 0

        for nudge_type, stats in nudge_stats.items():
            if stats["total"] < self.MIN_EVENTS_FOR_ANALYSIS:
                continue

            resolution_rate = stats["resolved"] / stats["total"]
            escalation_rate = stats["escalated"] / stats["total"]
            avg_resolution_time = (
                sum(stats["resolution_times"]) / len(stats["resolution_times"])
                if stats["resolution_times"]
                else None
            )

            nudge_type_stats[nudge_type] = {
                "total_nudges": stats["total"],
                "resolved_count": stats["resolved"],
                "escalated_count": stats["escalated"],
                "resolution_rate": round(resolution_rate, 3),
                "escalation_rate": round(escalation_rate, 3),
                "avg_resolution_time_hours": (
                    round(avg_resolution_time, 2) if avg_resolution_time else None
                ),
                "top_failure_reasons": dict(stats["failure_reasons"].most_common(3)),
            }

            total_nudges += stats["total"]
            total_resolved += stats["resolved"]

        # Calculate overall effectiveness
        overall_effectiveness = total_resolved / total_nudges if total_nudges > 0 else 0.0

        # Analyze timing patterns
        all_resolution_times = []
        for stats in nudge_stats.values():
            all_resolution_times.extend(stats["resolution_times"])

        timing_analysis = {
            "avg_resolution_time_hours": (
                round(sum(all_resolution_times) / len(all_resolution_times), 2)
                if all_resolution_times
                else None
            ),
            "min_resolution_time_hours": (
                round(min(all_resolution_times), 2) if all_resolution_times else None
            ),
            "max_resolution_time_hours": (
                round(max(all_resolution_times), 2) if all_resolution_times else None
            ),
            "samples": len(all_resolution_times),
        }

        # Identify escalation patterns
        escalation_patterns: list[dict[str, Any]] = []
        for trigger, count in escalation_triggers.most_common(5):
            if count >= 2:  # At least 2 occurrences
                escalation_patterns.append(
                    {
                        "trigger": trigger,
                        "count": count,
                        "severity": "high" if count >= 5 else "medium",
                    }
                )

        # Generate recommendations
        recommendations: list[dict[str, Any]] = []

        # Recommend for low-effectiveness nudge types
        for nudge_type, stats in nudge_type_stats.items():
            if stats["resolution_rate"] < 0.5:
                recommendations.append(
                    {
                        "nudge_type": nudge_type,
                        "priority": "high",
                        "action": f"Improve nudge handling for '{nudge_type}'",
                        "details": f"Only {stats['resolution_rate']:.0%} resolution rate, "
                        f"top failures: {list(stats['top_failure_reasons'].keys())[:2]}",
                    }
                )

        # Recommend for common escalation triggers
        for pattern in escalation_patterns[:2]:
            recommendations.append(
                {
                    "trigger": pattern["trigger"],
                    "priority": pattern["severity"],
                    "action": f"Address escalation trigger: {pattern['trigger']}",
                    "details": f"Caused {pattern['count']} escalations",
                }
            )

        logger.info(
            "Analyzed nudge effectiveness: %d nudge types, %.1f%% overall effectiveness",
            len(nudge_type_stats),
            overall_effectiveness * 100,
        )

        return {
            "overall_effectiveness": round(overall_effectiveness, 3),
            "nudge_type_stats": nudge_type_stats,
            "timing_analysis": timing_analysis,
            "escalation_patterns": escalation_patterns,
            "recommendations": recommendations,
        }

    def detect_flaky_tests(self) -> list[dict[str, Any]]:
        """Identify tests that fail intermittently.

        Analyzes ci_retry_state.json to detect flaky tests:
        - Tests that fail >20% of runs without code changes
        - Tests with high variance in execution time
        - Tests that correlate with specific slot/time patterns

        Returns:
            List of flaky test records, each containing:
            - test_id: Test identifier
            - flakiness_score: 0.0 to 1.0 indicating how flaky the test is
            - failure_rate: Percentage of runs that fail
            - retry_count: Number of retries observed
            - patterns: Detected patterns (time-based, slot-based, etc.)
            - recommendation: Suggested action
        """
        ci_data = self._get_ci_retry_state()

        if not ci_data:
            logger.info("No CI retry data available for flaky test detection")
            return []

        retries = ci_data.get("retries", [])
        if not isinstance(retries, list):
            retries = []

        # Group retries by test identifier
        test_stats: dict[str, dict[str, Any]] = defaultdict(
            lambda: {
                "total_runs": 0,
                "failures": 0,
                "successes": 0,
                "retry_attempts": [],
                "workflows": Counter(),
                "failure_reasons": Counter(),
                "timestamps": [],
            }
        )

        for retry in retries:
            if not isinstance(retry, dict):
                continue

            # Get test identifier
            test_id = retry.get(
                "test_name", retry.get("test_id", retry.get("workflow", retry.get("run_id")))
            )
            if not test_id:
                continue

            stats = test_stats[str(test_id)]
            stats["total_runs"] += 1

            # Track outcome
            outcome = str(retry.get("outcome", "")).lower()
            if outcome in ("success", "passed"):
                stats["successes"] += 1
            elif outcome in ("failed", "error", "failure"):
                stats["failures"] += 1

            # Track retry attempts
            attempt = retry.get("attempt", retry.get("retry_number", 1))
            stats["retry_attempts"].append(attempt)

            # Track workflow
            workflow = retry.get("workflow")
            if workflow:
                stats["workflows"][workflow] += 1

            # Track failure reasons
            reason = retry.get("failure_reason", retry.get("error_message"))
            if reason:
                stats["failure_reasons"][reason] += 1

            # Track timestamps for time-based patterns
            timestamp = retry.get("timestamp", retry.get("created_at"))
            if timestamp:
                stats["timestamps"].append(timestamp)

        # Identify flaky tests
        flaky_tests: list[dict[str, Any]] = []

        for test_id, stats in test_stats.items():
            if stats["total_runs"] < self.MIN_EVENTS_FOR_ANALYSIS:
                continue

            # Calculate failure rate
            failure_rate = stats["failures"] / stats["total_runs"]

            # A test is flaky if it has both successes and failures
            has_mixed_outcomes = stats["successes"] > 0 and stats["failures"] > 0

            # Calculate flakiness score
            # Higher score if failure rate is around 50% (most unpredictable)
            # and if there are multiple retries
            if has_mixed_outcomes:
                # Score based on how close to 50% failure rate (most flaky)
                balance_score = 1.0 - abs(0.5 - failure_rate) * 2

                # Score based on retry frequency
                max_attempt = max(stats["retry_attempts"]) if stats["retry_attempts"] else 1
                retry_score = min(1.0, (max_attempt - 1) / 3)  # Normalize to 0-1

                flakiness_score = (balance_score * 0.6) + (retry_score * 0.4)
            else:
                # Consistently failing tests aren't flaky, just broken
                flakiness_score = 0.0 if failure_rate >= 1.0 else failure_rate * 0.3

            # Only report tests above threshold
            if flakiness_score < self.FLAKY_TEST_THRESHOLD:
                continue

            # Detect patterns
            patterns: list[str] = []

            # Check for workflow-specific patterns
            if len(stats["workflows"]) > 1:
                patterns.append("multi-workflow")
            elif stats["workflows"]:
                top_workflow = stats["workflows"].most_common(1)[0][0]
                patterns.append(f"workflow:{top_workflow}")

            # Check for specific failure reason patterns
            if stats["failure_reasons"]:
                top_reason = stats["failure_reasons"].most_common(1)[0][0]
                if "timeout" in str(top_reason).lower():
                    patterns.append("timeout-related")
                elif "connection" in str(top_reason).lower():
                    patterns.append("connection-related")
                elif "flak" in str(top_reason).lower():
                    patterns.append("known-flaky")

            # Generate recommendation based on patterns
            if "timeout-related" in patterns:
                recommendation = "Increase timeout or optimize test performance"
            elif "connection-related" in patterns:
                recommendation = "Review network/connection handling in test setup"
            elif flakiness_score >= 0.7:
                recommendation = "High priority: Rewrite test with better isolation"
            else:
                recommendation = "Review for race conditions or external dependencies"

            flaky_tests.append(
                {
                    "test_id": test_id,
                    "flakiness_score": round(flakiness_score, 3),
                    "failure_rate": round(failure_rate, 3),
                    "total_runs": stats["total_runs"],
                    "failures": stats["failures"],
                    "successes": stats["successes"],
                    "max_retry_attempt": (
                        max(stats["retry_attempts"]) if stats["retry_attempts"] else 1
                    ),
                    "patterns": patterns,
                    "top_failure_reasons": dict(stats["failure_reasons"].most_common(2)),
                    "workflows": dict(stats["workflows"]),
                    "recommendation": recommendation,
                    "severity": "high" if flakiness_score >= 0.6 else "medium",
                }
            )

        # Sort by flakiness score
        flaky_tests.sort(key=lambda x: x["flakiness_score"], reverse=True)

        logger.info(
            "Detected %d flaky tests from %d total tests analyzed",
            len(flaky_tests),
            len(test_stats),
        )

        return flaky_tests

    def generate_insights(self) -> dict[str, Any]:
        """Aggregate all analyses into actionable insights.

        Combines results from slot reliability, nudge effectiveness, and flaky
        test detection into a comprehensive insights report that can feed into
        the self-improvement loop.

        Returns:
            Dictionary containing:
            - timestamp: When the analysis was performed
            - summary: High-level summary statistics
            - slot_reliability: Results from analyze_slot_reliability()
            - nudge_effectiveness: Results from analyze_nudge_effectiveness()
            - flaky_tests: Results from detect_flaky_tests()
            - prioritized_actions: Ordered list of recommended actions
            - health_score: Overall system health score (0.0 to 1.0)
        """
        timestamp = datetime.now().isoformat()

        # Run all analyses
        slot_reliability = self.analyze_slot_reliability()
        nudge_effectiveness = self.analyze_nudge_effectiveness()
        flaky_tests = self.detect_flaky_tests()

        # Calculate health score
        # Weight components based on available data. If no data for a component,
        # it doesn't contribute to the score (neither positive nor negative).
        slot_score = slot_reliability.get("overall_reliability", 1.0)
        nudge_score = nudge_effectiveness.get("overall_effectiveness", 1.0)

        # Calculate test stability score (inverse of average flakiness)
        if flaky_tests:
            avg_flakiness = sum(t["flakiness_score"] for t in flaky_tests) / len(flaky_tests)
            test_score = 1.0 - avg_flakiness
        else:
            test_score = 1.0

        # Determine weights based on data availability
        # If no data for a component, treat it as neutral (don't penalize)
        has_slot_data = len(slot_reliability.get("slot_metrics", {})) > 0
        has_nudge_data = len(nudge_effectiveness.get("nudge_type_stats", {})) > 0
        has_test_data = len(flaky_tests) > 0

        # Default weights
        slot_weight = 0.40
        nudge_weight = 0.35
        test_weight = 0.25

        # If no data for any component, redistribute weights or use 1.0
        if not has_slot_data and not has_nudge_data and not has_test_data:
            # No data at all - assume healthy (can't measure problems)
            health_score = 1.0
        else:
            # Redistribute weights based on available data
            total_weight = 0.0
            weighted_score = 0.0

            if has_slot_data:
                total_weight += slot_weight
                weighted_score += slot_score * slot_weight
            if has_nudge_data:
                total_weight += nudge_weight
                weighted_score += nudge_score * nudge_weight
            if has_test_data:
                total_weight += test_weight
                weighted_score += test_score * test_weight

            # Normalize by total weight, or use 1.0 if no data
            health_score = weighted_score / total_weight if total_weight > 0 else 1.0

        # Collect all recommendations and prioritize
        all_actions: list[dict[str, Any]] = []

        # Add slot recommendations
        for rec in slot_reliability.get("recommendations", []):
            all_actions.append(
                {
                    "source": "slot_reliability",
                    "priority": rec.get("priority", "medium"),
                    "action": rec.get("action", ""),
                    "details": rec.get("details", ""),
                    "slot_id": rec.get("slot_id"),
                }
            )

        # Add nudge recommendations
        for rec in nudge_effectiveness.get("recommendations", []):
            all_actions.append(
                {
                    "source": "nudge_effectiveness",
                    "priority": rec.get("priority", "medium"),
                    "action": rec.get("action", ""),
                    "details": rec.get("details", ""),
                    "nudge_type": rec.get("nudge_type"),
                    "trigger": rec.get("trigger"),
                }
            )

        # Add flaky test actions
        for test in flaky_tests[:5]:  # Top 5 flakiest tests
            all_actions.append(
                {
                    "source": "flaky_tests",
                    "priority": test.get("severity", "medium"),
                    "action": f"Fix flaky test: {test['test_id']}",
                    "details": test.get("recommendation", ""),
                    "test_id": test["test_id"],
                    "flakiness_score": test["flakiness_score"],
                }
            )

        # Sort by priority
        priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        all_actions.sort(key=lambda x: priority_order.get(x.get("priority", "medium"), 4))

        # Generate summary
        summary = {
            "total_slots_analyzed": len(slot_reliability.get("slot_metrics", {})),
            "problematic_slots": len(slot_reliability.get("problematic_slots", [])),
            "nudge_types_analyzed": len(nudge_effectiveness.get("nudge_type_stats", {})),
            "overall_nudge_effectiveness": nudge_effectiveness.get("overall_effectiveness", 0),
            "flaky_tests_detected": len(flaky_tests),
            "critical_actions": sum(1 for a in all_actions if a.get("priority") == "critical"),
            "high_priority_actions": sum(1 for a in all_actions if a.get("priority") == "high"),
        }

        insights = {
            "timestamp": timestamp,
            "summary": summary,
            "slot_reliability": slot_reliability,
            "nudge_effectiveness": nudge_effectiveness,
            "flaky_tests": flaky_tests,
            "prioritized_actions": all_actions,
            "health_score": round(health_score, 3),
        }

        logger.info(
            "Generated insights: health_score=%.1f%%, %d prioritized actions",
            health_score * 100,
            len(all_actions),
        )

        return insights

    def clear_cache(self) -> None:
        """Clear cached state data to force reload on next analysis."""
        self._slot_history = None
        self._nudge_state = None
        self._ci_retry_state = None
        logger.debug("Cleared telemetry state cache")

    def export_insights(self, output_path: Path | str) -> bool:
        """Export insights to a JSON file.

        Args:
            output_path: Path where the insights JSON will be written.

        Returns:
            True if export was successful, False otherwise.
        """
        output_path = Path(output_path)

        try:
            insights = self.generate_insights()

            # Ensure parent directory exists
            output_path.parent.mkdir(parents=True, exist_ok=True)

            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(insights, f, indent=2, ensure_ascii=False, default=str)
                f.write("\n")

            logger.info("Exported insights to: %s", output_path)
            return True

        except OSError as e:
            logger.error("Failed to export insights to %s: %s", output_path, e)
            return False
