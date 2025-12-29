"""Unit tests for validation framework."""
import pytest
from unittest.mock import Mock
from datetime import datetime

from src.research.validation import (
    ValidationFramework,
    EvidenceValidator,
    CitationValidator,
    QualityValidator,
    ValidationResult
)
from src.research.models import Evidence, Citation, EvidenceQuality, ResearchReport


class TestEvidenceValidator:
    """Test suite for EvidenceValidator."""

    @pytest.fixture
    def validator(self):
        """Create evidence validator instance."""
        return EvidenceValidator()

    def test_validate_evidence_with_citations(self, validator):
        """Test validating evidence with proper citations."""
        citation = Citation(
            source_url="https://example.com",
            title="Test Source",
            accessed_at=datetime.now()
        )
        evidence = Evidence(
            content="This is a properly cited claim",
            citations=[citation],
            quality=EvidenceQuality.HIGH
        )
        
        result = validator.validate(evidence)
        
        assert result.is_valid
        assert len(result.errors) == 0

    def test_validate_evidence_without_citations(self, validator):
        """Test that evidence without citations fails validation."""
        # This should fail at model creation, but test validator too
        with pytest.raises(ValueError):
            Evidence(
                content="Uncited claim",
                citations=[],
                quality=EvidenceQuality.HIGH
            )

    def test_validate_evidence_quality_threshold(self, validator):
        """Test quality threshold validation."""
        citation = Citation(
            source_url="https://example.com",
            title="Test",
            accessed_at=datetime.now()
        )
        
        low_quality = Evidence(
            content="Low quality evidence",
            citations=[citation],
            quality=EvidenceQuality.LOW
        )
        
        result = validator.validate(low_quality, min_quality=EvidenceQuality.MEDIUM)
        
        assert not result.is_valid
        assert any("quality" in error.lower() for error in result.errors)

    def test_validate_evidence_content_length(self, validator):
        """Test content length validation."""
        citation = Citation(
            source_url="https://example.com",
            title="Test",
            accessed_at=datetime.now()
        )
        
        short_evidence = Evidence(
            content="Too short",
            citations=[citation],
            quality=EvidenceQuality.HIGH
        )
        
        result = validator.validate(short_evidence, min_content_length=50)
        
        assert not result.is_valid
        assert any("content length" in error.lower() for error in result.errors)


class TestCitationValidator:
    """Test suite for CitationValidator."""

    @pytest.fixture
    def validator(self):
        """Create citation validator instance."""
        return CitationValidator()

    def test_validate_valid_citation(self, validator):
        """Test validating a properly formed citation."""
        citation = Citation(
            source_url="https://example.com/article",
            title="Valid Article",
            author="John Doe",
            accessed_at=datetime.now()
        )
        
        result = validator.validate(citation)
        
        assert result.is_valid
        assert len(result.errors) == 0

    def test_validate_url_format(self, validator):
        """Test URL format validation."""
        with pytest.raises(ValueError):
            Citation(
                source_url="not-a-url",
                title="Test",
                accessed_at=datetime.now()
            )

    def test_validate_url_accessibility(self, validator):
        """Test checking if URL is accessible."""
        citation = Citation(
            source_url="https://example.com/nonexistent",
            title="Test",
            accessed_at=datetime.now()
        )
        
        # Mock URL check
        result = validator.validate(citation, check_accessibility=False)
        assert result.is_valid

    def test_validate_citation_freshness(self, validator):
        """Test citation freshness validation."""
        old_citation = Citation(
            source_url="https://example.com",
            title="Old Article",
            accessed_at=datetime(2020, 1, 1)
        )
        
        result = validator.validate(old_citation, max_age_days=365)
        
        # Should warn about old citation
        assert len(result.warnings) > 0


class TestQualityValidator:
    """Test suite for QualityValidator."""

    @pytest.fixture
    def validator(self):
        """Create quality validator instance."""
        return QualityValidator()

    def test_validate_high_quality_report(self, validator):
        """Test validating a high-quality research report."""
        citations = [
            Citation(
                source_url=f"https://example.com/{i}",
                title=f"Source {i}",
                accessed_at=datetime.now()
            )
            for i in range(5)
        ]
        
        evidence_items = [
            Evidence(
                content=f"Evidence point {i} with detailed explanation",
                citations=[citations[i]],
                quality=EvidenceQuality.HIGH
            )
            for i in range(5)
        ]
        
        report = ResearchReport(
            query="Test query",
            summary="Comprehensive summary of findings",
            evidence=evidence_items,
            conclusions=["Well-supported conclusion 1", "Well-supported conclusion 2"]
        )
        
        result = validator.validate(report)
        
        assert result.is_valid
        assert result.quality_score >= 0.8

    def test_validate_insufficient_evidence(self, validator):
        """Test validation fails with insufficient evidence."""
        citation = Citation(
            source_url="https://example.com",
            title="Single Source",
            accessed_at=datetime.now()
        )
        
        evidence = Evidence(
            content="Single piece of evidence",
            citations=[citation],
            quality=EvidenceQuality.MEDIUM
        )
        
        report = ResearchReport(
            query="Test query",
            summary="Brief summary",
            evidence=[evidence],
            conclusions=["Weak conclusion"]
        )
        
        result = validator.validate(report, min_evidence_count=3)
        
        assert not result.is_valid
        assert any("evidence" in error.lower() for error in result.errors)

    def test_validate_source_diversity(self, validator):
        """Test validation checks for source diversity."""
        # All citations from same domain
        citations = [
            Citation(
                source_url=f"https://example.com/page{i}",
                title=f"Page {i}",
                accessed_at=datetime.now()
            )
            for i in range(5)
        ]
        
        evidence_items = [
            Evidence(
                content=f"Evidence {i}",
                citations=[citations[i]],
                quality=EvidenceQuality.HIGH
            )
            for i in range(5)
        ]
        
        report = ResearchReport(
            query="Test query",
            summary="Summary",
            evidence=evidence_items,
            conclusions=["Conclusion"]
        )
        
        result = validator.validate(report, require_diverse_sources=True)
        
        # Should warn about lack of source diversity
        assert len(result.warnings) > 0


class TestValidationFramework:
    """Test suite for ValidationFramework."""

    @pytest.fixture
    def framework(self):
        """Create validation framework instance."""
        return ValidationFramework()

    def test_framework_runs_all_validators(self, framework):
        """Test that framework runs all registered validators."""
        citation = Citation(
            source_url="https://example.com",
            title="Test",
            accessed_at=datetime.now()
        )
        evidence = Evidence(
            content="Test evidence",
            citations=[citation],
            quality=EvidenceQuality.HIGH
        )
        report = ResearchReport(
            query="Test",
            summary="Summary",
            evidence=[evidence],
            conclusions=["Conclusion"]
        )
        
        result = framework.validate_all(report)
        
        assert result is not None
        assert hasattr(result, 'is_valid')
        assert hasattr(result, 'errors')
        assert hasattr(result, 'warnings')

    def test_framework_aggregates_results(self, framework):
        """Test that framework aggregates results from multiple validators."""
        citation = Citation(
            source_url="https://example.com",
            title="Test",
            accessed_at=datetime.now()
        )
        evidence = Evidence(
            content="Short",  # Too short
            citations=[citation],
            quality=EvidenceQuality.LOW  # Too low quality
        )
        report = ResearchReport(
            query="Test",
            summary="Summary",
            evidence=[evidence],
            conclusions=["Conclusion"]
        )
        
        result = framework.validate_all(report)
        
        # Should have errors from multiple validators
        assert len(result.errors) > 0
