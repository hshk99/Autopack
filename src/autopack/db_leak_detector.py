"""Connection pool leak detection and monitoring."""

import logging
from sqlalchemy.pool import Pool

logger = logging.getLogger(__name__)


class ConnectionLeakDetector:
    """Monitors SQLAlchemy connection pool for leaks."""

    def __init__(self, pool: Pool, threshold: float = 0.8):
        """
        Initialize the connection leak detector.

        Args:
            pool: SQLAlchemy connection pool instance
            threshold: Alert threshold (0-1.0). Default 0.8 = 80% utilization
        """
        self.pool = pool
        self.threshold = threshold  # Alert when threshold% pool used

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
                f"Connection pool leak detected: {utilization*100:.1f}% utilization "
                f"({checked_out}/{size} connections)"
            )

        return health
