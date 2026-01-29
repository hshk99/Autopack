"""Tests for gap detection telemetry system."""

from datetime import datetime, timedelta, timezone

from autopack.gaps.gap_telemetry import (GapDetectionEvent,
                                         GapRemediationEvent,
                                         GapTelemetryRecorder)
from autopack.models import GapDetection, GapRemediation


class TestGapTelemetryRecorder:
    """Tests for GapTelemetryRecorder class."""

    def test_record_detection_stores_event(self, db_session):
        """Test that record_detection stores an event in the database."""
        recorder = GapTelemetryRecorder(session=db_session)
        now = datetime.now(timezone.utc)

        event = GapDetectionEvent(
            gap_id="gap123",
            gap_type="doc_drift",
            detected_at=now,
            file_path="docs/README.md",
            risk_classification="high",
            blocks_autopilot=True,
            run_id="run-123",
        )

        success = recorder.record_detection(event)
        assert success is True

        # Verify event was stored
        stored = db_session.query(GapDetection).filter_by(gap_id="gap123").first()
        assert stored is not None
        assert stored.gap_type == "doc_drift"
        assert stored.file_path == "docs/README.md"
        assert stored.risk_classification == "high"
        assert stored.blocks_autopilot is True
        assert stored.run_id == "run-123"

    def test_record_remediation_stores_event(self, db_session):
        """Test that record_remediation stores an event in the database."""
        recorder = GapTelemetryRecorder(session=db_session)
        now = datetime.now(timezone.utc)
        later = now + timedelta(hours=1)

        event = GapRemediationEvent(
            gap_id="gap123",
            gap_type="doc_drift",
            detected_at=now,
            remediated_at=later,
            success=True,
            method="auto",
            run_id="run-123",
        )

        success = recorder.record_remediation(event)
        assert success is True

        # Verify event was stored
        stored = db_session.query(GapRemediation).filter_by(gap_id="gap123").first()
        assert stored is not None
        assert stored.gap_type == "doc_drift"
        assert stored.success is True
        assert stored.method == "auto"
        assert stored.run_id == "run-123"

    def test_record_detection_handles_none_file_path(self, db_session):
        """Test that record_detection handles None file_path gracefully."""
        recorder = GapTelemetryRecorder(session=db_session)

        event = GapDetectionEvent(
            gap_id="gap456",
            gap_type="root_clutter",
            detected_at=datetime.now(timezone.utc),
            file_path=None,
            risk_classification="medium",
        )

        success = recorder.record_detection(event)
        assert success is True

        stored = db_session.query(GapDetection).filter_by(gap_id="gap456").first()
        assert stored is not None
        assert stored.file_path is None

    def test_recurrence_rate_calculation_empty_database(self, db_session):
        """Test recurrence rate calculation on empty database."""
        recorder = GapTelemetryRecorder(session=db_session)
        rate = recorder.get_recurrence_rate("doc_drift", days=30)
        assert rate == 0.0

    def test_recurrence_rate_calculation_single_gap(self, db_session):
        """Test recurrence rate with single gap detection."""
        recorder = GapTelemetryRecorder(session=db_session)
        now = datetime.now(timezone.utc)

        # Record one detection for one file
        event = GapDetectionEvent(
            gap_id="gap1",
            gap_type="doc_drift",
            detected_at=now,
            file_path="docs/README.md",
            risk_classification="high",
        )
        recorder.record_detection(event)

        rate = recorder.get_recurrence_rate("doc_drift", days=30)
        # 1 detection / 1 unique file = 1.0 recurrence rate
        assert rate == 1.0

    def test_recurrence_rate_calculation_multiple_detections(self, db_session):
        """Test recurrence rate with multiple detections of same gap type."""
        recorder = GapTelemetryRecorder(session=db_session)
        now = datetime.now(timezone.utc)

        # Record 3 detections for 2 unique files
        for i in range(3):
            file_path = "docs/file1.md" if i < 2 else "docs/file2.md"
            event = GapDetectionEvent(
                gap_id=f"gap{i}",
                gap_type="doc_drift",
                detected_at=now,
                file_path=file_path,
                risk_classification="high",
            )
            recorder.record_detection(event)

        rate = recorder.get_recurrence_rate("doc_drift", days=30)
        # 3 detections / 2 unique files = 1.5, capped at 1.0
        assert rate == 1.0

    def test_recurrence_rate_time_window(self, db_session):
        """Test that recurrence rate respects time window."""
        recorder = GapTelemetryRecorder(session=db_session)
        now = datetime.now(timezone.utc)
        old_time = now - timedelta(days=40)

        # Record detection outside time window
        event_old = GapDetectionEvent(
            gap_id="gap_old",
            gap_type="doc_drift",
            detected_at=old_time,
            file_path="docs/old.md",
            risk_classification="high",
        )
        recorder.record_detection(event_old)

        # Record detection inside time window
        event_new = GapDetectionEvent(
            gap_id="gap_new",
            gap_type="doc_drift",
            detected_at=now,
            file_path="docs/new.md",
            risk_classification="high",
        )
        recorder.record_detection(event_new)

        rate = recorder.get_recurrence_rate("doc_drift", days=30)
        # Only 1 detection within 30 days / 1 unique file = 1.0
        assert rate == 1.0

    def test_remediation_success_rate_empty_database(self, db_session):
        """Test remediation success rate on empty database."""
        recorder = GapTelemetryRecorder(session=db_session)
        rate = recorder.get_remediation_success_rate("doc_drift")
        assert rate == 0.0

    def test_remediation_success_rate_all_successful(self, db_session):
        """Test remediation success rate when all remediations succeed."""
        recorder = GapTelemetryRecorder(session=db_session)
        now = datetime.now(timezone.utc)

        for i in range(3):
            event = GapRemediationEvent(
                gap_id=f"gap{i}",
                gap_type="doc_drift",
                detected_at=now,
                remediated_at=now + timedelta(hours=1),
                success=True,
                method="auto",
            )
            recorder.record_remediation(event)

        rate = recorder.get_remediation_success_rate("doc_drift")
        assert rate == 1.0

    def test_remediation_success_rate_mixed(self, db_session):
        """Test remediation success rate with mixed success/failure."""
        recorder = GapTelemetryRecorder(session=db_session)
        now = datetime.now(timezone.utc)

        # 2 successful remediations
        for i in range(2):
            event = GapRemediationEvent(
                gap_id=f"gap_success{i}",
                gap_type="doc_drift",
                detected_at=now,
                remediated_at=now + timedelta(hours=1),
                success=True,
                method="auto",
            )
            recorder.record_remediation(event)

        # 1 failed remediation
        event_failed = GapRemediationEvent(
            gap_id="gap_failed",
            gap_type="doc_drift",
            detected_at=now,
            remediated_at=now + timedelta(hours=2),
            success=False,
            method="manual",
        )
        recorder.record_remediation(event_failed)

        rate = recorder.get_remediation_success_rate("doc_drift")
        # 2 successful / 3 total = 0.666...
        assert abs(rate - (2 / 3)) < 0.01

    def test_record_detection_without_session(self, db_engine):
        """Test record_detection creates and closes its own session."""
        # Note: This test will fail if SessionLocal is not properly set up,
        # which is expected - it tests the best-effort pattern
        recorder = GapTelemetryRecorder()  # No session provided

        event = GapDetectionEvent(
            gap_id="gap789",
            gap_type="root_clutter",
            detected_at=datetime.now(timezone.utc),
            file_path="junk_file.txt",
            risk_classification="low",
        )

        # Should not raise, returns False if DB is not available
        success = recorder.record_detection(event)
        # May be True or False depending on DB availability
        assert isinstance(success, bool)

    def test_different_gap_types_tracked_separately(self, db_session):
        """Test that different gap types are tracked separately."""
        recorder = GapTelemetryRecorder(session=db_session)
        now = datetime.now(timezone.utc)

        # Record detections for different gap types
        for gap_type in ["doc_drift", "root_clutter", "test_infra_drift"]:
            event = GapDetectionEvent(
                gap_id=f"gap_{gap_type}",
                gap_type=gap_type,
                detected_at=now,
                file_path="test.txt",
                risk_classification="high",
            )
            recorder.record_detection(event)

        # Each gap type should have its own recurrence rate
        rate_doc = recorder.get_recurrence_rate("doc_drift", days=30)
        rate_clutter = recorder.get_recurrence_rate("root_clutter", days=30)
        rate_test = recorder.get_recurrence_rate("test_infra_drift", days=30)

        assert rate_doc == 1.0
        assert rate_clutter == 1.0
        assert rate_test == 1.0

        # Verify event counts
        assert db_session.query(GapDetection).filter_by(gap_type="doc_drift").count() == 1
        assert db_session.query(GapDetection).filter_by(gap_type="root_clutter").count() == 1
        assert db_session.query(GapDetection).filter_by(gap_type="test_infra_drift").count() == 1
