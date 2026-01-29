"""Unit tests for ResearchToAnchorMapper module."""

import pytest

from autopack.intention_anchor.v2 import IntentionAnchorV2
from autopack.research.anchor_mapper import (CONFIDENCE_THRESHOLD,
                                             MappingConfidence, PivotMapping,
                                             PivotType, ResearchToAnchorMapper)
from autopack.research.idea_parser import ParsedIdea, ProjectType, RiskProfile
from autopack.research.models.bootstrap_session import (BootstrapPhase,
                                                        BootstrapSession,
                                                        ResearchPhaseResult)


class TestMappingConfidence:
    """Test suite for MappingConfidence model."""

    def test_mapping_confidence_creation(self):
        """Test creating MappingConfidence with valid values."""
        confidence = MappingConfidence(
            score=0.85,
            reasoning="High confidence mapping from market research",
            sources=["market_research.user_needs"],
        )
        assert confidence.score == 0.85
        assert "High confidence" in confidence.reasoning
        assert len(confidence.sources) == 1

    def test_mapping_confidence_score_bounds(self):
        """Test that confidence score is bounded between 0 and 1."""
        with pytest.raises(ValueError):
            MappingConfidence(score=1.5, reasoning="Invalid score")

        with pytest.raises(ValueError):
            MappingConfidence(score=-0.1, reasoning="Invalid score")

    def test_mapping_confidence_valid_bounds(self):
        """Test that confidence score allows boundary values."""
        low = MappingConfidence(score=0.0, reasoning="Minimum score")
        assert low.score == 0.0

        high = MappingConfidence(score=1.0, reasoning="Maximum score")
        assert high.score == 1.0


class TestPivotMapping:
    """Test suite for PivotMapping dataclass."""

    def test_pivot_mapping_creation(self):
        """Test creating PivotMapping with all fields."""
        mapping = PivotMapping(
            pivot_type=PivotType.NORTH_STAR,
            confidence=MappingConfidence(score=0.8, reasoning="Good mapping", sources=["source1"]),
            mapped_data={"desired_outcomes": ["outcome1", "outcome2"]},
            clarifying_questions=["What is the main goal?"],
        )
        assert mapping.pivot_type == PivotType.NORTH_STAR
        assert mapping.confidence.score == 0.8
        assert len(mapping.mapped_data["desired_outcomes"]) == 2
        assert len(mapping.clarifying_questions) == 1

    def test_pivot_mapping_defaults(self):
        """Test PivotMapping default values."""
        mapping = PivotMapping(
            pivot_type=PivotType.BUDGET_COST,
            confidence=MappingConfidence(score=0.5, reasoning="Low confidence"),
        )
        assert mapping.mapped_data == {}
        assert mapping.clarifying_questions == []


class TestPivotType:
    """Test suite for PivotType enum."""

    def test_all_pivot_types_exist(self):
        """Test that all expected pivot types are defined."""
        assert PivotType.NORTH_STAR == "north_star"
        assert PivotType.SAFETY_RISK == "safety_risk"
        assert PivotType.EVIDENCE_VERIFICATION == "evidence_verification"
        assert PivotType.SCOPE_BOUNDARIES == "scope_boundaries"
        assert PivotType.BUDGET_COST == "budget_cost"
        assert PivotType.MEMORY_CONTINUITY == "memory_continuity"
        assert PivotType.GOVERNANCE_REVIEW == "governance_review"
        assert PivotType.PARALLELISM_ISOLATION == "parallelism_isolation"

    def test_pivot_type_count(self):
        """Test that there are exactly 8 pivot types."""
        assert len(PivotType) == 8


@pytest.fixture
def sample_bootstrap_session():
    """Create a sample BootstrapSession for testing."""
    session = BootstrapSession(
        session_id="test-session-123",
        idea_hash="abc123",
        parsed_idea_title="Test E-commerce Platform",
        parsed_idea_type="ecommerce",
        current_phase=BootstrapPhase.COMPLETED,
    )

    # Populate market research data
    session.market_research = ResearchPhaseResult(
        phase=BootstrapPhase.MARKET_RESEARCH,
        status="completed",
        data={
            "user_needs": ["Fast checkout", "Secure payments", "Mobile app"],
            "core_value_proposition": ["Easy to use online shopping"],
            "success_metrics": ["Conversion rate > 3%", "Cart abandonment < 50%"],
            "non_goals": ["Social media integration", "Gamification"],
        },
    )

    # Populate competitive analysis data
    session.competitive_analysis = ResearchPhaseResult(
        phase=BootstrapPhase.COMPETITIVE_ANALYSIS,
        status="completed",
        data={
            "competitors": ["Shopify", "WooCommerce"],
            "market_gaps": ["Better mobile experience"],
        },
    )

    # Populate technical feasibility data
    session.technical_feasibility = ResearchPhaseResult(
        phase=BootstrapPhase.TECHNICAL_FEASIBILITY,
        status="completed",
        data={
            "api_restrictions": ["Rate limits on payment API"],
            "security_concerns": ["PCI DSS compliance required"],
            "legal_requirements": ["GDPR compliance for EU customers"],
            "hard_blocks": ["Must use approved payment processors"],
            "proof_of_concept_results": ["Payment integration works"],
            "verification_requirements": ["Security audit required"],
            "resource_requirements": {
                "token_budget": 100000,
                "time_limit_seconds": 3600,
            },
            "concurrency_requirements": {
                "parallel_allowed": True,
                "max_concurrent": 4,
                "isolation_model": "four_layer",
            },
        },
    )

    return session


@pytest.fixture
def sample_parsed_idea():
    """Create a sample ParsedIdea for testing."""
    return ParsedIdea(
        title="Test E-commerce Platform",
        description="An e-commerce platform for selling products online",
        raw_requirements=[
            "User authentication",
            "Product catalog",
            "Shopping cart",
            "Payment processing",
            "Order tracking",
        ],
        detected_project_type=ProjectType.ECOMMERCE,
        risk_profile=RiskProfile.MEDIUM,
        dependencies=["Stripe", "Auth0"],
        confidence_score=0.85,
        raw_text="Original idea text here",
    )


class TestResearchToAnchorMapperInit:
    """Test suite for ResearchToAnchorMapper initialization."""

    def test_mapper_default_initialization(self):
        """Test mapper initialization with defaults."""
        mapper = ResearchToAnchorMapper()
        assert mapper.confidence_threshold == CONFIDENCE_THRESHOLD
        assert mapper._auto_populate_never_allow is False

    def test_mapper_custom_threshold(self):
        """Test mapper initialization with custom threshold."""
        mapper = ResearchToAnchorMapper(confidence_threshold=0.5)
        assert mapper.confidence_threshold == 0.5

    def test_mapper_never_allow_cannot_be_enabled(self):
        """Test that auto_populate_safety_risk_never_allow cannot be enabled."""
        # This should log a warning but still set the flag to False
        mapper = ResearchToAnchorMapper(auto_populate_safety_risk_never_allow=True)
        assert mapper._auto_populate_never_allow is False


class TestMapToAnchor:
    """Test suite for map_to_anchor method."""

    def test_map_to_anchor_returns_tuple(self, sample_bootstrap_session, sample_parsed_idea):
        """Test that map_to_anchor returns correct tuple type."""
        mapper = ResearchToAnchorMapper()
        result = mapper.map_to_anchor(sample_bootstrap_session, sample_parsed_idea)

        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], IntentionAnchorV2)
        assert isinstance(result[1], list)

    def test_map_to_anchor_creates_valid_anchor(self, sample_bootstrap_session, sample_parsed_idea):
        """Test that the created anchor has expected structure."""
        mapper = ResearchToAnchorMapper()
        anchor, questions = mapper.map_to_anchor(sample_bootstrap_session, sample_parsed_idea)

        assert anchor.format_version == "v2"
        assert anchor.project_id is not None
        assert anchor.created_at is not None
        assert anchor.raw_input_digest is not None
        assert anchor.pivot_intentions is not None

    def test_map_to_anchor_without_parsed_idea(self, sample_bootstrap_session):
        """Test mapping without a parsed idea."""
        mapper = ResearchToAnchorMapper()
        anchor, questions = mapper.map_to_anchor(sample_bootstrap_session, None)

        assert anchor is not None
        assert anchor.project_id == sample_bootstrap_session.session_id

    def test_map_to_anchor_generates_questions_for_low_confidence(
        self, sample_bootstrap_session, sample_parsed_idea
    ):
        """Test that questions are generated for low-confidence pivots."""
        mapper = ResearchToAnchorMapper(confidence_threshold=0.99)
        anchor, questions = mapper.map_to_anchor(sample_bootstrap_session, sample_parsed_idea)

        # With very high threshold, all pivots should generate questions
        assert len(questions) > 0


class TestNorthStarMapping:
    """Test suite for NorthStar pivot mapping."""

    def test_north_star_extracts_desired_outcomes(
        self, sample_bootstrap_session, sample_parsed_idea
    ):
        """Test that desired outcomes are extracted from research."""
        mapper = ResearchToAnchorMapper()
        anchor, _ = mapper.map_to_anchor(sample_bootstrap_session, sample_parsed_idea)

        north_star = anchor.pivot_intentions.north_star
        assert north_star is not None
        assert len(north_star.desired_outcomes) > 0
        # Should include user needs from market research
        assert any("checkout" in o.lower() for o in north_star.desired_outcomes)

    def test_north_star_extracts_success_signals(
        self, sample_bootstrap_session, sample_parsed_idea
    ):
        """Test that success signals are extracted."""
        mapper = ResearchToAnchorMapper()
        anchor, _ = mapper.map_to_anchor(sample_bootstrap_session, sample_parsed_idea)

        north_star = anchor.pivot_intentions.north_star
        assert north_star is not None
        assert len(north_star.success_signals) > 0
        assert any("conversion" in s.lower() for s in north_star.success_signals)

    def test_north_star_extracts_non_goals(self, sample_bootstrap_session, sample_parsed_idea):
        """Test that non-goals are extracted."""
        mapper = ResearchToAnchorMapper()
        anchor, _ = mapper.map_to_anchor(sample_bootstrap_session, sample_parsed_idea)

        north_star = anchor.pivot_intentions.north_star
        assert north_star is not None
        assert len(north_star.non_goals) > 0


class TestEvidenceVerificationMapping:
    """Test suite for EvidenceVerification pivot mapping."""

    def test_evidence_extracts_hard_blocks(self, sample_bootstrap_session, sample_parsed_idea):
        """Test that hard blocks are extracted from technical feasibility."""
        mapper = ResearchToAnchorMapper()
        anchor, _ = mapper.map_to_anchor(sample_bootstrap_session, sample_parsed_idea)

        evidence = anchor.pivot_intentions.evidence_verification
        assert evidence is not None
        assert len(evidence.hard_blocks) > 0
        assert any("payment" in b.lower() for b in evidence.hard_blocks)

    def test_evidence_extracts_required_proofs(self, sample_bootstrap_session, sample_parsed_idea):
        """Test that required proofs are extracted."""
        mapper = ResearchToAnchorMapper()
        anchor, _ = mapper.map_to_anchor(sample_bootstrap_session, sample_parsed_idea)

        evidence = anchor.pivot_intentions.evidence_verification
        assert evidence is not None
        assert len(evidence.required_proofs) > 0


class TestScopeBoundariesMapping:
    """Test suite for ScopeBoundaries pivot mapping."""

    def test_scope_has_default_protected_paths(self, sample_bootstrap_session, sample_parsed_idea):
        """Test that default protected paths are set."""
        mapper = ResearchToAnchorMapper()
        anchor, _ = mapper.map_to_anchor(sample_bootstrap_session, sample_parsed_idea)

        scope = anchor.pivot_intentions.scope_boundaries
        assert scope is not None
        assert len(scope.protected_paths) > 0
        assert ".git" in scope.protected_paths
        assert ".env" in scope.protected_paths


class TestBudgetCostMapping:
    """Test suite for BudgetCost pivot mapping."""

    def test_budget_extracts_token_cap(self, sample_bootstrap_session, sample_parsed_idea):
        """Test that token cap is extracted from resource requirements."""
        mapper = ResearchToAnchorMapper()
        anchor, _ = mapper.map_to_anchor(sample_bootstrap_session, sample_parsed_idea)

        budget = anchor.pivot_intentions.budget_cost
        assert budget is not None
        assert budget.token_cap_global == 100000

    def test_budget_extracts_time_cap(self, sample_bootstrap_session, sample_parsed_idea):
        """Test that time cap is extracted."""
        mapper = ResearchToAnchorMapper()
        anchor, _ = mapper.map_to_anchor(sample_bootstrap_session, sample_parsed_idea)

        budget = anchor.pivot_intentions.budget_cost
        assert budget is not None
        assert budget.time_cap_seconds == 3600


class TestMemoryContinuityMapping:
    """Test suite for MemoryContinuity pivot mapping."""

    def test_memory_has_default_persistence(self, sample_bootstrap_session, sample_parsed_idea):
        """Test that default persistence settings are applied."""
        mapper = ResearchToAnchorMapper()
        anchor, _ = mapper.map_to_anchor(sample_bootstrap_session, sample_parsed_idea)

        memory = anchor.pivot_intentions.memory_continuity
        assert memory is not None
        assert "intention_anchor" in memory.persist_to_sot
        assert "execution_logs" in memory.persist_to_sot
        assert "execution_logs" in memory.retention_rules


class TestGovernanceReviewMapping:
    """Test suite for GovernanceReview pivot mapping."""

    def test_governance_default_policy_deny(self, sample_bootstrap_session, sample_parsed_idea):
        """Test that default policy is deny for medium risk."""
        mapper = ResearchToAnchorMapper()
        anchor, _ = mapper.map_to_anchor(sample_bootstrap_session, sample_parsed_idea)

        governance = anchor.pivot_intentions.governance_review
        assert governance is not None
        assert governance.default_policy == "deny"


class TestParallelismIsolationMapping:
    """Test suite for ParallelismIsolation pivot mapping."""

    def test_parallelism_extracts_settings(self, sample_bootstrap_session, sample_parsed_idea):
        """Test that parallelism settings are extracted."""
        mapper = ResearchToAnchorMapper()
        anchor, _ = mapper.map_to_anchor(sample_bootstrap_session, sample_parsed_idea)

        parallelism = anchor.pivot_intentions.parallelism_isolation
        assert parallelism is not None
        assert parallelism.allowed is True
        assert parallelism.max_concurrent_runs == 4
        assert parallelism.isolation_model == "four_layer"


class TestConfidenceReport:
    """Test suite for confidence report generation."""

    def test_get_confidence_report(self, sample_bootstrap_session, sample_parsed_idea):
        """Test generating a confidence report."""
        mapper = ResearchToAnchorMapper()

        # First do a mapping to get the internal mappings
        mappings = mapper._map_all_pivots(sample_bootstrap_session, sample_parsed_idea)
        report = mapper.get_confidence_report(mappings)

        assert len(report) == 8
        assert "north_star" in report
        assert "safety_risk" in report
        assert all(isinstance(v, MappingConfidence) for v in report.values())


class TestProjectTypeSpecificMapping:
    """Test suite for project type-specific behavior."""

    def test_trading_project_gets_verification_gates(self):
        """Test that trading projects get specific verification gates."""
        session = BootstrapSession(
            session_id="trading-test",
            idea_hash="abc",
            parsed_idea_title="Trading Bot",
            parsed_idea_type="trading",
        )
        idea = ParsedIdea(
            title="Trading Bot",
            description="Automated trading system",
            detected_project_type=ProjectType.TRADING,
            risk_profile=RiskProfile.HIGH,
        )

        mapper = ResearchToAnchorMapper()
        anchor, _ = mapper.map_to_anchor(session, idea)

        evidence = anchor.pivot_intentions.evidence_verification
        assert evidence is not None
        assert any("risk" in g.lower() for g in evidence.verification_gates)

    def test_high_risk_project_gets_block_policy(self):
        """Test that high-risk projects get block cost escalation policy."""
        session = BootstrapSession(
            session_id="high-risk-test",
            idea_hash="abc",
            parsed_idea_title="High Risk Project",
            parsed_idea_type="trading",
        )
        idea = ParsedIdea(
            title="High Risk Project",
            description="A high-risk project",
            detected_project_type=ProjectType.TRADING,
            risk_profile=RiskProfile.HIGH,
        )

        mapper = ResearchToAnchorMapper()
        anchor, _ = mapper.map_to_anchor(session, idea)

        budget = anchor.pivot_intentions.budget_cost
        assert budget is not None
        assert budget.cost_escalation_policy == "block"


class TestQuestionGeneration:
    """Test suite for clarifying question generation."""

    def test_low_confidence_generates_questions(self):
        """Test that low confidence pivots generate questions."""
        # Create session with minimal data to get low confidence
        session = BootstrapSession(
            session_id="minimal-test",
            idea_hash="abc",
            parsed_idea_title="Minimal Project",
            parsed_idea_type="other",
        )

        mapper = ResearchToAnchorMapper()
        anchor, questions = mapper.map_to_anchor(session, None)

        # Should have questions due to low confidence
        assert len(questions) > 0

    def test_safety_risk_always_generates_never_allow_question(
        self, sample_bootstrap_session, sample_parsed_idea
    ):
        """Test that SafetyRisk always generates never_allow question."""
        mapper = ResearchToAnchorMapper()
        anchor, questions = mapper.map_to_anchor(sample_bootstrap_session, sample_parsed_idea)

        # Should always have a question about never_allow
        assert any("NEVER" in q and "allow" in q.lower() for q in questions)


class TestMetadataMapping:
    """Test suite for metadata mapping."""

    def test_anchor_has_metadata(self, sample_bootstrap_session, sample_parsed_idea):
        """Test that anchor has proper metadata."""
        mapper = ResearchToAnchorMapper()
        anchor, _ = mapper.map_to_anchor(sample_bootstrap_session, sample_parsed_idea)

        assert anchor.metadata is not None
        assert anchor.metadata.author == "ResearchToAnchorMapper"
        assert "bootstrap_session" in anchor.metadata.source
        assert sample_bootstrap_session.session_id in anchor.metadata.source


class TestEdgeCases:
    """Test suite for edge cases."""

    def test_empty_research_data(self):
        """Test mapping with empty research data."""
        session = BootstrapSession(
            session_id="empty-test",
            idea_hash="abc",
            parsed_idea_title="Empty Test",
            parsed_idea_type="other",
        )

        mapper = ResearchToAnchorMapper()
        anchor, questions = mapper.map_to_anchor(session, None)

        # Should still produce valid anchor
        assert anchor is not None
        assert anchor.format_version == "v2"
        # Should have many questions due to missing data
        assert len(questions) > 0

    def test_partial_research_data(self, sample_bootstrap_session):
        """Test mapping with partial research data."""
        # Clear some data
        sample_bootstrap_session.competitive_analysis.data = {}

        mapper = ResearchToAnchorMapper()
        anchor, _ = mapper.map_to_anchor(sample_bootstrap_session, None)

        # Should still work
        assert anchor is not None

    def test_list_type_fields_in_research_data(self):
        """Test handling of list-type fields in research data."""
        session = BootstrapSession(
            session_id="list-test",
            idea_hash="abc",
            parsed_idea_title="List Test",
            parsed_idea_type="other",
        )
        session.technical_feasibility.data = {
            "session_requirements": ["persist user data", "maintain state"],
            "state_persistence_needs": ["session tokens", "user preferences"],
        }

        mapper = ResearchToAnchorMapper()
        anchor, _ = mapper.map_to_anchor(session, None)

        memory = anchor.pivot_intentions.memory_continuity
        assert memory is not None
        assert len(memory.persist_to_sot) > 2  # Includes defaults plus extracted

    def test_dict_type_fields_in_research_data(self):
        """Test handling of dict-type fields in research data."""
        session = BootstrapSession(
            session_id="dict-test",
            idea_hash="abc",
            parsed_idea_title="Dict Test",
            parsed_idea_type="other",
        )
        session.technical_feasibility.data = {
            "session_requirements": {
                "persist": ["user_data", "settings"],
                "indexes": ["user_id_index"],
            }
        }

        mapper = ResearchToAnchorMapper()
        anchor, _ = mapper.map_to_anchor(session, None)

        memory = anchor.pivot_intentions.memory_continuity
        assert memory is not None
        assert "user_data" in memory.persist_to_sot
        assert "user_id_index" in memory.derived_indexes
