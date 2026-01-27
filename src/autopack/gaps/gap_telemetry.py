"""Telemetry for gap detection effectiveness."""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from ..database import SessionLocal


@dataclass
class GapDetectionEvent:
    """Records a gap detection event."""

    gap_id: str
    gap_type: str
    detected_at: datetime
    file_path: Optional[str] = None
    risk_classification: str = "medium"
    blocks_autopilot: bool = False
    run_id: Optional[str] = None


@dataclass
class GapRemediationEvent:
    """Records a gap remediation event."""

    gap_id: str
    gap_type: str
    detected_at: datetime
    remediated_at: datetime
    success: bool
    method: str  # "auto", "manual", "ignored"
    run_id: Optional[str] = None


class GapTelemetryRecorder:
    """Records gap detection and remediation telemetry."""

    def __init__(self, session: Optional[Session] = None):
        self._session = session
        self._owns_session = session is None

    def record_detection(self, event: GapDetectionEvent) -> bool:
        """Record a gap detection event.

        Returns:
            True if write succeeded, False otherwise.
        """
        try:
            from ..models import GapDetection

            session = self._session or SessionLocal()
            try:
                db_event = GapDetection(
                    gap_id=event.gap_id,
                    gap_type=event.gap_type,
                    detected_at=event.detected_at,
                    file_path=event.file_path,
                    risk_classification=event.risk_classification,
                    blocks_autopilot=event.blocks_autopilot,
                    run_id=event.run_id,
                )
                session.add(db_event)
                session.commit()
                return True
            finally:
                if self._owns_session:
                    session.close()
        except Exception as e:
            import logging

            logger = logging.getLogger(__name__)
            logger.debug(f"Failed to record gap detection telemetry: {e}")
            return False

    def record_remediation(self, event: GapRemediationEvent) -> bool:
        """Record a gap remediation event.

        Returns:
            True if write succeeded, False otherwise.
        """
        try:
            from ..models import GapRemediation

            session = self._session or SessionLocal()
            try:
                db_event = GapRemediation(
                    gap_id=event.gap_id,
                    gap_type=event.gap_type,
                    detected_at=event.detected_at,
                    remediated_at=event.remediated_at,
                    success=event.success,
                    method=event.method,
                    run_id=event.run_id,
                )
                session.add(db_event)
                session.commit()
                return True
            finally:
                if self._owns_session:
                    session.close()
        except Exception as e:
            import logging

            logger = logging.getLogger(__name__)
            logger.debug(f"Failed to record gap remediation telemetry: {e}")
            return False

    def get_recurrence_rate(self, gap_type: str, days: int = 30) -> float:
        """Get recurrence rate for a gap type over N days.

        Returns:
            Float between 0.0 and 1.0 representing recurrence rate.
        """
        try:
            from datetime import timedelta

            from sqlalchemy import func

            from ..models import GapDetection

            session = self._session or SessionLocal()
            try:
                cutoff_time = datetime.now(timezone.utc) - timedelta(days=days)

                # Count total detections of this gap type in the time window
                total_detections = (
                    session.query(func.count(GapDetection.id))
                    .filter(
                        GapDetection.gap_type == gap_type,
                        GapDetection.detected_at >= cutoff_time,
                    )
                    .scalar()
                )

                if total_detections == 0:
                    return 0.0

                # Count unique files with this gap type in the time window
                unique_files = (
                    session.query(func.count(func.distinct(GapDetection.file_path)))
                    .filter(
                        GapDetection.gap_type == gap_type,
                        GapDetection.detected_at >= cutoff_time,
                        GapDetection.file_path.isnot(None),
                    )
                    .scalar()
                )

                if unique_files == 0:
                    return 0.0

                # Recurrence rate = detections / unique files
                return min(1.0, total_detections / unique_files)
            finally:
                if self._owns_session:
                    session.close()
        except Exception as e:
            import logging

            logger = logging.getLogger(__name__)
            logger.debug(f"Failed to calculate recurrence rate: {e}")
            return 0.0

    def get_remediation_success_rate(self, gap_type: str) -> float:
        """Get remediation success rate for a gap type.

        Returns:
            Float between 0.0 and 1.0 representing success rate.
        """
        try:
            from sqlalchemy import func

            from ..models import GapRemediation

            session = self._session or SessionLocal()
            try:
                total_remediations = (
                    session.query(func.count(GapRemediation.id))
                    .filter(GapRemediation.gap_type == gap_type)
                    .scalar()
                )

                if total_remediations == 0:
                    return 0.0

                successful_remediations = (
                    session.query(func.count(GapRemediation.id))
                    .filter(
                        GapRemediation.gap_type == gap_type,
                        GapRemediation.success.is_(True),
                    )
                    .scalar()
                )

                return successful_remediations / total_remediations
            finally:
                if self._owns_session:
                    session.close()
        except Exception as e:
            import logging

            logger = logging.getLogger(__name__)
            logger.debug(f"Failed to calculate remediation success rate: {e}")
            return 0.0
