"""Project Intention Memory: IntentionAnchorV2 re-exports.

This module provides backward-compatible imports for the intention system.
The v1 schema (ProjectIntention, ProjectIntentionManager) has been removed
as part of IMP-CLEAN-002. Use IntentionAnchorV2 for all new code.

See docs/INTENTION_MIGRATION_GUIDE.md for migration instructions.
"""

# Re-export v2 components for convenience
from .intention_anchor.v2 import (BudgetCostIntention,
                                  EvidenceVerificationIntention,
                                  GovernanceReviewIntention, IntentionAnchorV2,
                                  IntentionMetadata, MemoryContinuityIntention,
                                  NorthStarIntention,
                                  ParallelismIsolationIntention,
                                  PivotIntentions, SafetyRiskIntention,
                                  ScopeBoundariesIntention, create_from_inputs,
                                  validate_pivot_completeness)

__all__ = [
    # v2 core
    "IntentionAnchorV2",
    "create_from_inputs",
    "validate_pivot_completeness",
    # v2 intention types
    "NorthStarIntention",
    "SafetyRiskIntention",
    "EvidenceVerificationIntention",
    "ScopeBoundariesIntention",
    "BudgetCostIntention",
    "MemoryContinuityIntention",
    "GovernanceReviewIntention",
    "ParallelismIsolationIntention",
    # v2 models
    "PivotIntentions",
    "IntentionMetadata",
]
