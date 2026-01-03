#!/usr/bin/env python3
"""
Tests for smart retry policies in pending_moves.py

Verifies that per-reason retry policies correctly control:
- Retry attempt limits
- Backoff calculations
- Escalation to needs_manual status
"""

import json
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest
import sys

# Add tidy scripts to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts" / "tidy"))

from pending_moves import PendingMovesQueue, RETRY_POLICIES


class TestSmartRetryPolicies:
    """Test suite for smart retry policies."""

    def test_locked_policy_retries_with_backoff(self):
        """Test that 'locked' reason retries with exponential backoff, no escalation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            queue_file = workspace / "test_queue.json"

            queue = PendingMovesQueue(queue_file, workspace, use_smart_policies=True)

            src = workspace / "locked_file.txt"
            dest = workspace / "archive" / "locked_file.txt"

            # Enqueue with 'locked' reason
            item_id = queue.enqueue(
                src=src,
                dest=dest,
                reason="locked",
                error_info=PermissionError("File is locked")
            )

            # Verify initial state
            items = queue.data["items"]
            assert len(items) == 1
            assert items[0]["status"] == "pending"
            assert items[0]["reason"] == "locked"
            assert items[0]["attempt_count"] == 1

            # Simulate retries up to max_attempts - 1
            policy = RETRY_POLICIES["locked"]
            for i in range(2, policy["max_attempts"]):
                queue.enqueue(
                    src=src,
                    dest=dest,
                    reason="locked",
                    error_info=PermissionError("File is locked")
                )

                # Should still be pending (no escalation)
                assert items[0]["status"] == "pending"
                assert items[0]["attempt_count"] == i

            # At max_attempts, should abandon
            queue.enqueue(
                src=src,
                dest=dest,
                reason="locked",
                error_info=PermissionError("File is locked")
            )

            assert items[0]["status"] == "abandoned"
            assert items[0]["attempt_count"] == policy["max_attempts"]

    def test_dest_exists_immediate_escalation(self):
        """Test that 'dest_exists' immediately escalates to needs_manual on first attempt."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            queue_file = workspace / "test_queue.json"

            queue = PendingMovesQueue(queue_file, workspace, use_smart_policies=True)

            src = workspace / "duplicate.txt"
            dest = workspace / "archive" / "duplicate.txt"

            # Enqueue with 'dest_exists' reason
            item_id = queue.enqueue(
                src=src,
                dest=dest,
                reason="dest_exists",
                error_info=FileExistsError("Destination already exists")
            )

            # Verify immediate escalation
            items = queue.data["items"]
            assert len(items) == 1
            assert items[0]["status"] == "needs_manual"
            assert items[0]["reason"] == "dest_exists"
            assert items[0]["attempt_count"] == 1
            assert "manual_reason" in items[0]
            assert "collision" in items[0]["manual_reason"].lower()

    def test_permission_fast_escalation(self):
        """Test that 'permission' reason escalates after 3 attempts."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            queue_file = workspace / "test_queue.json"

            queue = PendingMovesQueue(queue_file, workspace, use_smart_policies=True)

            src = workspace / "no_access.txt"
            dest = workspace / "archive" / "no_access.txt"

            # Enqueue with 'permission' reason
            queue.enqueue(
                src=src,
                dest=dest,
                reason="permission",
                error_info=PermissionError("Access denied")
            )

            items = queue.data["items"]
            assert items[0]["status"] == "pending"

            # Retry 1 more time (total 2 attempts)
            queue.enqueue(
                src=src,
                dest=dest,
                reason="permission",
                error_info=PermissionError("Access denied")
            )

            # Should still be pending at 2 attempts
            assert items[0]["status"] == "pending"
            assert items[0]["attempt_count"] == 2

            # At 3rd attempt should escalate
            queue.enqueue(
                src=src,
                dest=dest,
                reason="permission",
                error_info=PermissionError("Access denied")
            )

            assert items[0]["status"] == "needs_manual"
            assert items[0]["attempt_count"] == 3
            assert "manual_reason" in items[0]

    def test_unknown_bounded_retries(self):
        """Test that 'unknown' reason has bounded retries (5) then escalates."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            queue_file = workspace / "test_queue.json"

            queue = PendingMovesQueue(queue_file, workspace, use_smart_policies=True)

            src = workspace / "mystery.txt"
            dest = workspace / "archive" / "mystery.txt"

            # Enqueue with 'unknown' reason
            queue.enqueue(
                src=src,
                dest=dest,
                reason="unknown",
                error_info=RuntimeError("Unknown error")
            )

            items = queue.data["items"]
            assert items[0]["status"] == "pending"

            # Retry 3 more times (total 4 attempts)
            for _ in range(3):
                queue.enqueue(
                    src=src,
                    dest=dest,
                    reason="unknown",
                    error_info=RuntimeError("Unknown error")
                )

            # Should still be pending at 4 attempts
            assert items[0]["status"] == "pending"
            assert items[0]["attempt_count"] == 4

            # At 5th attempt should escalate
            queue.enqueue(
                src=src,
                dest=dest,
                reason="unknown",
                error_info=RuntimeError("Unknown error")
            )

            assert items[0]["status"] == "needs_manual"
            assert items[0]["attempt_count"] == 5

    def test_backoff_calculation_by_policy(self):
        """Test that backoff is calculated using policy-specific settings."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            queue_file = workspace / "test_queue.json"

            queue = PendingMovesQueue(queue_file, workspace, use_smart_policies=True)

            # Test locked policy backoff (5 min base)
            policy_locked = queue._get_policy("locked")
            backoff_1 = queue._calculate_backoff(1, policy_locked)
            assert backoff_1 == 300  # 5 min

            backoff_2 = queue._calculate_backoff(2, policy_locked)
            assert backoff_2 == 600  # 10 min

            backoff_3 = queue._calculate_backoff(3, policy_locked)
            assert backoff_3 == 1200  # 20 min

            # Test permission policy backoff (1 min base)
            policy_permission = queue._get_policy("permission")
            backoff_perm_1 = queue._calculate_backoff(1, policy_permission)
            assert backoff_perm_1 == 60  # 1 min

            # Test dest_exists policy backoff (0 - no retry)
            policy_dest = queue._get_policy("dest_exists")
            backoff_dest = queue._calculate_backoff(1, policy_dest)
            assert backoff_dest == 0  # No backoff - immediate escalation

    def test_queue_summary_includes_needs_manual(self):
        """Test that queue summary correctly counts needs_manual items."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            queue_file = workspace / "test_queue.json"

            queue = PendingMovesQueue(queue_file, workspace, use_smart_policies=True)

            # Add items with different statuses
            queue.enqueue(
                src=workspace / "locked.txt",
                dest=workspace / "archive" / "locked.txt",
                reason="locked",
                error_info=PermissionError("Locked")
            )

            queue.enqueue(
                src=workspace / "duplicate.txt",
                dest=workspace / "archive" / "duplicate.txt",
                reason="dest_exists",
                error_info=FileExistsError("Exists")
            )

            summary = queue.get_summary()
            assert summary["total"] == 2
            assert summary["pending"] == 1
            assert summary["needs_manual"] == 1

    def test_fallback_to_default_policy_when_disabled(self):
        """Test that queue falls back to default policy when use_smart_policies=False."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            queue_file = workspace / "test_queue.json"

            # Create queue with smart policies disabled
            queue = PendingMovesQueue(
                queue_file,
                workspace,
                use_smart_policies=False,
                max_attempts=10,
                base_backoff_seconds=120
            )

            # Get policy for any reason - should return defaults
            policy = queue._get_policy("dest_exists")
            assert policy["max_attempts"] == 10
            assert policy["base_backoff_seconds"] == 120
            assert policy["escalate_to_manual"] == False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
