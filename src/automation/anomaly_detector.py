"""Anomaly detection for automated task generation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal


@dataclass
class Anomaly:
    """A detected anomaly requiring action."""

    anomaly_id: str
    anomaly_type: Literal[
        "repeated_ci_failure",
        "stuck_slot",
        "escalation_spike",
        "performance_degradation",
        "pattern_break",
    ]
    severity: Literal["low", "medium", "high", "critical"]
    detected_at: datetime
    affected_components: list[str]
    evidence: dict
    suggested_action: str


class AnomalyDetector:
    """Detects anomalies from telemetry and system state."""

    def __init__(
        self,
        telemetry_path: str = "telemetry_events.json",
        slot_history_path: str = "slot_history.json",
        ci_state_path: str = "ci_retry_state.json",
    ):
        self.telemetry_path = Path(telemetry_path)
        self.slot_history_path = Path(slot_history_path)
        self.ci_state_path = Path(ci_state_path)
        self.anomaly_log_path = Path("anomalies_detected.json")

    def detect_all(self) -> list[Anomaly]:
        """Run all anomaly detection checks."""
        anomalies: list[Anomaly] = []
        anomalies.extend(self._detect_repeated_ci_failures())
        anomalies.extend(self._detect_stuck_slots())
        anomalies.extend(self._detect_escalation_spikes())
        anomalies.extend(self._detect_performance_degradation())

        if anomalies:
            self._log_anomalies(anomalies)
        return anomalies

    def _detect_repeated_ci_failures(self) -> list[Anomaly]:
        """Detect PRs with repeated CI failures (same error 3+ times)."""
        anomalies: list[Anomaly] = []
        if self.ci_state_path.exists():
            with open(self.ci_state_path) as f:
                ci_state = json.load(f)

            for pr_key, pr_data in ci_state.items():
                retry_count = pr_data.get("retry_count", 0)
                if retry_count >= 3:
                    anomalies.append(
                        Anomaly(
                            anomaly_id=(
                                f"ci_fail_{pr_key}_" f"{datetime.now().strftime('%Y%m%d%H%M')}"
                            ),
                            anomaly_type="repeated_ci_failure",
                            severity="high" if retry_count >= 5 else "medium",
                            detected_at=datetime.now(),
                            affected_components=[f"PR#{pr_key}"],
                            evidence={
                                "retry_count": retry_count,
                                "last_error": pr_data.get("last_error", "unknown"),
                            },
                            suggested_action=(
                                f"Investigate root cause of CI failure in PR#{pr_key}"
                            ),
                        )
                    )
        return anomalies

    def _detect_stuck_slots(self) -> list[Anomaly]:
        """Detect slots stuck on same phase for too long (>2 hours)."""
        anomalies: list[Anomaly] = []
        if self.slot_history_path.exists():
            with open(self.slot_history_path) as f:
                slot_history = json.load(f)

            for slot_id, history in slot_history.items():
                if not history:
                    continue
                last_entry = history[-1]
                last_update = datetime.fromisoformat(
                    last_entry.get("timestamp", datetime.now().isoformat())
                )
                hours_stuck = (datetime.now() - last_update).total_seconds() / 3600

                if hours_stuck > 2:
                    anomalies.append(
                        Anomaly(
                            anomaly_id=(
                                f"stuck_slot_{slot_id}_" f"{datetime.now().strftime('%Y%m%d%H%M')}"
                            ),
                            anomaly_type="stuck_slot",
                            severity="high" if hours_stuck > 4 else "medium",
                            detected_at=datetime.now(),
                            affected_components=[f"slot_{slot_id}"],
                            evidence={
                                "hours_stuck": round(hours_stuck, 2),
                                "last_phase": last_entry.get("phase_id"),
                                "last_status": last_entry.get("status"),
                            },
                            suggested_action=(
                                f"Reset slot {slot_id} or investigate blocking issue"
                            ),
                        )
                    )
        return anomalies

    def _detect_escalation_spikes(self) -> list[Anomaly]:
        """Detect unusual spikes in escalation reports."""
        anomalies: list[Anomaly] = []
        if self.telemetry_path.exists():
            with open(self.telemetry_path) as f:
                events = json.load(f).get("events", [])

            hour_ago = datetime.now() - timedelta(hours=1)
            recent_escalations = [
                e
                for e in events
                if e.get("event_type") == "escalation"
                and datetime.fromisoformat(e.get("timestamp", "2000-01-01")) > hour_ago
            ]

            if len(recent_escalations) >= 5:
                affected = list(
                    set(e.get("payload", {}).get("slot_id", "unknown") for e in recent_escalations)
                )
                anomalies.append(
                    Anomaly(
                        anomaly_id=(
                            f"escalation_spike_" f"{datetime.now().strftime('%Y%m%d%H%M')}"
                        ),
                        anomaly_type="escalation_spike",
                        severity="critical",
                        detected_at=datetime.now(),
                        affected_components=affected,
                        evidence={
                            "escalation_count": len(recent_escalations),
                            "time_window": "1 hour",
                        },
                        suggested_action=(
                            "Investigate systemic issue causing multiple escalations"
                        ),
                    )
                )
        return anomalies

    def _detect_performance_degradation(self) -> list[Anomaly]:
        """Detect significant performance degradation."""
        # Placeholder for future implementation
        return []

    def _log_anomalies(self, anomalies: list[Anomaly]) -> None:
        """Log detected anomalies to file."""
        existing: list[dict] = []
        if self.anomaly_log_path.exists():
            with open(self.anomaly_log_path) as f:
                existing = json.load(f).get("anomalies", [])

        new_entries = [
            {
                "anomaly_id": a.anomaly_id,
                "anomaly_type": a.anomaly_type,
                "severity": a.severity,
                "detected_at": a.detected_at.isoformat(),
                "affected_components": a.affected_components,
                "evidence": a.evidence,
                "suggested_action": a.suggested_action,
            }
            for a in anomalies
        ]

        with open(self.anomaly_log_path, "w") as f:
            json.dump({"anomalies": existing + new_entries}, f, indent=2)
