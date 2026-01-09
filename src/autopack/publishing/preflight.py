"""Publish preflight gate for content/IP/compliance checks.

Implements gap analysis item 6.10:
- Deterministic preflight checks before publishing
- Heuristic IP/compliance flagging
- Required disclosure detection
"""

import json
import logging
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .models import (
    PublishPacket,
    PublishPacketStatus,
    ComplianceFlag,
    ComplianceFlagSeverity,
    MediaAsset,
)

logger = logging.getLogger(__name__)


# Heuristic patterns for compliance checking
# These are basic patterns - real implementations would use more sophisticated checks
TRADEMARK_PATTERNS = [
    (r"\b(disney|marvel|nintendo|pokemon|sony|microsoft|apple|google)\b", "Major brand trademark"),
    (r"\b(coca[- ]?cola|pepsi|nike|adidas|gucci|prada)\b", "Brand trademark"),
    (r"\b(youtube|tiktok|instagram|facebook|twitter)\b", "Social platform trademark"),
]

BANNED_CONTENT_PATTERNS = [
    (r"\b(?:pirated?|crack(?:ed)?|keygen|torrent)\b", "Piracy-related content"),
    (r"\b(?:counterfeit|replica|fake\s+brand)\b", "Counterfeit goods"),
    (r"\b(?:weapon|firearm|ammunition|explosive)\b", "Restricted items"),
]

AI_CONTENT_INDICATORS = [
    r"\b(ai[- ]?generated|artificial intelligence|machine learning)\b",
    r"\b(dall[- ]?e|midjourney|stable\s+diffusion|chatgpt)\b",
    r"\b(generated\s+by|created\s+with)\s+\w*\s*ai\b",
]

DISCLOSURE_REQUIREMENTS = {
    "youtube": [
        "AI-generated content must be disclosed per YouTube policy",
    ],
    "etsy": [
        "Handmade claims require disclosure if AI-assisted",
        "Digital items must be clearly labeled",
    ],
    "shopify": [
        "Product origin must be accurately represented",
    ],
}


class PublishPreflightGate:
    """Gate for publish operations requiring preflight checks.

    Ensures no publish/list operation occurs without:
    1. A completed preflight check
    2. An approved publish packet
    3. Verification that content matches the approved packet
    """

    def __init__(self, output_dir: Optional[Path] = None):
        """Initialize the preflight gate.

        Args:
            output_dir: Directory for storing publish packet artifacts
        """
        self.output_dir = output_dir or Path(".autonomous_runs")

    def create_packet(
        self,
        provider: str,
        action: str,
        title: str,
        description: str,
        tags: Optional[list[str]] = None,
        media_assets: Optional[list[MediaAsset]] = None,
        run_id: Optional[str] = None,
        phase_number: Optional[int] = None,
    ) -> PublishPacket:
        """Create a new publish packet for review.

        Args:
            provider: Target platform (youtube, etsy, shopify)
            action: Action type (publish, list, update)
            title: Content title
            description: Content description
            tags: Content tags
            media_assets: Media files with hashes
            run_id: Associated run ID
            phase_number: Phase that triggered this

        Returns:
            PublishPacket ready for preflight checks
        """
        packet = PublishPacket(
            packet_id=str(uuid.uuid4()),
            provider=provider,
            action=action,
            title=title,
            description=description,
            tags=tags or [],
            media_assets=media_assets or [],
            run_id=run_id,
            phase_number=phase_number,
        )

        logger.info(f"Created publish packet: {packet.packet_id} for {provider}/{action}")

        return packet

    def run_preflight_checks(self, packet: PublishPacket) -> PublishPacket:
        """Run all preflight checks on a packet.

        Checks for:
        - Trademark/brand keywords
        - Banned content patterns
        - AI content indicators (for disclosure requirements)
        - Provider-specific requirements

        Args:
            packet: The publish packet to check

        Returns:
            Updated packet with compliance flags and disclosures
        """
        all_text = f"{packet.title} {packet.description} {' '.join(packet.tags)}".lower()

        # Check for trademark keywords
        for pattern, message in TRADEMARK_PATTERNS:
            matches = re.findall(pattern, all_text, re.IGNORECASE)
            if matches:
                packet.compliance_flags.append(
                    ComplianceFlag(
                        category="trademark",
                        severity=ComplianceFlagSeverity.WARNING,
                        message=f"Trademark detected: {message}",
                        detected_text=", ".join(set(matches)),
                        remediation="Ensure you have rights to use this trademark or remove reference",
                    )
                )

        # Check for banned content patterns
        for pattern, message in BANNED_CONTENT_PATTERNS:
            matches = re.findall(pattern, all_text, re.IGNORECASE)
            if matches:
                packet.compliance_flags.append(
                    ComplianceFlag(
                        category="banned_content",
                        severity=ComplianceFlagSeverity.BLOCKING,
                        message=f"Banned content detected: {message}",
                        detected_text=", ".join(set(matches)),
                        remediation="Remove prohibited content before publishing",
                    )
                )

        # Check for AI content indicators
        is_ai_content = any(
            re.search(pattern, all_text, re.IGNORECASE) for pattern in AI_CONTENT_INDICATORS
        )

        if is_ai_content:
            packet.compliance_flags.append(
                ComplianceFlag(
                    category="disclosure",
                    severity=ComplianceFlagSeverity.INFO,
                    message="AI-generated content detected",
                    remediation="Ensure proper AI disclosure per platform policy",
                )
            )

            # Add required disclosures for this provider
            provider_disclosures = DISCLOSURE_REQUIREMENTS.get(packet.provider, [])
            packet.required_disclosures.extend(provider_disclosures)

        # Mark as ready for review
        packet.status = PublishPacketStatus.PENDING_REVIEW

        logger.info(
            f"Preflight complete for {packet.packet_id}: "
            f"{len(packet.compliance_flags)} flags, "
            f"{len(packet.required_disclosures)} disclosures"
        )

        return packet

    def approve_packet(
        self,
        packet: PublishPacket,
        approval_id: str,
        reviewer_notes: Optional[str] = None,
    ) -> PublishPacket:
        """Approve a packet for publishing.

        Args:
            packet: The packet to approve
            approval_id: Reference to approval record
            reviewer_notes: Optional notes from reviewer

        Returns:
            Updated packet with approved status

        Raises:
            ValueError: If packet cannot be approved (blocking flags, etc.)
        """
        if not packet.can_be_approved():
            blocking = [
                f for f in packet.compliance_flags if f.severity == ComplianceFlagSeverity.BLOCKING
            ]
            raise ValueError(
                f"Cannot approve packet with blocking issues: " f"{[f.message for f in blocking]}"
            )

        packet.status = PublishPacketStatus.APPROVED
        packet.approval_id = approval_id
        packet.reviewer_notes = reviewer_notes
        packet.reviewed_at = datetime.now(timezone.utc)

        logger.info(f"Approved publish packet: {packet.packet_id}")

        return packet

    def reject_packet(
        self,
        packet: PublishPacket,
        reviewer_notes: str,
    ) -> PublishPacket:
        """Reject a packet.

        Args:
            packet: The packet to reject
            reviewer_notes: Reason for rejection

        Returns:
            Updated packet with rejected status
        """
        packet.status = PublishPacketStatus.REJECTED
        packet.reviewer_notes = reviewer_notes
        packet.reviewed_at = datetime.now(timezone.utc)

        logger.info(f"Rejected publish packet: {packet.packet_id}")

        return packet

    def verify_and_publish(
        self,
        packet: PublishPacket,
        actual_content_hash: str,
    ) -> bool:
        """Verify content matches approved packet before publishing.

        Args:
            packet: The approved packet
            actual_content_hash: Hash of actual content being published

        Returns:
            True if verification passes

        Raises:
            ValueError: If verification fails
        """
        if not packet.can_be_published():
            raise ValueError(f"Packet {packet.packet_id} is not approved (status: {packet.status})")

        if actual_content_hash != packet.content_hash():
            raise ValueError(
                f"Content hash mismatch: approved={packet.content_hash()[:16]}... "
                f"actual={actual_content_hash[:16]}..."
            )

        packet.status = PublishPacketStatus.PUBLISHED
        packet.published_at = datetime.now(timezone.utc)

        logger.info(f"Verified and marked as published: {packet.packet_id}")

        return True

    def save_packet_artifact(
        self,
        packet: PublishPacket,
        run_dir: Optional[Path] = None,
    ) -> Path:
        """Save packet as run-local artifact.

        Args:
            packet: The packet to save
            run_dir: Directory for this run's artifacts

        Returns:
            Path to saved artifact
        """
        if run_dir is None:
            run_dir = self.output_dir / "publish_packets"

        run_dir.mkdir(parents=True, exist_ok=True)
        artifact_path = run_dir / f"publish_packet_{packet.packet_id}.json"

        artifact_path.write_text(
            json.dumps(packet.to_dict(), indent=2),
            encoding="utf-8",
        )

        logger.info(f"Saved publish packet artifact: {artifact_path}")

        return artifact_path

    def load_packet_artifact(self, artifact_path: Path) -> PublishPacket:
        """Load packet from artifact file.

        Args:
            artifact_path: Path to artifact JSON

        Returns:
            Loaded PublishPacket
        """
        data = json.loads(artifact_path.read_text(encoding="utf-8"))
        return PublishPacket.from_dict(data)
