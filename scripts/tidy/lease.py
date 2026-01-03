"""
Cross-process lease primitive for tidy system.

Provides safe coordination between concurrent tidy operations using
filesystem-based atomic locking with stale lock detection and heartbeat renewal.

Thread safety: Not thread-safe. Designed for single-threaded process coordination.
Platform: Windows and Unix compatible (uses os.O_CREAT | os.O_EXCL).
"""

from __future__ import annotations
import json
import logging
import os
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class Lease:
    """
    Cross-process exclusive lease using atomic file creation.

    Features:
    - Atomic acquire using os.O_CREAT | os.O_EXCL (Windows/Unix safe)
    - TTL-based stale lock detection (prevents deadlock from crashed processes)
    - Heartbeat/renewal for long-running operations (prevents premature expiry)
    - Ownership verification (prevents accidental renewal of stolen locks)
    - Grace period for lock breaking (reduces race conditions during cleanup)

    Example:
        lease = Lease(
            lock_path=Path(".autonomous_runs/.locks/tidy.lock"),
            owner="tidy_up",
            ttl_seconds=1800  # 30 minutes
        )
        lease.acquire(timeout_seconds=30)
        try:
            # ... long-running work ...
            lease.renew()  # Extend TTL periodically
        finally:
            lease.release()
    """

    lock_path: Path
    owner: str
    ttl_seconds: int = 1800  # 30 min default (was 15 min, increased for first-run scenarios)
    poll_seconds: float = 0.5
    grace_period_seconds: int = 120  # 2 min grace before breaking stale locks

    # Internal state
    _token: Optional[str] = None  # UUID for ownership verification
    _acquired: bool = False

    def _now(self) -> datetime:
        """Get current UTC time."""
        return datetime.utcnow()

    def _payload(self) -> dict:
        """Generate lock file payload with ownership and expiry metadata."""
        if self._token is None:
            self._token = str(uuid.uuid4())

        return {
            "owner": self.owner,
            "token": self._token,
            "pid": os.getpid(),
            "created_at": self._now().isoformat() + "Z",
            "expires_at": (self._now() + timedelta(seconds=self.ttl_seconds)).isoformat() + "Z",
            "last_renewed_at": self._now().isoformat() + "Z",
        }

    def _is_stale(self, lock_data: dict) -> tuple[bool, str]:
        """
        Check if a lock is stale (expired + grace period).

        Returns:
            (is_stale, reason) tuple
        """
        try:
            expires_at = datetime.fromisoformat(lock_data["expires_at"].rstrip("Z"))
            now = self._now()

            # Add grace period to avoid breaking locks during renewal
            grace_expires = expires_at + timedelta(seconds=self.grace_period_seconds)

            if now > grace_expires:
                age_seconds = (now - expires_at).total_seconds()
                return True, f"expired {age_seconds:.0f}s ago (grace period: {self.grace_period_seconds}s)"

            return False, "not expired"

        except (KeyError, ValueError) as e:
            # Malformed lock file - treat as stale if old enough
            return True, f"malformed lock data: {e}"

    def _read_lock(self) -> Optional[dict]:
        """Read and parse lock file. Returns None if unreadable."""
        try:
            content = self.lock_path.read_text(encoding="utf-8")
            return json.loads(content)
        except (FileNotFoundError, json.JSONDecodeError, OSError) as e:
            logger.debug(f"[LEASE] Could not read lock file: {e}")
            return None

    def _write_lock(self, data: dict, mode: str = "create") -> bool:
        """
        Write lock file atomically.

        Args:
            data: Lock payload
            mode: "create" (O_EXCL) or "update" (temp+replace)

        Returns:
            True if successful, False otherwise
        """
        try:
            if mode == "create":
                # Atomic create (fails if exists)
                fd = os.open(str(self.lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2)
                return True

            elif mode == "update":
                # Atomic update (temp + replace)
                tmp_path = self.lock_path.with_suffix(self.lock_path.suffix + ".tmp")
                tmp_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

                # Try atomic replace with retries (antivirus/indexing tolerance)
                for attempt in range(3):
                    try:
                        tmp_path.replace(self.lock_path)
                        return True
                    except OSError as e:
                        if attempt < 2:
                            logger.debug(f"[LEASE] Replace attempt {attempt + 1} failed: {e}, retrying...")
                            time.sleep(0.1 * (attempt + 1))
                        else:
                            raise

                return False

        except FileExistsError:
            return False  # Expected for create mode

        except OSError as e:
            logger.warning(f"[LEASE] Failed to write lock file ({mode}): {e}")
            return False

    def acquire(self, timeout_seconds: int = 30) -> None:
        """
        Acquire exclusive lease with timeout.

        Blocks until lease is acquired or timeout expires.
        Automatically breaks stale locks (expired + grace period).

        Args:
            timeout_seconds: Maximum time to wait for lease acquisition

        Raises:
            TimeoutError: If lease cannot be acquired within timeout
            RuntimeError: If lease is already acquired by this instance
        """
        if self._acquired:
            raise RuntimeError(f"Lease already acquired by this instance (owner={self.owner})")

        deadline = time.time() + timeout_seconds
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)

        attempt_count = 0
        last_log_time = 0

        while True:
            attempt_count += 1

            # Try to create lock file (atomic)
            if not self.lock_path.exists():
                if self._write_lock(self._payload(), mode="create"):
                    self._acquired = True
                    logger.info(f"[LEASE] Acquired lease: {self.lock_path} (owner={self.owner}, token={self._token[:8]}...)")
                    return

            # Lock exists - check if stale
            lock_data = self._read_lock()

            if lock_data is None:
                # Unreadable/malformed lock - treat as stale (safe default)
                logger.warning(f"[LEASE] Breaking unreadable/malformed lock (cannot parse lock data)")
                self.lock_path.unlink(missing_ok=True)
                continue

            else:
                is_stale, reason = self._is_stale(lock_data)
                if is_stale:
                    owner = lock_data.get("owner", "unknown")
                    pid = lock_data.get("pid", "unknown")
                    logger.warning(f"[LEASE] Breaking stale lock: {reason} (owner={owner}, pid={pid})")
                    self.lock_path.unlink(missing_ok=True)
                    continue

                # Lock is valid - log if waiting a while
                if time.time() - last_log_time > 5:
                    owner = lock_data.get("owner", "unknown")
                    expires_at = lock_data.get("expires_at", "unknown")
                    logger.info(f"[LEASE] Waiting for lock (owner={owner}, expires={expires_at})")
                    last_log_time = time.time()

            # Check timeout
            if time.time() > deadline:
                owner_info = f"owner={lock_data.get('owner', 'unknown')}" if lock_data else "unknown owner"
                raise TimeoutError(
                    f"Could not acquire lease within {timeout_seconds}s: {self.lock_path} "
                    f"(held by {owner_info}, attempts={attempt_count})"
                )

            time.sleep(self.poll_seconds)

    def renew(self) -> bool:
        """
        Renew lease by extending TTL (heartbeat).

        Safe to call periodically during long-running operations.
        Verifies ownership before renewal to detect stolen locks.

        Returns:
            True if renewed successfully, False otherwise

        Raises:
            RuntimeError: If lease was not acquired or ownership verification fails
        """
        if not self._acquired:
            raise RuntimeError("Cannot renew lease that was not acquired")

        # Verify we still own the lock
        lock_data = self._read_lock()

        if lock_data is None:
            logger.error(f"[LEASE] Cannot renew - lock file is missing or unreadable")
            return False

        if lock_data.get("token") != self._token:
            logger.error(
                f"[LEASE] Cannot renew - lock ownership changed "
                f"(expected token={self._token[:8]}..., found={lock_data.get('token', 'none')[:8]}...)"
            )
            self._acquired = False  # Mark as lost
            return False

        # Update expiry and last_renewed_at
        new_payload = self._payload()
        new_payload["created_at"] = lock_data.get("created_at", new_payload["created_at"])  # Preserve original

        if self._write_lock(new_payload, mode="update"):
            logger.info(f"[LEASE] Renewed lease: {self.lock_path} (new expiry: {new_payload['expires_at']})")
            return True

        logger.warning(f"[LEASE] Failed to renew lease (write failed)")
        return False

    def release(self) -> None:
        """
        Release lease by deleting lock file.

        Safe to call even if not acquired (idempotent).
        Does not verify ownership (for cleanup scenarios).
        """
        if not self._acquired:
            logger.debug(f"[LEASE] Release called but lease was not acquired")
            return

        try:
            self.lock_path.unlink(missing_ok=True)
            logger.info(f"[LEASE] Released lease: {self.lock_path} (owner={self.owner})")
        except OSError as e:
            logger.warning(f"[LEASE] Failed to release lease: {e}")
        finally:
            self._acquired = False
            self._token = None

    def is_acquired(self) -> bool:
        """Check if lease is currently acquired by this instance."""
        return self._acquired
