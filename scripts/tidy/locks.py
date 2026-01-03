"""
Per-subsystem locks with canonical ordering for deadlock prevention.

Implements BUILD-165 requirements:
- Multiple fine-grained locks per subsystem (queue, runs, archive, docs)
- Canonical acquisition order to prevent deadlocks
- Reverse release order
- Integration with existing Lease infrastructure

Design:
- Keep umbrella tidy.lock as safety net until subsystem locks are proven stable
- Canonical order: queue → runs → archive → docs
- Renew umbrella at phase boundaries; renew subsystem locks only when held
"""

from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, List, Optional
import sys

# Import existing lease infrastructure
sys.path.insert(0, str(Path(__file__).parent))
from lease import Lease

# Canonical lock ordering to prevent deadlocks
LOCK_ORDER = ["queue", "runs", "archive", "docs"]


def lock_path(repo_root: Path, name: str) -> Path:
    """
    Get path for a named subsystem lock.

    Args:
        repo_root: Repository root directory
        name: Lock name (e.g., "queue", "runs", "archive", "docs")

    Returns:
        Path to lock file (.autonomous_runs/.locks/{name}.lock)
    """
    return repo_root / ".autonomous_runs" / ".locks" / f"{name}.lock"


@dataclass
class MultiLock:
    """
    Multiple fine-grained locks with canonical ordering.

    Prevents deadlocks by always acquiring locks in the same order:
    queue → runs → archive → docs

    Releases locks in reverse order (LIFO).

    Features:
    - Canonical acquisition order (specified in LOCK_ORDER)
    - Reverse release order
    - Individual TTL and timeout configuration
    - Optional disable for emergency bypass

    Example:
        multi_lock = MultiLock(
            repo_root=Path("/path/to/repo"),
            owner="tidy_up:phase1",
            ttl_seconds=1800,
            timeout_seconds=30
        )

        # Acquire subsystem locks in canonical order
        multi_lock.acquire(["archive", "queue"])  # Will acquire in order: queue, archive

        try:
            # ... mutation work on queue and archive ...
            multi_lock.renew()  # Renew all held locks
        finally:
            multi_lock.release()  # Release in reverse order: archive, queue
    """

    repo_root: Path
    owner: str
    ttl_seconds: int = 1800  # 30 minutes default
    timeout_seconds: int = 30
    enabled: bool = True
    leases: List[Lease] = field(default_factory=list)

    def acquire(self, names: Iterable[str]) -> None:
        """
        Acquire subsystem locks in canonical order.

        Locks are always acquired in the order specified by LOCK_ORDER,
        regardless of the order they are requested in. This prevents
        deadlocks when multiple processes acquire overlapping lock sets.

        Args:
            names: Subsystem names to lock (e.g., ["queue", "archive"])

        Raises:
            TimeoutError: If any lock cannot be acquired within timeout
            RuntimeError: If locks are already acquired
        """
        if not self.enabled:
            return

        if self.leases:
            raise RuntimeError(
                f"MultiLock already holds {len(self.leases)} lock(s). "
                "Release existing locks before acquiring new ones."
            )

        # Sort requested locks by canonical order
        order_map = {name: idx for idx, name in enumerate(LOCK_ORDER)}
        requested = sorted(set(names), key=lambda n: order_map.get(n, 999))

        # Warn about unknown lock names
        unknown = [n for n in requested if n not in LOCK_ORDER]
        if unknown:
            import logging
            logging.warning(
                f"[MULTI-LOCK] Unknown subsystem lock names: {unknown}. "
                f"Known locks: {LOCK_ORDER}"
            )

        # Acquire locks in canonical order
        self.leases = []
        acquired_names = []

        try:
            for name in requested:
                lease = Lease(
                    lock_path=lock_path(self.repo_root, name),
                    owner=f"{self.owner}:{name}",
                    ttl_seconds=self.ttl_seconds
                )
                lease.acquire(timeout_seconds=self.timeout_seconds)
                self.leases.append(lease)
                acquired_names.append(name)

        except Exception as e:
            # On failure, release any locks we already acquired (in reverse order)
            for lease in reversed(self.leases):
                try:
                    lease.release()
                except Exception:
                    pass  # Best effort cleanup

            self.leases = []
            raise TimeoutError(
                f"Failed to acquire subsystem locks {requested}. "
                f"Acquired {acquired_names} before failing at {name}: {e}"
            ) from e

    def renew(self) -> None:
        """
        Renew all held locks by extending their TTL.

        Safe to call periodically during long-running operations.
        Verifies ownership before renewal to detect stolen locks.

        Raises:
            RuntimeError: If any lock renewal fails
        """
        if not self.enabled or not self.leases:
            return

        failed = []
        for lease in self.leases:
            if not lease.renew():
                failed.append(lease.lock_path.name)

        if failed:
            raise RuntimeError(
                f"Failed to renew {len(failed)} subsystem lock(s): {failed}. "
                "Locks may have been stolen or expired."
            )

    def release(self) -> None:
        """
        Release all held locks in reverse order (LIFO).

        Safe to call even if not acquired (idempotent).
        Always releases in reverse order to maintain proper nesting.
        """
        if not self.enabled or not self.leases:
            return

        # Release in reverse order (LIFO)
        for lease in reversed(self.leases):
            lease.release()

        self.leases = []

    def is_acquired(self) -> bool:
        """Check if any locks are currently held."""
        return bool(self.leases)

    def held_locks(self) -> List[str]:
        """Get list of currently held lock names."""
        if not self.leases:
            return []

        return [
            lease.lock_path.stem.replace('.lock', '')
            for lease in self.leases
        ]
