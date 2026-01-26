"""Dynamic task generator from detected anomalies."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .anomaly_detector import Anomaly


@dataclass
class GeneratedTask:
    """A dynamically generated task from anomaly detection."""

    task_id: str
    title: str
    description: str
    priority: str
    source_anomaly_id: str
    suggested_files: list[str]
    auto_executable: bool


class DynamicTaskGenerator:
    """Generates remediation tasks from detected anomalies."""

    def __init__(self, output_path: str = "dynamic_tasks.json"):
        self.output_path = Path(output_path)
        self.task_templates: dict[str, dict] = {
            "repeated_ci_failure": {
                "title_template": "Fix repeated CI failure in {component}",
                "files": ["scripts/check_pr_status.ps1", "ci_retry_state.json"],
                "auto_executable": False,
            },
            "stuck_slot": {
                "title_template": "Resolve stuck slot {component}",
                "files": ["scripts/auto_fill_empty_slots.ps1", "slot_history.json"],
                "auto_executable": True,
            },
            "escalation_spike": {
                "title_template": "Investigate escalation spike affecting {component}",
                "files": [
                    "src/escalation/connection_error_handler.py",
                    "escalation_reports/",
                ],
                "auto_executable": False,
            },
            "performance_degradation": {
                "title_template": "Address performance degradation in {component}",
                "files": ["src/telemetry/performance_metrics.py"],
                "auto_executable": False,
            },
        }

    def generate_tasks(self, anomalies: list[Anomaly]) -> list[GeneratedTask]:
        """Generate tasks from detected anomalies."""
        tasks: list[GeneratedTask] = []
        for anomaly in anomalies:
            template = self.task_templates.get(anomaly.anomaly_type)
            if not template:
                continue

            component = anomaly.affected_components[0] if anomaly.affected_components else "unknown"
            task = GeneratedTask(
                task_id=f"TASK-{anomaly.anomaly_id}",
                title=template["title_template"].format(component=component),
                description=self._generate_description(anomaly),
                priority=self._map_severity_to_priority(anomaly.severity),
                source_anomaly_id=anomaly.anomaly_id,
                suggested_files=template["files"],
                auto_executable=template["auto_executable"],
            )
            tasks.append(task)

        if tasks:
            self._save_tasks(tasks)
        return tasks

    def _generate_description(self, anomaly: Anomaly) -> str:
        """Generate task description from anomaly."""
        desc = f"Anomaly detected: {anomaly.anomaly_type}\n\n"
        desc += f"Severity: {anomaly.severity}\n"
        desc += f"Detected: {anomaly.detected_at.isoformat()}\n\n"
        desc += f"Evidence:\n{json.dumps(anomaly.evidence, indent=2)}\n\n"
        desc += f"Suggested action: {anomaly.suggested_action}"
        return desc

    def _map_severity_to_priority(self, severity: str) -> str:
        """Map anomaly severity to task priority."""
        return {"critical": "P0", "high": "P1", "medium": "P2", "low": "P3"}.get(severity, "P2")

    def _save_tasks(self, tasks: list[GeneratedTask]) -> None:
        """Save generated tasks to file."""
        existing: list[dict] = []
        if self.output_path.exists():
            with open(self.output_path) as f:
                existing = json.load(f).get("tasks", [])

        new_entries = [
            {
                "task_id": t.task_id,
                "title": t.title,
                "description": t.description,
                "priority": t.priority,
                "source_anomaly_id": t.source_anomaly_id,
                "suggested_files": t.suggested_files,
                "auto_executable": t.auto_executable,
                "generated_at": datetime.now().isoformat(),
                "status": "pending",
            }
            for t in tasks
        ]

        with open(self.output_path, "w") as f:
            json.dump({"tasks": existing + new_entries}, f, indent=2)

    def execute_auto_tasks(self, tasks: list[GeneratedTask]) -> dict[str, bool]:
        """Execute tasks marked as auto-executable."""
        results: dict[str, bool] = {}
        for task in tasks:
            if not task.auto_executable:
                continue
            if "stuck_slot" in task.source_anomaly_id:
                results[task.task_id] = self._auto_fix_stuck_slot(task)
            else:
                results[task.task_id] = False
        return results

    def _auto_fix_stuck_slot(self, task: GeneratedTask) -> bool:
        """Auto-fix a stuck slot by resetting it."""
        # Placeholder - implement actual reset logic
        return False
