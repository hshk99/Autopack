"""
Data structures for Universal Research Analysis System

These structures support project-agnostic research analysis that works
for any project (Autopack, file-organizer, or future projects).
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional
from datetime import datetime
from enum import Enum


class ResearchType(Enum):
    """Types of research files (universal across projects)"""

    # Strategic Research
    PRODUCT_VISION = "product_vision"  # Product intent, positioning, target users
    MARKET_RESEARCH = "market_research"  # Competitive landscape, market analysis
    STRATEGIC_REVIEW = "strategic_review"  # Strategic assessments, pivots

    # Domain Research
    DOMAIN_REQUIREMENTS = "domain_requirements"  # Tax, legal, immigration, etc.
    REGULATORY_COMPLIANCE = "regulatory_compliance"  # Legal/compliance requirements
    USER_RESEARCH = "user_research"  # User interviews, surveys, personas

    # Technical Research
    COMPETITIVE_ANALYSIS = "competitive_analysis"  # Competitor feature analysis
    API_INTEGRATION = "api_integration"  # Third-party API capabilities
    CODE_STUDY = "code_study"  # External codebase studies
    TECH_EVALUATION = "tech_evaluation"  # Technology stack evaluations

    # Feature Research
    FEATURE_DEMAND = "feature_demand"  # User-requested features
    FEATURE_SPEC = "feature_spec"  # Detailed feature specifications

    # Meta Research
    META_ANALYSIS = "meta_analysis"  # Consolidation of other research
    LESSONS_LEARNED = "lessons_learned"  # Retrospectives, learnings

    # Other
    REFERENCE = "reference"  # Reference materials
    UNKNOWN = "unknown"  # Uncategorized research


class GapType(Enum):
    """Types of gaps between current state and research findings"""

    FEATURE_GAP = "feature_gap"  # Missing features vs market/user research
    CAPABILITY_GAP = "capability_gap"  # Missing capabilities vs technical research
    COMPLIANCE_GAP = "compliance_gap"  # Missing compliance vs regulatory research
    MARKET_GAP = "market_gap"  # Missing competitive parity
    VISION_GAP = "vision_gap"  # Misalignment with product vision
    TECHNICAL_DEBT = "technical_debt"  # Architecture vs best practices


class Priority(Enum):
    """Priority levels for gaps/decisions"""

    CRITICAL = "critical"  # Blocking, must do now
    HIGH = "high"  # Important, should do soon
    MEDIUM = "medium"  # Valuable, can schedule
    LOW = "low"  # Nice to have, backlog


class Effort(Enum):
    """Effort estimates"""

    LOW = "low"  # Days
    MEDIUM = "medium"  # Weeks
    HIGH = "high"  # Months


class DecisionType(Enum):
    """Decision outcomes"""

    IMPLEMENT_NOW = "implement_now"  # Add to active development
    IMPLEMENT_LATER = "implement_later"  # Add to FUTURE_PLAN
    REVIEW = "review"  # Needs more research/discussion
    REJECT = "reject"  # Not aligned with vision/constraints


@dataclass
class ProjectContext:
    """
    Universal project context assembled from SOT files and research.

    Works for any project by extracting relevant information from:
    - SOT files (current state)
    - Research files (strategy, vision, domain)
    """

    project_id: str
    assembled_at: datetime = field(default_factory=datetime.now)

    # Current State (from SOT files)
    implemented_features: List[Dict] = field(default_factory=list)  # From BUILD_HISTORY
    architecture_constraints: List[Dict] = field(
        default_factory=list
    )  # From ARCHITECTURE_DECISIONS
    known_issues: List[Dict] = field(default_factory=list)  # From DEBUG_LOG
    planned_features: List[Dict] = field(default_factory=list)  # From FUTURE_PLAN
    learned_rules: List[Dict] = field(default_factory=list)  # From LEARNED_RULES.json

    # Strategy & Vision (from research)
    vision_statement: Optional[str] = None  # From product vision research
    target_users: List[str] = field(default_factory=list)  # Who is this for?
    core_principles: List[str] = field(default_factory=list)  # Design principles
    positioning: Optional[str] = None  # Market positioning

    # Domain Context (from research)
    domain_focus: List[str] = field(default_factory=list)  # Tax, legal, finance, etc.
    regulatory_requirements: List[str] = field(default_factory=list)  # Compliance needs
    user_pain_points: List[str] = field(default_factory=list)  # User problems to solve

    # Market Context (from research)
    key_competitors: List[str] = field(default_factory=list)
    competitive_gaps: List[str] = field(default_factory=list)  # What competitors have that we don't
    competitive_advantages: List[str] = field(default_factory=list)  # What we have that they don't
    market_opportunities: List[str] = field(default_factory=list)

    # Technical Context
    tech_stack: List[str] = field(default_factory=list)  # Technologies in use
    integration_points: List[str] = field(default_factory=list)  # External APIs/services
    technical_constraints: List[str] = field(default_factory=list)

    # Resource Context
    budget_constraints: Dict = field(default_factory=dict)
    timeline_constraints: Dict = field(default_factory=dict)
    team_capabilities: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        """Convert to dictionary for serialization"""
        return {
            "project_id": self.project_id,
            "assembled_at": self.assembled_at.isoformat(),
            "implemented_features": self.implemented_features,
            "architecture_constraints": self.architecture_constraints,
            "known_issues": self.known_issues,
            "planned_features": self.planned_features,
            "learned_rules": self.learned_rules,
            "vision_statement": self.vision_statement,
            "target_users": self.target_users,
            "core_principles": self.core_principles,
            "positioning": self.positioning,
            "domain_focus": self.domain_focus,
            "regulatory_requirements": self.regulatory_requirements,
            "user_pain_points": self.user_pain_points,
            "key_competitors": self.key_competitors,
            "competitive_gaps": self.competitive_gaps,
            "competitive_advantages": self.competitive_advantages,
            "market_opportunities": self.market_opportunities,
            "tech_stack": self.tech_stack,
            "integration_points": self.integration_points,
            "technical_constraints": self.technical_constraints,
            "budget_constraints": self.budget_constraints,
            "timeline_constraints": self.timeline_constraints,
            "team_capabilities": self.team_capabilities,
        }


@dataclass
class ResearchFile:
    """Metadata about a research file"""

    file_path: str
    research_type: ResearchType
    title: str
    summary: str
    key_findings: List[str] = field(default_factory=list)
    created_at: Optional[datetime] = None
    last_updated: Optional[datetime] = None
    word_count: int = 0
    metadata: Dict = field(default_factory=dict)


@dataclass
class ResearchCatalog:
    """Catalog of all research files for a project"""

    project_id: str
    research_files: List[ResearchFile] = field(default_factory=list)
    total_files: int = 0
    total_words: int = 0
    cataloged_at: datetime = field(default_factory=datetime.now)

    def get_by_type(self, research_type: ResearchType) -> List[ResearchFile]:
        """Get all research files of a specific type"""
        return [f for f in self.research_files if f.research_type == research_type]

    def get_strategic_research(self) -> List[ResearchFile]:
        """Get all strategic research (vision, market, strategy)"""
        strategic_types = {
            ResearchType.PRODUCT_VISION,
            ResearchType.MARKET_RESEARCH,
            ResearchType.STRATEGIC_REVIEW,
        }
        return [f for f in self.research_files if f.research_type in strategic_types]

    def get_domain_research(self) -> List[ResearchFile]:
        """Get all domain research (requirements, compliance, users)"""
        domain_types = {
            ResearchType.DOMAIN_REQUIREMENTS,
            ResearchType.REGULATORY_COMPLIANCE,
            ResearchType.USER_RESEARCH,
        }
        return [f for f in self.research_files if f.research_type in domain_types]


@dataclass
class ResearchGap:
    """Gap between current state and research findings"""

    gap_id: str
    gap_type: GapType
    title: str
    description: str
    current_state: str  # What we have now
    desired_state: str  # What research suggests we should have
    source_research: List[str] = field(
        default_factory=list
    )  # Research files that surfaced this gap
    priority: Priority = Priority.MEDIUM
    effort: Effort = Effort.MEDIUM
    impact_areas: List[str] = field(default_factory=list)  # Areas affected
    blockers: List[str] = field(default_factory=list)  # What's blocking this
    dependencies: List[str] = field(default_factory=list)  # What this depends on
    metadata: Dict = field(default_factory=dict)


@dataclass
class OpportunityAnalysis:
    """Analysis of opportunities from research"""

    project_id: str
    gaps: List[ResearchGap] = field(default_factory=list)
    strategic_insights: List[str] = field(default_factory=list)  # Cross-cutting insights
    analyzed_at: datetime = field(default_factory=datetime.now)

    def get_by_priority(self, priority: Priority) -> List[ResearchGap]:
        """Get gaps by priority"""
        return [g for g in self.gaps if g.priority == priority]

    def get_by_type(self, gap_type: GapType) -> List[ResearchGap]:
        """Get gaps by type"""
        return [g for g in self.gaps if g.gap_type == gap_type]

    def get_critical_gaps(self) -> List[ResearchGap]:
        """Get critical priority gaps"""
        return self.get_by_priority(Priority.CRITICAL)


@dataclass
class ImplementationDecision:
    """Decision about whether/how to implement a gap"""

    decision_id: str
    gap: ResearchGap
    decision: DecisionType
    rationale: str  # Why this decision was made
    strategic_alignment: str  # How this aligns with vision/strategy
    user_impact: str  # Impact on users
    competitive_impact: str  # Impact on competitive position
    prerequisites: List[str] = field(default_factory=list)  # What needs to happen first
    estimated_value: float = 0.0  # 0-10 scale
    estimated_effort: float = 0.0  # 0-10 scale
    roi_score: float = 0.0  # value/effort ratio
    decided_at: datetime = field(default_factory=datetime.now)
    metadata: Dict = field(default_factory=dict)


@dataclass
class DecisionReport:
    """Report of all decisions made"""

    project_id: str
    decisions: List[ImplementationDecision] = field(default_factory=list)
    decided_at: datetime = field(default_factory=datetime.now)

    def get_by_decision_type(self, decision_type: DecisionType) -> List[ImplementationDecision]:
        """Get decisions by type"""
        return [d for d in self.decisions if d.decision == decision_type]

    def get_implement_now(self) -> List[ImplementationDecision]:
        """Get decisions to implement now"""
        return self.get_by_decision_type(DecisionType.IMPLEMENT_NOW)

    def get_implement_later(self) -> List[ImplementationDecision]:
        """Get decisions to implement later"""
        return self.get_by_decision_type(DecisionType.IMPLEMENT_LATER)

    def get_high_roi(self, threshold: float = 1.0) -> List[ImplementationDecision]:
        """Get high ROI decisions"""
        return [d for d in self.decisions if d.roi_score >= threshold]
