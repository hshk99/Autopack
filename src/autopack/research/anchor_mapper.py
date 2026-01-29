"""ResearchToAnchorMapper - Core Pipeline Bridge.

Maps research findings from BootstrapSession to IntentionAnchorV2 structure.
This is the key missing bridge in the research-to-anchor pipeline.

Pivot Mapping Rules:
- NorthStar <- market_analysis, user_needs, core_value_proposition
- SafetyRisk <- api_restrictions, legal_requirements, security_concerns
  (CRITICAL: never_allow is NEVER auto-populated)
- EvidenceVerification <- technical_feasibility, proof_of_concept_results
- ScopeBoundaries <- platform_policies, feature_limits, excluded_functionality
- BudgetCost <- cost_estimates, resource_requirements, pricing_tiers
- MemoryContinuity <- session_requirements, state_persistence_needs
- GovernanceReview <- compliance_requirements, review_checkpoints
- ParallelismIsolation <- concurrency_requirements, isolation_boundaries
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field

from ..intention_anchor.v2 import (
    BudgetCostIntention,
    EvidenceVerificationIntention,
    GovernanceReviewIntention,
    IntentionAnchorV2,
    IntentionMetadata,
    MemoryContinuityIntention,
    NorthStarIntention,
    ParallelismIsolationIntention,
    PivotIntentions,
    SafetyRiskIntention,
    ScopeBoundariesIntention,
)
from .idea_parser import ParsedIdea, ProjectType, RiskProfile
from .models.bootstrap_session import BootstrapSession

logger = logging.getLogger(__name__)


class PivotType(str, Enum):
    """Enumeration of pivot types for mapping."""

    NORTH_STAR = "north_star"
    SAFETY_RISK = "safety_risk"
    EVIDENCE_VERIFICATION = "evidence_verification"
    SCOPE_BOUNDARIES = "scope_boundaries"
    BUDGET_COST = "budget_cost"
    MEMORY_CONTINUITY = "memory_continuity"
    GOVERNANCE_REVIEW = "governance_review"
    PARALLELISM_ISOLATION = "parallelism_isolation"


class MappingConfidence(BaseModel):
    """Confidence score with reasoning for a pivot mapping."""

    score: float = Field(..., ge=0.0, le=1.0, description="Confidence score between 0.0 and 1.0")
    reasoning: str = Field(..., description="Explanation for the confidence score")
    sources: list[str] = Field(
        default_factory=list, description="Research sources used for this mapping"
    )


@dataclass
class PivotMapping:
    """Individual pivot mapping result."""

    pivot_type: PivotType
    confidence: MappingConfidence
    mapped_data: dict[str, Any] = field(default_factory=dict)
    clarifying_questions: list[str] = field(default_factory=list)


# Confidence threshold below which clarifying questions are generated
CONFIDENCE_THRESHOLD = 0.7

# Risk tolerance mapping from ParsedIdea RiskProfile
_RISK_TOLERANCE_MAP: dict[RiskProfile, str] = {
    RiskProfile.HIGH: "minimal",
    RiskProfile.MEDIUM: "low",
    RiskProfile.LOW: "moderate",
}

# Default questions for each pivot type when confidence is low
_PIVOT_QUESTIONS: dict[PivotType, list[str]] = {
    PivotType.NORTH_STAR: [
        "What are the primary desired outcomes for this project?",
        "How will you measure success for this project?",
        "What explicitly should NOT be in scope (non-goals)?",
    ],
    PivotType.SAFETY_RISK: [
        "What operations must NEVER be allowed under any circumstances?",
        "What operations should require explicit approval before execution?",
        "What is the acceptable risk tolerance level (minimal/low/moderate/high)?",
    ],
    PivotType.EVIDENCE_VERIFICATION: [
        "What hard blockers must pass before proceeding?",
        "What proof artifacts are required to verify progress?",
        "What verification gates must be passed?",
    ],
    PivotType.SCOPE_BOUNDARIES: [
        "Which directories/paths should be allowed for writes?",
        "Which paths should be protected from modification?",
        "What network endpoints should be allowed?",
    ],
    PivotType.BUDGET_COST: [
        "What is the maximum token budget for this project?",
        "What is the maximum time allowed for operations?",
        "What should happen when cost limits are exceeded?",
    ],
    PivotType.MEMORY_CONTINUITY: [
        "What data should persist to source-of-truth ledgers?",
        "What derived indexes should be maintained?",
        "What are the data retention requirements?",
    ],
    PivotType.GOVERNANCE_REVIEW: [
        "Should the default policy be deny or allow?",
        "What operations can be auto-approved?",
        "How should approvals be requested?",
    ],
    PivotType.PARALLELISM_ISOLATION: [
        "Should parallel execution be allowed?",
        "What isolation model should be used?",
        "How many concurrent runs should be allowed?",
    ],
}


class ResearchToAnchorMapper:
    """Maps research findings to IntentionAnchorV2 structure.

    This is the core pipeline bridge that converts research session results
    into a structured anchor that can be used for project execution.

    CRITICAL: SafetyRisk.never_allow is NEVER auto-populated. This field
    requires explicit user confirmation due to its safety-critical nature.
    """

    def __init__(
        self,
        confidence_threshold: float = CONFIDENCE_THRESHOLD,
        auto_populate_safety_risk_never_allow: bool = False,
    ):
        """Initialize the mapper.

        Args:
            confidence_threshold: Minimum confidence to skip clarifying questions
            auto_populate_safety_risk_never_allow: MUST remain False. Safety guard.
        """
        self.confidence_threshold = confidence_threshold
        # CRITICAL: This flag is hardcoded to False and should never be changed
        # The parameter exists only to document the intentional design decision
        self._auto_populate_never_allow = False
        if auto_populate_safety_risk_never_allow:
            logger.warning(
                "[SECURITY] Attempted to enable auto_populate_safety_risk_never_allow. "
                "This is not allowed. The flag will remain False."
            )

    def map_to_anchor(
        self,
        bootstrap_session: BootstrapSession,
        parsed_idea: Optional[ParsedIdea] = None,
    ) -> tuple[IntentionAnchorV2, list[str]]:
        """Map research results to IntentionAnchorV2.

        Args:
            bootstrap_session: Completed bootstrap session with research results
            parsed_idea: Optional parsed idea for additional context

        Returns:
            Tuple of (IntentionAnchorV2, clarifying_questions)
            - anchor: The mapped anchor (may have incomplete pivots)
            - clarifying_questions: Questions for low-confidence pivots
        """
        logger.info(f"[AnchorMapper] Mapping session {bootstrap_session.session_id} to anchor")

        # Map each pivot type
        pivot_mappings = self._map_all_pivots(bootstrap_session, parsed_idea)

        # Collect all clarifying questions
        all_questions: list[str] = []
        for mapping in pivot_mappings:
            # SafetyRisk questions are ALWAYS collected regardless of threshold
            # because never_allow can NEVER be auto-populated
            if mapping.pivot_type == PivotType.SAFETY_RISK:
                all_questions.extend(mapping.clarifying_questions)
            elif mapping.confidence.score < self.confidence_threshold:
                all_questions.extend(mapping.clarifying_questions)

        # Build the anchor
        anchor = self._build_anchor(bootstrap_session, parsed_idea, pivot_mappings)

        logger.info(
            f"[AnchorMapper] Mapped {len(pivot_mappings)} pivots, "
            f"{len(all_questions)} clarifying questions generated"
        )

        return anchor, all_questions

    def _map_all_pivots(
        self,
        session: BootstrapSession,
        idea: Optional[ParsedIdea],
    ) -> list[PivotMapping]:
        """Map all pivot types from research data.

        Args:
            session: Bootstrap session with research data
            idea: Parsed idea for context

        Returns:
            List of PivotMapping objects
        """
        return [
            self._map_north_star(session, idea),
            self._map_safety_risk(session, idea),
            self._map_evidence_verification(session, idea),
            self._map_scope_boundaries(session, idea),
            self._map_budget_cost(session, idea),
            self._map_memory_continuity(session, idea),
            self._map_governance_review(session, idea),
            self._map_parallelism_isolation(session, idea),
        ]

    def _map_north_star(
        self,
        session: BootstrapSession,
        idea: Optional[ParsedIdea],
    ) -> PivotMapping:
        """Map NorthStar pivot from market analysis and user needs."""
        sources: list[str] = []
        desired_outcomes: list[str] = []
        success_signals: list[str] = []
        non_goals: list[str] = []
        confidence_factors: list[float] = []

        # Extract from market research
        market_data = session.market_research.data
        if market_data.get("user_needs"):
            desired_outcomes.extend(market_data["user_needs"])
            sources.append("market_research.user_needs")
            confidence_factors.append(0.8)

        if market_data.get("core_value_proposition"):
            if isinstance(market_data["core_value_proposition"], list):
                desired_outcomes.extend(market_data["core_value_proposition"])
            else:
                desired_outcomes.append(str(market_data["core_value_proposition"]))
            sources.append("market_research.core_value_proposition")
            confidence_factors.append(0.9)

        if market_data.get("success_metrics"):
            success_signals.extend(market_data["success_metrics"])
            sources.append("market_research.success_metrics")
            confidence_factors.append(0.85)

        if market_data.get("non_goals"):
            non_goals.extend(market_data["non_goals"])
            sources.append("market_research.non_goals")
            confidence_factors.append(0.9)

        # Extract from parsed idea
        if idea:
            if idea.raw_requirements:
                # Treat requirements as desired outcomes
                desired_outcomes.extend(idea.raw_requirements[:5])
                sources.append("parsed_idea.raw_requirements")
                confidence_factors.append(0.7)

            if idea.description:
                desired_outcomes.append(f"Implement: {idea.description[:100]}")
                sources.append("parsed_idea.description")
                confidence_factors.append(0.6)

        # Calculate confidence
        confidence_score = (
            sum(confidence_factors) / len(confidence_factors) if confidence_factors else 0.3
        )

        # Generate questions if low confidence
        questions = []
        if confidence_score < self.confidence_threshold:
            questions = _PIVOT_QUESTIONS[PivotType.NORTH_STAR].copy()

        return PivotMapping(
            pivot_type=PivotType.NORTH_STAR,
            confidence=MappingConfidence(
                score=confidence_score,
                reasoning=f"Mapped from {len(sources)} sources",
                sources=sources,
            ),
            mapped_data={
                "desired_outcomes": list(set(desired_outcomes)),
                "success_signals": list(set(success_signals)),
                "non_goals": list(set(non_goals)),
            },
            clarifying_questions=questions,
        )

    def _map_safety_risk(
        self,
        session: BootstrapSession,
        idea: Optional[ParsedIdea],
    ) -> PivotMapping:
        """Map SafetyRisk pivot.

        CRITICAL: never_allow is NEVER auto-populated. This field requires
        explicit user confirmation.
        """
        sources: list[str] = []
        requires_approval: list[str] = []
        risk_tolerance = "low"  # Safe default
        confidence_factors: list[float] = []

        # Extract from technical feasibility (api_restrictions, security_concerns)
        tech_data = session.technical_feasibility.data
        if tech_data.get("api_restrictions"):
            requires_approval.extend(tech_data["api_restrictions"])
            sources.append("technical_feasibility.api_restrictions")
            confidence_factors.append(0.8)

        if tech_data.get("security_concerns"):
            requires_approval.extend(tech_data["security_concerns"])
            sources.append("technical_feasibility.security_concerns")
            confidence_factors.append(0.85)

        if tech_data.get("legal_requirements"):
            requires_approval.extend(tech_data["legal_requirements"])
            sources.append("technical_feasibility.legal_requirements")
            confidence_factors.append(0.9)

        # Extract risk tolerance from parsed idea
        if idea:
            risk_tolerance = _RISK_TOLERANCE_MAP.get(idea.risk_profile, "low")
            sources.append("parsed_idea.risk_profile")
            confidence_factors.append(0.8)

        # Calculate confidence (capped because never_allow cannot be auto-populated)
        base_confidence = (
            sum(confidence_factors) / len(confidence_factors) if confidence_factors else 0.3
        )
        # Cap confidence at 0.6 because never_allow must be user-provided
        confidence_score = min(base_confidence, 0.6)

        # ALWAYS generate questions for never_allow
        questions = [
            "CRITICAL: What operations must NEVER be allowed under any circumstances? "
            "(This field cannot be auto-populated for safety reasons)"
        ]
        if confidence_score < self.confidence_threshold:
            questions.extend(_PIVOT_QUESTIONS[PivotType.SAFETY_RISK][1:])

        return PivotMapping(
            pivot_type=PivotType.SAFETY_RISK,
            confidence=MappingConfidence(
                score=confidence_score,
                reasoning="never_allow requires explicit user confirmation; "
                f"mapped requires_approval from {len(sources)} sources",
                sources=sources,
            ),
            mapped_data={
                # CRITICAL: never_allow is intentionally empty
                "never_allow": [],
                "requires_approval": list(set(requires_approval)),
                "risk_tolerance": risk_tolerance,
            },
            clarifying_questions=questions,
        )

    def _map_evidence_verification(
        self,
        session: BootstrapSession,
        idea: Optional[ParsedIdea],
    ) -> PivotMapping:
        """Map EvidenceVerification pivot from technical feasibility."""
        sources: list[str] = []
        hard_blocks: list[str] = []
        required_proofs: list[str] = []
        verification_gates: list[str] = []
        confidence_factors: list[float] = []

        # Extract from technical feasibility
        tech_data = session.technical_feasibility.data
        if tech_data.get("hard_blocks") or tech_data.get("blockers"):
            blocks = tech_data.get("hard_blocks", []) + tech_data.get("blockers", [])
            hard_blocks.extend(blocks)
            sources.append("technical_feasibility.hard_blocks")
            confidence_factors.append(0.9)

        if tech_data.get("proof_of_concept_results"):
            results = tech_data["proof_of_concept_results"]
            if isinstance(results, list):
                required_proofs.extend(results)
            else:
                required_proofs.append(str(results))
            sources.append("technical_feasibility.proof_of_concept_results")
            confidence_factors.append(0.85)

        if tech_data.get("verification_requirements"):
            verification_gates.extend(tech_data["verification_requirements"])
            sources.append("technical_feasibility.verification_requirements")
            confidence_factors.append(0.85)

        if tech_data.get("required_proofs"):
            required_proofs.extend(tech_data["required_proofs"])
            sources.append("technical_feasibility.required_proofs")
            confidence_factors.append(0.9)

        # Add default verification gates based on project type
        if idea:
            if idea.detected_project_type == ProjectType.TRADING:
                verification_gates.append("Risk management tests must pass")
                verification_gates.append("Financial calculation accuracy verified")
            elif idea.detected_project_type == ProjectType.ECOMMERCE:
                verification_gates.append("Payment processing tests must pass")
                verification_gates.append("Inventory management verified")
            sources.append("parsed_idea.project_type_defaults")
            confidence_factors.append(0.5)

        confidence_score = (
            sum(confidence_factors) / len(confidence_factors) if confidence_factors else 0.3
        )

        questions = []
        if confidence_score < self.confidence_threshold:
            questions = _PIVOT_QUESTIONS[PivotType.EVIDENCE_VERIFICATION].copy()

        return PivotMapping(
            pivot_type=PivotType.EVIDENCE_VERIFICATION,
            confidence=MappingConfidence(
                score=confidence_score,
                reasoning=f"Mapped from {len(sources)} technical feasibility sources",
                sources=sources,
            ),
            mapped_data={
                "hard_blocks": list(set(hard_blocks)),
                "required_proofs": list(set(required_proofs)),
                "verification_gates": list(set(verification_gates)),
            },
            clarifying_questions=questions,
        )

    def _map_scope_boundaries(
        self,
        session: BootstrapSession,
        idea: Optional[ParsedIdea],
    ) -> PivotMapping:
        """Map ScopeBoundaries pivot from platform policies."""
        sources: list[str] = []
        allowed_write_roots: list[str] = []
        protected_paths: list[str] = []
        network_allowlist: list[str] = []
        confidence_factors: list[float] = []

        # Extract from technical feasibility
        tech_data = session.technical_feasibility.data
        if tech_data.get("platform_policies"):
            policies = tech_data["platform_policies"]
            if isinstance(policies, dict):
                if policies.get("allowed_paths"):
                    allowed_write_roots.extend(policies["allowed_paths"])
                if policies.get("protected_paths"):
                    protected_paths.extend(policies["protected_paths"])
            sources.append("technical_feasibility.platform_policies")
            confidence_factors.append(0.8)

        if tech_data.get("feature_limits"):
            # Feature limits can inform scope boundaries
            sources.append("technical_feasibility.feature_limits")
            confidence_factors.append(0.6)

        if tech_data.get("network_requirements"):
            network_allowlist.extend(tech_data["network_requirements"])
            sources.append("technical_feasibility.network_requirements")
            confidence_factors.append(0.75)

        # Add defaults based on project type
        if idea:
            # Default protected paths
            protected_paths.extend([".git", ".env", "credentials", "secrets"])
            sources.append("default_protected_paths")
            confidence_factors.append(0.5)

        confidence_score = (
            sum(confidence_factors) / len(confidence_factors) if confidence_factors else 0.3
        )

        questions = []
        if confidence_score < self.confidence_threshold:
            questions = _PIVOT_QUESTIONS[PivotType.SCOPE_BOUNDARIES].copy()

        return PivotMapping(
            pivot_type=PivotType.SCOPE_BOUNDARIES,
            confidence=MappingConfidence(
                score=confidence_score,
                reasoning=f"Mapped from {len(sources)} sources",
                sources=sources,
            ),
            mapped_data={
                "allowed_write_roots": list(set(allowed_write_roots)),
                "protected_paths": list(set(protected_paths)),
                "network_allowlist": list(set(network_allowlist)),
            },
            clarifying_questions=questions,
        )

    def _map_budget_cost(
        self,
        session: BootstrapSession,
        idea: Optional[ParsedIdea],
    ) -> PivotMapping:
        """Map BudgetCost pivot from cost estimates."""
        sources: list[str] = []
        token_cap_global: Optional[int] = None
        token_cap_per_call: Optional[int] = None
        time_cap_seconds: Optional[int] = None
        cost_escalation_policy = "request_approval"
        confidence_factors: list[float] = []

        # Extract from market research (pricing_tiers)
        market_data = session.market_research.data
        if market_data.get("pricing_tiers") or market_data.get("cost_estimates"):
            sources.append("market_research.cost_estimates")
            confidence_factors.append(0.6)

        # Extract from technical feasibility (resource_requirements)
        tech_data = session.technical_feasibility.data
        if tech_data.get("resource_requirements"):
            reqs = tech_data["resource_requirements"]
            if isinstance(reqs, dict):
                if reqs.get("token_budget"):
                    token_cap_global = int(reqs["token_budget"])
                if reqs.get("time_limit_seconds"):
                    time_cap_seconds = int(reqs["time_limit_seconds"])
            sources.append("technical_feasibility.resource_requirements")
            confidence_factors.append(0.8)

        if tech_data.get("cost_estimates"):
            sources.append("technical_feasibility.cost_estimates")
            confidence_factors.append(0.7)

        # Set defaults based on risk profile
        if idea and idea.risk_profile == RiskProfile.HIGH:
            cost_escalation_policy = "block"
            sources.append("risk_profile_default")
            confidence_factors.append(0.6)

        confidence_score = (
            sum(confidence_factors) / len(confidence_factors) if confidence_factors else 0.3
        )

        questions = []
        if confidence_score < self.confidence_threshold:
            questions = _PIVOT_QUESTIONS[PivotType.BUDGET_COST].copy()

        return PivotMapping(
            pivot_type=PivotType.BUDGET_COST,
            confidence=MappingConfidence(
                score=confidence_score,
                reasoning=f"Mapped from {len(sources)} sources",
                sources=sources,
            ),
            mapped_data={
                "token_cap_global": token_cap_global,
                "token_cap_per_call": token_cap_per_call,
                "time_cap_seconds": time_cap_seconds,
                "cost_escalation_policy": cost_escalation_policy,
            },
            clarifying_questions=questions,
        )

    def _map_memory_continuity(
        self,
        session: BootstrapSession,
        idea: Optional[ParsedIdea],
    ) -> PivotMapping:
        """Map MemoryContinuity pivot from session requirements."""
        sources: list[str] = []
        persist_to_sot: list[str] = []
        derived_indexes: list[str] = []
        retention_rules: dict[str, str] = {}
        confidence_factors: list[float] = []

        # Extract from technical feasibility
        tech_data = session.technical_feasibility.data
        if tech_data.get("session_requirements"):
            reqs = tech_data["session_requirements"]
            if isinstance(reqs, list):
                persist_to_sot.extend(reqs)
            elif isinstance(reqs, dict):
                if reqs.get("persist"):
                    persist_to_sot.extend(reqs["persist"])
                if reqs.get("indexes"):
                    derived_indexes.extend(reqs["indexes"])
            sources.append("technical_feasibility.session_requirements")
            confidence_factors.append(0.8)

        if tech_data.get("state_persistence_needs"):
            needs = tech_data["state_persistence_needs"]
            if isinstance(needs, list):
                persist_to_sot.extend(needs)
            sources.append("technical_feasibility.state_persistence_needs")
            confidence_factors.append(0.75)

        # Add defaults
        persist_to_sot.extend(["intention_anchor", "execution_logs"])
        retention_rules["execution_logs"] = "30_days"
        retention_rules["intention_anchor"] = "permanent"
        sources.append("default_persistence")
        confidence_factors.append(0.5)

        confidence_score = (
            sum(confidence_factors) / len(confidence_factors) if confidence_factors else 0.4
        )

        questions = []
        if confidence_score < self.confidence_threshold:
            questions = _PIVOT_QUESTIONS[PivotType.MEMORY_CONTINUITY].copy()

        return PivotMapping(
            pivot_type=PivotType.MEMORY_CONTINUITY,
            confidence=MappingConfidence(
                score=confidence_score,
                reasoning=f"Mapped from {len(sources)} sources",
                sources=sources,
            ),
            mapped_data={
                "persist_to_sot": list(set(persist_to_sot)),
                "derived_indexes": list(set(derived_indexes)),
                "retention_rules": retention_rules,
            },
            clarifying_questions=questions,
        )

    def _map_governance_review(
        self,
        session: BootstrapSession,
        idea: Optional[ParsedIdea],
    ) -> PivotMapping:
        """Map GovernanceReview pivot from compliance requirements."""
        sources: list[str] = []
        default_policy = "deny"  # Safe default
        auto_approve_rules: list[dict[str, Any]] = []
        approval_channels: list[str] = []
        confidence_factors: list[float] = []

        # Extract from technical feasibility
        tech_data = session.technical_feasibility.data
        if tech_data.get("compliance_requirements"):
            sources.append("technical_feasibility.compliance_requirements")
            confidence_factors.append(0.8)

        if tech_data.get("review_checkpoints"):
            checkpoints = tech_data["review_checkpoints"]
            if isinstance(checkpoints, list):
                # Convert checkpoints to approval channels
                approval_channels.extend(checkpoints)
            sources.append("technical_feasibility.review_checkpoints")
            confidence_factors.append(0.75)

        # Set default policy based on risk
        if idea:
            if idea.risk_profile == RiskProfile.LOW:
                default_policy = "allow"
                # Add auto-approve rules for low-risk projects
                auto_approve_rules.append(
                    {
                        "rule_id": "read_only_ops",
                        "description": "Auto-approve read-only operations",
                        "conditions": ["operation_type == 'read'"],
                    }
                )
            sources.append("risk_profile_governance")
            confidence_factors.append(0.7)

        confidence_score = (
            sum(confidence_factors) / len(confidence_factors) if confidence_factors else 0.4
        )

        questions = []
        if confidence_score < self.confidence_threshold:
            questions = _PIVOT_QUESTIONS[PivotType.GOVERNANCE_REVIEW].copy()

        return PivotMapping(
            pivot_type=PivotType.GOVERNANCE_REVIEW,
            confidence=MappingConfidence(
                score=confidence_score,
                reasoning=f"Mapped from {len(sources)} sources, default_policy={default_policy}",
                sources=sources,
            ),
            mapped_data={
                "default_policy": default_policy,
                "auto_approve_rules": auto_approve_rules,
                "approval_channels": approval_channels,
            },
            clarifying_questions=questions,
        )

    def _map_parallelism_isolation(
        self,
        session: BootstrapSession,
        idea: Optional[ParsedIdea],
    ) -> PivotMapping:
        """Map ParallelismIsolation pivot from concurrency requirements."""
        sources: list[str] = []
        allowed = False  # Safe default
        isolation_model = "none"
        max_concurrent_runs = 1
        confidence_factors: list[float] = []

        # Extract from technical feasibility
        tech_data = session.technical_feasibility.data
        if tech_data.get("concurrency_requirements"):
            reqs = tech_data["concurrency_requirements"]
            if isinstance(reqs, dict):
                allowed = reqs.get("parallel_allowed", False)
                if reqs.get("max_concurrent"):
                    max_concurrent_runs = int(reqs["max_concurrent"])
                if reqs.get("isolation_model"):
                    isolation_model = reqs["isolation_model"]
            sources.append("technical_feasibility.concurrency_requirements")
            confidence_factors.append(0.85)

        if tech_data.get("isolation_boundaries"):
            # If isolation boundaries are defined, enable isolation
            allowed = True
            isolation_model = "four_layer"
            sources.append("technical_feasibility.isolation_boundaries")
            confidence_factors.append(0.8)

        confidence_score = (
            sum(confidence_factors) / len(confidence_factors) if confidence_factors else 0.4
        )

        questions = []
        if confidence_score < self.confidence_threshold:
            questions = _PIVOT_QUESTIONS[PivotType.PARALLELISM_ISOLATION].copy()

        return PivotMapping(
            pivot_type=PivotType.PARALLELISM_ISOLATION,
            confidence=MappingConfidence(
                score=confidence_score,
                reasoning=f"Mapped from {len(sources)} sources, parallelism={'enabled' if allowed else 'disabled'}",
                sources=sources,
            ),
            mapped_data={
                "allowed": allowed,
                "isolation_model": isolation_model,
                "max_concurrent_runs": max_concurrent_runs,
            },
            clarifying_questions=questions,
        )

    def _build_anchor(
        self,
        session: BootstrapSession,
        idea: Optional[ParsedIdea],
        mappings: list[PivotMapping],
    ) -> IntentionAnchorV2:
        """Build IntentionAnchorV2 from pivot mappings.

        Args:
            session: Bootstrap session
            idea: Parsed idea
            mappings: List of pivot mappings

        Returns:
            Constructed IntentionAnchorV2
        """
        # Create a mapping dict for easy lookup
        mapping_dict = {m.pivot_type: m for m in mappings}

        # Determine project_id
        project_id = session.session_id
        if idea:
            project_id = idea.title.lower().replace(" ", "_")[:50]

        # Compute raw input digest
        raw_input = session.parsed_idea_title or (idea.raw_text if idea else "")

        # Build pivot intentions
        pivot_intentions = PivotIntentions()

        # NorthStar
        ns_mapping = mapping_dict.get(PivotType.NORTH_STAR)
        if ns_mapping and ns_mapping.mapped_data:
            pivot_intentions.north_star = NorthStarIntention(
                desired_outcomes=ns_mapping.mapped_data.get("desired_outcomes", []),
                success_signals=ns_mapping.mapped_data.get("success_signals", []),
                non_goals=ns_mapping.mapped_data.get("non_goals", []),
            )

        # SafetyRisk (never_allow intentionally empty)
        sr_mapping = mapping_dict.get(PivotType.SAFETY_RISK)
        if sr_mapping and sr_mapping.mapped_data:
            pivot_intentions.safety_risk = SafetyRiskIntention(
                never_allow=[],  # CRITICAL: Never auto-populated
                requires_approval=sr_mapping.mapped_data.get("requires_approval", []),
                risk_tolerance=sr_mapping.mapped_data.get("risk_tolerance", "low"),
            )

        # EvidenceVerification
        ev_mapping = mapping_dict.get(PivotType.EVIDENCE_VERIFICATION)
        if ev_mapping and ev_mapping.mapped_data:
            pivot_intentions.evidence_verification = EvidenceVerificationIntention(
                hard_blocks=ev_mapping.mapped_data.get("hard_blocks", []),
                required_proofs=ev_mapping.mapped_data.get("required_proofs", []),
                verification_gates=ev_mapping.mapped_data.get("verification_gates", []),
            )

        # ScopeBoundaries
        sb_mapping = mapping_dict.get(PivotType.SCOPE_BOUNDARIES)
        if sb_mapping and sb_mapping.mapped_data:
            pivot_intentions.scope_boundaries = ScopeBoundariesIntention(
                allowed_write_roots=sb_mapping.mapped_data.get("allowed_write_roots", []),
                protected_paths=sb_mapping.mapped_data.get("protected_paths", []),
                network_allowlist=sb_mapping.mapped_data.get("network_allowlist", []),
            )

        # BudgetCost
        bc_mapping = mapping_dict.get(PivotType.BUDGET_COST)
        if bc_mapping and bc_mapping.mapped_data:
            pivot_intentions.budget_cost = BudgetCostIntention(
                token_cap_global=bc_mapping.mapped_data.get("token_cap_global"),
                token_cap_per_call=bc_mapping.mapped_data.get("token_cap_per_call"),
                time_cap_seconds=bc_mapping.mapped_data.get("time_cap_seconds"),
                cost_escalation_policy=bc_mapping.mapped_data.get(
                    "cost_escalation_policy", "request_approval"
                ),
            )

        # MemoryContinuity
        mc_mapping = mapping_dict.get(PivotType.MEMORY_CONTINUITY)
        if mc_mapping and mc_mapping.mapped_data:
            pivot_intentions.memory_continuity = MemoryContinuityIntention(
                persist_to_sot=mc_mapping.mapped_data.get("persist_to_sot", []),
                derived_indexes=mc_mapping.mapped_data.get("derived_indexes", []),
                retention_rules=mc_mapping.mapped_data.get("retention_rules", {}),
            )

        # GovernanceReview
        gr_mapping = mapping_dict.get(PivotType.GOVERNANCE_REVIEW)
        if gr_mapping and gr_mapping.mapped_data:
            from ..intention_anchor.v2 import AutoApprovalRule

            auto_rules = []
            for rule_data in gr_mapping.mapped_data.get("auto_approve_rules", []):
                auto_rules.append(
                    AutoApprovalRule(
                        rule_id=rule_data.get("rule_id", ""),
                        description=rule_data.get("description", ""),
                        conditions=rule_data.get("conditions", []),
                    )
                )

            pivot_intentions.governance_review = GovernanceReviewIntention(
                default_policy=gr_mapping.mapped_data.get("default_policy", "deny"),
                auto_approve_rules=auto_rules,
                approval_channels=gr_mapping.mapped_data.get("approval_channels", []),
            )

        # ParallelismIsolation
        pi_mapping = mapping_dict.get(PivotType.PARALLELISM_ISOLATION)
        if pi_mapping and pi_mapping.mapped_data:
            pivot_intentions.parallelism_isolation = ParallelismIsolationIntention(
                allowed=pi_mapping.mapped_data.get("allowed", False),
                isolation_model=pi_mapping.mapped_data.get("isolation_model", "none"),
                max_concurrent_runs=pi_mapping.mapped_data.get("max_concurrent_runs", 1),
            )

        # Build metadata
        metadata = IntentionMetadata(
            author="ResearchToAnchorMapper",
            source=f"bootstrap_session:{session.session_id}",
            tags=[session.parsed_idea_type] if session.parsed_idea_type else [],
        )

        # Compute raw input digest
        import hashlib

        raw_input_digest = hashlib.sha256(raw_input.encode("utf-8", errors="ignore")).hexdigest()[
            :16
        ]

        return IntentionAnchorV2(
            project_id=project_id,
            created_at=datetime.now(timezone.utc),
            raw_input_digest=raw_input_digest,
            pivot_intentions=pivot_intentions,
            metadata=metadata,
        )

    def get_confidence_report(self, mappings: list[PivotMapping]) -> dict[str, MappingConfidence]:
        """Get a confidence report for all pivot mappings.

        Args:
            mappings: List of pivot mappings

        Returns:
            Dictionary mapping pivot type name to confidence
        """
        return {m.pivot_type.value: m.confidence for m in mappings}
