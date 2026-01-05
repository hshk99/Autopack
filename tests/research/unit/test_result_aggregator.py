"""Unit tests for research result aggregation."""

import pytest


class TestResultAggregator:
    """Test suite for result aggregation functionality."""

    def test_result_merging(self):
        """Test merging results from multiple sources."""
        result1 = {"source": "s1", "findings": ["finding1", "finding2"]}
        result2 = {"source": "s2", "findings": ["finding3", "finding4"]}

        merged = {
            "sources": [result1["source"], result2["source"]],
            "findings": result1["findings"] + result2["findings"],
        }

        assert len(merged["sources"]) == 2
        assert len(merged["findings"]) == 4
        assert "finding1" in merged["findings"]
        assert "finding4" in merged["findings"]

    def test_duplicate_removal(self):
        """Test removal of duplicate findings."""
        findings = ["finding1", "finding2", "finding1", "finding3", "finding2"]
        unique_findings = list(dict.fromkeys(findings))

        assert len(unique_findings) == 3
        assert unique_findings.count("finding1") == 1
        assert unique_findings.count("finding2") == 1

    def test_confidence_scoring(self):
        """Test confidence score calculation."""
        results = [
            {"finding": "f1", "confidence": 0.9},
            {"finding": "f1", "confidence": 0.8},
            {"finding": "f1", "confidence": 0.85},
        ]

        # Average confidence for same finding
        total_confidence = sum(r["confidence"] for r in results)
        avg_confidence = total_confidence / len(results)

        assert avg_confidence == pytest.approx(0.85, rel=0.01)

    def test_source_weighting(self):
        """Test weighted aggregation by source reliability."""
        results = [
            {"source": "s1", "weight": 1.0, "value": 100},
            {"source": "s2", "weight": 0.8, "value": 80},
            {"source": "s3", "weight": 0.6, "value": 60},
        ]

        weighted_sum = sum(r["value"] * r["weight"] for r in results)
        total_weight = sum(r["weight"] for r in results)
        weighted_avg = weighted_sum / total_weight

        assert weighted_avg == pytest.approx(83.33, rel=0.01)

    def test_result_ranking(self):
        """Test ranking results by relevance."""
        results = [
            {"id": "r1", "relevance": 0.7},
            {"id": "r2", "relevance": 0.9},
            {"id": "r3", "relevance": 0.5},
        ]

        ranked = sorted(results, key=lambda x: x["relevance"], reverse=True)

        assert ranked[0]["id"] == "r2"
        assert ranked[1]["id"] == "r1"
        assert ranked[2]["id"] == "r3"

    def test_result_filtering(self):
        """Test filtering results by criteria."""
        results = [
            {"id": "r1", "confidence": 0.9, "relevance": 0.8},
            {"id": "r2", "confidence": 0.6, "relevance": 0.7},
            {"id": "r3", "confidence": 0.95, "relevance": 0.9},
        ]

        min_confidence = 0.8
        filtered = [r for r in results if r["confidence"] >= min_confidence]

        assert len(filtered) == 2
        assert all(r["confidence"] >= min_confidence for r in filtered)

    def test_result_grouping(self):
        """Test grouping results by category."""
        results = [
            {"id": "r1", "category": "market"},
            {"id": "r2", "category": "technical"},
            {"id": "r3", "category": "market"},
        ]

        grouped = {}
        for result in results:
            category = result["category"]
            if category not in grouped:
                grouped[category] = []
            grouped[category].append(result)

        assert len(grouped["market"]) == 2
        assert len(grouped["technical"]) == 1

    def test_result_summarization(self):
        """Test result summarization."""
        results = [
            {"finding": "Market size is $1B"},
            {"finding": "Growth rate is 20%"},
            {"finding": "Key players: A, B, C"},
        ]

        summary = {
            "total_findings": len(results),
            "key_points": [r["finding"] for r in results[:2]],
        }

        assert summary["total_findings"] == 3
        assert len(summary["key_points"]) == 2
