"""Planning module - gap-to-action mapping with governance.

Public API exports:
    - PlanProposalV1: plan proposal schema
    - PlanProposer: gap-to-action mapper with governance
    - propose_plan: create plan from anchor and gap report
    - propose_plan_from_files: library façade for CLI/programmatic use (BUILD-179)
    - PlanProposalResult: result type for propose_plan_from_files
"""

from .models import (
    PlanProposalV1,
    Action,
    EstimatedCost,
    GovernanceChecks,
    PlanSummary,
    ProtectedPathCheck,
    BudgetCompliance,
)
from .plan_proposer import PlanProposer, propose_plan
from .api import propose_plan_from_files, PlanProposalResult

__all__ = [
    # Models
    "PlanProposalV1",
    "Action",
    "EstimatedCost",
    "GovernanceChecks",
    "PlanSummary",
    "ProtectedPathCheck",
    "BudgetCompliance",
    # Proposer
    "PlanProposer",
    "propose_plan",
    # Library API (BUILD-179)
    "propose_plan_from_files",
    "PlanProposalResult",
]
