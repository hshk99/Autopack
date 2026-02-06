"""
Data models for the AI Innovation Monitor.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Optional


class SourceType(Enum):
    """Source types for AI innovations."""

    ARXIV = "arxiv"
    HUGGINGFACE = "huggingface"
    GITHUB = "github"
    REDDIT = "reddit"
    HACKERNEWS = "hackernews"
    BLOG = "blog"
    NEWS = "news"


@dataclass
class RawInnovation:
    """
    Raw item from scraping - no LLM processing yet.

    This is the output of Stage 1 scrapers (0 tokens).
    """

    id: str
    title: str
    source: SourceType
    url: str
    published_date: datetime
    body_text: str  # Abstract, description, or post body
    upvotes: int = 0  # Engagement signal
    comments: int = 0
    tags: List[str] = field(default_factory=list)  # Source-provided tags


@dataclass
class ScoredInnovation:
    """
    Innovation with computed relevance score.

    Output of Stage 1 rule-based scoring (0 tokens).
    """

    raw: RawInnovation
    score: float  # 0.0 to 1.0
    score_breakdown: dict = field(default_factory=dict)

    @property
    def id(self) -> str:
        return self.raw.id

    @property
    def title(self) -> str:
        return self.raw.title


@dataclass
class ImprovementAssessment:
    """
    LLM-generated assessment of improvement potential.

    Output of Stage 2 LLM assessment (uses tokens).
    """

    innovation_id: str
    innovation_title: str
    innovation_url: str
    source: SourceType

    # Improvement estimates (percentage, 0-100)
    capability_improvement: int = 0
    efficiency_improvement: int = 0
    token_efficiency_improvement: int = 0
    speed_improvement: int = 0

    # Computed
    overall_improvement: float = 0.0  # Weighted average (0.0 to 1.0)
    meets_threshold: bool = False  # >10%

    # Details
    applicable_components: List[str] = field(default_factory=list)
    rationale: str = ""
    implementation_effort: str = "medium"  # low/medium/high

    # Metadata
    assessed_at: Optional[datetime] = None
    confidence: float = 0.5

    def __post_init__(self):
        """Calculate overall improvement if not set."""
        if self.overall_improvement == 0.0 and any(
            [
                self.capability_improvement,
                self.efficiency_improvement,
                self.token_efficiency_improvement,
                self.speed_improvement,
            ]
        ):
            # Weighted average
            self.overall_improvement = (
                self.capability_improvement * 0.3
                + self.efficiency_improvement * 0.2
                + self.token_efficiency_improvement * 0.3
                + self.speed_improvement * 0.2
            ) / 100.0

        self.meets_threshold = self.overall_improvement >= 0.10


@dataclass
class DailyScanResult:
    """Result of a daily innovation scan."""

    scanned_count: int
    new_count: int
    above_threshold_count: int
    notifications_sent: int
    timestamp: datetime
    errors: List[str] = field(default_factory=list)


@dataclass
class WeeklySummaryStats:
    """Statistics for weekly summary."""

    start_date: str
    end_date: str
    total_scanned: int
    passed_filter: int
    assessed: int
    above_threshold: int
    top_innovations: List[ImprovementAssessment] = field(default_factory=list)
    next_scan: str = "Tomorrow 06:00 UTC"
