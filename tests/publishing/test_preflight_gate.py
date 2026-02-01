"""Tests for publish preflight gate.

Validates gap analysis requirement 6.10:
- No publish operation without approved packet
- Content hash verification before publishing
- Compliance flag detection
"""

from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from autopack.publishing import (ComplianceFlag, PublishPacket,
                                 PublishPacketStatus, PublishPreflightGate)
from autopack.publishing.models import ComplianceFlagSeverity


class TestPublishPacket:
    """Test PublishPacket model."""

    def test_content_hash_deterministic(self):
        """Content hash is deterministic for same content."""
        packet1 = PublishPacket(
            packet_id="test-1",
            provider="youtube",
            action="publish",
            title="Test Video",
            description="A test video",
            tags=["test", "demo"],
        )
        packet2 = PublishPacket(
            packet_id="test-2",  # Different ID
            provider="youtube",
            action="publish",
            title="Test Video",
            description="A test video",
            tags=["demo", "test"],  # Different order, same content
        )

        assert packet1.content_hash() == packet2.content_hash()

    def test_content_hash_changes_with_content(self):
        """Content hash changes when content changes."""
        packet1 = PublishPacket(
            packet_id="test-1",
            provider="youtube",
            action="publish",
            title="Original Title",
            description="Description",
        )
        packet2 = PublishPacket(
            packet_id="test-1",
            provider="youtube",
            action="publish",
            title="Modified Title",
            description="Description",
        )

        assert packet1.content_hash() != packet2.content_hash()

    def test_blocking_flag_detection(self):
        """Blocking flags are detected."""
        packet = PublishPacket(
            packet_id="test-1",
            provider="etsy",
            action="list",
            title="Test",
            description="Test",
            compliance_flags=[
                ComplianceFlag(
                    category="banned_content",
                    severity=ComplianceFlagSeverity.BLOCKING,
                    message="Blocked",
                )
            ],
        )

        assert packet.has_blocking_flags() is True

    def test_can_be_approved_with_blocking_flag(self):
        """Cannot approve with blocking flags."""
        packet = PublishPacket(
            packet_id="test-1",
            provider="etsy",
            action="list",
            title="Test",
            description="Test",
            status=PublishPacketStatus.PENDING_REVIEW,
            compliance_flags=[
                ComplianceFlag(
                    category="banned_content",
                    severity=ComplianceFlagSeverity.BLOCKING,
                    message="Blocked",
                )
            ],
        )

        assert packet.can_be_approved() is False

    def test_can_be_approved_with_warning_only(self):
        """Can approve with warning flags only."""
        packet = PublishPacket(
            packet_id="test-1",
            provider="etsy",
            action="list",
            title="Test",
            description="Test",
            status=PublishPacketStatus.PENDING_REVIEW,
            compliance_flags=[
                ComplianceFlag(
                    category="trademark",
                    severity=ComplianceFlagSeverity.WARNING,
                    message="Warning only",
                )
            ],
        )

        assert packet.can_be_approved() is True


class TestPreflightGate:
    """Test PublishPreflightGate."""

    @pytest.fixture
    def gate(self):
        return PublishPreflightGate()

    def test_create_packet(self, gate):
        """Create packet generates valid structure."""
        packet = gate.create_packet(
            provider="youtube",
            action="publish",
            title="My Video",
            description="A great video",
            tags=["fun", "entertaining"],
        )

        assert packet.packet_id is not None
        assert packet.provider == "youtube"
        assert packet.action == "publish"
        assert packet.status == PublishPacketStatus.DRAFT

    def test_preflight_detects_trademark(self, gate):
        """Preflight detects trademark keywords."""
        packet = gate.create_packet(
            provider="youtube",
            action="publish",
            title="My Disney Fan Video",
            description="A tribute to Disney movies",
        )

        packet = gate.run_preflight_checks(packet)

        trademark_flags = [f for f in packet.compliance_flags if f.category == "trademark"]
        assert len(trademark_flags) > 0
        assert packet.status == PublishPacketStatus.PENDING_REVIEW

    def test_preflight_detects_banned_content(self, gate):
        """Preflight detects banned content (blocking)."""
        packet = gate.create_packet(
            provider="etsy",
            action="list",
            title="Software Keys",
            description="Cracked software and keygens available",
        )

        packet = gate.run_preflight_checks(packet)

        blocking_flags = [
            f for f in packet.compliance_flags if f.severity == ComplianceFlagSeverity.BLOCKING
        ]
        assert len(blocking_flags) > 0
        assert packet.has_blocking_flags() is True

    def test_preflight_detects_ai_content(self, gate):
        """Preflight detects AI-generated content."""
        packet = gate.create_packet(
            provider="youtube",
            action="publish",
            title="AI-Generated Art Showcase",
            description="Art created with Midjourney and DALL-E",
        )

        packet = gate.run_preflight_checks(packet)

        disclosure_flags = [f for f in packet.compliance_flags if f.category == "disclosure"]
        assert len(disclosure_flags) > 0
        assert len(packet.required_disclosures) > 0

    def test_approve_packet_success(self, gate):
        """Can approve packet without blocking flags."""
        packet = gate.create_packet(
            provider="youtube",
            action="publish",
            title="My Original Video",
            description="100% original content",
        )
        packet = gate.run_preflight_checks(packet)

        approved = gate.approve_packet(packet, approval_id="approval-123")

        assert approved.status == PublishPacketStatus.APPROVED
        assert approved.approval_id == "approval-123"

    def test_approve_packet_blocked(self, gate):
        """Cannot approve packet with blocking flags."""
        packet = gate.create_packet(
            provider="etsy",
            action="list",
            title="Pirated Content",
            description="Cracked software",
        )
        packet = gate.run_preflight_checks(packet)

        with pytest.raises(ValueError, match="blocking"):
            gate.approve_packet(packet, approval_id="approval-123")

    def test_reject_packet(self, gate):
        """Can reject packet with notes."""
        packet = gate.create_packet(
            provider="youtube",
            action="publish",
            title="Some Video",
            description="Description",
        )
        packet = gate.run_preflight_checks(packet)

        rejected = gate.reject_packet(packet, reviewer_notes="Not suitable for channel")

        assert rejected.status == PublishPacketStatus.REJECTED
        assert rejected.reviewer_notes == "Not suitable for channel"

    def test_verify_and_publish_success(self, gate):
        """Verify succeeds with matching content hash."""
        packet = gate.create_packet(
            provider="youtube",
            action="publish",
            title="My Video",
            description="Description",
        )
        packet = gate.run_preflight_checks(packet)
        packet = gate.approve_packet(packet, approval_id="approval-123")

        # Verify with correct hash
        result = gate.verify_and_publish(packet, packet.content_hash())

        assert result is True
        assert packet.status == PublishPacketStatus.PUBLISHED

    def test_verify_and_publish_hash_mismatch(self, gate):
        """Verify fails with mismatched content hash."""
        packet = gate.create_packet(
            provider="youtube",
            action="publish",
            title="My Video",
            description="Description",
        )
        packet = gate.run_preflight_checks(packet)
        packet = gate.approve_packet(packet, approval_id="approval-123")

        # Verify with wrong hash
        with pytest.raises(ValueError, match="Content hash mismatch"):
            gate.verify_and_publish(packet, "wrong_hash")

    def test_verify_requires_approval(self, gate):
        """Cannot publish without approval."""
        packet = gate.create_packet(
            provider="youtube",
            action="publish",
            title="My Video",
            description="Description",
        )
        packet = gate.run_preflight_checks(packet)

        # Not approved - should fail
        with pytest.raises(ValueError, match="not approved"):
            gate.verify_and_publish(packet, packet.content_hash())

    def test_save_and_load_artifact(self, gate):
        """Packet can be saved and loaded."""
        packet = gate.create_packet(
            provider="youtube",
            action="publish",
            title="My Video",
            description="Description",
            tags=["test"],
        )
        packet = gate.run_preflight_checks(packet)

        with TemporaryDirectory() as tmpdir:
            artifact_path = gate.save_packet_artifact(packet, Path(tmpdir))

            loaded = gate.load_packet_artifact(artifact_path)

            assert loaded.packet_id == packet.packet_id
            assert loaded.title == packet.title
            assert loaded.status == packet.status
            assert loaded.content_hash() == packet.content_hash()
