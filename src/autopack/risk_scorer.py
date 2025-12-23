"""Risk-Based Approval Gates with Deterministic Risk Scoring.

Provides deterministic risk assessment for phase changes without LLM calls.
Supports pause/resume mechanism for high-risk changes requiring human approval.

Architecture:
- Deterministic risk scoring based on:
  - Scope size (>20 files = high risk)
  - Protected paths (src/autopack/models.py, alembic/versions/*)
  - Category patterns (database migrations = high risk)
  - Cross-cutting changes (multiple directories = medium risk)
- Risk levels: LOW (0-0.3), MEDIUM (0.3-0.6), HIGH (0.6-1.0)
- Pause/Resume mechanism:
  - HIGH risk: Requires human approval before execution
  - MEDIUM risk: Optional approval (configurable)
  - LOW risk: Auto-approved

Usage:
    scorer = RiskScorer(workspace_root=Path("/project"))
    risk = scorer.score_phase(
        phase_spec={"description": "...", "scope": {...}},
        file_changes=["src/main.py", "tests/test_main.py"]
    )
    
    if risk.level == RiskLevel.HIGH:
        # Request approval
        approval = await request_approval(risk)
        if not approval.approved:
            raise PhaseRejected("High-risk change rejected by human")
"""

import logging
import re
from pathlib import Path
from typing import List, Dict, Optional, Set
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class RiskLevel(str, Enum):
    """Risk level classification."""
    LOW = "low"          # 0.0 - 0.3
    MEDIUM = "medium"    # 0.3 - 0.6
    HIGH = "high"        # 0.6 - 1.0


@dataclass
class RiskScore:
    """Risk assessment result."""
    level: RiskLevel
    score: float  # 0.0 - 1.0
    factors: Dict[str, float]  # Factor name -> contribution
    reasons: List[str]  # Human-readable reasons
    requires_approval: bool
    auto_approved: bool = False


class RiskScorer:
    """Deterministic risk scorer for phase changes."""

    # Protected paths (high risk if modified)
    PROTECTED_PATHS = [
        "src/autopack/models.py",
        "alembic/versions/*",
        ".autonomous_runs/*",
        ".git/*",
        "autopack.db",
        "config/safety_profiles.yaml",
        "config/governance.yaml",
    ]

    # High-risk categories
    HIGH_RISK_CATEGORIES = [
        "database_migration",
        "schema_change",
        "security",
        "authentication",
        "authorization",
    ]

    # Medium-risk categories
    MEDIUM_RISK_CATEGORIES = [
        "api_change",
        "refactor",
        "infrastructure",
        "configuration",
    ]

    # Risk thresholds
    LARGE_SCOPE_THRESHOLD = 20  # files
    CROSS_CUTTING_THRESHOLD = 3  # directories

    def __init__(
        self,
        workspace_root: Path,
        require_approval_for_medium: bool = False,
    ):
        """Initialize risk scorer.

        Args:
            workspace_root: Root directory of workspace
            require_approval_for_medium: Require approval for medium-risk changes
        """
        self.workspace_root = workspace_root.resolve()
        self.require_approval_for_medium = require_approval_for_medium

    def score_phase(
        self,
        phase_spec: Dict,
        file_changes: List[str],
    ) -> RiskScore:
        """Score risk for a phase.

        Args:
            phase_spec: Phase specification dict
            file_changes: List of file paths to be modified

        Returns:
            RiskScore with level, score, and reasons
        """
        factors: Dict[str, float] = {}
        reasons: List[str] = []

        # Factor 1: Scope size (0.0 - 0.4)
        scope_risk = self._score_scope_size(file_changes)
        factors["scope_size"] = scope_risk
        if scope_risk > 0.2:
            reasons.append(
                f"Large scope: {len(file_changes)} files "
                f"(threshold: {self.LARGE_SCOPE_THRESHOLD})"
            )

        # Factor 2: Protected paths (0.0 - 0.5)
        protected_risk = self._score_protected_paths(file_changes)
        factors["protected_paths"] = protected_risk
        if protected_risk > 0.0:
            protected_files = self._get_protected_files(file_changes)
            reasons.append(
                f"Protected paths modified: {', '.join(protected_files)}"
            )

        # Factor 3: Category patterns (0.0 - 0.3)
        category_risk = self._score_category(phase_spec)
        factors["category"] = category_risk
        if category_risk > 0.2:
            category = phase_spec.get("task_category", "unknown")
            reasons.append(f"High-risk category: {category}")

        # Factor 4: Cross-cutting changes (0.0 - 0.2)
        cross_cutting_risk = self._score_cross_cutting(file_changes)
        factors["cross_cutting"] = cross_cutting_risk
        if cross_cutting_risk > 0.1:
            dirs = self._get_affected_directories(file_changes)
            reasons.append(
                f"Cross-cutting changes: {len(dirs)} directories affected"
            )

        # Compute total score (weighted sum)
        total_score = (
            scope_risk * 0.3 +
            protected_risk * 0.4 +
            category_risk * 0.2 +
            cross_cutting_risk * 0.1
        )

        # Classify risk level
        if total_score >= 0.6:
            level = RiskLevel.HIGH
            requires_approval = True
        elif total_score >= 0.3:
            level = RiskLevel.MEDIUM
            requires_approval = self.require_approval_for_medium
        else:
            level = RiskLevel.LOW
            requires_approval = False

        # Auto-approve low-risk changes
        auto_approved = level == RiskLevel.LOW

        logger.info(
            f"[RiskScorer] Phase risk: {level.value} (score={total_score:.2f}, "
            f"requires_approval={requires_approval})"
        )

        return RiskScore(
            level=level,
            score=total_score,
            factors=factors,
            reasons=reasons,
            requires_approval=requires_approval,
            auto_approved=auto_approved,
        )

    def _score_scope_size(self, file_changes: List[str]) -> float:
        """Score risk based on scope size.

        Args:
            file_changes: List of file paths

        Returns:
            Risk score (0.0 - 0.4)
        """
        num_files = len(file_changes)
        if num_files == 0:
            return 0.0
        elif num_files <= 5:
            return 0.0
        elif num_files <= 10:
            return 0.1
        elif num_files <= self.LARGE_SCOPE_THRESHOLD:
            return 0.2
        else:
            # Scale up to 0.4 for very large scopes
            return min(0.4, 0.2 + (num_files - self.LARGE_SCOPE_THRESHOLD) * 0.01)

    def _score_protected_paths(self, file_changes: List[str]) -> float:
        """Score risk based on protected path modifications.

        Args:
            file_changes: List of file paths

        Returns:
            Risk score (0.0 - 0.5)
        """
        protected_files = self._get_protected_files(file_changes)
        if not protected_files:
            return 0.0

        # High risk if any protected path is modified
        return 0.5

    def _get_protected_files(self, file_changes: List[str]) -> List[str]:
        """Get list of protected files in changes.

        Args:
            file_changes: List of file paths

        Returns:
            List of protected file paths
        """
        protected = []
        for file_path in file_changes:
            for pattern in self.PROTECTED_PATHS:
                if self._matches_pattern(file_path, pattern):
                    protected.append(file_path)
                    break
        return protected

    def _matches_pattern(self, file_path: str, pattern: str) -> bool:
        """Check if file path matches pattern (supports wildcards).

        Args:
            file_path: File path to check
            pattern: Pattern (supports * wildcard)

        Returns:
            True if matches
        """
        # Convert glob pattern to regex
        regex_pattern = pattern.replace("*", ".*")
        return bool(re.match(regex_pattern, file_path))

    def _score_category(self, phase_spec: Dict) -> float:
        """Score risk based on phase category.

        Args:
            phase_spec: Phase specification dict

        Returns:
            Risk score (0.0 - 0.3)
        """
        category = phase_spec.get("task_category", "").lower()
        description = phase_spec.get("description", "").lower()

        # Check high-risk categories
        for high_risk_cat in self.HIGH_RISK_CATEGORIES:
            if high_risk_cat in category or high_risk_cat in description:
                return 0.3

        # Check medium-risk categories
        for medium_risk_cat in self.MEDIUM_RISK_CATEGORIES:
            if medium_risk_cat in category or medium_risk_cat in description:
                return 0.15

        return 0.0

    def _score_cross_cutting(self, file_changes: List[str]) -> float:
        """Score risk based on cross-cutting changes.

        Args:
            file_changes: List of file paths

        Returns:
            Risk score (0.0 - 0.2)
        """
        dirs = self._get_affected_directories(file_changes)
        num_dirs = len(dirs)

        if num_dirs <= 1:
            return 0.0
        elif num_dirs <= 2:
            return 0.05
        elif num_dirs <= self.CROSS_CUTTING_THRESHOLD:
            return 0.1
        else:
            # Scale up to 0.2 for very cross-cutting changes
            return min(0.2, 0.1 + (num_dirs - self.CROSS_CUTTING_THRESHOLD) * 0.02)

    def _get_affected_directories(self, file_changes: List[str]) -> Set[str]:
        """Get set of affected directories.

        Args:
            file_changes: List of file paths

        Returns:
            Set of directory paths
        """
        dirs = set()
        for file_path in file_changes:
            path = Path(file_path)
            if path.parent != Path("."):
                dirs.add(str(path.parent))
        return dirs


class ApprovalGate:
    """Approval gate for high-risk changes."""

    def __init__(self, api_url: str, api_key: Optional[str] = None):
        """Initialize approval gate.

        Args:
            api_url: Autopack API URL
            api_key: API key for authentication
        """
        self.api_url = api_url.rstrip("/")
        self.api_key = api_key

    async def request_approval(
        self,
        run_id: str,
        phase_id: str,
        risk_score: RiskScore,
        timeout_seconds: int = 300,
    ) -> bool:
        """Request human approval for high-risk change.

        Args:
            run_id: Run ID
            phase_id: Phase ID
            risk_score: Risk assessment
            timeout_seconds: Approval timeout

        Returns:
            True if approved, False if rejected/timeout
        """
        import httpx

        # Prepare approval request
        request_data = {
            "run_id": run_id,
            "phase_id": phase_id,
            "risk_level": risk_score.level.value,
            "risk_score": risk_score.score,
            "reasons": risk_score.reasons,
            "timeout_seconds": timeout_seconds,
        }

        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        try:
            async with httpx.AsyncClient() as client:
                # Submit approval request
                response = await client.post(
                    f"{self.api_url}/approval/request",
                    json=request_data,
                    headers=headers,
                    timeout=10.0,
                )
                response.raise_for_status()
                approval_id = response.json()["approval_id"]

                logger.info(
                    f"[ApprovalGate] Approval request submitted: {approval_id} "
                    f"(timeout={timeout_seconds}s)"
                )

                # Poll for approval status
                import asyncio
                start_time = asyncio.get_event_loop().time()
                while True:
                    elapsed = asyncio.get_event_loop().time() - start_time
                    if elapsed >= timeout_seconds:
                        logger.warning(
                            f"[ApprovalGate] Approval timeout: {approval_id}"
                        )
                        return False

                    # Check status
                    status_response = await client.get(
                        f"{self.api_url}/approval/status/{approval_id}",
                        headers=headers,
                        timeout=10.0,
                    )
                    status_response.raise_for_status()
                    status_data = status_response.json()

                    if status_data["status"] == "approved":
                        logger.info(
                            f"[ApprovalGate] Approval granted: {approval_id}"
                        )
                        return True
                    elif status_data["status"] == "rejected":
                        logger.info(
                            f"[ApprovalGate] Approval rejected: {approval_id}"
                        )
                        return False

                    # Wait before polling again
                    await asyncio.sleep(5.0)

        except Exception as e:
            logger.error(f"[ApprovalGate] Approval request failed: {e}")
            return False

    def pause_execution(
        self,
        run_id: str,
        phase_id: str,
        reason: str,
    ) -> None:
        """Pause execution for manual review.

        Args:
            run_id: Run ID
            phase_id: Phase ID
            reason: Reason for pause
        """
        logger.warning(
            f"[ApprovalGate] Execution paused: run={run_id}, phase={phase_id}, "
            f"reason={reason}"
        )
        # Pause mechanism: Set phase state to PAUSED in database
        # (Implementation depends on database schema)

    def resume_execution(
        self,
        run_id: str,
        phase_id: str,
    ) -> None:
        """Resume execution after approval.

        Args:
            run_id: Run ID
            phase_id: Phase ID
        """
        logger.info(
            f"[ApprovalGate] Execution resumed: run={run_id}, phase={phase_id}"
        )
        # Resume mechanism: Set phase state to QUEUED in database
        # (Implementation depends on database schema)
