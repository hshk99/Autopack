"""Historical metrics database for long-term analysis."""

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


class MetricsDatabase:
    """SQLite-backed metrics history."""

    SCHEMA = """
    CREATE TABLE IF NOT EXISTS daily_metrics (
        date TEXT PRIMARY KEY,
        pr_merge_time_avg REAL,
        ci_failure_rate REAL,
        tasks_completed INTEGER,
        stagnation_count INTEGER,
        slot_utilization_avg REAL
    );

    CREATE TABLE IF NOT EXISTS phase_outcomes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        phase_id TEXT,
        outcome TEXT,
        duration_seconds REAL,
        ci_runs INTEGER,
        timestamp TEXT
    );

    CREATE TABLE IF NOT EXISTS failure_patterns (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        pattern_hash TEXT UNIQUE,
        failure_type TEXT,
        occurrence_count INTEGER,
        last_seen TEXT,
        resolution TEXT
    );
    """

    def __init__(self, db_path: str = "data/metrics_history.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript(self.SCHEMA)

    def store_daily_metrics(self, metrics: Dict[str, Any]) -> None:
        """Store daily aggregated metrics."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO daily_metrics
                (date, pr_merge_time_avg, ci_failure_rate, tasks_completed,
                 stagnation_count, slot_utilization_avg)
                VALUES (?, ?, ?, ?, ?, ?)
            """,
                (
                    datetime.now().strftime("%Y-%m-%d"),
                    metrics.get("pr_merge_time_avg", 0.0),
                    metrics.get("ci_failure_rate", 0.0),
                    metrics.get("tasks_completed", 0),
                    metrics.get("stagnation_count", 0),
                    metrics.get("slot_utilization_avg", 0.0),
                ),
            )

    def record_phase_outcome(
        self, phase_id: str, outcome: str, duration_seconds: float, ci_runs: int
    ) -> None:
        """Record the outcome of a phase execution."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO phase_outcomes
                (phase_id, outcome, duration_seconds, ci_runs, timestamp)
                VALUES (?, ?, ?, ?, ?)
            """,
                (phase_id, outcome, duration_seconds, ci_runs, datetime.now().isoformat()),
            )

    def record_failure_pattern(
        self,
        pattern_hash: str,
        failure_type: str,
        resolution: Optional[str] = None,
    ) -> None:
        """Record or update a failure pattern."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO failure_patterns
                (pattern_hash, failure_type, occurrence_count, last_seen, resolution)
                VALUES (?, ?, 1, ?, ?)
                ON CONFLICT(pattern_hash) DO UPDATE SET
                    occurrence_count = occurrence_count + 1,
                    last_seen = excluded.last_seen,
                    resolution = COALESCE(excluded.resolution, resolution)
            """,
                (
                    pattern_hash,
                    failure_type,
                    datetime.now().isoformat(),
                    resolution,
                ),
            )

    def get_daily_metrics(self, days: int = 30) -> List[Dict[str, Any]]:
        """Retrieve daily metrics for the last N days."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                """
                SELECT * FROM daily_metrics
                ORDER BY date DESC LIMIT ?
            """,
                (days,),
            )
            return [dict(row) for row in cursor.fetchall()]

    def get_phase_outcomes(self, phase_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Retrieve phase outcomes, optionally filtered by phase_id."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            if phase_id:
                cursor = conn.execute(
                    "SELECT * FROM phase_outcomes WHERE phase_id = ?",
                    (phase_id,),
                )
            else:
                cursor = conn.execute("SELECT * FROM phase_outcomes")
            return [dict(row) for row in cursor.fetchall()]

    def get_failure_patterns(self, failure_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """Retrieve failure patterns, optionally filtered by type."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            if failure_type:
                cursor = conn.execute(
                    "SELECT * FROM failure_patterns WHERE failure_type = ?",
                    (failure_type,),
                )
            else:
                cursor = conn.execute("SELECT * FROM failure_patterns")
            return [dict(row) for row in cursor.fetchall()]
