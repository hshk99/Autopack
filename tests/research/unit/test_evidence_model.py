"""Unit tests for evidence model and citation enforcement."""

import pytest
from datetime import datetime

from autopack.research.models import Evidence, Citation, EvidenceQuality


class TestEvidence:
    """Test suite for Evidence model."""

    def test_evidence_requires_citation(self):
        """Test that evidence requires at least one citation."""
        with pytest.raises(ValueError, match="Evidence must have at least one citation"):
            Evidence(
                content="This is a claim without citation",
                citations=[],
                quality=EvidenceQuality.HIGH,
            )

    def test_evidence_with_valid_citation(self):
        """Test creating evidence with valid citation."""
        citation = Citation(
            source_url="https://example.com/article",
            title="Example Article",
            author="John Doe",
            accessed_at=datetime.now(),
        )

        evidence = Evidence(
            content="This is a properly cited claim",
            citations=[citation],
            quality=EvidenceQuality.HIGH,
        )

        assert evidence.content == "This is a properly cited claim"
        assert len(evidence.citations) == 1
        assert evidence.citations[0] == citation

    def test_evidence_multiple_citations(self):
        """Test evidence can have multiple citations."""
        citation1 = Citation(
            source_url="https://example.com/article1", title="Article 1", accessed_at=datetime.now()
        )
        citation2 = Citation(
            source_url="https://example.com/article2", title="Article 2", accessed_at=datetime.now()
        )

        evidence = Evidence(
            content="Claim supported by multiple sources",
            citations=[citation1, citation2],
            quality=EvidenceQuality.HIGH,
        )

        assert len(evidence.citations) == 2

    def test_evidence_quality_levels(self):
        """Test different evidence quality levels."""
        citation = Citation(
            source_url="https://example.com", title="Test", accessed_at=datetime.now()
        )

        for quality in [EvidenceQuality.HIGH, EvidenceQuality.MEDIUM, EvidenceQuality.LOW]:
            evidence = Evidence(content="Test content", citations=[citation], quality=quality)
            assert evidence.quality == quality


class TestCitation:
    """Test suite for Citation model."""

    def test_citation_requires_source_url(self):
        """Test that citation requires source URL."""
        with pytest.raises(ValueError):
            Citation(source_url="", title="Test", accessed_at=datetime.now())

    def test_citation_with_all_fields(self):
        """Test citation with all optional fields."""
        accessed = datetime.now()
        citation = Citation(
            source_url="https://example.com/article",
            title="Complete Article",
            author="Jane Smith",
            publication_date=datetime(2024, 1, 1),
            accessed_at=accessed,
            excerpt="This is an excerpt from the article",
        )

        assert citation.source_url == "https://example.com/article"
        assert citation.title == "Complete Article"
        assert citation.author == "Jane Smith"
        assert citation.publication_date == datetime(2024, 1, 1)
        assert citation.accessed_at == accessed
        assert citation.excerpt == "This is an excerpt from the article"

    def test_citation_minimal_fields(self):
        """Test citation with only required fields."""
        accessed = datetime.now()
        citation = Citation(
            source_url="https://example.com", title="Minimal Citation", accessed_at=accessed
        )

        assert citation.source_url == "https://example.com"
        assert citation.title == "Minimal Citation"
        assert citation.accessed_at == accessed
        assert citation.author is None
        assert citation.publication_date is None

    def test_citation_url_validation(self):
        """Test URL validation in citations."""
        with pytest.raises(ValueError, match="Invalid URL"):
            Citation(source_url="not-a-valid-url", title="Test", accessed_at=datetime.now())
