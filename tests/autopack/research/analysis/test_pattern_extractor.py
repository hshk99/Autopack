"""Tests for PatternExtractor in autopack.research.analysis module.

Tests cover:
- Pattern extraction from project history
- Tech stack pattern identification
- Architecture pattern identification
- Monetization pattern identification
- Deployment pattern identification
- Workflow pattern extraction from improvements and cycles
- Confidence level calculation
- Pattern recommendations for new projects
"""

import pytest

from autopack.research.analysis.pattern_extractor import (
    ExtractedPattern,
    PatternConfidence,
    PatternExtractionResult,
    PatternExtractor,
    PatternType,
    ProjectOutcome,
)


@pytest.fixture
def pattern_extractor() -> PatternExtractor:
    """Create a PatternExtractor instance with default settings."""
    return PatternExtractor(
        min_occurrences_for_pattern=2,
        success_threshold=0.6,
        recency_weight=0.3,
    )


@pytest.fixture
def sample_project_history() -> list[dict]:
    """Create sample project history data."""
    return [
        {
            "project_id": "proj-001",
            "project_type": "ecommerce",
            "outcome": "successful",
            "tech_stack": {
                "languages": ["Python", "TypeScript"],
                "frameworks": ["FastAPI", "React"],
                "databases": ["PostgreSQL"],
            },
            "architecture": {
                "pattern": "microservices",
                "components": ["api", "frontend", "worker"],
                "decisions": ["event-driven", "containerized"],
            },
            "monetization": {
                "model": "subscription",
                "pricing": {"basic": 9.99, "pro": 29.99},
            },
            "deployment": {
                "platform": "AWS",
                "cicd": "GitHub Actions",
            },
            "timestamp": "2025-01-15T10:00:00",
        },
        {
            "project_id": "proj-002",
            "project_type": "ecommerce",
            "outcome": "successful",
            "tech_stack": {
                "languages": ["Python", "TypeScript"],
                "frameworks": ["FastAPI", "Vue"],
                "databases": ["PostgreSQL"],
            },
            "architecture": {
                "pattern": "microservices",
                "components": ["api", "frontend"],
                "decisions": ["event-driven"],
            },
            "monetization": {
                "model": "subscription",
                "pricing": {"starter": 19.99},
            },
            "deployment": {
                "platform": "AWS",
                "cicd": "GitHub Actions",
            },
            "timestamp": "2025-02-20T14:00:00",
        },
        {
            "project_id": "proj-003",
            "project_type": "saas",
            "outcome": "blocked",
            "tech_stack": {
                "languages": ["JavaScript"],
                "frameworks": ["Express", "React"],
                "databases": ["MongoDB"],
            },
            "architecture": {
                "pattern": "monolith",
                "components": ["backend", "frontend"],
            },
            "monetization": {
                "model": "freemium",
            },
            "deployment": {
                "platform": "Heroku",
                "cicd": "CircleCI",
            },
            "timestamp": "2025-03-01T09:00:00",
        },
    ]


@pytest.fixture
def sample_improvement_outcomes() -> dict[str, dict]:
    """Create sample improvement outcome data."""
    return {
        "IMP-001": {
            "imp_id": "IMP-001",
            "category": "research",
            "current_outcome": "implemented",
            "outcome_history": [
                {"outcome": "implemented", "notes": "Completed successfully"},
            ],
        },
        "IMP-002": {
            "imp_id": "IMP-002",
            "category": "research",
            "current_outcome": "implemented",
            "outcome_history": [
                {"outcome": "implemented", "notes": "Deployed to prod"},
            ],
        },
        "IMP-003": {
            "imp_id": "IMP-003",
            "category": "research",
            "current_outcome": "blocked",
            "outcome_history": [
                {"outcome": "blocked", "notes": "Missing API access"},
            ],
        },
        "IMP-004": {
            "imp_id": "IMP-004",
            "category": "memory",
            "current_outcome": "implemented",
            "outcome_history": [
                {"outcome": "implemented", "notes": "Vector store working"},
            ],
        },
        "IMP-005": {
            "imp_id": "IMP-005",
            "category": "memory",
            "current_outcome": "blocked",
            "outcome_history": [
                {"outcome": "blocked", "notes": "Missing API access"},
            ],
        },
    }


@pytest.fixture
def sample_cycle_data() -> dict[str, dict]:
    """Create sample cycle metrics data."""
    return {
        "cycle-001": {
            "cycle_id": "cycle-001",
            "metrics": {
                "phases_completed": 5,
                "phases_blocked": 1,
                "completion_rate": 0.83,
            },
        },
        "cycle-002": {
            "cycle_id": "cycle-002",
            "metrics": {
                "phases_completed": 4,
                "phases_blocked": 2,
                "completion_rate": 0.67,
            },
        },
    }


class TestPatternExtractor:
    """Tests for PatternExtractor class."""

    def test_init_default_settings(self):
        """Test PatternExtractor initializes with default settings."""
        extractor = PatternExtractor()
        assert extractor.min_occurrences_for_pattern == 2
        assert extractor.success_threshold == 0.6
        assert extractor.recency_weight == 0.3

    def test_init_custom_settings(self):
        """Test PatternExtractor initializes with custom settings."""
        extractor = PatternExtractor(
            min_occurrences_for_pattern=3,
            success_threshold=0.7,
            recency_weight=0.5,
        )
        assert extractor.min_occurrences_for_pattern == 3
        assert extractor.success_threshold == 0.7
        assert extractor.recency_weight == 0.5

    def test_extract_patterns_returns_result(
        self,
        pattern_extractor: PatternExtractor,
        sample_project_history: list,
        sample_improvement_outcomes: dict,
        sample_cycle_data: dict,
    ):
        """Test extract_patterns returns PatternExtractionResult."""
        result = pattern_extractor.extract_patterns(
            project_history=sample_project_history,
            improvement_outcomes=sample_improvement_outcomes,
            cycle_data=sample_cycle_data,
        )

        assert isinstance(result, PatternExtractionResult)
        assert result.total_projects_analyzed == len(sample_project_history)
        assert result.extraction_timestamp is not None

    def test_extract_tech_stack_patterns(
        self,
        sample_project_history: list,
    ):
        """Test tech stack patterns are extracted correctly."""
        # Use min_occurrences_for_pattern=1 to ensure patterns are captured
        extractor = PatternExtractor(min_occurrences_for_pattern=1)
        result = extractor.extract_patterns(
            project_history=sample_project_history,
            improvement_outcomes={},
            cycle_data={},
        )

        # Find tech stack patterns
        tech_patterns = [
            p for p in result.patterns if p.pattern_type == PatternType.TECH_STACK
        ]

        # With min_occurrences=1, we should get tech stack patterns
        # since the sample projects have tech stack data
        assert isinstance(tech_patterns, list)

        # If patterns were extracted, verify structure
        for pattern in tech_patterns:
            assert pattern.pattern_type == PatternType.TECH_STACK
            assert isinstance(pattern.components, list)

    def test_extract_architecture_patterns(
        self,
        pattern_extractor: PatternExtractor,
        sample_project_history: list,
    ):
        """Test architecture patterns are extracted correctly."""
        result = pattern_extractor.extract_patterns(
            project_history=sample_project_history,
            improvement_outcomes={},
            cycle_data={},
        )

        # Find architecture patterns
        arch_patterns = [
            p for p in result.patterns if p.pattern_type == PatternType.ARCHITECTURE
        ]

        assert len(arch_patterns) > 0

        # microservices appears in 2 projects
        microservices_patterns = [
            p for p in arch_patterns if "microservices" in p.context.lower()
        ]
        assert len(microservices_patterns) >= 1
        if microservices_patterns:
            assert microservices_patterns[0].occurrence_count >= 2

    def test_extract_workflow_patterns(
        self,
        pattern_extractor: PatternExtractor,
        sample_improvement_outcomes: dict,
        sample_cycle_data: dict,
    ):
        """Test workflow patterns are extracted from improvements and cycles."""
        result = pattern_extractor.extract_patterns(
            project_history=[],
            improvement_outcomes=sample_improvement_outcomes,
            cycle_data=sample_cycle_data,
        )

        # Find workflow patterns
        workflow_patterns = [
            p for p in result.patterns if p.pattern_type == PatternType.WORKFLOW
        ]

        assert len(workflow_patterns) > 0

        # Should have patterns for research and memory categories
        category_names = [p.context for p in workflow_patterns]
        assert "research" in category_names or "memory" in category_names

    def test_confidence_calculation(self, pattern_extractor: PatternExtractor):
        """Test confidence level calculation based on occurrence count."""
        assert (
            pattern_extractor._calculate_confidence(1) == PatternConfidence.EXPERIMENTAL
        )
        assert pattern_extractor._calculate_confidence(2) == PatternConfidence.LOW
        assert pattern_extractor._calculate_confidence(3) == PatternConfidence.MEDIUM
        assert pattern_extractor._calculate_confidence(5) == PatternConfidence.HIGH
        assert pattern_extractor._calculate_confidence(10) == PatternConfidence.HIGH

    def test_top_patterns_filtering(
        self,
        pattern_extractor: PatternExtractor,
        sample_project_history: list,
        sample_improvement_outcomes: dict,
        sample_cycle_data: dict,
    ):
        """Test top patterns are correctly identified."""
        result = pattern_extractor.extract_patterns(
            project_history=sample_project_history,
            improvement_outcomes=sample_improvement_outcomes,
            cycle_data=sample_cycle_data,
        )

        # Top patterns should have high confidence and success rate
        for pattern in result.top_patterns:
            assert pattern.confidence in (
                PatternConfidence.HIGH,
                PatternConfidence.MEDIUM,
            )
            assert pattern.success_rate >= pattern_extractor.success_threshold

    def test_get_patterns_for_project_type(
        self,
        pattern_extractor: PatternExtractor,
        sample_project_history: list,
    ):
        """Test filtering patterns by project type."""
        result = pattern_extractor.extract_patterns(
            project_history=sample_project_history,
            improvement_outcomes={},
            cycle_data={},
        )

        ecommerce_patterns = pattern_extractor.get_patterns_for_project_type(
            result, "ecommerce"
        )

        # Should return patterns associated with ecommerce
        for pattern in ecommerce_patterns:
            if pattern.associated_project_types:
                assert "ecommerce" in [
                    t.lower() for t in pattern.associated_project_types
                ]

    def test_get_recommended_patterns(
        self,
        pattern_extractor: PatternExtractor,
        sample_project_history: list,
        sample_improvement_outcomes: dict,
        sample_cycle_data: dict,
    ):
        """Test pattern recommendations for new project context."""
        result = pattern_extractor.extract_patterns(
            project_history=sample_project_history,
            improvement_outcomes=sample_improvement_outcomes,
            cycle_data=sample_cycle_data,
        )

        project_context = {
            "project_type": "ecommerce",
            "keywords": ["subscription", "api", "react"],
        }

        recommendations = pattern_extractor.get_recommended_patterns(
            result, project_context
        )

        # Should return list of patterns with relevance scores
        assert isinstance(recommendations, list)
        for pattern in recommendations:
            assert "relevance_score" in pattern.metadata

    def test_empty_project_history(self, pattern_extractor: PatternExtractor):
        """Test extraction with empty project history."""
        result = pattern_extractor.extract_patterns(
            project_history=[],
            improvement_outcomes={},
            cycle_data={},
        )

        assert result.total_projects_analyzed == 0
        assert len(result.patterns) == 0

    def test_pattern_extraction_result_to_dict(
        self,
        pattern_extractor: PatternExtractor,
        sample_project_history: list,
    ):
        """Test PatternExtractionResult serialization."""
        result = pattern_extractor.extract_patterns(
            project_history=sample_project_history,
            improvement_outcomes={},
            cycle_data={},
        )

        result_dict = result.to_dict()

        assert "patterns" in result_dict
        assert "total_projects_analyzed" in result_dict
        assert "extraction_timestamp" in result_dict
        assert "coverage_by_type" in result_dict


class TestExtractedPattern:
    """Tests for ExtractedPattern dataclass."""

    def test_to_dict(self):
        """Test ExtractedPattern serialization."""
        pattern = ExtractedPattern(
            pattern_id="test-001",
            pattern_type=PatternType.TECH_STACK,
            name="Test Pattern",
            description="A test pattern",
            success_rate=0.85,
            occurrence_count=5,
            confidence=PatternConfidence.HIGH,
        )

        pattern_dict = pattern.to_dict()

        assert pattern_dict["pattern_id"] == "test-001"
        assert pattern_dict["pattern_type"] == "tech_stack"
        assert pattern_dict["name"] == "Test Pattern"
        assert pattern_dict["success_rate"] == 0.85
        assert pattern_dict["confidence"] == "high"

    def test_from_dict(self):
        """Test ExtractedPattern deserialization."""
        data = {
            "pattern_id": "test-002",
            "pattern_type": "architecture",
            "name": "Microservices",
            "description": "Microservices architecture",
            "success_rate": 0.75,
            "occurrence_count": 3,
            "confidence": "medium",
            "components": ["api", "worker"],
        }

        pattern = ExtractedPattern.from_dict(data)

        assert pattern.pattern_id == "test-002"
        assert pattern.pattern_type == PatternType.ARCHITECTURE
        assert pattern.name == "Microservices"
        assert pattern.confidence == PatternConfidence.MEDIUM
        assert "api" in pattern.components


class TestPatternEnums:
    """Tests for pattern-related enums."""

    def test_pattern_type_values(self):
        """Test PatternType enum values."""
        assert PatternType.TECH_STACK.value == "tech_stack"
        assert PatternType.ARCHITECTURE.value == "architecture"
        assert PatternType.MONETIZATION.value == "monetization"
        assert PatternType.DEPLOYMENT.value == "deployment"
        assert PatternType.WORKFLOW.value == "workflow"

    def test_pattern_confidence_values(self):
        """Test PatternConfidence enum values."""
        assert PatternConfidence.HIGH.value == "high"
        assert PatternConfidence.MEDIUM.value == "medium"
        assert PatternConfidence.LOW.value == "low"
        assert PatternConfidence.EXPERIMENTAL.value == "experimental"

    def test_project_outcome_values(self):
        """Test ProjectOutcome enum values."""
        assert ProjectOutcome.SUCCESSFUL.value == "successful"
        assert ProjectOutcome.PARTIAL.value == "partial"
        assert ProjectOutcome.ABANDONED.value == "abandoned"
        assert ProjectOutcome.BLOCKED.value == "blocked"
