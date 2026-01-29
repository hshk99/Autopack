"""Policy monitor service.

Monitors provider policy pages and gates actions on policy freshness.
"""

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .models import (PolicyCategory, PolicyDiff, PolicyGateResult,
                     PolicySnapshot, PolicyStatus, ProviderPolicyConfig)

logger = logging.getLogger(__name__)


# Default provider configurations
DEFAULT_PROVIDERS = {
    "youtube": ProviderPolicyConfig.youtube(),
    "etsy": ProviderPolicyConfig.etsy(),
    "shopify": ProviderPolicyConfig.shopify(),
}


class PolicyMonitor:
    """Service for monitoring provider policies.

    Usage:
        monitor = PolicyMonitor(storage_dir=Path(".policy_snapshots"))

        # Check if we can proceed with an action
        result = monitor.check_policy_gate("youtube", "publish")
        if not result.can_proceed:
            print(f"Cannot proceed: {result.error_message}")

        # Fetch fresh snapshots
        monitor.refresh_snapshots("youtube")

        # Acknowledge a policy change
        monitor.acknowledge_change(diff_id="...", operator="admin")
    """

    def __init__(
        self,
        storage_dir: Optional[Path] = None,
        providers: Optional[dict[str, ProviderPolicyConfig]] = None,
    ):
        """Initialize the policy monitor.

        Args:
            storage_dir: Directory for storing policy snapshots
            providers: Provider configurations (defaults to YouTube, Etsy, Shopify)
        """
        self.storage_dir = storage_dir or Path(".policy_snapshots")
        self.providers = providers or DEFAULT_PROVIDERS
        self._snapshots: dict[str, dict[str, PolicySnapshot]] = {}
        self._diffs: dict[str, PolicyDiff] = {}

        # Load existing snapshots
        self._load_snapshots()

    def _load_snapshots(self) -> None:
        """Load existing snapshots from storage."""
        if not self.storage_dir.exists():
            return

        for provider_dir in self.storage_dir.iterdir():
            if not provider_dir.is_dir():
                continue

            provider = provider_dir.name
            self._snapshots[provider] = {}

            snapshot_file = provider_dir / "latest_snapshots.json"
            if snapshot_file.exists():
                try:
                    data = json.loads(snapshot_file.read_text(encoding="utf-8"))
                    for category, snap_data in data.items():
                        self._snapshots[provider][category] = PolicySnapshot(
                            snapshot_id=snap_data["snapshot_id"],
                            provider=snap_data["provider"],
                            policy_url=snap_data["policy_url"],
                            policy_category=PolicyCategory(snap_data["policy_category"]),
                            content_hash=snap_data["content_hash"],
                            fetched_at=datetime.fromisoformat(snap_data["fetched_at"]),
                            content_summary=snap_data.get("content_summary", ""),
                            status=PolicyStatus(snap_data.get("status", "fresh")),
                            acknowledged_at=(
                                datetime.fromisoformat(snap_data["acknowledged_at"])
                                if snap_data.get("acknowledged_at")
                                else None
                            ),
                            acknowledged_by=snap_data.get("acknowledged_by"),
                            freshness_days=snap_data.get("freshness_days", 7),
                        )
                except (json.JSONDecodeError, KeyError) as e:
                    logger.warning(f"Failed to load snapshots for {provider}: {e}")

    def _save_snapshots(self, provider: str) -> None:
        """Save snapshots for a provider."""
        provider_dir = self.storage_dir / provider
        provider_dir.mkdir(parents=True, exist_ok=True)

        if provider not in self._snapshots:
            return

        data = {category: snap.to_dict() for category, snap in self._snapshots[provider].items()}

        snapshot_file = provider_dir / "latest_snapshots.json"
        snapshot_file.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def get_snapshot(self, provider: str, category: PolicyCategory) -> Optional[PolicySnapshot]:
        """Get the latest snapshot for a provider/category."""
        return self._snapshots.get(provider, {}).get(category.value)

    def get_all_snapshots(self, provider: str) -> list[PolicySnapshot]:
        """Get all snapshots for a provider."""
        return list(self._snapshots.get(provider, {}).values())

    def create_snapshot(
        self,
        provider: str,
        policy_url: str,
        category: PolicyCategory,
        content: str,
        content_summary: str = "",
    ) -> PolicySnapshot:
        """Create a new policy snapshot.

        Args:
            provider: Provider name
            policy_url: URL of the policy page
            category: Policy category
            content: Raw content of the policy page
            content_summary: Optional summary

        Returns:
            New PolicySnapshot
        """
        content_hash = PolicySnapshot.compute_hash(content)
        now = datetime.now(timezone.utc)

        # Check for changes from previous snapshot
        old_snapshot = self.get_snapshot(provider, category)
        status = PolicyStatus.FRESH

        if old_snapshot and old_snapshot.content_hash != content_hash:
            status = PolicyStatus.CHANGED
            # Create a diff record
            diff = PolicyDiff(
                diff_id=f"diff-{uuid.uuid4().hex[:12]}",
                provider=provider,
                policy_category=category,
                old_snapshot_id=old_snapshot.snapshot_id,
                new_snapshot_id=f"snap-{uuid.uuid4().hex[:12]}",
                old_hash=old_snapshot.content_hash,
                new_hash=content_hash,
                detected_at=now,
                summary=f"Policy content changed for {provider} {category.value}",
            )
            self._diffs[diff.diff_id] = diff
            self._save_diff(diff)

        snapshot = PolicySnapshot(
            snapshot_id=f"snap-{uuid.uuid4().hex[:12]}",
            provider=provider,
            policy_url=policy_url,
            policy_category=category,
            content_hash=content_hash,
            fetched_at=now,
            content_summary=content_summary,
            raw_content=content,
            status=status,
            freshness_days=self.providers.get(
                provider, ProviderPolicyConfig(provider)
            ).freshness_days,
        )

        # Store snapshot
        if provider not in self._snapshots:
            self._snapshots[provider] = {}
        self._snapshots[provider][category.value] = snapshot
        self._save_snapshots(provider)

        logger.info(
            f"Created policy snapshot: {snapshot.snapshot_id} "
            f"(provider={provider}, category={category.value}, status={status.value})"
        )

        return snapshot

    def _save_diff(self, diff: PolicyDiff) -> None:
        """Save a policy diff to storage."""
        provider_dir = self.storage_dir / diff.provider
        provider_dir.mkdir(parents=True, exist_ok=True)

        diffs_file = provider_dir / "policy_diffs.json"
        diffs_data = []
        if diffs_file.exists():
            try:
                diffs_data = json.loads(diffs_file.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                pass

        diffs_data.append(diff.to_dict())
        diffs_file.write_text(json.dumps(diffs_data, indent=2), encoding="utf-8")

    def check_policy_gate(
        self,
        provider: str,
        action: str,
        required_categories: Optional[list[PolicyCategory]] = None,
    ) -> PolicyGateResult:
        """Check if an action can proceed based on policy status.

        Args:
            provider: Provider to check
            action: Action being attempted (e.g., "publish", "list")
            required_categories: Specific categories to check (defaults to all)

        Returns:
            PolicyGateResult indicating if action can proceed
        """
        config = self.providers.get(provider)
        if not config:
            return PolicyGateResult(
                can_proceed=False,
                provider=provider,
                action=action,
                error_message=f"Unknown provider: {provider}",
            )

        if not config.enabled:
            return PolicyGateResult(
                can_proceed=True,
                provider=provider,
                action=action,
            )

        # Determine which categories to check
        if required_categories:
            categories_to_check = required_categories
        else:
            categories_to_check = [
                PolicyCategory(p["category"]) if isinstance(p["category"], str) else p["category"]
                for p in config.policies
            ]

        stale = []
        unacknowledged = []
        missing = []
        now = datetime.now(timezone.utc)

        for category in categories_to_check:
            snapshot = self.get_snapshot(provider, category)

            if snapshot is None:
                missing.append(category.value)
                continue

            if not snapshot.is_fresh(now):
                stale.append(category.value)

            if snapshot.status == PolicyStatus.CHANGED:
                unacknowledged.append(category.value)

        can_proceed = not stale and not unacknowledged and not missing
        error_message = None

        if not can_proceed:
            parts = []
            if stale:
                parts.append(f"stale policies: {stale}")
            if unacknowledged:
                parts.append(f"unacknowledged changes: {unacknowledged}")
            if missing:
                parts.append(f"missing snapshots: {missing}")
            error_message = f"Policy gate blocked for {provider}/{action}: {'; '.join(parts)}"

        return PolicyGateResult(
            can_proceed=can_proceed,
            provider=provider,
            action=action,
            stale_policies=stale,
            unacknowledged_changes=unacknowledged,
            missing_snapshots=missing,
            error_message=error_message,
        )

    def acknowledge_change(
        self,
        provider: str,
        category: PolicyCategory,
        operator: str,
        notes: str = "",
    ) -> Optional[PolicySnapshot]:
        """Acknowledge a policy change.

        Args:
            provider: Provider name
            category: Policy category
            operator: Operator acknowledging the change
            notes: Optional acknowledgment notes

        Returns:
            Updated snapshot, or None if not found
        """
        snapshot = self.get_snapshot(provider, category)
        if snapshot is None:
            return None

        if snapshot.status != PolicyStatus.CHANGED:
            logger.warning(
                f"Snapshot {snapshot.snapshot_id} is not in CHANGED status "
                f"(current: {snapshot.status})"
            )
            return snapshot

        snapshot.status = PolicyStatus.ACKNOWLEDGED
        snapshot.acknowledged_at = datetime.now(timezone.utc)
        snapshot.acknowledged_by = operator

        self._save_snapshots(provider)

        logger.info(f"Acknowledged policy change: {snapshot.snapshot_id} by {operator}")

        return snapshot

    def get_unacknowledged_changes(self, provider: Optional[str] = None) -> list[PolicySnapshot]:
        """Get all snapshots with unacknowledged changes.

        Args:
            provider: Optional provider filter

        Returns:
            List of snapshots needing acknowledgment
        """
        results = []

        providers_to_check = [provider] if provider else self._snapshots.keys()

        for p in providers_to_check:
            for snapshot in self._snapshots.get(p, {}).values():
                if snapshot.status == PolicyStatus.CHANGED:
                    results.append(snapshot)

        return results

    def get_health_summary(self) -> dict:
        """Get overall policy monitoring health summary."""
        now = datetime.now(timezone.utc)

        summary = {
            "checked_at": now.isoformat(),
            "providers": {},
            "overall_status": "healthy",
            "stale_count": 0,
            "changed_count": 0,
            "missing_count": 0,
        }

        for provider, config in self.providers.items():
            if not config.enabled:
                continue

            provider_summary = {
                "enabled": True,
                "policies": [],
                "status": "healthy",
            }

            for policy in config.policies:
                category = (
                    PolicyCategory(policy["category"])
                    if isinstance(policy["category"], str)
                    else policy["category"]
                )
                snapshot = self.get_snapshot(provider, category)

                policy_status = {
                    "name": policy.get("name", category.value),
                    "category": category.value,
                    "status": "missing",
                }

                if snapshot:
                    if snapshot.status == PolicyStatus.CHANGED:
                        policy_status["status"] = "changed"
                        summary["changed_count"] += 1
                    elif not snapshot.is_fresh(now):
                        policy_status["status"] = "stale"
                        summary["stale_count"] += 1
                    else:
                        policy_status["status"] = "fresh"
                    policy_status["last_checked"] = snapshot.fetched_at.isoformat()
                else:
                    summary["missing_count"] += 1

                provider_summary["policies"].append(policy_status)

            # Determine provider status
            statuses = [p["status"] for p in provider_summary["policies"]]
            if "changed" in statuses:
                provider_summary["status"] = "attention_required"
            elif "stale" in statuses or "missing" in statuses:
                provider_summary["status"] = "degraded"
            else:
                provider_summary["status"] = "healthy"

            summary["providers"][provider] = provider_summary

        # Determine overall status
        if summary["changed_count"] > 0:
            summary["overall_status"] = "attention_required"
        elif summary["stale_count"] > 0 or summary["missing_count"] > 0:
            summary["overall_status"] = "degraded"

        return summary
