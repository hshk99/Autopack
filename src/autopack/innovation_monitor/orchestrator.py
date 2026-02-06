"""
Orchestrator for the AI Innovation Monitor pipeline.

Coordinates the full scan → filter → assess → notify pipeline.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .models import (
    DailyScanResult,
    ImprovementAssessment,
    RawInnovation,
    ScoredInnovation,
    WeeklySummaryStats,
)
from .keyword_filter import KeywordFilter, KeywordFilterConfig
from .relevance_scorer import RelevanceScorer, ScoringWeights
from .deduplicator import Deduplicator
from .llm_assessor import LLMAssessor
from .email_notifier import EmailNotifier

from .scrapers import (
    ArxivScraper,
    RedditScraper,
    HackerNewsScraper,
    HuggingFaceScraper,
    GitHubTrendingScraper,
)

logger = logging.getLogger(__name__)


class InnovationMonitorOrchestrator:
    """
    Main orchestrator for the AI Innovation Monitor.

    Token-efficient pipeline:
    1. Scrape sources (0 tokens)
    2. Keyword filter (0 tokens)
    3. Relevance score (0 tokens)
    4. Deduplicate (0 tokens)
    5. LLM assess top 10 (~6k tokens)
    6. Email notify (0 tokens)
    """

    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None,
    ):
        """
        Initialize orchestrator with configuration.

        Args:
            config: Configuration dictionary (or load from file)
        """
        self.config = config or self._load_config()

        # Initialize components
        self._init_scrapers()
        self._init_pipeline()

        # Storage paths
        self.data_dir = Path(self.config.get("data_dir", "data/innovation_monitor"))
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from file or use defaults."""
        config_path = Path("config/innovation_monitor.yaml")

        if config_path.exists():
            try:
                import yaml

                with open(config_path, "r") as f:
                    return yaml.safe_load(f) or {}
            except Exception as e:
                logger.warning(f"Failed to load config: {e}")

        return self._default_config()

    def _default_config(self) -> Dict[str, Any]:
        """Default configuration."""
        return {
            "enabled": True,
            "sources": {
                "arxiv": {"enabled": True},
                "reddit": {"enabled": True},
                "hackernews": {"enabled": True},
                "huggingface": {"enabled": True},
                "github": {"enabled": True},
            },
            "keywords": [
                "RAG",
                "retrieval augmented",
                "vector database",
                "embedding",
                "agent",
                "LLM",
                "token efficiency",
            ],
            "assessment": {
                "max_candidates": 10,
                "improvement_threshold": 0.10,
            },
            "data_dir": "data/innovation_monitor",
        }

    def _init_scrapers(self) -> None:
        """Initialize source scrapers based on config."""
        self.scrapers = []

        sources = self.config.get("sources", {})

        if sources.get("arxiv", {}).get("enabled", True):
            self.scrapers.append(ArxivScraper())

        if sources.get("reddit", {}).get("enabled", True):
            subreddits = sources.get("reddit", {}).get("subreddits")
            self.scrapers.append(RedditScraper(subreddits=subreddits))

        if sources.get("hackernews", {}).get("enabled", True):
            self.scrapers.append(HackerNewsScraper())

        if sources.get("huggingface", {}).get("enabled", True):
            self.scrapers.append(HuggingFaceScraper())

        if sources.get("github", {}).get("enabled", True):
            self.scrapers.append(GitHubTrendingScraper())

        logger.info(f"[Orchestrator] Initialized {len(self.scrapers)} scrapers")

    def _init_pipeline(self) -> None:
        """Initialize pipeline components."""
        # Keyword filter
        filter_config = KeywordFilterConfig()
        custom_keywords = self.config.get("keyword_filter", {}).get("required")
        if custom_keywords:
            filter_config.required_keywords = custom_keywords
        self.keyword_filter = KeywordFilter(filter_config)

        # Relevance scorer
        self.scorer = RelevanceScorer(keyword_filter=self.keyword_filter)

        # Deduplicator
        seen_file = str(self.data_dir / "seen.json")
        self.deduplicator = Deduplicator(seen_file=seen_file)

        # LLM assessor
        assessment_config = self.config.get("assessment", {})
        self.assessor = LLMAssessor(
            improvement_threshold=assessment_config.get("improvement_threshold", 0.10),
        )

        # Email notifier
        self.notifier = EmailNotifier()

    async def run_daily_scan(
        self,
        lookback_days: int = 1,
    ) -> DailyScanResult:
        """
        Run the full daily scan pipeline.

        Args:
            lookback_days: Days to look back for new innovations

        Returns:
            DailyScanResult with scan statistics
        """
        since = datetime.now(timezone.utc) - timedelta(days=lookback_days)
        keywords = self.config.get("keywords", [])
        errors = []

        logger.info(f"[Orchestrator] Starting daily scan (since {since})")

        # Stage 1: Scrape (0 tokens)
        all_innovations: List[RawInnovation] = []
        for scraper in self.scrapers:
            try:
                innovations = await scraper.scrape(since, keywords)
                all_innovations.extend(innovations)
            except Exception as e:
                logger.error(f"[Orchestrator] Scraper {scraper.source_name} failed: {e}")
                errors.append(f"{scraper.source_name}: {e}")

        logger.info(f"[Orchestrator] Scraped {len(all_innovations)} raw items")
        total_scanned = len(all_innovations)

        # Stage 2: Keyword filter (0 tokens)
        filtered = self.keyword_filter.filter(all_innovations)
        logger.info(f"[Orchestrator] {len(filtered)} passed keyword filter")

        # Stage 3: Score (0 tokens)
        scored = self.scorer.score(filtered)

        # Stage 4: Deduplicate (0 tokens)
        unique = self.deduplicator.deduplicate(scored)
        logger.info(f"[Orchestrator] {len(unique)} unique after dedup")

        if not unique:
            logger.info("[Orchestrator] No new innovations to assess")
            return DailyScanResult(
                scanned_count=total_scanned,
                new_count=0,
                above_threshold_count=0,
                notifications_sent=0,
                timestamp=datetime.now(timezone.utc),
                errors=errors,
            )

        # Stage 5: LLM assess top candidates (uses tokens)
        max_candidates = self.config.get("assessment", {}).get("max_candidates", 10)
        assessments = await self.assessor.assess(unique, max_candidates)

        # Count above threshold
        above_threshold = [a for a in assessments if a.meets_threshold]
        logger.info(f"[Orchestrator] {len(above_threshold)} innovations above threshold")

        # Stage 6: Notify (0 tokens)
        notifications_sent = 0
        for assessment in above_threshold:
            if self.notifier.send_innovation_alert(assessment):
                notifications_sent += 1

        # Save assessments for weekly summary
        self._save_assessments(assessments)

        result = DailyScanResult(
            scanned_count=total_scanned,
            new_count=len(unique),
            above_threshold_count=len(above_threshold),
            notifications_sent=notifications_sent,
            timestamp=datetime.now(timezone.utc),
            errors=errors,
        )

        logger.info(
            f"[Orchestrator] Scan complete: {result.scanned_count} scanned, "
            f"{result.new_count} new, {result.above_threshold_count} above threshold, "
            f"{result.notifications_sent} notifications sent"
        )

        return result

    def _save_assessments(self, assessments: List[ImprovementAssessment]) -> None:
        """Save assessments to JSONL file for weekly summary."""
        assessments_file = self.data_dir / "assessments.jsonl"

        try:
            with open(assessments_file, "a", encoding="utf-8") as f:
                for assessment in assessments:
                    data = {
                        "innovation_id": assessment.innovation_id,
                        "innovation_title": assessment.innovation_title,
                        "innovation_url": assessment.innovation_url,
                        "source": assessment.source.value,
                        "overall_improvement": assessment.overall_improvement,
                        "meets_threshold": assessment.meets_threshold,
                        "applicable_components": assessment.applicable_components,
                        "rationale": assessment.rationale,
                        "assessed_at": (
                            assessment.assessed_at.isoformat() if assessment.assessed_at else None
                        ),
                    }
                    f.write(json.dumps(data, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.warning(f"[Orchestrator] Failed to save assessments: {e}")

    def _load_week_assessments(self) -> List[ImprovementAssessment]:
        """Load assessments from the past week."""
        assessments_file = self.data_dir / "assessments.jsonl"
        assessments = []

        if not assessments_file.exists():
            return assessments

        cutoff = datetime.now(timezone.utc) - timedelta(days=7)

        try:
            with open(assessments_file, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        data = json.loads(line.strip())
                        assessed_at = data.get("assessed_at")
                        if assessed_at:
                            dt = datetime.fromisoformat(assessed_at.replace("Z", "+00:00"))
                            if dt < cutoff:
                                continue

                        from .models import SourceType

                        assessment = ImprovementAssessment(
                            innovation_id=data["innovation_id"],
                            innovation_title=data["innovation_title"],
                            innovation_url=data["innovation_url"],
                            source=SourceType(data["source"]),
                            overall_improvement=data["overall_improvement"],
                            meets_threshold=data["meets_threshold"],
                            applicable_components=data.get("applicable_components", []),
                            rationale=data.get("rationale", ""),
                        )
                        assessments.append(assessment)
                    except (json.JSONDecodeError, KeyError, ValueError):
                        continue
        except Exception as e:
            logger.warning(f"[Orchestrator] Failed to load assessments: {e}")

        return assessments

    def send_weekly_summary(self) -> bool:
        """Generate and send weekly summary email."""
        assessments = self._load_week_assessments()

        # Calculate stats
        now = datetime.now(timezone.utc)
        week_ago = now - timedelta(days=7)

        # Get top innovations (above threshold, sorted by improvement)
        above_threshold = [a for a in assessments if a.meets_threshold]
        top_innovations = sorted(
            above_threshold,
            key=lambda a: a.overall_improvement,
            reverse=True,
        )[:5]

        stats = WeeklySummaryStats(
            start_date=week_ago.strftime("%Y-%m-%d"),
            end_date=now.strftime("%Y-%m-%d"),
            total_scanned=len(assessments) * 10,  # Rough estimate
            passed_filter=len(assessments) * 3,  # Rough estimate
            assessed=len(assessments),
            above_threshold=len(above_threshold),
            top_innovations=top_innovations,
            next_scan="Tomorrow 06:00 UTC",
        )

        return self.notifier.send_weekly_summary(stats)

    def run_sync(self, lookback_days: int = 1) -> DailyScanResult:
        """Synchronous wrapper for run_daily_scan."""
        return asyncio.run(self.run_daily_scan(lookback_days))


def create_orchestrator_from_config(
    config_path: str = "config/innovation_monitor.yaml",
) -> InnovationMonitorOrchestrator:
    """
    Create orchestrator from configuration file.

    Args:
        config_path: Path to YAML configuration file

    Returns:
        Configured InnovationMonitorOrchestrator
    """
    config = None

    if Path(config_path).exists():
        try:
            import yaml

            with open(config_path, "r") as f:
                config = yaml.safe_load(f)
        except Exception as e:
            logger.warning(f"Failed to load config from {config_path}: {e}")

    return InnovationMonitorOrchestrator(config=config)
