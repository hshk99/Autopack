"""Plan proposer - gap-to-action mapping with governance.

Maps gaps to bounded actions under strict governance rules:
- Default-deny approval policy
- Narrow auto-approval rules
- Protected path enforcement
- Budget compliance
- Risk scoring
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from ..gaps.models import GapReportV1, Gap
from ..intention_anchor.v2 import IntentionAnchorV2
from .models import (
    Action,
    BudgetCompliance,
    EstimatedCost,
    GovernanceChecks,
    PlanMetadata,
    PlanProposalV1,
    PlanSummary,
    ProtectedPathCheck,
)

logger = logging.getLogger(__name__)

PROPOSER_VERSION = "1.0.0"

# NEVER_AUTO_APPROVE paths (always require approval)
NEVER_AUTO_APPROVE_PATTERNS = [
    "docs/",
    "config/",
    ".github/",
    "src/autopack/",
    "tests/",
]


class PlanProposer:
    """Plan proposer with governance.

    Maps gaps to actions with:
    - Risk scoring
    - Approval classification (auto/requires/blocked)
    - Protected path checks
    - Budget compliance
    - Default-deny policy
    """

    def __init__(
        self,
        anchor: IntentionAnchorV2,
        gap_report: GapReportV1,
        workspace_root: Optional[Path] = None,
    ):
        """Initialize plan proposer.

        Args:
            anchor: Intention anchor v2
            gap_report: Gap report v1
            workspace_root: Workspace root (for path checks)
        """
        self.anchor = anchor
        self.gap_report = gap_report
        self.workspace_root = workspace_root or Path.cwd()
        self.actions: List[Action] = []

    def propose(self) -> PlanProposalV1:
        """Generate plan proposal from gaps.

        Returns:
            PlanProposalV1 with actions and governance checks
        """
        start_time = datetime.now(timezone.utc)

        # Generate actions for each gap
        self.actions = []
        for gap in self.gap_report.gaps:
            actions = self._propose_actions_for_gap(gap)
            self.actions.extend(actions)

        # Apply governance checks
        self._apply_governance()

        # Compute summary
        summary = self._compute_summary()

        # Compute governance checks summary
        governance_checks = self._compute_governance_checks()

        # Compute metadata
        elapsed_ms = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)
        metadata = PlanMetadata(
            proposer_version=PROPOSER_VERSION,
            generation_duration_ms=elapsed_ms,
        )

        # Generate gap report ID from digest
        gap_report_id = f"gap-report-{self.gap_report.workspace_state_digest[:12]}"

        proposal = PlanProposalV1(
            project_id=self.anchor.project_id,
            run_id=self.gap_report.run_id,
            generated_at=datetime.now(timezone.utc),
            anchor_id=f"anchor-{self.anchor.raw_input_digest}",
            gap_report_id=gap_report_id,
            actions=self.actions,
            summary=summary,
            governance_checks=governance_checks,
            metadata=metadata,
        )

        logger.info(
            f"[PlanProposer] Generated plan: {len(self.actions)} actions "
            f"({summary.auto_approved_actions} auto-approved, "
            f"{summary.requires_approval_actions} require approval, "
            f"{summary.blocked_actions} blocked)"
        )

        return proposal

    def _propose_actions_for_gap(self, gap: Gap) -> List[Action]:
        """Propose actions for a single gap.

        Args:
            gap: Gap to remediate

        Returns:
            List of proposed actions
        """
        actions = []

        if gap.gap_type == "doc_drift":
            actions.append(
                self._create_action(
                    gap=gap,
                    action_type="doc_update",
                    title=f"Update documentation for {gap.title or gap.gap_id}",
                    description="Run tidy system to update SOT documentation",
                    command="python -m scripts.tidy.tidy_up --execute",
                    risk_score=0.3,
                    risk_factors=["Modifies docs/"],
                    estimated_tokens=500,
                    estimated_time=10,
                )
            )

        elif gap.gap_type == "root_clutter":
            actions.append(
                self._create_action(
                    gap=gap,
                    action_type="file_move",
                    title=f"Organize workspace: {gap.title or gap.gap_id}",
                    description="Move cluttered files to docs/ or archive/",
                    command="python -m scripts.tidy.tidy_workspace --execute",
                    risk_score=0.2,
                    risk_factors=["Moves files"],
                    estimated_tokens=200,
                    estimated_time=5,
                )
            )

        elif gap.gap_type == "sot_duplicate":
            actions.append(
                self._create_action(
                    gap=gap,
                    action_type="file_delete",
                    title=f"Remove duplicate: {gap.title or gap.gap_id}",
                    description="Remove duplicate file and keep canonical version",
                    risk_score=0.4,
                    risk_factors=["Deletes files", "Modifies SOT"],
                    estimated_tokens=100,
                    estimated_time=2,
                )
            )

        elif gap.gap_type == "test_infra_drift":
            actions.append(
                self._create_action(
                    gap=gap,
                    action_type="test_fix",
                    title=f"Fix failing tests: {gap.title or gap.gap_id}",
                    description="Re-run and fix failed tests",
                    command="pytest -v --tb=short",
                    risk_score=0.5,
                    risk_factors=["Modifies tests/", "May require code changes"],
                    estimated_tokens=2000,
                    estimated_time=60,
                )
            )

        elif gap.gap_type == "memory_budget_cap_issue":
            actions.append(
                self._create_action(
                    gap=gap,
                    action_type="doc_update",
                    title=f"Split large files: {gap.title or gap.gap_id}",
                    description="Split or consolidate large files",
                    risk_score=0.4,
                    risk_factors=["Modifies docs/", "Restructures content"],
                    estimated_tokens=1000,
                    estimated_time=30,
                )
            )

        elif gap.gap_type == "windows_encoding_issue":
            actions.append(
                self._create_action(
                    gap=gap,
                    action_type="custom",
                    title=f"Fix encoding: {gap.title or gap.gap_id}",
                    description="Convert files to UTF-8 or add error handling",
                    risk_score=0.6,
                    risk_factors=["Modifies file encoding", "May corrupt content"],
                    estimated_tokens=500,
                    estimated_time=15,
                )
            )

        elif gap.gap_type == "baseline_policy_drift":
            actions.append(
                self._create_action(
                    gap=gap,
                    action_type="config_update",
                    title=f"Update baseline policy: {gap.title or gap.gap_id}",
                    description="Create or update baseline policy configuration",
                    risk_score=0.5,
                    risk_factors=["Modifies config/", "Changes governance"],
                    estimated_tokens=300,
                    estimated_time=10,
                )
            )

        elif gap.gap_type == "protected_path_violation":
            actions.append(
                self._create_action(
                    gap=gap,
                    action_type="doc_update",
                    title=f"Review protected path changes: {gap.title or gap.gap_id}",
                    description="Review and commit protected path modifications",
                    risk_score=0.8,
                    risk_factors=["Modifies protected paths", "Requires review"],
                    estimated_tokens=200,
                    estimated_time=5,
                )
            )

        elif gap.gap_type == "db_lock_contention":
            actions.append(
                self._create_action(
                    gap=gap,
                    action_type="file_delete",
                    title=f"Clear database lock: {gap.title or gap.gap_id}",
                    description="Clear stale database lock file",
                    risk_score=0.7,
                    risk_factors=["Modifies database state", "May disrupt other runs"],
                    estimated_tokens=50,
                    estimated_time=1,
                )
            )

        elif gap.gap_type == "git_state_corruption":
            actions.append(
                self._create_action(
                    gap=gap,
                    action_type="git_operation",
                    title=f"Repair git state: {gap.title or gap.gap_id}",
                    description="Run git fsck and repair",
                    risk_score=0.9,
                    risk_factors=["Modifies git state", "Critical operation"],
                    estimated_tokens=100,
                    estimated_time=10,
                )
            )

        else:
            # Unknown gap type
            actions.append(
                self._create_action(
                    gap=gap,
                    action_type="custom",
                    title=f"Manual review required: {gap.title or gap.gap_id}",
                    description=f"Unknown gap type: {gap.gap_type}",
                    risk_score=1.0,
                    risk_factors=["Unknown gap type", "Manual intervention required"],
                    estimated_tokens=0,
                    estimated_time=0,
                )
            )

        return actions

    def _create_action(
        self,
        gap: Gap,
        action_type: str,
        title: str,
        description: str,
        risk_score: float,
        risk_factors: List[str],
        estimated_tokens: int = 0,
        estimated_time: int = 0,
        command: Optional[str] = None,
    ) -> Action:
        """Create an action for a gap.

        Args:
            gap: Gap to remediate
            action_type: Type of action
            title: Action title
            description: Action description
            risk_score: Risk score (0.0-1.0)
            risk_factors: List of risk factors
            estimated_tokens: Estimated token cost
            estimated_time: Estimated time in seconds
            command: Optional command to execute

        Returns:
            Action instance
        """
        # Generate stable action ID
        action_id = self._generate_action_id(gap.gap_id, action_type)

        # Extract target paths from gap evidence
        target_paths = []
        if gap.evidence:
            target_paths = gap.evidence.file_paths[:10]  # Limit to 10

        # Create estimated cost
        estimated_cost = None
        if estimated_tokens > 0 or estimated_time > 0:
            estimated_cost = EstimatedCost(
                tokens=estimated_tokens if estimated_tokens > 0 else None,
                time_seconds=estimated_time if estimated_time > 0 else None,
                api_calls=0,
            )

        # Initial approval status (will be updated by governance)
        approval_status = "requires_approval"
        approval_reason = "Default-deny policy"

        action = Action(
            action_id=action_id,
            action_type=action_type,
            title=title,
            description=description,
            target_gap_ids=[gap.gap_id],
            risk_score=risk_score,
            risk_factors=risk_factors,
            approval_status=approval_status,
            approval_reason=approval_reason,
            target_paths=target_paths,
            command=command,
            estimated_cost=estimated_cost,
            dependencies=[],
            rollback_strategy=f"git restore {' '.join(target_paths[:5])}" if target_paths else None,
        )

        return action

    def _apply_governance(self) -> None:
        """Apply governance rules to actions.

        Updates approval_status based on:
        - Default-deny policy
        - Auto-approval rules from anchor
        - Protected path checks
        - Budget compliance
        - Risk score thresholds
        """
        for action in self.actions:
            # Start with default-deny
            action.approval_status = "requires_approval"
            action.approval_reason = "Default-deny policy"

            # Check if blocked by high risk or autopilot blocker
            if action.risk_score >= 0.8:
                action.approval_status = "blocked"
                action.approval_reason = f"High risk score: {action.risk_score}"
                continue

            # Check NEVER_AUTO_APPROVE paths
            if self._touches_never_auto_approve_paths(action):
                action.approval_status = "requires_approval"
                action.approval_reason = "Touches NEVER_AUTO_APPROVE paths"
                continue

            # Check protected paths from anchor
            if self._touches_protected_paths(action):
                action.approval_status = "requires_approval"
                action.approval_reason = "Touches protected paths from anchor"
                continue

            # Check auto-approval rules from anchor
            if self._matches_auto_approval_rules(action):
                action.approval_status = "auto_approved"
                action.approval_reason = "Matches narrow auto-approval rule"
                continue

            # Low-risk, small actions with allowed paths can be auto-approved
            if (
                action.risk_score < 0.3
                and action.action_type in ["file_move", "doc_update", "tidy_apply"]
                and not self._touches_protected_paths(action)
            ):
                action.approval_status = "auto_approved"
                action.approval_reason = "Low-risk, allowed paths, narrow scope"
                continue

    def _touches_never_auto_approve_paths(self, action: Action) -> bool:
        """Check if action touches NEVER_AUTO_APPROVE paths.

        Args:
            action: Action to check

        Returns:
            True if touches never-auto-approve paths
        """
        for path in action.target_paths:
            for pattern in NEVER_AUTO_APPROVE_PATTERNS:
                if path.startswith(pattern):
                    return True
        return False

    def _touches_protected_paths(self, action: Action) -> bool:
        """Check if action touches protected paths from anchor.

        Args:
            action: Action to check

        Returns:
            True if touches protected paths
        """
        if not self.anchor.pivot_intentions.scope_boundaries:
            return False

        protected_paths = self.anchor.pivot_intentions.scope_boundaries.protected_paths
        for path in action.target_paths:
            for protected in protected_paths:
                if path.startswith(protected):
                    return True
        return False

    def _matches_auto_approval_rules(self, action: Action) -> bool:
        """Check if action matches narrow auto-approval rules from anchor.

        Args:
            action: Action to check

        Returns:
            True if matches auto-approval rules
        """
        if not self.anchor.pivot_intentions.governance_review:
            return False

        auto_approve_rules = self.anchor.pivot_intentions.governance_review.auto_approve_rules
        for rule in auto_approve_rules:
            # Simple condition matching (would be more sophisticated in production)
            if all(
                cond in action.description
                or cond in action.title
                or cond in str(action.action_type)
                for cond in rule.conditions
            ):
                return True
        return False

    def _compute_summary(self) -> PlanSummary:
        """Compute plan summary statistics.

        Returns:
            PlanSummary instance
        """
        total_tokens = 0
        total_time = 0

        for action in self.actions:
            if action.estimated_cost:
                if action.estimated_cost.tokens:
                    total_tokens += action.estimated_cost.tokens
                if action.estimated_cost.time_seconds:
                    total_time += action.estimated_cost.time_seconds

        return PlanSummary(
            total_actions=len(self.actions),
            auto_approved_actions=sum(
                1 for a in self.actions if a.approval_status == "auto_approved"
            ),
            requires_approval_actions=sum(
                1 for a in self.actions if a.approval_status == "requires_approval"
            ),
            blocked_actions=sum(1 for a in self.actions if a.approval_status == "blocked"),
            total_estimated_tokens=total_tokens if total_tokens > 0 else None,
            total_estimated_time_seconds=total_time if total_time > 0 else None,
        )

    def _compute_governance_checks(self) -> GovernanceChecks:
        """Compute governance checks summary.

        Returns:
            GovernanceChecks instance
        """
        # Collect protected path checks
        protected_path_checks = []
        for action in self.actions:
            for path in action.target_paths:
                is_protected = any(
                    path.startswith(pattern) for pattern in NEVER_AUTO_APPROVE_PATTERNS
                )
                protected_path_checks.append(
                    ProtectedPathCheck(
                        path=path, is_protected=is_protected, action_id=action.action_id
                    )
                )

        # Collect never-auto-approve violations
        violations = []
        for action in self.actions:
            if (
                self._touches_never_auto_approve_paths(action)
                and action.approval_status == "auto_approved"
            ):
                violations.append(action.action_id)

        # Check budget compliance
        budget_compliance = self._check_budget_compliance()

        return GovernanceChecks(
            default_deny_applied=True,
            never_auto_approve_violations=violations,
            protected_path_checks=protected_path_checks[:20],  # Limit to 20
            budget_compliance=budget_compliance,
        )

    def _check_budget_compliance(self) -> BudgetCompliance:
        """Check budget compliance.

        Returns:
            BudgetCompliance instance
        """
        summary = self._compute_summary()

        # Check against anchor budget caps
        within_global_cap = True
        within_per_call_cap = True
        estimated_usage_pct = None

        if self.anchor.pivot_intentions.budget_cost:
            budget = self.anchor.pivot_intentions.budget_cost

            if budget.token_cap_global and summary.total_estimated_tokens:
                estimated_usage_pct = summary.total_estimated_tokens / budget.token_cap_global
                within_global_cap = summary.total_estimated_tokens <= budget.token_cap_global

            if budget.token_cap_per_call:
                for action in self.actions:
                    if action.estimated_cost and action.estimated_cost.tokens:
                        if action.estimated_cost.tokens > budget.token_cap_per_call:
                            within_per_call_cap = False
                            break

        return BudgetCompliance(
            within_global_cap=within_global_cap,
            within_per_call_cap=within_per_call_cap,
            estimated_usage_pct=estimated_usage_pct,
        )

    def _generate_action_id(self, gap_id: str, action_type: str) -> str:
        """Generate stable action ID.

        Args:
            gap_id: Gap ID
            action_type: Action type

        Returns:
            Action ID (16 hex chars)
        """
        combined = f"{gap_id}:{action_type}"
        digest = hashlib.sha256(combined.encode("utf-8")).hexdigest()
        return f"action-{digest[:12]}"


def propose_plan(
    anchor: IntentionAnchorV2,
    gap_report: GapReportV1,
    workspace_root: Optional[Path] = None,
) -> PlanProposalV1:
    """Propose plan from anchor and gap report.

    Args:
        anchor: Intention anchor v2
        gap_report: Gap report v1
        workspace_root: Workspace root (for path checks)

    Returns:
        PlanProposalV1 instance
    """
    proposer = PlanProposer(anchor, gap_report, workspace_root)
    return proposer.propose()
