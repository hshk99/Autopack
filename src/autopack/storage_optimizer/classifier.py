"""
Policy-aware file classifier for identifying cleanup candidates.

Classifies files and directories based on storage policy rules,
ensuring protected paths are never flagged for cleanup.
"""

from typing import List, Optional

from .models import ScanResult, CleanupCandidate
from .policy import StoragePolicy, is_path_protected, get_category_for_path


class FileClassifier:
    """
    Classifies files and directories as cleanup candidates based on policy.

    Key principles:
    1. NEVER classify protected paths (checked first)
    2. Use policy categories for classification
    3. Respect retention windows
    4. Mark approval requirements correctly
    """

    def __init__(self, policy: StoragePolicy):
        """
        Initialize classifier with storage policy.

        Args:
            policy: StoragePolicy object with protection and categorization rules
        """
        self.policy = policy

    def classify(self, scan_result: ScanResult) -> Optional[CleanupCandidate]:
        """
        Classify a single scan result as a cleanup candidate.

        Args:
            scan_result: ScanResult to classify

        Returns:
            CleanupCandidate if the item can be cleaned up, None if protected or not suitable
        """
        # Step 1: CRITICAL - Check if path is protected
        if is_path_protected(scan_result.path, self.policy):
            return None  # Never flag protected paths

        # Step 2: Determine category based on path
        category = get_category_for_path(scan_result.path, self.policy)

        if category is None:
            return None  # No category match, skip

        # Get category policy
        cat_policy = self.policy.categories.get(category)
        if cat_policy is None or not cat_policy.delete_enabled:
            return None  # Category doesn't allow deletion

        # Step 3: Check retention window if applicable
        retention_policy = self.policy.retention.get(category)
        if retention_policy and retention_policy.delete_after_days:
            if scan_result.age_days < retention_policy.delete_after_days:
                return None  # Within retention window, don't delete

        # Step 4: Build cleanup candidate
        reason = self._generate_reason(scan_result, category, cat_policy)

        return CleanupCandidate(
            path=scan_result.path,
            category=category,
            size_bytes=scan_result.size_bytes,
            age_days=scan_result.age_days,
            reason=reason,
            can_auto_delete=not cat_policy.delete_requires_approval,
            requires_approval=cat_policy.delete_requires_approval,
            modified=scan_result.modified,
        )

    def classify_batch(self, scan_results: List[ScanResult]) -> List[CleanupCandidate]:
        """
        Classify multiple scan results.

        Args:
            scan_results: List of ScanResult objects to classify

        Returns:
            List of CleanupCandidate objects (excludes protected paths)
        """
        candidates = []

        for scan_result in scan_results:
            candidate = self.classify(scan_result)
            if candidate is not None:
                candidates.append(candidate)

        return candidates

    def _generate_reason(self, scan_result: ScanResult, category: str, cat_policy) -> str:
        """
        Generate human-readable reason for cleanup recommendation.

        Args:
            scan_result: The scan result being classified
            category: Category name
            cat_policy: Category policy object

        Returns:
            Human-readable reason string
        """
        reasons = []

        # Category match
        reasons.append(f"Matched category '{category}'")

        # Age-based reasoning
        if scan_result.age_days > 365:
            reasons.append(f"not modified in {scan_result.age_days // 365} year(s)")
        elif scan_result.age_days > 90:
            reasons.append(f"not modified in {scan_result.age_days} days")
        elif scan_result.age_days > 30:
            reasons.append(f"over {scan_result.age_days // 30} month(s) old")

        # Size-based reasoning
        if scan_result.size_gb > 1.0:
            reasons.append(f"large size ({scan_result.size_gb:.1f} GB)")
        elif scan_result.size_mb > 100:
            reasons.append(f"size: {scan_result.size_mb:.0f} MB")

        # Specific category insights
        if category == "dev_caches":
            if "node_modules" in scan_result.path:
                reasons.append("node_modules can be regenerated via npm install")
            elif "venv" in scan_result.path or ".venv" in scan_result.path:
                reasons.append("virtual environment can be recreated")
            elif "__pycache__" in scan_result.path or scan_result.path.endswith(".pyc"):
                reasons.append("Python cache, safe to delete")

        elif category == "diagnostics_logs":
            reasons.append("diagnostic logs can be archived or deleted")

        elif category == "runs":
            if scan_result.age_days > 180:
                reasons.append("old run data beyond retention window")

        return "; ".join(reasons)

    def get_protected_paths(self, scan_results: List[ScanResult]) -> List[str]:
        """
        Identify which scanned paths are protected by policy.

        Useful for reporting what won't be cleaned.

        Args:
            scan_results: List of ScanResult objects

        Returns:
            List of protected path strings
        """
        protected = []

        for scan_result in scan_results:
            if is_path_protected(scan_result.path, self.policy):
                protected.append(scan_result.path)

        return protected

    def get_statistics(self, candidates: List[CleanupCandidate]) -> dict:
        """
        Generate statistics about cleanup candidates.

        Args:
            candidates: List of CleanupCandidate objects

        Returns:
            Dictionary with statistics by category
        """
        stats = {
            "total_candidates": len(candidates),
            "total_size_bytes": sum(c.size_bytes for c in candidates),
            "requires_approval": sum(1 for c in candidates if c.requires_approval),
            "can_auto_delete": sum(1 for c in candidates if c.can_auto_delete),
            "by_category": {},
        }

        # Group by category
        for candidate in candidates:
            cat = candidate.category
            if cat not in stats["by_category"]:
                stats["by_category"][cat] = {
                    "count": 0,
                    "total_size_bytes": 0,
                    "requires_approval": 0,
                }

            stats["by_category"][cat]["count"] += 1
            stats["by_category"][cat]["total_size_bytes"] += candidate.size_bytes
            if candidate.requires_approval:
                stats["by_category"][cat]["requires_approval"] += 1

        return stats
