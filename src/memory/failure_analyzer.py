"""Failure pattern detection and categorization."""

import hashlib
import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from .metrics_db import MetricsDatabase


class FailureAnalyzer:
    """Analyzes and categorizes failure patterns."""

    FAILURE_CATEGORIES = [
        "ci_test_failure",
        "ci_build_failure",
        "merge_conflict",
        "stagnation",
        "connection_error",
        "permission_denied",
        "rate_limit",
        "lint_failure",
        "type_error",
        "unknown",
    ]

    def __init__(self, metrics_db: MetricsDatabase):
        """Initialize with MetricsDatabase instance."""
        self.db = metrics_db
        self.pattern_cache: Dict[str, Dict[str, Any]] = {}

    def categorize_failure(self, error_text: str) -> str:
        """Determine failure category from error text."""
        error_lower = error_text.lower()

        if "test" in error_lower and ("fail" in error_lower or "error" in error_lower):
            return "ci_test_failure"
        elif "build" in error_lower and "fail" in error_lower:
            return "ci_build_failure"
        elif "merge conflict" in error_lower or "conflict" in error_lower:
            return "merge_conflict"
        elif "stagnation" in error_lower or "timeout" in error_lower:
            return "stagnation"
        elif "connection" in error_lower or "network" in error_lower:
            return "connection_error"
        elif "permission" in error_lower or "access denied" in error_lower:
            return "permission_denied"
        elif "rate limit" in error_lower or "too many requests" in error_lower:
            return "rate_limit"
        elif "lint" in error_lower or "black" in error_lower or "isort" in error_lower:
            return "lint_failure"
        elif "type" in error_lower and "error" in error_lower:
            return "type_error"
        return "unknown"

    def compute_pattern_hash(self, error_text: str) -> str:
        """Generate hash for deduplication by normalizing error text."""
        # Remove numbers, paths, and timestamps for pattern matching
        # Order matters: git hashes and paths before number replacement
        normalized = error_text.lower()
        normalized = re.sub(r"[a-f0-9]{40}", "HASH", normalized)  # Git hashes
        normalized = re.sub(r"c:\\[^\s]+", "PATH", normalized)  # Windows paths
        normalized = re.sub(r"/[^\s]+", "PATH", normalized)  # Unix paths
        normalized = re.sub(r"\d+", "N", normalized)  # Numbers last
        return hashlib.md5(normalized.encode()).hexdigest()[:12]

    def record_failure(
        self, phase_id: str, error_text: str, resolved_by: Optional[str] = None
    ) -> str:
        """Record a failure occurrence and return pattern hash."""
        pattern_hash = self.compute_pattern_hash(error_text)
        category = self.categorize_failure(error_text)

        # Store in database using existing MetricsDatabase method
        self.db.record_failure_pattern(pattern_hash, category, resolved_by)

        return pattern_hash

    def get_resolution_suggestion(self, error_text: str) -> Optional[str]:
        """Suggest resolution based on similar past failures."""
        pattern_hash = self.compute_pattern_hash(error_text)

        with self.db._get_connection() as conn:
            cursor = conn.execute(
                "SELECT resolution FROM failure_patterns "
                "WHERE pattern_hash = ? AND resolution IS NOT NULL",
                (pattern_hash,),
            )
            row = cursor.fetchone()
            return row[0] if row else None

    def get_failure_statistics(self) -> Dict[str, Any]:
        """Get statistics about failure patterns."""
        with self.db._get_connection() as conn:
            conn.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))

            # Count by category
            cursor = conn.execute("""
                SELECT failure_type, SUM(occurrence_count) as total
                FROM failure_patterns
                GROUP BY failure_type
                ORDER BY total DESC
            """)
            by_category = {row["failure_type"]: row["total"] for row in cursor.fetchall()}

            # Top recurring patterns
            cursor = conn.execute("""
                SELECT pattern_hash, failure_type, occurrence_count, resolution
                FROM failure_patterns
                ORDER BY occurrence_count DESC
                LIMIT 10
            """)
            top_patterns = cursor.fetchall()

            return {
                "by_category": by_category,
                "top_patterns": top_patterns,
                "total_unique_patterns": len(by_category),
            }

    def detect_new_patterns(self, since_hours: int = 24) -> List[Dict[str, Any]]:
        """Detect patterns that emerged in the last N hours."""
        cutoff = (datetime.now() - timedelta(hours=since_hours)).isoformat()

        with self.db._get_connection() as conn:
            conn.row_factory = lambda c, r: dict(zip([col[0] for col in c.description], r))
            cursor = conn.execute(
                """
                SELECT pattern_hash, failure_type, occurrence_count, last_seen, resolution
                FROM failure_patterns
                WHERE last_seen >= ?
                ORDER BY last_seen DESC
            """,
                (cutoff,),
            )
            return cursor.fetchall()
