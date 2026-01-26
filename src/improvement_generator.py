"""Improvement Generator from Telemetry Patterns.

Converts detected patterns into IMP entries for AUTOPACK_IMPS_MASTER.json.
This module bridges the gap between pattern detection and actionable improvements,
enabling the self-improvement loop to automatically generate improvement tasks.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class ImprovementGenerator:
    """Generates improvement entries from telemetry patterns.

    This class takes detected patterns from TelemetryAnalyzer and converts them
    into structured IMP (Improvement) entries that can be appended to the master
    improvements file for tracking and prioritization.
    """

    # Map pattern types to improvement categories
    PATTERN_TO_CATEGORY: dict[str, str] = {
        "repeated_ci_failure": "testing",
        "consistent_ci_failure": "testing",
        "flaky_test": "testing",
        "merge_conflict": "code_quality",
        "connection_error": "reliability",
        "connection_error_detected": "reliability",
        "permission_loop": "devex",
        "escalation_spike": "automation",
        "escalation_pattern": "automation",
        "repeated_failure": "reliability",
        "phase_failure": "automation",
        "workflow_failure": "ci_cd",
        "ci_failure_reason": "ci_cd",
        "slot_high_failure_rate": "reliability",
        "frequent_event": "monitoring",
        "slot_error_type": "reliability",
    }

    # Map pattern types to default priorities
    PATTERN_TO_PRIORITY: dict[str, str] = {
        "consistent_ci_failure": "critical",
        "flaky_test": "high",
        "repeated_failure": "high",
        "phase_failure": "high",
        "slot_high_failure_rate": "high",
        "escalation_pattern": "medium",
        "workflow_failure": "medium",
        "ci_failure_reason": "medium",
        "frequent_event": "medium",
        "slot_error_type": "medium",
        "connection_error": "medium",
    }

    # Map severity to priority for override
    SEVERITY_TO_PRIORITY: dict[str, str] = {
        "critical": "critical",
        "high": "high",
        "medium": "medium",
        "low": "low",
    }

    def __init__(self, master_file_path: str | Path) -> None:
        """Initialize the ImprovementGenerator.

        Args:
            master_file_path: Path to AUTOPACK_IMPS_MASTER.json file.
        """
        self.master_file = Path(master_file_path)
        self._imp_counter = 0

    def _generate_imp_id(self, pattern: dict[str, Any]) -> str:
        """Generate a unique IMP ID for a pattern.

        Args:
            pattern: The detected pattern dictionary.

        Returns:
            Unique IMP identifier string.
        """
        pattern_type = pattern.get("pattern_type", "unknown")
        # Create a deterministic hash based on pattern content
        description = pattern.get("description", "")
        hash_input = f"{pattern_type}:{description}"
        hash_value = abs(hash(hash_input)) % 10000

        # Map pattern type to prefix
        prefix_map = {
            "flaky_test": "TEST",
            "consistent_ci_failure": "TEST",
            "repeated_failure": "REL",
            "phase_failure": "AUTO",
            "escalation_pattern": "AUTO",
            "workflow_failure": "CICD",
            "ci_failure_reason": "CICD",
            "slot_high_failure_rate": "REL",
            "frequent_event": "MON",
            "slot_error_type": "REL",
        }
        prefix = prefix_map.get(pattern_type, "GEN")

        return f"IMP-{prefix}-{hash_value:04d}"

    def _generate_title(self, pattern: dict[str, Any]) -> str:
        """Generate a descriptive title for an improvement.

        Args:
            pattern: The detected pattern dictionary.

        Returns:
            Human-readable improvement title.
        """
        pattern_type = pattern.get("pattern_type", "")

        if pattern_type == "flaky_test":
            test_id = pattern.get("test_id", "unknown")
            return f"Stabilize flaky test: {test_id}"
        elif pattern_type == "consistent_ci_failure":
            test_id = pattern.get("test_id", "unknown")
            return f"Fix consistently failing test: {test_id}"
        elif pattern_type == "repeated_failure":
            reason = pattern.get("failure_reason", "unknown")
            return f"Address recurring failure: {reason}"
        elif pattern_type == "phase_failure":
            phase_type = pattern.get("phase_type", "unknown")
            return f"Improve phase reliability: {phase_type}"
        elif pattern_type == "escalation_pattern":
            trigger = pattern.get("trigger", "unknown")
            return f"Reduce escalations from: {trigger}"
        elif pattern_type == "workflow_failure":
            workflow = pattern.get("workflow", "unknown")
            return f"Fix workflow failures: {workflow}"
        elif pattern_type == "ci_failure_reason":
            reason = pattern.get("failure_reason", "unknown")
            return f"Address CI failure cause: {reason}"
        elif pattern_type == "slot_high_failure_rate":
            slot_id = pattern.get("slot_id", "unknown")
            return f"Investigate slot {slot_id} failures"
        elif pattern_type == "frequent_event":
            event_type = pattern.get("event_type", "unknown")
            return f"Reduce frequency of: {event_type}"
        elif pattern_type == "slot_error_type":
            error_type = pattern.get("error_type", "unknown")
            return f"Handle slot error: {error_type}"
        else:
            return f"Address detected pattern: {pattern_type}"

    def _generate_description(self, pattern: dict[str, Any]) -> str:
        """Generate a detailed description for an improvement.

        Args:
            pattern: The detected pattern dictionary.

        Returns:
            Detailed description of the improvement.
        """
        pattern_type = pattern.get("pattern_type", "")
        base_description = pattern.get("description", "")
        occurrence_count = pattern.get("occurrence_count", pattern.get("failure_count", 0))

        if pattern_type == "flaky_test":
            retry_count = pattern.get("retry_count", 0)
            success_rate = pattern.get("success_rate", 0)
            return (
                f"{base_description}. "
                f"Success rate: {success_rate:.0%} over {retry_count} attempts. "
                "Investigate race conditions, timing issues, or external dependencies."
            )
        elif pattern_type == "consistent_ci_failure":
            return (
                f"{base_description}. "
                "This test has not passed in any recent run. "
                "Root cause investigation required."
            )
        elif pattern_type == "slot_high_failure_rate":
            failure_rate = pattern.get("failure_rate", 0)
            return (
                f"{base_description}. "
                f"Failure rate: {failure_rate:.0%}. "
                "Check slot configuration, resource allocation, and concurrent operations."
            )
        elif occurrence_count > 0:
            return (
                f"{base_description}. "
                f"Detected {occurrence_count} occurrences. "
                "Pattern suggests systemic issue requiring attention."
            )
        else:
            return base_description

    def _generate_recommended_action(self, pattern: dict[str, Any]) -> str:
        """Generate recommended actions for an improvement.

        Args:
            pattern: The detected pattern dictionary.

        Returns:
            Actionable recommendations string.
        """
        pattern_type = pattern.get("pattern_type", "")

        actions = {
            "flaky_test": (
                "1. Review test for non-deterministic behavior\n"
                "2. Add proper wait conditions or mocks\n"
                "3. Isolate external dependencies\n"
                "4. Consider test quarantine while fixing"
            ),
            "consistent_ci_failure": (
                "1. Check recent code changes affecting this test\n"
                "2. Verify test environment configuration\n"
                "3. Review test dependencies and setup\n"
                "4. Run test locally with verbose output"
            ),
            "repeated_failure": (
                "1. Analyze failure logs for common patterns\n"
                "2. Implement more robust error handling\n"
                "3. Add retry logic with exponential backoff\n"
                "4. Consider adding monitoring alerts"
            ),
            "phase_failure": (
                "1. Review phase implementation for edge cases\n"
                "2. Add validation at phase boundaries\n"
                "3. Implement graceful degradation\n"
                "4. Add detailed logging for debugging"
            ),
            "escalation_pattern": (
                "1. Review escalation thresholds\n"
                "2. Add intermediate resolution steps\n"
                "3. Implement automated remediation\n"
                "4. Update runbooks for manual handling"
            ),
            "workflow_failure": (
                "1. Check workflow configuration\n"
                "2. Review resource limits and timeouts\n"
                "3. Add better failure notifications\n"
                "4. Implement workflow-level retries"
            ),
            "slot_high_failure_rate": (
                "1. Review slot resource allocation\n"
                "2. Check for conflicting operations\n"
                "3. Implement slot health checks\n"
                "4. Consider slot isolation or pooling"
            ),
            "frequent_event": (
                "1. Investigate root cause of events\n"
                "2. Implement preventive measures\n"
                "3. Add event rate limiting\n"
                "4. Update alerting thresholds"
            ),
        }

        return actions.get(
            pattern_type,
            "1. Analyze pattern details\n2. Implement appropriate fix\n3. Add tests\n4. Monitor results",
        )

    def pattern_to_imp(self, pattern: dict[str, Any]) -> dict[str, Any]:
        """Convert a detected pattern to an IMP entry.

        Args:
            pattern: The detected pattern dictionary from TelemetryAnalyzer.

        Returns:
            IMP-formatted dictionary ready for the master file.
        """
        pattern_type = pattern.get("pattern_type", "unknown")
        severity = pattern.get("severity", "medium")

        # Determine priority: use severity if available, else default for pattern type
        priority = self.SEVERITY_TO_PRIORITY.get(
            severity, self.PATTERN_TO_PRIORITY.get(pattern_type, "medium")
        )

        # Determine category
        category = self.PATTERN_TO_CATEGORY.get(pattern_type, "general")

        imp_entry = {
            "id": self._generate_imp_id(pattern),
            "title": self._generate_title(pattern),
            "category": category,
            "priority": priority,
            "status": "pending",
            "description": self._generate_description(pattern),
            "recommended_action": self._generate_recommended_action(pattern),
            "source": {
                "type": "telemetry_auto_generated",
                "pattern_type": pattern_type,
                "telemetry_source": pattern.get("source", "unknown"),
                "occurrence_count": pattern.get(
                    "occurrence_count", pattern.get("failure_count", 1)
                ),
            },
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "auto_generated": True,
        }

        # Add pattern-specific metadata
        if pattern_type == "flaky_test":
            imp_entry["metadata"] = {
                "test_id": pattern.get("test_id"),
                "retry_count": pattern.get("retry_count"),
                "success_rate": pattern.get("success_rate"),
            }
        elif pattern_type == "slot_high_failure_rate":
            imp_entry["metadata"] = {
                "slot_id": pattern.get("slot_id"),
                "failure_rate": pattern.get("failure_rate"),
                "total_events": pattern.get("total_events"),
            }
        elif pattern_type in ("repeated_failure", "ci_failure_reason"):
            imp_entry["metadata"] = {
                "failure_reason": pattern.get("failure_reason"),
            }
        elif pattern_type == "phase_failure":
            imp_entry["metadata"] = {
                "phase_type": pattern.get("phase_type"),
            }
        elif pattern_type == "workflow_failure":
            imp_entry["metadata"] = {
                "workflow": pattern.get("workflow"),
            }

        return imp_entry

    def _load_master_file(self) -> dict[str, Any]:
        """Load the master improvements file.

        Returns:
            Parsed JSON data or default structure if file doesn't exist.
        """
        if not self.master_file.exists():
            logger.info("Master file not found, creating new structure")
            return {"improvements": [], "metadata": {"version": "1.0", "last_updated": None}}

        try:
            with open(self.master_file, encoding="utf-8") as f:
                data = json.load(f)
                logger.debug(
                    "Loaded master file with %d improvements", len(data.get("improvements", []))
                )
                return data
        except json.JSONDecodeError as e:
            logger.warning("Failed to parse master file: %s. Creating new structure.", e)
            return {"improvements": [], "metadata": {"version": "1.0", "last_updated": None}}
        except OSError as e:
            logger.warning("Failed to read master file: %s. Creating new structure.", e)
            return {"improvements": [], "metadata": {"version": "1.0", "last_updated": None}}

    def _save_master_file(self, data: dict[str, Any]) -> None:
        """Save data to the master improvements file.

        Args:
            data: The data to save.
        """
        # Ensure parent directory exists
        self.master_file.parent.mkdir(parents=True, exist_ok=True)

        # Update metadata
        data["metadata"]["last_updated"] = datetime.now().isoformat()

        with open(self.master_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.write("\n")  # Add trailing newline

        logger.info("Saved master file with %d improvements", len(data.get("improvements", [])))

    def _is_duplicate(self, new_imp: dict[str, Any], existing_imps: list[dict[str, Any]]) -> bool:
        """Check if an improvement is a duplicate of an existing one.

        Duplicates are identified by:
        1. Same ID
        2. Same pattern type and similar description
        3. Same title (for auto-generated improvements)

        Args:
            new_imp: The new improvement to check.
            existing_imps: List of existing improvements.

        Returns:
            True if the improvement is a duplicate, False otherwise.
        """
        new_id = new_imp.get("id", "")
        new_title = new_imp.get("title", "")
        new_pattern_type = new_imp.get("source", {}).get("pattern_type", "")

        for existing in existing_imps:
            # Check ID match
            if existing.get("id") == new_id:
                logger.debug("Duplicate found by ID: %s", new_id)
                return True

            # Check title match for auto-generated improvements
            if (
                existing.get("auto_generated")
                and new_imp.get("auto_generated")
                and existing.get("title") == new_title
            ):
                logger.debug("Duplicate found by title: %s", new_title)
                return True

            # Check pattern type and metadata match
            existing_source = existing.get("source", {})
            if (
                existing_source.get("pattern_type") == new_pattern_type
                and existing.get("metadata") == new_imp.get("metadata")
                and existing.get("status") == "pending"
            ):
                logger.debug("Duplicate found by pattern and metadata: %s", new_pattern_type)
                return True

        return False

    def append_to_master(self, improvements: list[dict[str, Any]]) -> int:
        """Append new improvements to master file, avoiding duplicates.

        Args:
            improvements: List of IMP entries to append.

        Returns:
            Number of improvements actually added (excluding duplicates).
        """
        if not improvements:
            logger.info("No improvements to append")
            return 0

        master_data = self._load_master_file()
        existing_imps = master_data.get("improvements", [])

        added_count = 0
        for imp in improvements:
            if not self._is_duplicate(imp, existing_imps):
                existing_imps.append(imp)
                added_count += 1
                logger.debug("Added improvement: %s", imp.get("id"))
            else:
                logger.debug("Skipped duplicate improvement: %s", imp.get("id"))

        if added_count > 0:
            master_data["improvements"] = existing_imps
            self._save_master_file(master_data)
            logger.info(
                "Appended %d new improvements (%d duplicates skipped)",
                added_count,
                len(improvements) - added_count,
            )
        else:
            logger.info("No new improvements to add (all were duplicates)")

        return added_count

    def generate_from_patterns(self, patterns: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Generate IMP entries from a list of patterns.

        Convenience method that converts multiple patterns to IMP entries.

        Args:
            patterns: List of detected patterns from TelemetryAnalyzer.

        Returns:
            List of IMP-formatted dictionaries.
        """
        improvements = []
        for pattern in patterns:
            imp = self.pattern_to_imp(pattern)
            improvements.append(imp)

        # Sort by priority
        priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        improvements.sort(key=lambda x: priority_order.get(x.get("priority", "medium"), 4))

        logger.info("Generated %d improvements from %d patterns", len(improvements), len(patterns))
        return improvements

    def get_pending_improvements(self) -> list[dict[str, Any]]:
        """Get all pending improvements from the master file.

        Returns:
            List of improvements with status 'pending'.
        """
        master_data = self._load_master_file()
        improvements = master_data.get("improvements", [])
        pending = [imp for imp in improvements if imp.get("status") == "pending"]
        logger.debug(
            "Found %d pending improvements out of %d total", len(pending), len(improvements)
        )
        return pending

    def mark_improvement_status(self, imp_id: str, status: str) -> bool:
        """Update the status of an improvement.

        Args:
            imp_id: The improvement ID to update.
            status: New status (e.g., 'in_progress', 'completed', 'cancelled').

        Returns:
            True if the improvement was found and updated, False otherwise.
        """
        valid_statuses = {"pending", "in_progress", "completed", "cancelled", "deferred"}
        if status not in valid_statuses:
            logger.warning("Invalid status '%s'. Must be one of: %s", status, valid_statuses)
            return False

        master_data = self._load_master_file()
        improvements = master_data.get("improvements", [])

        for imp in improvements:
            if imp.get("id") == imp_id:
                imp["status"] = status
                imp["updated_at"] = datetime.now().isoformat()
                self._save_master_file(master_data)
                logger.info("Updated improvement %s status to '%s'", imp_id, status)
                return True

        logger.warning("Improvement %s not found in master file", imp_id)
        return False
