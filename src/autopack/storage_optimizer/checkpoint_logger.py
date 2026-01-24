"""
Checkpoint logger for Storage Optimizer execution tracking (BUILD-152).

Provides SHA256-based audit trail with dual-write pattern:
- Primary: PostgreSQL (execution_checkpoints table)
- Fallback: JSONL (.autonomous_runs/storage_execution.log)

Enables:
- Idempotency: Track deleted files by SHA256 to prevent re-suggestion
- Debugging: Full execution history with timestamps, errors, lock types
- Retry tracking: Record retry attempts and lock categorization
"""

import json
import logging
import hashlib
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Set, Dict, Any
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)


@dataclass
class ExecutionCheckpoint:
    """Single execution checkpoint record."""

    run_id: str
    candidate_id: Optional[int]
    action: str  # 'delete' | 'compress' | 'skip'
    path: str
    size_bytes: Optional[int]
    sha256: Optional[str]
    status: str  # 'completed' | 'failed' | 'skipped'
    error: Optional[str] = None
    lock_type: Optional[str] = None
    retry_count: int = 0
    timestamp: Optional[str] = None

    def __post_init__(self):
        """Auto-set timestamp if not provided."""
        if self.timestamp is None:
            self.timestamp = datetime.now(timezone.utc).isoformat()


class CheckpointLogger:
    """
    Dual-write checkpoint logger for Storage Optimizer execution.

    Adapted from scripts/tidy/tidy_logger.py pattern.

    Features:
    - Primary storage: PostgreSQL (execution_checkpoints table)
    - Fallback storage: JSONL (.autonomous_runs/storage_execution.log)
    - SHA256 checksums for idempotency tracking
    - Lock type classification for retry logic

    Example:
        ```python
        logger = CheckpointLogger()
        logger.log_execution(
            run_id="scan-123",
            candidate_id=42,
            action="delete",
            path="C:/temp/file.log",
            size_bytes=1024,
            sha256="abc123...",
            status="completed"
        )

        # Get deleted checksums for idempotency
        deleted = logger.get_deleted_checksums(lookback_days=90)
        if file_sha256 in deleted:
            print("Already deleted in previous run")
        ```
    """

    def __init__(self, dsn: Optional[str] = None, fallback_log_path: Optional[Path] = None):
        """
        Initialize checkpoint logger.

        Args:
            dsn: Database connection string (default: DATABASE_URL env var)
            fallback_log_path: JSONL fallback path (default: .autonomous_runs/storage_execution.log)
        """
        self.dsn = dsn or os.getenv("DATABASE_URL")
        self.pg = None  # PostgreSQL connection (lazy init)

        # Set fallback JSONL path
        if fallback_log_path is None:
            self.fallback = Path(".autonomous_runs/storage_execution.log")
        else:
            self.fallback = Path(fallback_log_path)

        # Ensure fallback directory exists
        self.fallback.parent.mkdir(parents=True, exist_ok=True)

        # Try to initialize PostgreSQL connection
        if self.dsn and "postgres" in self.dsn:
            self._ensure_table()

    def _ensure_table(self):
        """
        Ensure execution_checkpoints table exists in PostgreSQL.

        If table doesn't exist, logs warning and falls back to JSONL only.
        """
        try:
            import psycopg2

            self.pg = psycopg2.connect(self.dsn)
            logger.info("✓ CheckpointLogger: Connected to PostgreSQL")

            # Create table if needed (best-effort, idempotent).
            cursor = self.pg.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS execution_checkpoints (
                    id SERIAL PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    candidate_id INTEGER NULL,
                    action TEXT NOT NULL,
                    path TEXT NOT NULL,
                    size_bytes BIGINT NULL,
                    sha256 TEXT NULL,
                    status TEXT NOT NULL,
                    error TEXT NULL,
                    lock_type TEXT NULL,
                    retry_count INTEGER NOT NULL DEFAULT 0,
                    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                """)
            self.pg.commit()
            cursor.close()
        except Exception as e:
            logger.warning(
                f"CheckpointLogger: PostgreSQL unavailable, using JSONL fallback only: {e}"
            )
            self.pg = None

    def log_execution(
        self,
        run_id: str,
        candidate_id: Optional[int],
        action: str,
        path: str,
        size_bytes: Optional[int],
        sha256: Optional[str],
        status: str,
        error: Optional[str] = None,
        lock_type: Optional[str] = None,
        retry_count: int = 0,
    ):
        """
        Log an execution checkpoint.

        Args:
            run_id: Execution run identifier (e.g., "scan-123")
            candidate_id: Cleanup candidate ID (optional for batch operations)
            action: Action type ('delete' | 'compress' | 'skip')
            path: File/directory path
            size_bytes: Original size in bytes
            sha256: SHA256 checksum for idempotency
            status: Execution status ('completed' | 'failed' | 'skipped')
            error: Error message if failed
            lock_type: Lock type if failed due to lock ('searchindexer' | 'antivirus' | etc.)
            retry_count: Number of retry attempts
        """
        checkpoint = ExecutionCheckpoint(
            run_id=run_id,
            candidate_id=candidate_id,
            action=action,
            path=path,
            size_bytes=size_bytes,
            sha256=sha256,
            status=status,
            error=error,
            lock_type=lock_type,
            retry_count=retry_count,
        )

        # Try PostgreSQL first
        if self.pg:
            try:
                self._log_to_postgres(checkpoint)
                return
            except Exception as e:
                logger.warning(f"Failed to log to PostgreSQL: {e}, falling back to JSONL")
                # Fall through to JSONL fallback

        # Fallback to JSONL
        self._log_to_jsonl(checkpoint)

    def _log_to_postgres(self, checkpoint: ExecutionCheckpoint):
        """Write checkpoint to PostgreSQL execution_checkpoints table."""
        cursor = self.pg.cursor()

        cursor.execute(
            """
            INSERT INTO execution_checkpoints (
                run_id, candidate_id, action, path,
                size_bytes, sha256, status, error,
                lock_type, retry_count, timestamp
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                checkpoint.run_id,
                checkpoint.candidate_id,
                checkpoint.action,
                checkpoint.path,
                checkpoint.size_bytes,
                checkpoint.sha256,
                checkpoint.status,
                checkpoint.error,
                checkpoint.lock_type,
                checkpoint.retry_count,
                checkpoint.timestamp,
            ),
        )

        self.pg.commit()
        cursor.close()

    def _log_to_jsonl(self, checkpoint: ExecutionCheckpoint):
        """Write checkpoint to JSONL fallback log."""
        with self.fallback.open("a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(checkpoint)) + "\n")

    def get_deleted_checksums(self, lookback_days: int = 90) -> Set[str]:
        """
        Get SHA256 checksums of all successfully deleted files (for idempotency).

        Args:
            lookback_days: How many days back to look (default: 90)

        Returns:
            Set of SHA256 checksums for files deleted in last N days
        """
        deleted_checksums = set()

        # Try PostgreSQL first
        if self.pg:
            try:
                cursor = self.pg.cursor()
                cursor.execute(
                    """
                    SELECT DISTINCT sha256
                    FROM execution_checkpoints
                    WHERE action = 'delete'
                      AND status = 'completed'
                      AND sha256 IS NOT NULL
                      AND timestamp >= NOW() - INTERVAL '%s days'
                    """,
                    (lookback_days,),
                )

                for row in cursor.fetchall():
                    deleted_checksums.add(row[0])

                cursor.close()
                return deleted_checksums

            except Exception as e:
                logger.warning(
                    f"Failed to query PostgreSQL for deleted checksums: {e}, falling back to JSONL"
                )
                # Fall through to JSONL fallback

        # Fallback to JSONL parsing
        if self.fallback.exists():
            try:
                cutoff = datetime.now(timezone.utc).timestamp() - (lookback_days * 86400)

                with self.fallback.open("r", encoding="utf-8") as f:
                    for line in f:
                        try:
                            record = json.loads(line)

                            # Parse timestamp
                            ts = datetime.fromisoformat(record.get("timestamp", ""))
                            if ts.timestamp() < cutoff:
                                continue  # Too old

                            # Check if deleted
                            if (
                                record.get("action") == "delete"
                                and record.get("status") == "completed"
                            ):
                                sha256 = record.get("sha256")
                                if sha256:
                                    deleted_checksums.add(sha256)

                        except (json.JSONDecodeError, ValueError):
                            continue  # Skip malformed lines

            except Exception as e:
                logger.warning(f"Failed to parse JSONL for deleted checksums: {e}")

        return deleted_checksums

    def get_recent_failures(self, lookback_days: int = 7) -> list[Dict[str, Any]]:
        """
        Get recent execution failures for troubleshooting.

        Args:
            lookback_days: How many days back to look (default: 7)

        Returns:
            List of failure records with path, error, lock_type
        """
        failures = []

        # Try PostgreSQL first
        if self.pg:
            try:
                cursor = self.pg.cursor()
                cursor.execute(
                    """
                    SELECT path, error, lock_type, retry_count, timestamp
                    FROM execution_checkpoints
                    WHERE status = 'failed'
                      AND timestamp >= NOW() - INTERVAL '%s days'
                    ORDER BY timestamp DESC
                    LIMIT 100
                    """,
                    (lookback_days,),
                )

                for row in cursor.fetchall():
                    failures.append(
                        {
                            "path": row[0],
                            "error": row[1],
                            "lock_type": row[2],
                            "retry_count": row[3],
                            "timestamp": row[4].isoformat() if row[4] else None,
                        }
                    )

                cursor.close()
                return failures

            except Exception as e:
                logger.warning(
                    f"Failed to query PostgreSQL for failures: {e}, falling back to JSONL"
                )
                # Fall through to JSONL fallback

        # Fallback to JSONL parsing
        if self.fallback.exists():
            try:
                cutoff = datetime.now(timezone.utc).timestamp() - (lookback_days * 86400)

                with self.fallback.open("r", encoding="utf-8") as f:
                    for line in f:
                        try:
                            record = json.loads(line)

                            # Parse timestamp
                            ts = datetime.fromisoformat(record.get("timestamp", ""))
                            if ts.timestamp() < cutoff:
                                continue  # Too old

                            # Check if failed
                            if record.get("status") == "failed":
                                failures.append(
                                    {
                                        "path": record.get("path"),
                                        "error": record.get("error"),
                                        "lock_type": record.get("lock_type"),
                                        "retry_count": record.get("retry_count", 0),
                                        "timestamp": record.get("timestamp"),
                                    }
                                )

                        except (json.JSONDecodeError, ValueError):
                            continue  # Skip malformed lines

            except Exception as e:
                logger.warning(f"Failed to parse JSONL for failures: {e}")

        # Sort by timestamp descending, limit to 100
        failures.sort(key=lambda x: x["timestamp"] or "", reverse=True)
        return failures[:100]

    def close(self):
        """Close PostgreSQL connection if open."""
        if self.pg:
            self.pg.close()
            self.pg = None


# ==============================================================================
# SHA256 Utility
# ==============================================================================


def compute_sha256(file_path: Path) -> Optional[str]:
    """
    Compute SHA256 checksum for a file.

    Args:
        file_path: Path to file

    Returns:
        SHA256 hex digest, or None if file doesn't exist or is a directory
    """
    if not file_path.exists():
        return None

    if file_path.is_dir():
        # For directories, compute SHA256 of sorted file list + sizes
        # This gives a content-addressable identifier for directory state
        try:
            file_list = []
            for f in sorted(file_path.rglob("*")):
                if f.is_file():
                    rel_path = f.relative_to(file_path)
                    size = f.stat().st_size
                    file_list.append(f"{rel_path}:{size}")

            content = "\n".join(file_list).encode("utf-8")
            return hashlib.sha256(content).hexdigest()

        except Exception:
            return None

    # Single file: standard SHA256
    try:
        sha256_hash = hashlib.sha256()

        with open(file_path, "rb") as f:
            # Read in 64KB chunks
            for chunk in iter(lambda: f.read(65536), b""):
                sha256_hash.update(chunk)

        return sha256_hash.hexdigest()

    except Exception:
        return None
