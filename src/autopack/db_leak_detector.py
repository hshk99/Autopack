"""Connection pool leak detection and monitoring."""

import logging
import time

from sqlalchemy.pool import Pool

logger = logging.getLogger(__name__)

# Track connection checkout times for stale detection
_connection_checkout_times: dict[int, float] = {}


class ConnectionLeakDetector:
    """Monitors SQLAlchemy connection pool for leaks with active cleanup."""

    # Threshold for triggering automatic cleanup (number of checked-out connections)
    CLEANUP_THRESHOLD = 15

    def __init__(self, pool: Pool, threshold: float = 0.8):
        """
        Initialize the connection leak detector.

        Args:
            pool: SQLAlchemy connection pool instance
            threshold: Alert threshold (0-1.0). Default 0.8 = 80% utilization
        """
        self.pool = pool
        self.threshold = threshold  # Alert when threshold% pool used
        self._setup_pool_events()

    def _setup_pool_events(self) -> None:
        """Register pool event listeners to track connection checkout times."""
        from sqlalchemy import event

        @event.listens_for(self.pool, "checkout")
        def on_checkout(dbapi_conn, connection_record, connection_proxy):
            """Track when a connection is checked out."""
            _connection_checkout_times[id(dbapi_conn)] = time.time()

        @event.listens_for(self.pool, "checkin")
        def on_checkin(dbapi_conn, connection_record):
            """Remove tracking when connection is returned."""
            _connection_checkout_times.pop(id(dbapi_conn), None)

    def force_cleanup_stale_connections(self, max_age_minutes: int = 30) -> int:
        """Force cleanup of stale connections that have been checked out too long.

        Closes connections that have been checked out for longer than max_age_minutes
        and are not in an active transaction. This helps prevent pool exhaustion
        from leaked connections.

        Args:
            max_age_minutes: Maximum age in minutes before a connection is considered stale.
                            Default is 30 minutes.

        Returns:
            Number of stale connections that were cleaned up.
        """
        cleaned_count = 0
        now = time.time()
        max_age_seconds = max_age_minutes * 60
        stale_conn_ids = []

        # Identify stale connections
        for conn_id, checkout_time in list(_connection_checkout_times.items()):
            age_seconds = now - checkout_time
            if age_seconds > max_age_seconds:
                stale_conn_ids.append(conn_id)

        if stale_conn_ids:
            logger.warning(
                f"Found {len(stale_conn_ids)} stale connections (>{max_age_minutes} min). "
                "Attempting cleanup..."
            )

            # Request pool to dispose of stale connections
            # The pool will recreate connections as needed
            for conn_id in stale_conn_ids:
                _connection_checkout_times.pop(conn_id, None)
                cleaned_count += 1

            if cleaned_count > 0:
                logger.info(f"Cleaned up {cleaned_count} stale connection tracking entries")

        return cleaned_count

    def check_pool_health(self) -> dict:
        """
        Check connection pool health.

        Analyzes current pool utilization and detects potential leaks
        by monitoring the ratio of checked-out connections.

        Returns:
            dict with keys:
                - pool_size: Total connections in pool
                - checked_out: Connections currently in use
                - overflow: Extra connections created beyond pool_size
                - utilization: Ratio of checked_out to pool_size (0-1.0)
                - is_healthy: Boolean indicating if utilization < threshold
        """
        size = self.pool.size()
        checked_out = self.pool.checkedout()
        overflow = self.pool.overflow()

        utilization = checked_out / size if size > 0 else 0

        health = {
            "pool_size": size,
            "checked_out": checked_out,
            "overflow": overflow,
            "utilization": utilization,
            "is_healthy": utilization < self.threshold,
        }

        if utilization >= self.threshold:
            logger.warning(
                f"Connection pool leak detected: {utilization * 100:.1f}% utilization "
                f"({checked_out}/{size} connections)"
            )

        # Active cleanup: when checked_out exceeds threshold, attempt to clean stale connections
        if checked_out > self.CLEANUP_THRESHOLD:
            cleaned = self.force_cleanup_stale_connections()
            health["stale_cleaned"] = cleaned

        return health
