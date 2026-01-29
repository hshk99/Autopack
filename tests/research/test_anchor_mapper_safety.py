"""Safety-focused tests for ResearchToAnchorMapper.

These tests verify critical safety invariants, particularly that
SafetyRisk.never_allow is NEVER auto-populated by the mapper.
"""

from autopack.research.anchor_mapper import PivotType, ResearchToAnchorMapper
from autopack.research.idea_parser import ParsedIdea, ProjectType, RiskProfile
from autopack.research.models.bootstrap_session import BootstrapSession


class TestNeverAllowIsNeverAutoPopulated:
    """Critical tests ensuring never_allow is NEVER auto-populated."""

    def test_never_allow_empty_with_no_data(self):
        """Test that never_allow is empty when no research data exists."""
        session = BootstrapSession(
            session_id="empty-test",
            idea_hash="abc",
            parsed_idea_title="Empty Test",
            parsed_idea_type="other",
        )

        mapper = ResearchToAnchorMapper()
        anchor, _ = mapper.map_to_anchor(session, None)

        safety = anchor.pivot_intentions.safety_risk
        assert safety is not None
        assert safety.never_allow == []

    def test_never_allow_empty_with_security_concerns_in_research(self):
        """Test that never_allow remains empty even with security concerns in research."""
        session = BootstrapSession(
            session_id="security-test",
            idea_hash="abc",
            parsed_idea_title="Security Test",
            parsed_idea_type="trading",
        )
        session.technical_feasibility.data = {
            "security_concerns": [
                "Never access production database directly",
                "Never store plaintext passwords",
                "Never expose API keys in logs",
            ],
            "api_restrictions": [
                "Never exceed rate limits",
                "Never call deprecated endpoints",
            ],
        }

        mapper = ResearchToAnchorMapper()
        anchor, _ = mapper.map_to_anchor(session, None)

        safety = anchor.pivot_intentions.safety_risk
        assert safety is not None
        # CRITICAL: never_allow MUST be empty
        assert safety.never_allow == []
        # But requires_approval should have the items
        assert len(safety.requires_approval) > 0

    def test_never_allow_empty_with_high_risk_project(self):
        """Test that never_allow is empty even for high-risk projects."""
        session = BootstrapSession(
            session_id="high-risk-test",
            idea_hash="abc",
            parsed_idea_title="High Risk Trading Bot",
            parsed_idea_type="trading",
        )
        session.technical_feasibility.data = {
            "security_concerns": [
                "Financial data must be encrypted",
                "Trades must have confirmation",
            ],
            "legal_requirements": [
                "SEC compliance required",
                "Anti-money laundering checks",
            ],
        }
        idea = ParsedIdea(
            title="High Risk Trading Bot",
            description="Automated trading with real money",
            detected_project_type=ProjectType.TRADING,
            risk_profile=RiskProfile.HIGH,
        )

        mapper = ResearchToAnchorMapper()
        anchor, _ = mapper.map_to_anchor(session, idea)

        safety = anchor.pivot_intentions.safety_risk
        assert safety is not None
        # CRITICAL: never_allow MUST be empty regardless of risk level
        assert safety.never_allow == []
        # But risk_tolerance should reflect the high risk
        assert safety.risk_tolerance == "minimal"

    def test_never_allow_empty_with_explicit_never_keywords_in_data(self):
        """Test that never_allow is empty even when research contains 'never' keywords."""
        session = BootstrapSession(
            session_id="never-keyword-test",
            idea_hash="abc",
            parsed_idea_title="Never Keyword Test",
            parsed_idea_type="ecommerce",
        )
        session.technical_feasibility.data = {
            "security_concerns": [
                "NEVER store credit card CVV",
                "NEVER log sensitive data",
                "NEVER bypass authentication",
            ],
            "api_restrictions": [
                "NEVER call without rate limiting",
            ],
            # Attempt to inject never_allow data
            "never_allow": [
                "This should not be used",
                "Neither should this",
            ],
        }

        mapper = ResearchToAnchorMapper()
        anchor, _ = mapper.map_to_anchor(session, None)

        safety = anchor.pivot_intentions.safety_risk
        assert safety is not None
        # CRITICAL: never_allow MUST be empty even with explicit data
        assert safety.never_allow == []

    def test_mapper_flag_cannot_enable_auto_populate(self):
        """Test that auto_populate_safety_risk_never_allow flag cannot be enabled."""
        # Even if someone tries to enable it, it should remain False
        mapper = ResearchToAnchorMapper(auto_populate_safety_risk_never_allow=True)
        assert mapper._auto_populate_never_allow is False

        session = BootstrapSession(
            session_id="flag-test",
            idea_hash="abc",
            parsed_idea_title="Flag Test",
            parsed_idea_type="other",
        )
        session.technical_feasibility.data = {
            "security_concerns": ["Never allow X", "Never allow Y"],
        }

        anchor, _ = mapper.map_to_anchor(session, None)

        safety = anchor.pivot_intentions.safety_risk
        assert safety is not None
        # CRITICAL: Must still be empty
        assert safety.never_allow == []


class TestSafetyRiskConfidenceCapping:
    """Tests for SafetyRisk confidence capping behavior."""

    def test_safety_risk_confidence_capped_at_06(self):
        """Test that SafetyRisk confidence is capped at 0.6."""
        session = BootstrapSession(
            session_id="confidence-cap-test",
            idea_hash="abc",
            parsed_idea_title="Confidence Cap Test",
            parsed_idea_type="ecommerce",
        )
        # Provide comprehensive data that would normally give high confidence
        session.technical_feasibility.data = {
            "api_restrictions": ["Rate limit 1", "Rate limit 2", "Rate limit 3"],
            "security_concerns": ["Concern 1", "Concern 2", "Concern 3"],
            "legal_requirements": ["Requirement 1", "Requirement 2"],
        }
        idea = ParsedIdea(
            title="Comprehensive Project",
            description="Full data project",
            detected_project_type=ProjectType.ECOMMERCE,
            risk_profile=RiskProfile.LOW,
        )

        mapper = ResearchToAnchorMapper()
        mappings = mapper._map_all_pivots(session, idea)

        # Find SafetyRisk mapping
        safety_mapping = next(m for m in mappings if m.pivot_type == PivotType.SAFETY_RISK)

        # Confidence should be capped at 0.6
        assert safety_mapping.confidence.score <= 0.6


class TestSafetyRiskAlwaysGeneratesQuestion:
    """Tests ensuring SafetyRisk always generates clarifying questions."""

    def test_always_generates_never_allow_question(self):
        """Test that a question about never_allow is always generated."""
        session = BootstrapSession(
            session_id="question-test",
            idea_hash="abc",
            parsed_idea_title="Question Test",
            parsed_idea_type="other",
        )

        mapper = ResearchToAnchorMapper()
        anchor, questions = mapper.map_to_anchor(session, None)

        # Should always have a question about never_allow
        never_allow_questions = [q for q in questions if "NEVER" in q and "allow" in q.lower()]
        assert len(never_allow_questions) > 0

    def test_never_allow_question_mentions_safety(self):
        """Test that the never_allow question mentions safety reasons."""
        session = BootstrapSession(
            session_id="safety-mention-test",
            idea_hash="abc",
            parsed_idea_title="Safety Mention Test",
            parsed_idea_type="other",
        )

        mapper = ResearchToAnchorMapper()
        anchor, questions = mapper.map_to_anchor(session, None)

        # Find the never_allow question
        never_allow_question = next(
            (q for q in questions if "NEVER" in q and "allow" in q.lower()), None
        )
        assert never_allow_question is not None
        # Should mention safety or that it cannot be auto-populated
        assert "safety" in never_allow_question.lower() or "auto" in never_allow_question.lower()

    def test_question_generated_even_with_high_confidence_data(self):
        """Test that never_allow question is generated even with comprehensive data."""
        session = BootstrapSession(
            session_id="high-confidence-test",
            idea_hash="abc",
            parsed_idea_title="High Confidence Test",
            parsed_idea_type="ecommerce",
        )
        session.market_research.status = "completed"
        session.market_research.data = {
            "user_needs": ["Need 1", "Need 2"],
            "core_value_proposition": ["Value 1"],
            "success_metrics": ["Metric 1"],
        }
        session.competitive_analysis.status = "completed"
        session.competitive_analysis.data = {"competitors": ["A", "B"]}
        session.technical_feasibility.status = "completed"
        session.technical_feasibility.data = {
            "api_restrictions": ["Restriction 1"],
            "security_concerns": ["Concern 1"],
            "legal_requirements": ["Requirement 1"],
        }
        idea = ParsedIdea(
            title="Complete Project",
            description="A project with all the data",
            detected_project_type=ProjectType.ECOMMERCE,
            risk_profile=RiskProfile.LOW,
            raw_requirements=["Req 1", "Req 2", "Req 3"],
        )

        # Use low threshold so most pivots pass
        mapper = ResearchToAnchorMapper(confidence_threshold=0.3)
        anchor, questions = mapper.map_to_anchor(session, idea)

        # Should STILL have never_allow question
        never_allow_questions = [q for q in questions if "NEVER" in q and "allow" in q.lower()]
        assert len(never_allow_questions) > 0


class TestRequiresApprovalVsNeverAllow:
    """Tests for proper separation of requires_approval and never_allow."""

    def test_security_concerns_go_to_requires_approval(self):
        """Test that security concerns are mapped to requires_approval, not never_allow."""
        session = BootstrapSession(
            session_id="separation-test",
            idea_hash="abc",
            parsed_idea_title="Separation Test",
            parsed_idea_type="trading",
        )
        session.technical_feasibility.data = {
            "security_concerns": [
                "Direct database access",
                "Admin operations",
                "Data deletion",
            ],
        }

        mapper = ResearchToAnchorMapper()
        anchor, _ = mapper.map_to_anchor(session, None)

        safety = anchor.pivot_intentions.safety_risk
        assert safety is not None
        # Security concerns should be in requires_approval
        assert len(safety.requires_approval) == 3
        # never_allow must remain empty
        assert safety.never_allow == []

    def test_api_restrictions_go_to_requires_approval(self):
        """Test that API restrictions are mapped to requires_approval."""
        session = BootstrapSession(
            session_id="api-test",
            idea_hash="abc",
            parsed_idea_title="API Test",
            parsed_idea_type="automation",
        )
        session.technical_feasibility.data = {
            "api_restrictions": [
                "Rate limiting required",
                "Authentication required",
            ],
        }

        mapper = ResearchToAnchorMapper()
        anchor, _ = mapper.map_to_anchor(session, None)

        safety = anchor.pivot_intentions.safety_risk
        assert safety is not None
        assert len(safety.requires_approval) == 2
        assert safety.never_allow == []

    def test_legal_requirements_go_to_requires_approval(self):
        """Test that legal requirements are mapped to requires_approval."""
        session = BootstrapSession(
            session_id="legal-test",
            idea_hash="abc",
            parsed_idea_title="Legal Test",
            parsed_idea_type="ecommerce",
        )
        session.technical_feasibility.data = {
            "legal_requirements": [
                "GDPR compliance",
                "CCPA compliance",
                "PCI DSS compliance",
            ],
        }

        mapper = ResearchToAnchorMapper()
        anchor, _ = mapper.map_to_anchor(session, None)

        safety = anchor.pivot_intentions.safety_risk
        assert safety is not None
        assert len(safety.requires_approval) == 3
        assert safety.never_allow == []


class TestRiskToleranceMapping:
    """Tests for risk tolerance mapping based on project risk profile."""

    def test_high_risk_maps_to_minimal_tolerance(self):
        """Test that HIGH risk maps to 'minimal' risk tolerance."""
        session = BootstrapSession(
            session_id="high-risk",
            idea_hash="abc",
            parsed_idea_title="High Risk",
            parsed_idea_type="trading",
        )
        idea = ParsedIdea(
            title="Trading Bot",
            description="High risk trading",
            detected_project_type=ProjectType.TRADING,
            risk_profile=RiskProfile.HIGH,
        )

        mapper = ResearchToAnchorMapper()
        anchor, _ = mapper.map_to_anchor(session, idea)

        safety = anchor.pivot_intentions.safety_risk
        assert safety is not None
        assert safety.risk_tolerance == "minimal"

    def test_medium_risk_maps_to_low_tolerance(self):
        """Test that MEDIUM risk maps to 'low' risk tolerance."""
        session = BootstrapSession(
            session_id="medium-risk",
            idea_hash="abc",
            parsed_idea_title="Medium Risk",
            parsed_idea_type="ecommerce",
        )
        idea = ParsedIdea(
            title="E-commerce",
            description="Medium risk ecommerce",
            detected_project_type=ProjectType.ECOMMERCE,
            risk_profile=RiskProfile.MEDIUM,
        )

        mapper = ResearchToAnchorMapper()
        anchor, _ = mapper.map_to_anchor(session, idea)

        safety = anchor.pivot_intentions.safety_risk
        assert safety is not None
        assert safety.risk_tolerance == "low"

    def test_low_risk_maps_to_moderate_tolerance(self):
        """Test that LOW risk maps to 'moderate' risk tolerance."""
        session = BootstrapSession(
            session_id="low-risk",
            idea_hash="abc",
            parsed_idea_title="Low Risk",
            parsed_idea_type="content",
        )
        idea = ParsedIdea(
            title="Blog",
            description="Low risk blog",
            detected_project_type=ProjectType.CONTENT,
            risk_profile=RiskProfile.LOW,
        )

        mapper = ResearchToAnchorMapper()
        anchor, _ = mapper.map_to_anchor(session, idea)

        safety = anchor.pivot_intentions.safety_risk
        assert safety is not None
        assert safety.risk_tolerance == "moderate"


class TestSafetyMappingConfidenceReasoning:
    """Tests for SafetyRisk mapping confidence reasoning."""

    def test_confidence_reasoning_mentions_never_allow(self):
        """Test that confidence reasoning mentions never_allow requirement."""
        session = BootstrapSession(
            session_id="reasoning-test",
            idea_hash="abc",
            parsed_idea_title="Reasoning Test",
            parsed_idea_type="other",
        )

        mapper = ResearchToAnchorMapper()
        mappings = mapper._map_all_pivots(session, None)

        safety_mapping = next(m for m in mappings if m.pivot_type == PivotType.SAFETY_RISK)

        # Reasoning should mention never_allow requires user confirmation
        assert "never_allow" in safety_mapping.confidence.reasoning.lower()
        assert (
            "confirm" in safety_mapping.confidence.reasoning.lower()
            or "explicit" in safety_mapping.confidence.reasoning.lower()
        )
