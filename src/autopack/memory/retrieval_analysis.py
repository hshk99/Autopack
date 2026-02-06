"""
IMP-MEM-025: Retrieval Analysis Report Generator

Analyzes retrieval metrics to determine if hybrid search would be beneficial.
Generates reports with recommendations based on collected data.
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class AnalysisThresholds:
    """Thresholds for analysis recommendations."""

    # Minimum samples needed before generating recommendations
    min_samples_for_report: int = 100

    # If exact-match miss rate exceeds this, hybrid search is warranted
    exact_match_miss_threshold: float = 0.05  # 5%

    # If keyword-only discovery rate exceeds this, hybrid search is warranted
    keyword_only_discovery_threshold: float = 0.10  # 10%

    # Confidence levels for recommendations
    high_confidence_samples: int = 500
    medium_confidence_samples: int = 200


@dataclass
class CollectionStats:
    """Statistics for a single collection."""

    collection: str
    total_queries: int
    exact_match_exists_count: int
    exact_match_retrieved_count: int
    exact_match_miss_count: int
    exact_match_miss_rate: float
    keyword_only_total: int
    keyword_only_rate: float
    avg_vector_results: float
    avg_keyword_matches: float
    avg_overlap: float


@dataclass
class MissedResultExample:
    """Example of a potentially missed result."""

    query: str
    collection: str
    timestamp: str
    keyword_only_count: int
    vector_top_score: float
    query_terms: List[str]


@dataclass
class AnalysisReport:
    """Complete analysis report."""

    # Period
    period_start: str
    period_end: str
    days_analyzed: int

    # Overall stats
    total_queries: int
    total_collections_analyzed: int

    # Key metrics
    overall_exact_match_miss_rate: float
    overall_keyword_only_rate: float

    # Per-collection breakdown
    collection_stats: List[CollectionStats]

    # Examples of potential misses
    missed_result_examples: List[MissedResultExample]

    # Recommendation
    recommendation: (
        str  # "hybrid_search_warranted" | "vector_search_sufficient" | "insufficient_data"
    )
    confidence: str  # "high" | "medium" | "low"
    confidence_score: float

    # Reasoning
    reasoning: List[str]

    # Suggested actions
    suggested_actions: List[str]


class RetrievalAnalysisReport:
    """
    Generates analysis reports from retrieval metrics.

    IMP-MEM-025: Analyzes logged metrics to determine if hybrid search
    (vector + keyword) would improve retrieval effectiveness.
    """

    def __init__(
        self,
        metrics_path: str = "data/retrieval_metrics.jsonl",
        thresholds: Optional[AnalysisThresholds] = None,
    ):
        self.metrics_path = Path(metrics_path)
        self.thresholds = thresholds or AnalysisThresholds()

    def generate_report(self, days: int = 7) -> AnalysisReport:
        """
        Analyze retrieval metrics and generate report.

        Args:
            days: Number of days to analyze

        Returns:
            AnalysisReport with findings and recommendations
        """
        # Load metrics
        metrics = self._load_metrics(days)

        if len(metrics) < self.thresholds.min_samples_for_report:
            return self._insufficient_data_report(len(metrics), days)

        # Calculate statistics
        collection_stats = self._calculate_collection_stats(metrics)
        overall_stats = self._calculate_overall_stats(metrics, collection_stats)
        examples = self._find_missed_result_examples(metrics)

        # Generate recommendation
        recommendation, confidence, reasoning = self._generate_recommendation(
            overall_stats, collection_stats, len(metrics)
        )

        # Generate suggested actions
        actions = self._generate_suggested_actions(recommendation, overall_stats, collection_stats)

        # Build report
        now = datetime.now(timezone.utc)
        start = now - timedelta(days=days)

        return AnalysisReport(
            period_start=start.strftime("%Y-%m-%d"),
            period_end=now.strftime("%Y-%m-%d"),
            days_analyzed=days,
            total_queries=len(metrics),
            total_collections_analyzed=len(collection_stats),
            overall_exact_match_miss_rate=overall_stats["exact_match_miss_rate"],
            overall_keyword_only_rate=overall_stats["keyword_only_rate"],
            collection_stats=collection_stats,
            missed_result_examples=examples[:10],
            recommendation=recommendation,
            confidence=confidence,
            confidence_score=overall_stats.get("confidence_score", 0.5),
            reasoning=reasoning,
            suggested_actions=actions,
        )

    def _load_metrics(self, days: int) -> List[Dict[str, Any]]:
        """Load metrics from the log file."""
        if not self.metrics_path.exists():
            logger.warning(f"[IMP-MEM-025] Metrics file not found: {self.metrics_path}")
            return []

        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        metrics = []

        try:
            with open(self.metrics_path, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        data = json.loads(line.strip())
                        timestamp = datetime.fromisoformat(data["timestamp"].replace("Z", "+00:00"))
                        if timestamp >= cutoff:
                            metrics.append(data)
                    except (json.JSONDecodeError, KeyError, ValueError):
                        continue

        except Exception as e:
            logger.error(f"[IMP-MEM-025] Error loading metrics: {e}")

        return metrics

    def _calculate_collection_stats(
        self,
        metrics: List[Dict[str, Any]],
    ) -> List[CollectionStats]:
        """Calculate per-collection statistics."""
        by_collection: Dict[str, List[Dict]] = defaultdict(list)

        for m in metrics:
            by_collection[m.get("collection", "unknown")].append(m)

        stats = []
        for collection, collection_metrics in by_collection.items():
            total = len(collection_metrics)

            exact_exists = sum(
                1 for m in collection_metrics if m.get("exact_match_in_corpus", False)
            )
            exact_retrieved = sum(
                1 for m in collection_metrics if m.get("exact_match_retrieved", False)
            )
            exact_missed = exact_exists - exact_retrieved

            keyword_only_total = sum(m.get("keyword_only_count", 0) for m in collection_metrics)
            queries_with_keyword_only = sum(
                1 for m in collection_metrics if m.get("keyword_only_count", 0) > 0
            )

            avg_vector = (
                sum(m.get("vector_results_count", 0) for m in collection_metrics) / total
                if total > 0
                else 0
            )
            avg_keyword = (
                sum(m.get("keyword_matches_count", 0) for m in collection_metrics) / total
                if total > 0
                else 0
            )
            avg_overlap = (
                sum(m.get("overlap_count", 0) for m in collection_metrics) / total
                if total > 0
                else 0
            )

            stats.append(
                CollectionStats(
                    collection=collection,
                    total_queries=total,
                    exact_match_exists_count=exact_exists,
                    exact_match_retrieved_count=exact_retrieved,
                    exact_match_miss_count=exact_missed,
                    exact_match_miss_rate=exact_missed / exact_exists if exact_exists > 0 else 0,
                    keyword_only_total=keyword_only_total,
                    keyword_only_rate=queries_with_keyword_only / total if total > 0 else 0,
                    avg_vector_results=round(avg_vector, 2),
                    avg_keyword_matches=round(avg_keyword, 2),
                    avg_overlap=round(avg_overlap, 2),
                )
            )

        return sorted(stats, key=lambda s: s.total_queries, reverse=True)

    def _calculate_overall_stats(
        self,
        metrics: List[Dict[str, Any]],
        collection_stats: List[CollectionStats],
    ) -> Dict[str, float]:
        """Calculate overall statistics across all collections."""
        total = len(metrics)

        exact_exists = sum(1 for m in metrics if m.get("exact_match_in_corpus", False))
        exact_retrieved = sum(1 for m in metrics if m.get("exact_match_retrieved", False))
        exact_missed = exact_exists - exact_retrieved

        queries_with_keyword_only = sum(1 for m in metrics if m.get("keyword_only_count", 0) > 0)

        # Calculate confidence based on sample size
        if total >= self.thresholds.high_confidence_samples:
            confidence_score = 0.9
        elif total >= self.thresholds.medium_confidence_samples:
            confidence_score = 0.7
        else:
            confidence_score = 0.5

        return {
            "exact_match_miss_rate": exact_missed / exact_exists if exact_exists > 0 else 0,
            "keyword_only_rate": queries_with_keyword_only / total if total > 0 else 0,
            "confidence_score": confidence_score,
        }

    def _find_missed_result_examples(
        self,
        metrics: List[Dict[str, Any]],
    ) -> List[MissedResultExample]:
        """Find examples of potentially missed results."""
        examples = []

        for m in metrics:
            keyword_only = m.get("keyword_only_count", 0)
            if keyword_only > 0:
                examples.append(
                    MissedResultExample(
                        query=m.get("query_text", "")[:100],
                        collection=m.get("collection", "unknown"),
                        timestamp=m.get("timestamp", ""),
                        keyword_only_count=keyword_only,
                        vector_top_score=m.get("vector_top_score", 0),
                        query_terms=m.get("query_terms", [])[:5],
                    )
                )

        # Sort by keyword_only_count descending
        return sorted(examples, key=lambda e: e.keyword_only_count, reverse=True)

    def _generate_recommendation(
        self,
        overall_stats: Dict[str, float],
        collection_stats: List[CollectionStats],
        sample_count: int,
    ) -> tuple[str, str, List[str]]:
        """Generate recommendation based on analysis."""
        reasoning = []

        exact_miss_rate = overall_stats["exact_match_miss_rate"]
        keyword_only_rate = overall_stats["keyword_only_rate"]

        # Determine confidence level
        if sample_count >= self.thresholds.high_confidence_samples:
            confidence = "high"
        elif sample_count >= self.thresholds.medium_confidence_samples:
            confidence = "medium"
        else:
            confidence = "low"

        # Check thresholds
        exceeds_exact_match = exact_miss_rate > self.thresholds.exact_match_miss_threshold
        exceeds_keyword_only = keyword_only_rate > self.thresholds.keyword_only_discovery_threshold

        if exceeds_exact_match or exceeds_keyword_only:
            recommendation = "hybrid_search_warranted"

            if exceeds_exact_match:
                reasoning.append(
                    f"Exact-match miss rate ({exact_miss_rate:.1%}) exceeds "
                    f"threshold ({self.thresholds.exact_match_miss_threshold:.1%})"
                )

            if exceeds_keyword_only:
                reasoning.append(
                    f"Keyword-only discovery rate ({keyword_only_rate:.1%}) exceeds "
                    f"threshold ({self.thresholds.keyword_only_discovery_threshold:.1%})"
                )

            # Check which collections are most affected
            problem_collections = [
                s
                for s in collection_stats
                if s.exact_match_miss_rate > self.thresholds.exact_match_miss_threshold
                or s.keyword_only_rate > self.thresholds.keyword_only_discovery_threshold
            ]
            if problem_collections:
                reasoning.append(
                    f"Collections most affected: {', '.join(s.collection for s in problem_collections[:3])}"
                )

        else:
            recommendation = "vector_search_sufficient"
            reasoning.append(
                f"Exact-match miss rate ({exact_miss_rate:.1%}) is below "
                f"threshold ({self.thresholds.exact_match_miss_threshold:.1%})"
            )
            reasoning.append(
                f"Keyword-only discovery rate ({keyword_only_rate:.1%}) is below "
                f"threshold ({self.thresholds.keyword_only_discovery_threshold:.1%})"
            )
            reasoning.append("Current vector search is performing adequately")

        return recommendation, confidence, reasoning

    def _generate_suggested_actions(
        self,
        recommendation: str,
        overall_stats: Dict[str, float],
        collection_stats: List[CollectionStats],
    ) -> List[str]:
        """Generate suggested actions based on recommendation."""
        actions = []

        if recommendation == "hybrid_search_warranted":
            actions.append(
                "Consider implementing hybrid search (vector + keyword) for improved recall"
            )

            # Find most affected collections
            problem_collections = sorted(
                collection_stats,
                key=lambda s: s.exact_match_miss_rate + s.keyword_only_rate,
                reverse=True,
            )[:3]

            if problem_collections:
                collections_str = ", ".join(s.collection for s in problem_collections)
                actions.append(f"Priority collections for hybrid search: {collections_str}")

            actions.append("Options: Add FTS5 (SQLite) or use Qdrant's keyword filters")
            actions.append("Consider BM25 + vector score fusion (Reciprocal Rank Fusion)")

        elif recommendation == "vector_search_sufficient":
            actions.append("Continue using vector-only search")
            actions.append("Re-run analysis in 2 weeks with more data")
            actions.append("Monitor for user complaints about missed search results")

        else:  # insufficient_data
            actions.append("Continue collecting instrumentation data")
            actions.append(f"Need {self.thresholds.min_samples_for_report}+ queries for analysis")
            actions.append("Ensure instrumentation is enabled in config/memory.yaml")

        return actions

    def _insufficient_data_report(
        self,
        sample_count: int,
        days: int,
    ) -> AnalysisReport:
        """Generate report when insufficient data is available."""
        now = datetime.now(timezone.utc)
        start = now - timedelta(days=days)

        return AnalysisReport(
            period_start=start.strftime("%Y-%m-%d"),
            period_end=now.strftime("%Y-%m-%d"),
            days_analyzed=days,
            total_queries=sample_count,
            total_collections_analyzed=0,
            overall_exact_match_miss_rate=0.0,
            overall_keyword_only_rate=0.0,
            collection_stats=[],
            missed_result_examples=[],
            recommendation="insufficient_data",
            confidence="low",
            confidence_score=0.0,
            reasoning=[
                f"Only {sample_count} queries logged",
                f"Need at least {self.thresholds.min_samples_for_report} queries for analysis",
            ],
            suggested_actions=[
                "Continue collecting instrumentation data",
                "Ensure retrieval_instrumentation.enabled = true in config",
                f"Re-run analysis after collecting more data",
            ],
        )

    def calculate_hybrid_search_benefit(self) -> Dict[str, Any]:
        """
        Estimate improvement if hybrid search were implemented.

        Returns estimated recall improvement and affected query count.
        """
        metrics = self._load_metrics(days=30)

        if not metrics:
            return {
                "estimated_recall_improvement": 0.0,
                "queries_affected_per_week": 0,
                "recommendation_threshold": 0.10,
                "has_sufficient_data": False,
            }

        # Count queries where keyword found results that vector missed
        affected_queries = sum(1 for m in metrics if m.get("keyword_only_count", 0) > 0)

        total = len(metrics)
        weekly_rate = affected_queries / (total / 4) if total > 0 else 0  # Assume 4 weeks

        return {
            "estimated_recall_improvement": affected_queries / total if total > 0 else 0,
            "queries_affected_per_week": round(weekly_rate),
            "recommendation_threshold": 0.10,
            "has_sufficient_data": total >= self.thresholds.min_samples_for_report,
        }

    def export_report_json(self, report: AnalysisReport, output_path: str) -> None:
        """Export report to JSON file."""
        from dataclasses import asdict

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(asdict(report), f, indent=2, ensure_ascii=False)

        logger.info(f"[IMP-MEM-025] Report exported to {output_path}")

    def print_report(self, report: AnalysisReport) -> None:
        """Print report to console in readable format."""
        print("\n" + "=" * 60)
        print("IMP-MEM-025: RETRIEVAL INSTRUMENTATION ANALYSIS REPORT")
        print("=" * 60)

        print(
            f"\nPeriod: {report.period_start} to {report.period_end} ({report.days_analyzed} days)"
        )
        print(f"Total Queries Analyzed: {report.total_queries}")
        print(f"Collections Analyzed: {report.total_collections_analyzed}")

        print("\n--- KEY METRICS ---")
        print(f"Exact-Match Miss Rate: {report.overall_exact_match_miss_rate:.1%}")
        print(f"Keyword-Only Discovery Rate: {report.overall_keyword_only_rate:.1%}")

        print("\n--- RECOMMENDATION ---")
        print(f"Recommendation: {report.recommendation.upper()}")
        print(f"Confidence: {report.confidence} ({report.confidence_score:.0%})")

        print("\nReasoning:")
        for reason in report.reasoning:
            print(f"  - {reason}")

        print("\nSuggested Actions:")
        for action in report.suggested_actions:
            print(f"  - {action}")

        if report.collection_stats:
            print("\n--- COLLECTION BREAKDOWN ---")
            for stat in report.collection_stats[:5]:
                print(f"\n{stat.collection}:")
                print(f"  Queries: {stat.total_queries}")
                print(f"  Exact-Match Miss Rate: {stat.exact_match_miss_rate:.1%}")
                print(f"  Keyword-Only Rate: {stat.keyword_only_rate:.1%}")

        if report.missed_result_examples:
            print("\n--- EXAMPLE MISSED RESULTS ---")
            for ex in report.missed_result_examples[:3]:
                print(f"\nQuery: {ex.query[:60]}...")
                print(f"  Collection: {ex.collection}")
                print(f"  Keyword-only matches: {ex.keyword_only_count}")
                print(f"  Vector top score: {ex.vector_top_score:.3f}")

        print("\n" + "=" * 60)
