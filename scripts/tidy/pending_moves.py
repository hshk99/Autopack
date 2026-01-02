#!/usr/bin/env python3
"""
Persistent pending-moves queue for tidy system.

Handles locked files and other deferred moves by:
- Recording failed move attempts into a durable JSON queue
- Retrying eligible items on subsequent tidy runs
- Using exponential backoff with bounded attempts
- Abandoning items after max attempts or age threshold

Queue file location: .autonomous_runs/tidy_pending_moves.json
"""

import hashlib
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class PendingMovesQueue:
    """
    Manages a persistent queue of pending move operations.

    Thread safety: Not thread-safe. Intended for single-threaded tidy runs.
    """

    SCHEMA_VERSION = 1
    DEFAULT_MAX_ATTEMPTS = 10
    DEFAULT_ABANDON_AFTER_DAYS = 30
    DEFAULT_BASE_BACKOFF_SECONDS = 300  # 5 minutes
    DEFAULT_MAX_BACKOFF_SECONDS = 86400  # 24 hours

    # Queue caps/guardrails (P1 requirement)
    DEFAULT_MAX_QUEUE_ITEMS = 1000  # Maximum number of items in queue
    DEFAULT_MAX_QUEUE_BYTES = 10 * 1024 * 1024 * 1024  # 10 GB total

    def __init__(
        self,
        queue_file: Path,
        workspace_root: Path,
        queue_id: str = "autopack-root",
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
        abandon_after_days: int = DEFAULT_ABANDON_AFTER_DAYS,
        base_backoff_seconds: int = DEFAULT_BASE_BACKOFF_SECONDS,
        max_backoff_seconds: int = DEFAULT_MAX_BACKOFF_SECONDS,
        max_queue_items: int = DEFAULT_MAX_QUEUE_ITEMS,
        max_queue_bytes: int = DEFAULT_MAX_QUEUE_BYTES
    ):
        """
        Initialize pending moves queue.

        Args:
            queue_file: Path to JSON queue file
            workspace_root: Workspace root for path normalization
            queue_id: Stable identifier for this queue
            max_attempts: Maximum retry attempts before abandoning
            abandon_after_days: Days before abandoning regardless of attempts
            base_backoff_seconds: Initial backoff interval
            max_backoff_seconds: Maximum backoff interval
            max_queue_items: Maximum number of items allowed in queue
            max_queue_bytes: Maximum total bytes of pending items
        """
        self.queue_file = queue_file
        self.workspace_root = workspace_root
        self.queue_id = queue_id
        self.max_attempts = max_attempts
        self.abandon_after_days = abandon_after_days
        self.base_backoff_seconds = base_backoff_seconds
        self.max_backoff_seconds = max_backoff_seconds
        self.max_queue_items = max_queue_items
        self.max_queue_bytes = max_queue_bytes

        self.data: Dict = self._init_data()

    def _init_data(self) -> Dict:
        """Initialize or load queue data."""
        now = datetime.utcnow().isoformat() + "Z"

        return {
            "schema_version": self.SCHEMA_VERSION,
            "queue_id": self.queue_id,
            "created_at": now,
            "updated_at": now,
            "workspace_root": str(self.workspace_root),
            "defaults": {
                "max_attempts": self.max_attempts,
                "abandon_after_days": self.abandon_after_days,
                "base_backoff_seconds": self.base_backoff_seconds,
                "max_backoff_seconds": self.max_backoff_seconds,
            },
            "items": []
        }

    def load(self) -> bool:
        """
        Load queue from file.

        Returns:
            True if loaded successfully, False otherwise
        """
        if not self.queue_file.exists():
            logger.debug(f"[QUEUE] No existing queue file at {self.queue_file}")
            return False

        try:
            with open(self.queue_file, 'r', encoding='utf-8') as f:
                self.data = json.load(f)

            # Validate schema version
            if self.data.get("schema_version") != self.SCHEMA_VERSION:
                logger.warning(f"[QUEUE] Unsupported schema version {self.data.get('schema_version')}, resetting")
                self.data = self._init_data()
                return False

            logger.info(f"[QUEUE] Loaded {len(self.data['items'])} pending items from {self.queue_file}")
            return True
        except Exception as e:
            logger.error(f"[QUEUE] Failed to load queue: {e}")
            self.data = self._init_data()
            return False

    def save(self) -> bool:
        """
        Save queue to file.

        Returns:
            True if saved successfully, False otherwise
        """
        try:
            # Update timestamp
            self.data["updated_at"] = datetime.utcnow().isoformat() + "Z"

            # Ensure parent directory exists
            self.queue_file.parent.mkdir(parents=True, exist_ok=True)

            # Write atomically (write to temp, then rename)
            temp_file = self.queue_file.with_suffix('.tmp')
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(self.data, f, indent=2, ensure_ascii=False)

            temp_file.replace(self.queue_file)
            logger.debug(f"[QUEUE] Saved {len(self.data['items'])} pending items to {self.queue_file}")
            return True
        except Exception as e:
            logger.error(f"[QUEUE] Failed to save queue: {e}")
            return False

    @staticmethod
    def _make_item_id(src: str, dest: str, action: str = "move") -> str:
        """
        Generate stable ID for queue item.

        Args:
            src: Source path
            dest: Destination path
            action: Operation type

        Returns:
            Stable 16-character ID
        """
        # Normalize paths (lowercase, forward slashes)
        src_norm = str(Path(src)).lower().replace('\\', '/')
        dest_norm = str(Path(dest)).lower().replace('\\', '/')

        # Hash combination
        key = f"{src_norm}|{dest_norm}|{action}"
        return hashlib.sha256(key.encode('utf-8')).hexdigest()[:16]

    def _calculate_backoff(self, attempt_count: int) -> int:
        """
        Calculate exponential backoff delay.

        Args:
            attempt_count: Number of previous attempts

        Returns:
            Backoff seconds
        """
        if attempt_count <= 0:
            return 0

        # Exponential: base * (2 ^ (attempt - 1))
        backoff = self.base_backoff_seconds * (2 ** (attempt_count - 1))
        return min(backoff, self.max_backoff_seconds)

    def enqueue(
        self,
        src: Path,
        dest: Path,
        action: str = "move",
        reason: str = "locked",
        error_info: Optional[Exception] = None,
        bytes_estimate: Optional[int] = None,
        tags: Optional[List[str]] = None
    ) -> str:
        """
        Add or update item in queue.

        Enforces queue caps/guardrails:
        - Maximum number of items (DEFAULT_MAX_QUEUE_ITEMS)
        - Maximum total bytes (DEFAULT_MAX_QUEUE_BYTES)

        If caps are exceeded, the item is logged as a warning and not enqueued.

        Args:
            src: Source path
            dest: Destination path
            action: Operation type (currently only 'move')
            reason: Failure reason (locked, dest_exists, permission, unknown)
            error_info: Exception details
            bytes_estimate: Size estimate
            tags: Optional classifier tags

        Returns:
            Item ID
        """
        now = datetime.utcnow()
        now_iso = now.isoformat() + "Z"

        # Check queue caps BEFORE adding new items
        pending_items = [item for item in self.data["items"] if item["status"] == "pending"]
        current_count = len(pending_items)
        current_bytes = sum(item.get("bytes_estimate", 0) for item in pending_items if item.get("bytes_estimate"))

        # Make paths relative for ID check
        try:
            src_rel = src.relative_to(self.workspace_root)
        except ValueError:
            src_rel = src

        try:
            dest_rel = dest.relative_to(self.workspace_root)
        except ValueError:
            dest_rel = dest

        item_id = self._make_item_id(str(src_rel), str(dest_rel), action)

        # Check if already exists (updates don't count against caps)
        existing_idx = None
        for i, item in enumerate(self.data["items"]):
            if item["id"] == item_id:
                existing_idx = i
                break

        # Enforce caps for NEW items only
        if existing_idx is None:
            if current_count >= self.max_queue_items:
                logger.warning(
                    f"[QUEUE-CAP] Queue item limit reached ({self.max_queue_items}). "
                    f"Cannot enqueue {src_rel} (reason: {reason}). "
                    f"User should resolve pending items before continuing."
                )
                return item_id  # Return ID without enqueuing

            if bytes_estimate and (current_bytes + bytes_estimate) > self.max_queue_bytes:
                logger.warning(
                    f"[QUEUE-CAP] Queue byte limit reached ({self.max_queue_bytes / 1024 / 1024 / 1024:.2f} GB). "
                    f"Cannot enqueue {src_rel} ({bytes_estimate / 1024 / 1024:.2f} MB, reason: {reason}). "
                    f"User should resolve pending items before continuing."
                )
                return item_id  # Return ID without enqueuing

        if existing_idx is not None:
            # Update existing item
            item = self.data["items"][existing_idx]
            item["last_attempt_at"] = now_iso
            item["attempt_count"] += 1

            # Update error info
            if error_info:
                item["last_error"] = str(error_info)[:2000]
                item["last_error_type"] = type(error_info).__name__
                if hasattr(error_info, 'errno'):
                    item["last_error_errno"] = error_info.errno
                if hasattr(error_info, 'winerror'):
                    item["last_error_winerror"] = error_info.winerror

            # Calculate next eligible time with backoff
            backoff = self._calculate_backoff(item["attempt_count"])
            next_eligible = now + timedelta(seconds=backoff)
            item["next_eligible_at"] = next_eligible.isoformat() + "Z"

            # Check if should abandon
            first_seen = datetime.fromisoformat(item["first_seen_at"].rstrip('Z'))
            age_days = (now - first_seen).days

            if item["attempt_count"] >= self.max_attempts or age_days >= self.abandon_after_days:
                item["status"] = "abandoned"
                logger.warning(f"[QUEUE] Abandoning item {item_id} (attempts={item['attempt_count']}, age={age_days}d)")
        else:
            # Create new item
            item = {
                "id": item_id,
                "src": str(src_rel),
                "dest": str(dest_rel),
                "action": action,
                "status": "pending",
                "reason": reason,
                "first_seen_at": now_iso,
                "last_attempt_at": now_iso,
                "attempt_count": 1,
                "next_eligible_at": (now + timedelta(seconds=self.base_backoff_seconds)).isoformat() + "Z",
            }

            if error_info:
                item["last_error"] = str(error_info)[:2000]
                item["last_error_type"] = type(error_info).__name__
                if hasattr(error_info, 'errno'):
                    item["last_error_errno"] = error_info.errno
                if hasattr(error_info, 'winerror'):
                    item["last_error_winerror"] = error_info.winerror

            if bytes_estimate is not None:
                item["bytes_estimate"] = bytes_estimate

            if tags:
                item["tags"] = tags

            self.data["items"].append(item)

        return item_id

    def get_eligible_items(self, now: Optional[datetime] = None) -> List[Dict]:
        """
        Get items eligible for retry.

        Args:
            now: Current time (defaults to utcnow)

        Returns:
            List of eligible items
        """
        if now is None:
            now = datetime.utcnow()

        eligible = []
        for item in self.data["items"]:
            # Skip non-pending items
            if item["status"] != "pending":
                continue

            # Check if eligible based on backoff
            if "next_eligible_at" in item:
                next_eligible = datetime.fromisoformat(item["next_eligible_at"].rstrip('Z'))
                if next_eligible > now:
                    continue

            eligible.append(item)

        return eligible

    def mark_succeeded(self, item_id: str) -> bool:
        """
        Mark item as succeeded.

        Args:
            item_id: Item ID

        Returns:
            True if found and updated
        """
        for item in self.data["items"]:
            if item["id"] == item_id:
                item["status"] = "succeeded"
                item["last_attempt_at"] = datetime.utcnow().isoformat() + "Z"
                return True
        return False

    def get_summary(self) -> Dict[str, int]:
        """
        Get queue summary statistics.

        Returns:
            Dict with counts by status
        """
        summary = {
            "total": len(self.data["items"]),
            "pending": 0,
            "succeeded": 0,
            "abandoned": 0,
            "eligible_now": 0,
        }

        now = datetime.utcnow()
        for item in self.data["items"]:
            status = item["status"]
            summary[status] = summary.get(status, 0) + 1

            # Count eligible
            if status == "pending":
                if "next_eligible_at" not in item:
                    summary["eligible_now"] += 1
                else:
                    next_eligible = datetime.fromisoformat(item["next_eligible_at"].rstrip('Z'))
                    if next_eligible <= now:
                        summary["eligible_now"] += 1

        return summary

    def get_actionable_report(self, top_n: int = 10, now: Optional[datetime] = None) -> Dict:
        """
        Generate actionable report for pending queue items.

        This report is optimized for human decision-making:
        - Shows top N items by priority (attempts, age)
        - Suggests next actions (close process, reboot, rerun)
        - Provides clear summary statistics

        Args:
            top_n: Number of top items to show (default: 10)
            now: Current time (defaults to utcnow)

        Returns:
            Dict with report data including top items and suggested actions
        """
        if now is None:
            now = datetime.utcnow()

        # Get all pending items
        pending_items = [item for item in self.data["items"] if item["status"] == "pending"]

        # Calculate priority score (higher = more urgent)
        # Priority = attempt_count * 10 + age_days
        for item in pending_items:
            first_seen = datetime.fromisoformat(item["first_seen_at"].rstrip('Z'))
            age_days = (now - first_seen).days
            item["_age_days"] = age_days
            item["_priority"] = item["attempt_count"] * 10 + age_days

        # Sort by priority (descending)
        pending_items.sort(key=lambda x: x["_priority"], reverse=True)

        # Get top N
        top_items = pending_items[:top_n]

        # Calculate total bytes pending
        total_bytes = sum(item.get("bytes_estimate", 0) for item in pending_items if item.get("bytes_estimate"))

        # Determine suggested actions
        suggested_actions = []
        has_locked = any(item.get("reason") == "locked" for item in pending_items)

        if has_locked:
            suggested_actions.append({
                "action": "close_locking_processes",
                "description": "Close processes that may be locking files (database browsers, file explorers, IDEs)",
                "priority": "high"
            })
            suggested_actions.append({
                "action": "reboot",
                "description": "Reboot the system to release all file locks",
                "priority": "medium"
            })

        suggested_actions.append({
            "action": "rerun_tidy",
            "description": "Run 'python scripts/tidy/tidy_up.py --execute' to retry pending moves",
            "priority": "high"
        })

        # Build report
        report = {
            "timestamp": now.isoformat() + "Z",
            "summary": {
                "total_pending": len(pending_items),
                "total_bytes_estimate": total_bytes,
                "eligible_now": len([item for item in pending_items if self._is_eligible(item, now)]),
                "top_n_shown": min(top_n, len(pending_items)),
            },
            "top_items": [
                {
                    "src": item["src"],
                    "dest": item["dest"],
                    "reason": item.get("reason", "unknown"),
                    "attempt_count": item["attempt_count"],
                    "age_days": item["_age_days"],
                    "priority_score": item["_priority"],
                    "last_error": item.get("last_error", "")[:200],  # Truncate for readability
                    "next_eligible_at": item.get("next_eligible_at"),
                    "bytes_estimate": item.get("bytes_estimate"),
                }
                for item in top_items
            ],
            "suggested_actions": suggested_actions,
        }

        return report

    def _is_eligible(self, item: Dict, now: datetime) -> bool:
        """Check if an item is eligible for retry now."""
        if item["status"] != "pending":
            return False

        if "next_eligible_at" not in item:
            return True

        next_eligible = datetime.fromisoformat(item["next_eligible_at"].rstrip('Z'))
        return next_eligible <= now

    def cleanup_succeeded(self) -> int:
        """
        Remove succeeded items from queue.

        Returns:
            Number of items removed
        """
        before_count = len(self.data["items"])
        self.data["items"] = [
            item for item in self.data["items"]
            if item["status"] != "succeeded"
        ]
        removed = before_count - len(self.data["items"])

        if removed > 0:
            logger.info(f"[QUEUE] Removed {removed} succeeded items from queue")

        return removed


def retry_pending_moves(
    queue: PendingMovesQueue,
    dry_run: bool = True,
    verbose: bool = False
) -> Tuple[int, int, int]:
    """
    Retry eligible pending moves.

    IMPORTANT: In dry-run mode, this function does NOT mutate the queue
    (no status updates, no attempts incremented, no queue saves).

    Args:
        queue: Pending moves queue
        dry_run: If True, only simulate retries (NO queue mutation)
        verbose: If True, show detailed output

    Returns:
        Tuple of (retried_count, succeeded_count, failed_count)
    """
    eligible = queue.get_eligible_items()

    if not eligible:
        if verbose:
            print("[QUEUE-RETRY] No eligible items to retry")
        return 0, 0, 0

    print(f"[QUEUE-RETRY] Found {len(eligible)} eligible items to retry")
    if dry_run:
        print("[QUEUE-RETRY] DRY-RUN mode - no actual moves or queue updates will be performed")
    print()

    retried = 0
    succeeded = 0
    failed = 0

    for item in eligible:
        src = Path(queue.workspace_root) / item["src"]
        dest = Path(queue.workspace_root) / item["dest"]

        print(f"  RETRY [{item['attempt_count']} attempts] {item['src']} -> {item['dest']}")

        if dry_run:
            # CRITICAL: In dry-run, do NOT mutate the queue at all
            # Just report what would happen
            print(f"    [DRY-RUN] Would retry move (queue unchanged)")
            # Don't count as succeeded in dry-run to avoid confusion
            continue

        retried += 1

        try:
            # Ensure destination parent exists
            dest.parent.mkdir(parents=True, exist_ok=True)

            # Attempt move
            import shutil
            shutil.move(str(src), str(dest))

            # Mark succeeded (only in execute mode)
            queue.mark_succeeded(item["id"])
            succeeded += 1
            print(f"    SUCCESS")
        except Exception as e:
            # Re-queue with updated error info (only in execute mode)
            queue.enqueue(
                src=src,
                dest=dest,
                action=item["action"],
                reason=item["reason"],
                error_info=e
            )
            failed += 1
            print(f"    FAILED: {e}")

    print()
    return retried, succeeded, failed


def format_actionable_report_markdown(report: Dict) -> str:
    """
    Format actionable report as markdown.

    Args:
        report: Report dict from PendingMovesQueue.get_actionable_report()

    Returns:
        Markdown-formatted report string
    """
    lines = []
    lines.append("# Pending Moves Queue - Actionable Report")
    lines.append("")
    lines.append(f"**Generated**: {report['timestamp']}")
    lines.append("")

    # Summary
    summary = report["summary"]
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- **Total Pending**: {summary['total_pending']} items")
    lines.append(f"- **Total Size Estimate**: {summary['total_bytes_estimate'] / 1024 / 1024:.2f} MB")
    lines.append(f"- **Eligible Now**: {summary['eligible_now']} items")
    lines.append(f"- **Showing Top**: {summary['top_n_shown']} items")
    lines.append("")

    # Top items
    if report["top_items"]:
        lines.append("## Top Pending Items (by priority)")
        lines.append("")
        lines.append("| Priority | Attempts | Age (days) | Reason | Source | Last Error |")
        lines.append("|----------|----------|------------|--------|--------|------------|")

        for item in report["top_items"]:
            # Truncate paths for readability
            src_short = item["src"] if len(item["src"]) < 40 else "..." + item["src"][-37:]
            error_short = item["last_error"][:50] + "..." if len(item["last_error"]) > 50 else item["last_error"]
            error_short = error_short.replace("|", "\\|")  # Escape pipes for markdown

            lines.append(
                f"| {item['priority_score']} | {item['attempt_count']} | {item['age_days']} | "
                f"{item['reason']} | `{src_short}` | {error_short} |"
            )
        lines.append("")

    # Suggested actions
    if report["suggested_actions"]:
        lines.append("## Suggested Next Actions")
        lines.append("")

        for action in report["suggested_actions"]:
            priority_marker = "🔴" if action["priority"] == "high" else "🟡"
            lines.append(f"- **{priority_marker} {action['action'].replace('_', ' ').title()}**")
            lines.append(f"  - {action['description']}")
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("*This report shows the most problematic pending items. Close locking processes and rerun tidy to resolve.*")
    lines.append("")

    return "\n".join(lines)
