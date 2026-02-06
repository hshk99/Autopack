# AI Innovation Monitor - Implementation Plan

> **Status**: Proposed
> **Priority**: High
> **Category**: Strategic / Automation
> **Goal**: Automatically scan AI news, assess relevance to Autopack, notify if improvement potential >10%
> **Token Strategy**: Rule-based funnel with LLM only for final candidates (~90% token reduction)

## Overview

Build an automated system that:
1. **Scans** AI news/research on a regular schedule (daily/weekly) - **0 tokens**
2. **Filters** using rule-based keyword matching and scoring - **0 tokens**
3. **Assesses** top candidates with LLM for >10% improvement potential - **minimal tokens**
4. **Reports** via email or Telegram using templates - **0 tokens**

## Token-Efficient Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    TOKEN-EFFICIENT INNOVATION MONITOR                        │
└─────────────────────────────────────────────────────────────────────────────┘

STAGE 1: RULE-BASED FUNNEL (0 tokens)
═══════════════════════════════════════════════════════════════════════════════

┌──────────────┐    ┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│   Scraper    │───▶│   Keyword    │───▶│  Relevance   │───▶│   Dedup &    │
│              │    │   Filter     │    │   Scorer     │    │   Rank       │
├──────────────┤    ├──────────────┤    ├──────────────┤    ├──────────────┤
│ HTTP only    │    │ Regex/exact  │    │ Code-based   │    │ Hash-based   │
│ RSS feeds    │    │ match on     │    │ weighted     │    │ title simil. │
│ APIs         │    │ title+body   │    │ scoring      │    │ URL dedup    │
├──────────────┤    ├──────────────┤    ├──────────────┤    ├──────────────┤
│ ~100 items   │    │ → ~40 items  │    │ → ~15 items  │    │ → ~10 items  │
│ 0 tokens     │    │ 0 tokens     │    │ 0 tokens     │    │ 0 tokens     │
└──────────────┘    └──────────────┘    └──────────────┘    └──────────────┘


STAGE 2: LLM ASSESSMENT (tokens only for top candidates)
═══════════════════════════════════════════════════════════════════════════════

┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│   LLM Deep   │───▶│  Threshold   │───▶│   Notify     │
│  Assessment  │    │   Check      │    │  (template)  │
├──────────────┤    ├──────────────┤    ├──────────────┤
│ Only top 10  │    │ Code-based   │    │ Template msg │
│ ~2k tok/item │    │ >10% check   │    │ Telegram/    │
│              │    │              │    │ Email        │
├──────────────┤    ├──────────────┤    ├──────────────┤
│ ~20k tokens  │    │ → ~2 items   │    │ 0 tokens     │
└──────────────┘    └──────────────┘    └──────────────┘


DAILY TOKEN BUDGET: ~20k tokens (vs ~200k without funnel = 90% reduction)
MONTHLY COST: ~$1-3 (vs $15-30 without funnel)
```

## Component Breakdown: What Uses Tokens vs Code

| Component | Tokens | Approach |
|-----------|--------|----------|
| Web Scraping (Reddit, HN, ArXiv, HF) | **0** | HTTP requests, RSS, APIs |
| Keyword Filter | **0** | Regex patterns, exact match |
| Relevance Scorer | **0** | Weighted scoring formula |
| Deduplication | **0** | Hash + Levenshtein similarity |
| Category Classifier | **0** | Pattern matching on tags |
| **LLM Assessment** | **~2k/item** | Only for top 10 candidates |
| Threshold Check | **0** | Simple numeric comparison |
| Email Notification | **0** | Gmail SMTP + HTML templates (reuse from idea-genesis) |
| Weekly Summary | **0** | Template with aggregated stats |

## Stage 1: Rule-Based Components (0 Tokens)

### 1.1 Source Scraper

**Location**: `src/autopack/innovation_monitor/scrapers/`

```python
from dataclasses import dataclass
from typing import List, Optional
from datetime import datetime
from enum import Enum
import aiohttp
import feedparser

class SourceType(Enum):
    ARXIV = "arxiv"
    HUGGINGFACE = "huggingface"
    GITHUB = "github"
    REDDIT = "reddit"
    HACKERNEWS = "hackernews"
    BLOG = "blog"

@dataclass
class RawInnovation:
    """Raw item from scraping - no LLM processing yet."""
    id: str
    title: str
    source: SourceType
    url: str
    published_date: datetime
    body_text: str  # Abstract, description, or post body
    upvotes: int = 0  # Engagement signal
    comments: int = 0
    tags: List[str] = None  # Source-provided tags

class ArxivScraper:
    """Scrapes ArXiv RSS/API - 0 tokens."""

    FEED_URL = "http://export.arxiv.org/rss/cs.AI"
    API_URL = "http://export.arxiv.org/api/query"

    async def scrape(self, since: datetime) -> List[RawInnovation]:
        """
        Fetch recent papers from ArXiv.

        Uses RSS feed (free, no auth required).
        """
        async with aiohttp.ClientSession() as session:
            async with session.get(self.FEED_URL) as resp:
                content = await resp.text()

        feed = feedparser.parse(content)

        innovations = []
        for entry in feed.entries:
            pub_date = datetime(*entry.published_parsed[:6])
            if pub_date < since:
                continue

            innovations.append(RawInnovation(
                id=entry.id,
                title=entry.title,
                source=SourceType.ARXIV,
                url=entry.link,
                published_date=pub_date,
                body_text=entry.summary,  # Abstract
                tags=self._extract_categories(entry),
            ))

        return innovations

    def _extract_categories(self, entry) -> List[str]:
        """Extract arxiv categories as tags."""
        return [tag.term for tag in getattr(entry, 'tags', [])]


class RedditScraper:
    """Scrapes Reddit via JSON API - 0 tokens."""

    SUBREDDITS = ["MachineLearning", "LocalLLaMA", "LangChain"]

    async def scrape(self, since: datetime) -> List[RawInnovation]:
        """
        Fetch recent posts from AI subreddits.

        Uses Reddit's public JSON API (no auth for read-only).
        """
        innovations = []

        async with aiohttp.ClientSession() as session:
            for subreddit in self.SUBREDDITS:
                url = f"https://www.reddit.com/r/{subreddit}/new.json?limit=50"
                headers = {"User-Agent": "AutopackInnovationMonitor/1.0"}

                async with session.get(url, headers=headers) as resp:
                    data = await resp.json()

                for post in data["data"]["children"]:
                    p = post["data"]
                    pub_date = datetime.fromtimestamp(p["created_utc"])

                    if pub_date < since:
                        continue

                    innovations.append(RawInnovation(
                        id=p["id"],
                        title=p["title"],
                        source=SourceType.REDDIT,
                        url=f"https://reddit.com{p['permalink']}",
                        published_date=pub_date,
                        body_text=p.get("selftext", ""),
                        upvotes=p["ups"],
                        comments=p["num_comments"],
                        tags=[subreddit],
                    ))

        return innovations


class HackerNewsScraper:
    """Scrapes Hacker News via API - 0 tokens."""

    async def scrape(self, since: datetime) -> List[RawInnovation]:
        """Fetch recent HN stories about AI/ML."""
        # Use HN Algolia API for search
        # https://hn.algolia.com/api
        pass


class HuggingFaceScraper:
    """Scrapes HuggingFace daily papers - 0 tokens."""

    PAPERS_URL = "https://huggingface.co/api/daily_papers"

    async def scrape(self, since: datetime) -> List[RawInnovation]:
        """Fetch daily papers from HuggingFace."""
        pass


class GitHubTrendingScraper:
    """Scrapes GitHub trending - 0 tokens."""

    async def scrape(self, since: datetime) -> List[RawInnovation]:
        """Fetch trending repos in AI/ML topics."""
        # Scrape https://github.com/trending or use unofficial API
        pass
```

### 1.2 Keyword Filter (0 Tokens)

```python
import re
from typing import List, Set
from dataclasses import dataclass

@dataclass
class KeywordFilterConfig:
    """Configuration for keyword filtering."""

    # Must match at least one of these (case-insensitive)
    required_keywords: List[str] = None

    # Boost score if these appear
    boost_keywords: List[str] = None

    # Skip if these appear (spam filter)
    exclude_keywords: List[str] = None

    def __post_init__(self):
        self.required_keywords = self.required_keywords or [
            # Core RAG/Memory terms
            r"\bRAG\b",
            r"retrieval.augmented",
            r"vector.*(database|store|search)",
            r"embedding",
            r"semantic.search",
            r"memory.system",

            # Agent terms
            r"\bagent\b",
            r"agentic",
            r"autonomous",
            r"tool.use",

            # LLM efficiency
            r"token.efficien",
            r"context.window",
            r"context.length",
            r"long.context",

            # Specific innovations
            r"PageIndex",
            r"tree.index",
            r"hierarchical.*(index|retrieval)",
            r"hybrid.search",
            r"ColBERT",
            r"RAPTOR",
        ]

        self.boost_keywords = self.boost_keywords or [
            r"benchmark",
            r"SOTA|state.of.the.art",
            r"outperform",
            r"\d+%.*improv",  # "30% improvement"
            r"open.source",
            r"github\.com",
        ]

        self.exclude_keywords = self.exclude_keywords or [
            r"hiring|job.post",
            r"looking.for.co-?founder",
            r"rate.my",
            r"roast.my",
        ]


class KeywordFilter:
    """
    Rule-based keyword filtering - 0 tokens.

    Filters raw innovations based on regex pattern matching.
    """

    def __init__(self, config: KeywordFilterConfig = None):
        self.config = config or KeywordFilterConfig()
        self._compile_patterns()

    def _compile_patterns(self):
        """Pre-compile regex patterns for performance."""
        self.required_patterns = [
            re.compile(p, re.IGNORECASE)
            for p in self.config.required_keywords
        ]
        self.boost_patterns = [
            re.compile(p, re.IGNORECASE)
            for p in self.config.boost_keywords
        ]
        self.exclude_patterns = [
            re.compile(p, re.IGNORECASE)
            for p in self.config.exclude_keywords
        ]

    def filter(self, innovations: List[RawInnovation]) -> List[RawInnovation]:
        """
        Filter innovations based on keyword matching.

        Returns items that:
        - Match at least one required keyword
        - Don't match any exclude keywords
        """
        filtered = []

        for item in innovations:
            text = f"{item.title} {item.body_text}"

            # Check exclusions first (fast rejection)
            if any(p.search(text) for p in self.exclude_patterns):
                continue

            # Check required keywords
            if any(p.search(text) for p in self.required_patterns):
                filtered.append(item)

        return filtered

    def count_boost_matches(self, item: RawInnovation) -> int:
        """Count how many boost keywords match (for scoring)."""
        text = f"{item.title} {item.body_text}"
        return sum(1 for p in self.boost_patterns if p.search(text))
```

### 1.3 Relevance Scorer (0 Tokens)

```python
from dataclasses import dataclass
from typing import List

@dataclass
class ScoringWeights:
    """Weights for relevance scoring formula."""
    keyword_match: float = 0.3      # Keyword relevance
    engagement: float = 0.2         # Upvotes, comments
    recency: float = 0.15           # Newer = better
    source_quality: float = 0.2     # ArXiv > Reddit shitpost
    boost_keywords: float = 0.15    # Benchmark claims, etc.

@dataclass
class ScoredInnovation:
    """Innovation with computed relevance score."""
    raw: RawInnovation
    score: float
    score_breakdown: dict

class RelevanceScorer:
    """
    Code-based relevance scoring - 0 tokens.

    Computes a weighted score based on multiple signals.
    """

    SOURCE_QUALITY_SCORES = {
        SourceType.ARXIV: 1.0,        # Peer review signal
        SourceType.HUGGINGFACE: 0.9,  # Curated
        SourceType.GITHUB: 0.7,       # Varies widely
        SourceType.HACKERNEWS: 0.6,   # Community filter
        SourceType.REDDIT: 0.5,       # High noise
        SourceType.BLOG: 0.4,         # Unknown quality
    }

    def __init__(
        self,
        weights: ScoringWeights = None,
        keyword_filter: KeywordFilter = None
    ):
        self.weights = weights or ScoringWeights()
        self.keyword_filter = keyword_filter or KeywordFilter()

    def score(self, innovations: List[RawInnovation]) -> List[ScoredInnovation]:
        """
        Score and rank innovations by relevance.

        Returns sorted list (highest score first).
        """
        scored = []

        for item in innovations:
            breakdown = self._compute_score_breakdown(item)
            total = sum(
                getattr(self.weights, k) * v
                for k, v in breakdown.items()
            )

            scored.append(ScoredInnovation(
                raw=item,
                score=total,
                score_breakdown=breakdown
            ))

        # Sort by score descending
        return sorted(scored, key=lambda x: x.score, reverse=True)

    def _compute_score_breakdown(self, item: RawInnovation) -> dict:
        """Compute individual score components."""
        return {
            "keyword_match": self._keyword_score(item),
            "engagement": self._engagement_score(item),
            "recency": self._recency_score(item),
            "source_quality": self._source_quality_score(item),
            "boost_keywords": self._boost_score(item),
        }

    def _keyword_score(self, item: RawInnovation) -> float:
        """Score based on keyword match density."""
        text = f"{item.title} {item.body_text}"
        matches = sum(
            1 for p in self.keyword_filter.required_patterns
            if p.search(text)
        )
        # Normalize: 3+ matches = 1.0
        return min(matches / 3.0, 1.0)

    def _engagement_score(self, item: RawInnovation) -> float:
        """Score based on community engagement."""
        # Normalize engagement (varies by source)
        if item.source == SourceType.REDDIT:
            # Reddit: 100+ upvotes is significant
            return min(item.upvotes / 100.0, 1.0)
        elif item.source == SourceType.HACKERNEWS:
            # HN: 50+ points is significant
            return min(item.upvotes / 50.0, 1.0)
        elif item.source == SourceType.GITHUB:
            # GitHub: stars (if available)
            return min(item.upvotes / 500.0, 1.0)
        else:
            # ArXiv, HF don't have engagement metrics
            return 0.5  # Neutral

    def _recency_score(self, item: RawInnovation) -> float:
        """Score based on publication date."""
        age_days = (datetime.now() - item.published_date).days

        if age_days <= 1:
            return 1.0
        elif age_days <= 7:
            return 0.8
        elif age_days <= 30:
            return 0.5
        else:
            return 0.2

    def _source_quality_score(self, item: RawInnovation) -> float:
        """Score based on source reputation."""
        return self.SOURCE_QUALITY_SCORES.get(item.source, 0.3)

    def _boost_score(self, item: RawInnovation) -> float:
        """Score based on boost keyword matches."""
        count = self.keyword_filter.count_boost_matches(item)
        return min(count / 3.0, 1.0)
```

### 1.4 Deduplication (0 Tokens)

```python
import hashlib
from difflib import SequenceMatcher
from typing import List, Set

class Deduplicator:
    """
    Hash and similarity-based deduplication - 0 tokens.
    """

    def __init__(self, similarity_threshold: float = 0.85):
        self.similarity_threshold = similarity_threshold
        self.seen_hashes: Set[str] = set()
        self.seen_titles: List[str] = []

    def deduplicate(
        self,
        innovations: List[ScoredInnovation]
    ) -> List[ScoredInnovation]:
        """
        Remove duplicates based on:
        1. URL hash (exact duplicate)
        2. Title similarity (near duplicate)
        """
        unique = []

        for item in innovations:
            # Check URL hash
            url_hash = hashlib.md5(item.raw.url.encode()).hexdigest()
            if url_hash in self.seen_hashes:
                continue

            # Check title similarity
            if self._is_similar_to_seen(item.raw.title):
                continue

            # Unique - add to results and tracking
            unique.append(item)
            self.seen_hashes.add(url_hash)
            self.seen_titles.append(item.raw.title)

        return unique

    def _is_similar_to_seen(self, title: str) -> bool:
        """Check if title is similar to any seen title."""
        title_lower = title.lower()

        for seen in self.seen_titles:
            ratio = SequenceMatcher(
                None, title_lower, seen.lower()
            ).ratio()

            if ratio >= self.similarity_threshold:
                return True

        return False
```

## Stage 2: LLM Assessment (Minimal Tokens)

### 2.1 LLM Assessor (Only for Top 10 Candidates)

```python
@dataclass
class ImprovementAssessment:
    """LLM-generated assessment of improvement potential."""
    innovation_id: str
    innovation_title: str

    # Improvement estimates (percentage, 0-100)
    capability_improvement: int
    efficiency_improvement: int
    token_efficiency_improvement: int
    speed_improvement: int

    # Computed
    overall_improvement: float  # Weighted average
    meets_threshold: bool       # >10%

    # Reasoning (brief)
    applicable_components: List[str]
    rationale: str  # 1-2 sentences
    implementation_effort: str  # low/medium/high


class LLMAssessor:
    """
    LLM-based assessment - ONLY for top candidates after rule-based filtering.

    Optimized for minimal tokens:
    - Concise prompt
    - Structured output (no verbose reasoning)
    - ~2k tokens per assessment
    """

    SYSTEM_PROMPT = """You assess AI innovations for Autopack (an LLM-based codebase builder).

Autopack uses:
- Qdrant/FAISS vector memory with OpenAI embeddings
- Context injection from historical data
- Self-improvement loop via telemetry

Output JSON only. Be conservative - only estimate >10% if evidence is strong."""

    USER_TEMPLATE = """Innovation: {title}
Source: {source}
Summary: {summary}

Estimate improvement percentages (0-100) for Autopack:
- capability: new features enabled
- efficiency: cleaner architecture
- token_efficiency: fewer tokens for same result
- speed: faster execution

Output format:
{{"capability": N, "efficiency": N, "token_efficiency": N, "speed": N, "components": ["x"], "rationale": "1 sentence", "effort": "low|medium|high"}}"""

    def __init__(self, llm_client, threshold: float = 0.10):
        self.llm = llm_client
        self.threshold = threshold

    async def assess(
        self,
        candidates: List[ScoredInnovation],
        max_candidates: int = 10
    ) -> List[ImprovementAssessment]:
        """
        Assess top candidates using LLM.

        Only processes top N to minimize token usage.
        """
        assessments = []

        for candidate in candidates[:max_candidates]:
            assessment = await self._assess_one(candidate)
            assessments.append(assessment)

        return assessments

    async def _assess_one(
        self,
        candidate: ScoredInnovation
    ) -> ImprovementAssessment:
        """Assess single innovation (~2k tokens)."""
        prompt = self.USER_TEMPLATE.format(
            title=candidate.raw.title,
            source=candidate.raw.source.value,
            summary=candidate.raw.body_text[:1000],  # Truncate
        )

        response = await self.llm.complete(
            system=self.SYSTEM_PROMPT,
            user=prompt,
            max_tokens=200,  # Force concise output
        )

        data = json.loads(response)

        # Compute overall (weighted average)
        overall = (
            data["capability"] * 0.3 +
            data["efficiency"] * 0.2 +
            data["token_efficiency"] * 0.3 +
            data["speed"] * 0.2
        ) / 100.0

        return ImprovementAssessment(
            innovation_id=candidate.raw.id,
            innovation_title=candidate.raw.title,
            capability_improvement=data["capability"],
            efficiency_improvement=data["efficiency"],
            token_efficiency_improvement=data["token_efficiency"],
            speed_improvement=data["speed"],
            overall_improvement=overall,
            meets_threshold=overall >= self.threshold,
            applicable_components=data["components"],
            rationale=data["rationale"],
            implementation_effort=data["effort"],
        )
```

### 2.2 Email Notifier (Template-Based, 0 Tokens)

Reuses the same Gmail SMTP pattern from `idea-genesis-orchestrator/report_sender.py`.

```python
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

class EmailNotifier:
    """
    Email notification via Gmail SMTP - 0 tokens.

    Uses same pattern as idea-genesis-orchestrator/report_sender.py.

    Environment variables:
    - SMTP_HOST: smtp.gmail.com
    - SMTP_PORT: 587
    - SMTP_USER: your-email@gmail.com
    - SMTP_PASSWORD: Gmail App Password (not regular password)
    - EMAIL_TO: recipient email
    """

    EMAIL_SUBJECT_TEMPLATE = "🚀 AI Innovation Alert: {title}"

    EMAIL_HTML_TEMPLATE = """
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; padding: 20px; max-width: 600px; }}
            .header {{ background: #4A90D9; color: white; padding: 15px; border-radius: 5px 5px 0 0; }}
            .content {{ background: #f9f9f9; padding: 20px; border: 1px solid #ddd; }}
            .score {{ font-size: 32px; font-weight: bold; color: #2E7D32; }}
            .score-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin: 15px 0; }}
            .score-item {{ background: white; padding: 10px; border-radius: 5px; }}
            .components {{ background: #E3F2FD; padding: 10px; border-radius: 5px; margin: 10px 0; }}
            .rationale {{ font-style: italic; color: #555; border-left: 3px solid #4A90D9; padding-left: 10px; }}
            .footer {{ font-size: 12px; color: #888; margin-top: 20px; }}
            a {{ color: #4A90D9; }}
        </style>
    </head>
    <body>
        <div class="header">
            <h2>🚀 AI Innovation Alert for Autopack</h2>
        </div>
        <div class="content">
            <h3>{title}</h3>
            <p><strong>Source:</strong> {source} | <a href="{url}">View Original</a></p>

            <p class="score">Improvement Potential: {overall:.0%}</p>

            <div class="score-grid">
                <div class="score-item">
                    <strong>Capability</strong><br>{capability}%
                </div>
                <div class="score-item">
                    <strong>Token Efficiency</strong><br>{token_efficiency}%
                </div>
                <div class="score-item">
                    <strong>Speed</strong><br>{speed}%
                </div>
                <div class="score-item">
                    <strong>Implementation Effort</strong><br>{effort}
                </div>
            </div>

            <div class="components">
                <strong>Applicable Components:</strong> {components}
            </div>

            <div class="rationale">
                <strong>Why this matters:</strong><br>
                {rationale}
            </div>

            <div class="footer">
                Report #{report_id} | Generated {timestamp}
            </div>
        </div>
    </body>
    </html>
    """

    EMAIL_PLAIN_TEMPLATE = """
AI Innovation Alert for Autopack
================================

{title}

Source: {source}
URL: {url}

Improvement Potential: {overall:.0%}
- Capability: {capability}%
- Token Efficiency: {token_efficiency}%
- Speed: {speed}%
- Implementation Effort: {effort}

Applicable Components: {components}

Why this matters:
{rationale}

---
Report #{report_id} | {timestamp}
"""

    WEEKLY_SUMMARY_HTML = """
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; padding: 20px; }}
            .header {{ background: #4A90D9; color: white; padding: 15px; border-radius: 5px; }}
            .stats {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin: 20px 0; }}
            .stat {{ background: #f0f0f0; padding: 15px; text-align: center; border-radius: 5px; }}
            .stat-value {{ font-size: 24px; font-weight: bold; color: #333; }}
            .top-item {{ background: #fff; border: 1px solid #ddd; padding: 15px; margin: 10px 0; border-radius: 5px; }}
        </style>
    </head>
    <body>
        <div class="header">
            <h2>📊 Weekly AI Innovation Summary</h2>
            <p>{start_date} - {end_date}</p>
        </div>

        <div class="stats">
            <div class="stat">
                <div class="stat-value">{total_scanned}</div>
                <div>Scanned</div>
            </div>
            <div class="stat">
                <div class="stat-value">{passed_filter}</div>
                <div>Passed Filter</div>
            </div>
            <div class="stat">
                <div class="stat-value">{assessed}</div>
                <div>LLM Assessed</div>
            </div>
            <div class="stat">
                <div class="stat-value">{above_threshold}</div>
                <div>Above 10%</div>
            </div>
        </div>

        {top_items_section}

        <p style="color: #888; font-size: 12px;">Next scan: {next_scan}</p>
    </body>
    </html>
    """

    def __init__(self):
        """Load config from environment variables."""
        self.smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
        self.smtp_port = int(os.getenv("SMTP_PORT", "587"))
        self.smtp_user = os.getenv("SMTP_USER")
        self.smtp_password = os.getenv("SMTP_PASSWORD")
        self.email_to = os.getenv("EMAIL_TO")

    def is_configured(self) -> bool:
        """Check if email is properly configured."""
        return bool(
            self.smtp_host and
            self.smtp_user and
            self.smtp_password and
            self.email_to
        )

    def send_innovation_alert(
        self,
        assessment: ImprovementAssessment,
        innovation: RawInnovation,
    ) -> bool:
        """
        Send innovation alert via email.

        Returns True if sent successfully.
        """
        if not self.is_configured():
            logger.warning("Email not configured - skipping notification")
            return False

        try:
            # Build message
            msg = MIMEMultipart("alternative")
            msg["Subject"] = self.EMAIL_SUBJECT_TEMPLATE.format(
                title=innovation.title[:50]
            )
            msg["From"] = self.smtp_user
            msg["To"] = self.email_to

            # Template variables
            template_vars = {
                "title": innovation.title,
                "source": innovation.source.value,
                "url": innovation.url,
                "overall": assessment.overall_improvement,
                "capability": assessment.capability_improvement,
                "token_efficiency": assessment.token_efficiency_improvement,
                "speed": assessment.speed_improvement,
                "effort": assessment.implementation_effort,
                "components": ", ".join(assessment.applicable_components),
                "rationale": assessment.rationale,
                "report_id": innovation.id[:8],
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M UTC"),
            }

            # Plain text version
            text_part = MIMEText(
                self.EMAIL_PLAIN_TEMPLATE.format(**template_vars),
                "plain"
            )
            msg.attach(text_part)

            # HTML version
            html_part = MIMEText(
                self.EMAIL_HTML_TEMPLATE.format(**template_vars),
                "html"
            )
            msg.attach(html_part)

            # Send via SMTP
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_user, self.smtp_password)
                server.send_message(msg)

            logger.info(f"[Email] Innovation alert sent: {innovation.title[:50]}")
            return True

        except Exception as e:
            logger.error(f"[Email] Failed to send alert: {e}")
            return False

    def send_weekly_summary(
        self,
        stats: Dict,
        top_items: List[ImprovementAssessment],
    ) -> bool:
        """Send weekly summary email."""
        if not self.is_configured():
            return False

        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = f"📊 AI Innovation Weekly Summary - {datetime.now().strftime('%Y-%m-%d')}"
            msg["From"] = self.smtp_user
            msg["To"] = self.email_to

            # Build top items section
            top_items_html = ""
            for item in top_items[:5]:
                top_items_html += f"""
                <div class="top-item">
                    <strong>{item.innovation_title}</strong><br>
                    Improvement: {item.overall_improvement:.0%} |
                    Components: {', '.join(item.applicable_components)}
                </div>
                """

            html_content = self.WEEKLY_SUMMARY_HTML.format(
                start_date=stats["start_date"],
                end_date=stats["end_date"],
                total_scanned=stats["total_scanned"],
                passed_filter=stats["passed_filter"],
                assessed=stats["assessed"],
                above_threshold=stats["above_threshold"],
                top_items_section=top_items_html,
                next_scan=stats.get("next_scan", "Tomorrow 06:00 UTC"),
            )

            msg.attach(MIMEText(html_content, "html"))

            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_user, self.smtp_password)
                server.send_message(msg)

            logger.info("[Email] Weekly summary sent")
            return True

        except Exception as e:
            logger.error(f"[Email] Failed to send weekly summary: {e}")
            return False
```

## Token Budget Analysis

| Scenario | Items | Tokens | Cost |
|----------|-------|--------|------|
| Daily scan (100 raw → 10 assessed) | 10 | ~20k | ~$0.06 |
| Busy day (200 raw → 15 assessed) | 15 | ~30k | ~$0.09 |
| Weekly total | ~70 | ~140k | ~$0.42 |
| **Monthly total** | ~300 | ~600k | **~$1.80** |

Compare to "assess everything" approach:
- 100 items/day × 30 days × 5k tokens = 15M tokens/month = ~$45/month
- **Savings: 96%**

## Configuration

**File**: `config/innovation_monitor.yaml`

```yaml
# AI Innovation Monitor - Token-Efficient Configuration

enabled: false

schedule:
  daily_scan_time: "06:00"  # UTC
  weekly_summary_day: "monday"

# Stage 1: Rule-based (0 tokens)
scraping:
  sources:
    arxiv: { enabled: true, categories: ["cs.AI", "cs.CL", "cs.LG"] }
    reddit: { enabled: true, subreddits: ["MachineLearning", "LocalLLaMA"] }
    hackernews: { enabled: true }
    huggingface: { enabled: true }
    github: { enabled: true }

  keyword_filter:
    required:
      - "\\bRAG\\b"
      - "retrieval.augmented"
      - "vector.*(database|store)"
      - "embedding"
      - "memory.system"
      - "\\bagent\\b"
      - "token.efficien"
    exclude:
      - "hiring|job.post"
      - "rate.my|roast.my"

  scoring:
    weights:
      keyword_match: 0.3
      engagement: 0.2
      recency: 0.15
      source_quality: 0.2
      boost_keywords: 0.15

# Stage 2: LLM assessment (minimal tokens)
assessment:
  max_candidates: 10  # Only assess top 10
  llm_model: "claude-sonnet-4-20250514"  # Fast + cheap
  improvement_threshold: 0.10  # 10%

# Notifications (template-based, 0 tokens)
# Uses same Gmail SMTP pattern as idea-genesis-orchestrator/report_sender.py
notifications:
  primary_channel: email

  email:
    enabled: true
    # Environment variables (reuse from idea-genesis-orchestrator):
    # SMTP_HOST=smtp.gmail.com
    # SMTP_PORT=587
    # SMTP_USER=your-email@gmail.com
    # SMTP_PASSWORD=Gmail App Password (myaccount.google.com/apppasswords)
    # EMAIL_TO=recipient email

  telegram:
    enabled: false  # Optional backup
    bot_token: "${TELEGRAM_BOT_TOKEN}"
    chat_id: "${TELEGRAM_CHAT_ID}"
```

## Implementation Phases

### Phase 1: Scrapers (0 tokens)
- [ ] ArXiv RSS scraper
- [ ] Reddit JSON API scraper
- [ ] HackerNews Algolia API scraper
- [ ] HuggingFace daily papers scraper
- [ ] GitHub trending scraper

### Phase 2: Rule-Based Pipeline (0 tokens)
- [ ] Keyword filter with regex patterns
- [ ] Relevance scorer with weighted formula
- [ ] Deduplicator (hash + similarity)
- [ ] Storage for seen items

### Phase 3: LLM Assessment (minimal tokens)
- [ ] Concise assessment prompt
- [ ] Structured JSON output parsing
- [ ] Threshold checking

### Phase 4: Notifications (0 tokens)
- [ ] Email notifier (primary) - reuse Gmail SMTP from idea-genesis-orchestrator
- [ ] HTML + plain text email templates
- [ ] Weekly summary email generator
- [ ] (Optional) Telegram notifier as backup

### Phase 5: Orchestration
- [ ] Daily scan scheduler
- [ ] Weekly summary scheduler
- [ ] CLI commands
- [ ] Error handling and retries

## Summary

**Total token usage: ~600k/month (~$2)**

| Component | Tokens |
|-----------|--------|
| Scraping | 0 |
| Keyword Filter | 0 |
| Relevance Scorer | 0 |
| Deduplication | 0 |
| LLM Assessment (top 10 only) | ~20k/day |
| Notifications | 0 |
| Weekly Summary | 0 |

The key insight: **90%+ of the work can be done with code**. LLM is only needed for the final "is this >10% improvement?" judgment on pre-filtered candidates.
