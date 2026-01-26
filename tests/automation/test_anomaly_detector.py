"""Tests for AnomalyDetector class."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path


from src.automation.anomaly_detector import Anomaly, AnomalyDetector


class TestAnomalyDetector:
    """Test suite for AnomalyDetector."""

    def test_detector_initialization(self, tmp_path: Path) -> None:
        """Test detector initializes with correct paths."""
        detector = AnomalyDetector(
            telemetry_path=str(tmp_path / "telemetry.json"),
            slot_history_path=str(tmp_path / "slots.json"),
            ci_state_path=str(tmp_path / "ci.json"),
        )
        assert detector.telemetry_path == tmp_path / "telemetry.json"
        assert detector.slot_history_path == tmp_path / "slots.json"
        assert detector.ci_state_path == tmp_path / "ci.json"

    def test_detect_all_returns_empty_when_no_files(self, tmp_path: Path) -> None:
        """Test detect_all returns empty list when no data files exist."""
        detector = AnomalyDetector(
            telemetry_path=str(tmp_path / "nonexistent.json"),
            slot_history_path=str(tmp_path / "nonexistent2.json"),
            ci_state_path=str(tmp_path / "nonexistent3.json"),
        )
        anomalies = detector.detect_all()
        assert anomalies == []

    def test_detect_repeated_ci_failures_threshold(self, tmp_path: Path) -> None:
        """Test CI failure detection with retry count >= 3."""
        ci_state_file = tmp_path / "ci_state.json"
        ci_state_file.write_text(
            json.dumps(
                {
                    "123": {"retry_count": 3, "last_error": "lint failure"},
                    "456": {"retry_count": 2, "last_error": "test failure"},
                    "789": {"retry_count": 5, "last_error": "build failure"},
                }
            )
        )

        detector = AnomalyDetector(ci_state_path=str(ci_state_file))
        anomalies = detector._detect_repeated_ci_failures()

        assert len(anomalies) == 2
        pr_keys = [a.affected_components[0] for a in anomalies]
        assert "PR#123" in pr_keys
        assert "PR#789" in pr_keys
        assert "PR#456" not in pr_keys

    def test_detect_repeated_ci_failures_severity(self, tmp_path: Path) -> None:
        """Test CI failure severity escalates at 5+ retries."""
        ci_state_file = tmp_path / "ci_state.json"
        ci_state_file.write_text(
            json.dumps(
                {
                    "123": {"retry_count": 3, "last_error": "error"},
                    "456": {"retry_count": 5, "last_error": "error"},
                }
            )
        )

        detector = AnomalyDetector(ci_state_path=str(ci_state_file))
        anomalies = detector._detect_repeated_ci_failures()

        anomalies_by_pr = {a.affected_components[0]: a for a in anomalies}
        assert anomalies_by_pr["PR#123"].severity == "medium"
        assert anomalies_by_pr["PR#456"].severity == "high"

    def test_detect_stuck_slots_over_two_hours(self, tmp_path: Path) -> None:
        """Test stuck slot detection for slots idle > 2 hours."""
        three_hours_ago = (datetime.now() - timedelta(hours=3)).isoformat()
        one_hour_ago = (datetime.now() - timedelta(hours=1)).isoformat()

        slot_history_file = tmp_path / "slot_history.json"
        slot_history_file.write_text(
            json.dumps(
                {
                    "slot_1": [
                        {"timestamp": three_hours_ago, "phase_id": "phase_1", "status": "running"}
                    ],
                    "slot_2": [
                        {"timestamp": one_hour_ago, "phase_id": "phase_2", "status": "running"}
                    ],
                }
            )
        )

        detector = AnomalyDetector(slot_history_path=str(slot_history_file))
        anomalies = detector._detect_stuck_slots()

        assert len(anomalies) == 1
        assert anomalies[0].affected_components[0] == "slot_slot_1"
        assert anomalies[0].anomaly_type == "stuck_slot"

    def test_detect_stuck_slots_severity_escalates(self, tmp_path: Path) -> None:
        """Test stuck slot severity escalates at > 4 hours."""
        three_hours_ago = (datetime.now() - timedelta(hours=3)).isoformat()
        five_hours_ago = (datetime.now() - timedelta(hours=5)).isoformat()

        slot_history_file = tmp_path / "slot_history.json"
        slot_history_file.write_text(
            json.dumps(
                {
                    "slot_1": [{"timestamp": three_hours_ago, "phase_id": "p1", "status": "x"}],
                    "slot_2": [{"timestamp": five_hours_ago, "phase_id": "p2", "status": "x"}],
                }
            )
        )

        detector = AnomalyDetector(slot_history_path=str(slot_history_file))
        anomalies = detector._detect_stuck_slots()

        anomalies_by_slot = {a.affected_components[0]: a for a in anomalies}
        assert anomalies_by_slot["slot_slot_1"].severity == "medium"
        assert anomalies_by_slot["slot_slot_2"].severity == "high"

    def test_detect_escalation_spikes_threshold(self, tmp_path: Path) -> None:
        """Test escalation spike detection with >= 5 escalations in 1 hour."""
        now = datetime.now()
        recent_timestamp = (now - timedelta(minutes=30)).isoformat()
        old_timestamp = (now - timedelta(hours=2)).isoformat()

        telemetry_file = tmp_path / "telemetry.json"
        telemetry_file.write_text(
            json.dumps(
                {
                    "events": [
                        {
                            "event_type": "escalation",
                            "timestamp": recent_timestamp,
                            "payload": {"slot_id": "s1"},
                        },
                        {
                            "event_type": "escalation",
                            "timestamp": recent_timestamp,
                            "payload": {"slot_id": "s2"},
                        },
                        {
                            "event_type": "escalation",
                            "timestamp": recent_timestamp,
                            "payload": {"slot_id": "s3"},
                        },
                        {
                            "event_type": "escalation",
                            "timestamp": recent_timestamp,
                            "payload": {"slot_id": "s4"},
                        },
                        {
                            "event_type": "escalation",
                            "timestamp": recent_timestamp,
                            "payload": {"slot_id": "s5"},
                        },
                        {
                            "event_type": "escalation",
                            "timestamp": old_timestamp,
                            "payload": {"slot_id": "s6"},
                        },
                    ]
                }
            )
        )

        detector = AnomalyDetector(telemetry_path=str(telemetry_file))
        anomalies = detector._detect_escalation_spikes()

        assert len(anomalies) == 1
        assert anomalies[0].anomaly_type == "escalation_spike"
        assert anomalies[0].severity == "critical"
        assert anomalies[0].evidence["escalation_count"] == 5

    def test_detect_escalation_spikes_below_threshold(self, tmp_path: Path) -> None:
        """Test no spike detected with < 5 escalations."""
        recent_timestamp = (datetime.now() - timedelta(minutes=30)).isoformat()

        telemetry_file = tmp_path / "telemetry.json"
        telemetry_file.write_text(
            json.dumps(
                {
                    "events": [
                        {
                            "event_type": "escalation",
                            "timestamp": recent_timestamp,
                            "payload": {"slot_id": "s1"},
                        },
                        {
                            "event_type": "escalation",
                            "timestamp": recent_timestamp,
                            "payload": {"slot_id": "s2"},
                        },
                        {
                            "event_type": "escalation",
                            "timestamp": recent_timestamp,
                            "payload": {"slot_id": "s3"},
                        },
                        {
                            "event_type": "escalation",
                            "timestamp": recent_timestamp,
                            "payload": {"slot_id": "s4"},
                        },
                    ]
                }
            )
        )

        detector = AnomalyDetector(telemetry_path=str(telemetry_file))
        anomalies = detector._detect_escalation_spikes()

        assert len(anomalies) == 0

    def test_log_anomalies_creates_file(self, tmp_path: Path) -> None:
        """Test anomaly logging creates/appends to file."""
        detector = AnomalyDetector()
        detector.anomaly_log_path = tmp_path / "anomalies.json"

        anomalies = [
            Anomaly(
                anomaly_id="test_001",
                anomaly_type="stuck_slot",
                severity="medium",
                detected_at=datetime.now(),
                affected_components=["slot_1"],
                evidence={"hours_stuck": 3.5},
                suggested_action="Reset slot",
            )
        ]

        detector._log_anomalies(anomalies)

        assert detector.anomaly_log_path.exists()
        data = json.loads(detector.anomaly_log_path.read_text())
        assert len(data["anomalies"]) == 1
        assert data["anomalies"][0]["anomaly_id"] == "test_001"

    def test_log_anomalies_appends_to_existing(self, tmp_path: Path) -> None:
        """Test anomaly logging appends to existing file."""
        anomaly_file = tmp_path / "anomalies.json"
        anomaly_file.write_text(
            json.dumps(
                {"anomalies": [{"anomaly_id": "existing_001", "anomaly_type": "stuck_slot"}]}
            )
        )

        detector = AnomalyDetector()
        detector.anomaly_log_path = anomaly_file

        anomalies = [
            Anomaly(
                anomaly_id="new_002",
                anomaly_type="repeated_ci_failure",
                severity="high",
                detected_at=datetime.now(),
                affected_components=["PR#123"],
                evidence={"retry_count": 5},
                suggested_action="Investigate CI failure",
            )
        ]

        detector._log_anomalies(anomalies)

        data = json.loads(anomaly_file.read_text())
        assert len(data["anomalies"]) == 2
        ids = [a["anomaly_id"] for a in data["anomalies"]]
        assert "existing_001" in ids
        assert "new_002" in ids


class TestAnomalyDataclass:
    """Test suite for Anomaly dataclass."""

    def test_anomaly_creation(self) -> None:
        """Test Anomaly dataclass creation."""
        anomaly = Anomaly(
            anomaly_id="test_123",
            anomaly_type="stuck_slot",
            severity="high",
            detected_at=datetime.now(),
            affected_components=["slot_1", "slot_2"],
            evidence={"hours_stuck": 5.0},
            suggested_action="Reset slots",
        )
        assert anomaly.anomaly_id == "test_123"
        assert anomaly.anomaly_type == "stuck_slot"
        assert anomaly.severity == "high"
        assert len(anomaly.affected_components) == 2
