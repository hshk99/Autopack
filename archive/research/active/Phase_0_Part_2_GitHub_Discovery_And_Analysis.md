# Phase 0 Part 2: GitHub Discovery & Analysis

**Status**: 🚧 Ready for Implementation
**Estimated Effort**: 20-30 hours
**Timeline**: Week 1, Days 4-5 + Week 2, Day 1
**Build ID**: BUILD-034
**Depends On**: Part 1 (Evidence Foundation) ✅
**Enables**: Part 3 (Synthesis & Evaluation)

---

## Executive Summary

Build end-to-end pipeline for **ONE research mode** (Market Opportunity) using **ONE data source** (GitHub API) with **code-based decision frameworks** (Python does arithmetic, not LLMs).

This validates:
- GitHub API integration works
- Discovery finds relevant repos
- Gatherer extracts findings with evidence binding (from Part 1)
- Decision framework produces deterministic scores (NO hallucinated arithmetic)
- Cost stays under budget ($5/topic target)

**Success Criteria**:
- ✅ Can discover relevant GitHub repos for test topic ("file organization tools")
- ✅ Can extract findings from README with valid citations (extraction_span requirement enforced)
- ✅ Decision framework calculates deterministic Market Attractiveness Score
- ✅ End-to-end works: topic → discovery → extraction → decision score
- ✅ Cost <$5 per topic (within $8 budget, leaves headroom for Part 3)

**STOP/GO Gate**: If end-to-end fails or cost >$8 → simplify or abort Phase 0

---

## Background & Rationale

### Why GitHub Only (for Phase 0)?

GitHub API is the **ideal starting point** for validation:

✅ **Legal & Accessible**:
- Free tier: 5,000 requests/hour (authenticated)
- Well-documented REST API
- No ToS violations (unlike G2, Capterra scraping)
- No paywalls (unlike Statista, IBISWorld)

✅ **High Signal for Market Opportunity**:
- Star counts → proxy for market interest
- Commit activity → proxy for market health
- Issues/PRs → proxy for user engagement
- README → rich source of market narratives

✅ **Predictable & Stable**:
- Consistent response format (JSON)
- Reliable uptime (>99.9%)
- No anti-bot measures (uses API keys, not scraping)

### Why Code-Based Decision Frameworks?

All 3 GPT reviewers flagged **LLM arithmetic hallucination** as a showstopper (DEC-012).

**Problem**:
```python
# v2.0 (BAD):
prompt = "Calculate market attractiveness: (market_size * growth * accessibility) / (competition * barriers)"
result = llm.complete(prompt)
# LLM returns "11.2" when actual is 10.67 ❌
```

**Solution**:
```python
# Phase 0 (GOOD):
extracted = llm.complete("Extract: market_size, growth_rate, ... Return JSON")
score = (extracted.market_size * extracted.growth_rate) / extracted.competition  # Python!
```

**Key Insight**: LLMs extract, Python calculates. This is **deterministic** and **verifiable**.

---

## Implementation Specification

### 1. Directory Structure

```
src/autopack/research/
├── models/
│   ├── evidence.py          # ✅ From Part 1
│   └── validators.py        # ✅ From Part 1
├── discovery/
│   ├── __init__.py
│   └── github_discovery.py  # NEW: GitHubDiscoveryStrategy
├── gathering/
│   ├── __init__.py
│   └── github_gatherer.py   # NEW: GitHubGatherer
├── analysis/
│   ├── __init__.py
│   └── decision_frameworks.py  # NEW: MarketAttractivenessCalculator
└── tests/
    ├── test_github_discovery.py
    ├── test_github_gatherer.py
    └── test_market_attractiveness.py
```

### 2. Core Components

#### 2.1 GitHub Discovery Strategy (`discovery/github_discovery.py`)

**Purpose**: Find relevant GitHub repositories for a research topic

**Implementation**:

```python
"""GitHub repository discovery for market research."""

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional

import requests


@dataclass
class DiscoveredSource:
    """A discovered source from GitHub search."""

    source_type: str  # "github_repo"
    url: str  # Full repo URL
    title: str  # Repo name
    description: Optional[str]
    metadata: dict  # Stars, forks, language, last_updated, etc.
    discovered_at: datetime
    relevance_estimate: float  # 0.0-1.0 based on keyword match + metadata


class GitHubDiscoveryStrategy:
    """
    Discovers GitHub repositories relevant to a research topic.

    Uses GitHub Search API to find repos, then ranks by:
    - Keyword relevance (topic match in name/description)
    - Popularity (stars, forks)
    - Recency (last updated within 1 year)
    """

    def __init__(self, github_token: Optional[str] = None):
        """
        Initialize GitHub discovery.

        Args:
            github_token: GitHub personal access token (for higher rate limits)
                         If None, uses unauthenticated requests (60/hour limit)
        """
        self.github_token = github_token or os.getenv("GITHUB_TOKEN")
        self.base_url = "https://api.github.com"

        # Setup headers
        self.headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28"
        }
        if self.github_token:
            self.headers["Authorization"] = f"Bearer {self.github_token}"

    async def discover_sources(
        self,
        topic: str,
        max_results: int = 20,
        min_stars: int = 50,
        language: Optional[str] = None
    ) -> List[DiscoveredSource]:
        """
        Discover GitHub repositories for a topic.

        Example:
            discovery = GitHubDiscoveryStrategy()
            sources = await discovery.discover_sources(
                topic="file organization tools",
                max_results=15,
                min_stars=100
            )

        Args:
            topic: Research topic (e.g., "file organization tools")
            max_results: Maximum number of repos to return
            min_stars: Minimum star count (filters out low-signal repos)
            language: Optional language filter (e.g., "python", "typescript")

        Returns:
            List of DiscoveredSource objects, ranked by relevance
        """

        # Build search query
        query_parts = [topic]
        if min_stars:
            query_parts.append(f"stars:>={min_stars}")
        if language:
            query_parts.append(f"language:{language}")

        query = " ".join(query_parts)

        # Search repos
        search_url = f"{self.base_url}/search/repositories"
        params = {
            "q": query,
            "sort": "stars",  # Sort by popularity
            "order": "desc",
            "per_page": max_results
        }

        response = requests.get(search_url, headers=self.headers, params=params)
        response.raise_for_status()

        data = response.json()
        repos = data.get("items", [])

        # Convert to DiscoveredSource objects
        sources = []
        for repo in repos:
            source = DiscoveredSource(
                source_type="github_repo",
                url=repo["html_url"],
                title=repo["full_name"],
                description=repo.get("description"),
                metadata={
                    "stars": repo["stargazers_count"],
                    "forks": repo["forks_count"],
                    "language": repo.get("language"),
                    "last_updated": repo["updated_at"],
                    "topics": repo.get("topics", []),
                    "open_issues": repo.get("open_issues_count", 0)
                },
                discovered_at=datetime.now(timezone.utc),
                relevance_estimate=self._calculate_relevance(repo, topic)
            )
            sources.append(source)

        # Sort by relevance (descending)
        sources.sort(key=lambda s: s.relevance_estimate, reverse=True)

        return sources

    def _calculate_relevance(self, repo: dict, topic: str) -> float:
        """
        Calculate relevance score (0.0-1.0) for a repo.

        Factors:
        - Name/description match (40%)
        - Stars (30%)
        - Recency (20%)
        - Topics match (10%)

        Args:
            repo: GitHub API repo object
            topic: Research topic

        Returns:
            Relevance score (0.0-1.0)
        """
        score = 0.0

        # Factor 1: Name/description keyword match (40%)
        topic_lower = topic.lower()
        name_lower = repo["full_name"].lower()
        desc_lower = (repo.get("description") or "").lower()

        if topic_lower in name_lower:
            score += 0.4
        elif topic_lower in desc_lower:
            score += 0.3
        else:
            # Partial match (any keyword)
            keywords = topic_lower.split()
            matches = sum(1 for kw in keywords if kw in name_lower or kw in desc_lower)
            score += 0.4 * (matches / len(keywords))

        # Factor 2: Stars (30%)
        stars = repo["stargazers_count"]
        if stars >= 10000:
            score += 0.3
        elif stars >= 1000:
            score += 0.25
        elif stars >= 500:
            score += 0.20
        elif stars >= 100:
            score += 0.15
        else:
            score += 0.1

        # Factor 3: Recency (20%)
        from datetime import datetime
        last_updated = datetime.fromisoformat(repo["updated_at"].replace("Z", "+00:00"))
        days_since_update = (datetime.now(timezone.utc) - last_updated).days
        if days_since_update <= 30:
            score += 0.2
        elif days_since_update <= 90:
            score += 0.15
        elif days_since_update <= 365:
            score += 0.1
        else:
            score += 0.05

        # Factor 4: Topics match (10%)
        topics = repo.get("topics", [])
        topic_keywords = topic_lower.split()
        topic_matches = sum(1 for t in topics if any(kw in t for kw in topic_keywords))
        if topics:
            score += 0.1 * (topic_matches / len(topics))

        return min(score, 1.0)  # Cap at 1.0
```

#### 2.2 GitHub Gatherer (`gathering/github_gatherer.py`)

**Purpose**: Extract findings from GitHub README with evidence binding

**Implementation**:

```python
"""GitHub README content gathering with evidence binding."""

import re
from datetime import datetime, timezone
from typing import List, Optional

import requests
from bs4 import BeautifulSoup

from ..models.evidence import Finding
from ..discovery.github_discovery import DiscoveredSource


class GitHubGatherer:
    """
    Gathers findings from GitHub repository READMEs.

    CRITICAL: ALL findings must have valid extraction_span (enforced by Part 1).
    """

    def __init__(self, llm_client):
        """
        Initialize gatherer.

        Args:
            llm_client: LLM client for extraction (must support structured output)
        """
        self.llm_client = llm_client

    async def gather_findings(
        self,
        source: DiscoveredSource,
        topic: str,
        max_findings: int = 5
    ) -> List[Finding]:
        """
        Extract findings from GitHub repository.

        Args:
            source: DiscoveredSource from GitHubDiscoveryStrategy
            topic: Research topic (for relevance filtering)
            max_findings: Maximum findings to extract

        Returns:
            List of Finding objects with REQUIRED extraction_span
        """

        # Step 1: Fetch README
        readme_content = await self._fetch_readme(source.url)
        if not readme_content:
            return []

        # Step 2: Extract findings via LLM (with REQUIRED quotes)
        findings = await self._extract_findings_from_readme(
            readme_url=source.url,
            readme_content=readme_content,
            repo_metadata=source.metadata,
            topic=topic,
            max_findings=max_findings
        )

        return findings

    async def _fetch_readme(self, repo_url: str) -> Optional[str]:
        """
        Fetch README content from GitHub repo.

        Args:
            repo_url: GitHub repo URL (e.g., "https://github.com/user/repo")

        Returns:
            README text content (or None if not found)
        """
        # Convert HTML URL to raw README URL
        # Example: https://github.com/user/repo → https://raw.githubusercontent.com/user/repo/main/README.md
        parts = repo_url.replace("https://github.com/", "").split("/")
        if len(parts) < 2:
            return None

        user, repo = parts[0], parts[1]

        # Try main/master branches
        for branch in ["main", "master"]:
            raw_url = f"https://raw.githubusercontent.com/{user}/{repo}/{branch}/README.md"
            try:
                response = requests.get(raw_url, timeout=10)
                if response.status_code == 200:
                    return response.text
            except Exception:
                continue

        return None

    async def _extract_findings_from_readme(
        self,
        readme_url: str,
        readme_content: str,
        repo_metadata: dict,
        topic: str,
        max_findings: int
    ) -> List[Finding]:
        """
        Extract findings from README using LLM.

        CRITICAL: Prompt MUST require quoted spans (extraction_span).
        """

        # Build extraction prompt (MUST enforce evidence binding)
        extraction_prompt = f"""You are a research analyst extracting market intelligence findings from a GitHub repository README.

**Topic**: {topic}

**Repository Metadata**:
- Stars: {repo_metadata.get('stars', 0)}
- Forks: {repo_metadata.get('forks', 0)}
- Language: {repo_metadata.get('language', 'Unknown')}
- Last Updated: {repo_metadata.get('last_updated', 'Unknown')}

**README Content**:
{readme_content[:10000]}  # Limit to 10K chars

**CRITICAL REQUIREMENTS**:
1. Extract up to {max_findings} findings related to "{topic}"
2. For EACH finding, you MUST provide:
   - extraction_span: A direct quote from the README (minimum 20 characters)
   - title: Brief title (5-10 words)
   - content: Your interpretation/summary (1-3 sentences)
   - category: One of ["market_intelligence", "competitive_analysis", "technical_analysis"]
   - relevance_score: 0-10 (how relevant to topic)

3. **NEVER fabricate quotes**. If you cannot find a relevant quote, do not create a finding.

Return JSON array:
[
  {{
    "title": "...",
    "content": "...",
    "extraction_span": "DIRECT QUOTE FROM README (min 20 chars)",
    "category": "market_intelligence",
    "relevance_score": 8
  }},
  ...
]
"""

        # Call LLM with structured output
        response = await self.llm_client.complete(
            prompt=extraction_prompt,
            response_format="json"
        )

        # Parse response
        import json
        findings_data = json.loads(response.content)

        # Convert to Finding objects
        findings = []
        for data in findings_data[:max_findings]:
            try:
                # Create finding with evidence binding
                finding = Finding.create_with_hash(
                    category=data["category"],
                    title=data["title"],
                    content=data["content"],
                    source_url=readme_url,
                    extracted_at=datetime.now(timezone.utc),
                    extraction_span=data["extraction_span"],  # REQUIRED
                    relevance_score=data["relevance_score"],
                    recency_score=self._calculate_recency_score(repo_metadata),
                    trust_score=self._calculate_trust_score(repo_metadata)
                )

                # Validate (will raise if extraction_span is invalid)
                finding.validate()

                findings.append(finding)

            except (KeyError, ValueError) as e:
                # Skip invalid findings (missing extraction_span, too short, etc.)
                print(f"⚠️  Skipping invalid finding: {e}")
                continue

        return findings

    def _calculate_recency_score(self, metadata: dict) -> int:
        """
        Calculate recency score (0-10) based on last updated date.

        Args:
            metadata: Repo metadata with last_updated

        Returns:
            Recency score (10 = this week, 0 = >1 year)
        """
        last_updated_str = metadata.get("last_updated")
        if not last_updated_str:
            return 5

        try:
            last_updated = datetime.fromisoformat(last_updated_str.replace("Z", "+00:00"))
            days_ago = (datetime.now(timezone.utc) - last_updated).days

            if days_ago <= 7:
                return 10
            elif days_ago <= 30:
                return 9
            elif days_ago <= 90:
                return 8
            elif days_ago <= 180:
                return 7
            elif days_ago <= 365:
                return 6
            else:
                return max(0, 6 - (days_ago - 365) // 365)
        except Exception:
            return 5

    def _calculate_trust_score(self, metadata: dict) -> int:
        """
        Calculate trust score (0-3) based on repo metadata.

        Trust Tiers:
        - 0: Unverified (new repo, low activity)
        - 1: Community (>100 stars)
        - 2: Credible (>1000 stars)
        - 3: Authoritative (>10000 stars or official org)

        Args:
            metadata: Repo metadata

        Returns:
            Trust score (0-3)
        """
        stars = metadata.get("stars", 0)

        if stars >= 10000:
            return 3  # Authoritative
        elif stars >= 1000:
            return 2  # Credible
        elif stars >= 100:
            return 1  # Community
        else:
            return 0  # Unverified
```

#### 2.3 Market Attractiveness Calculator (`analysis/decision_frameworks.py`)

**Purpose**: Calculate market attractiveness score using CODE-BASED arithmetic (NOT LLM)

**Implementation**:

```python
"""Code-based decision frameworks for market analysis.

CRITICAL: Python does ALL arithmetic. LLMs ONLY extract structured data.
"""

from dataclasses import dataclass
from typing import List, Optional

from ..models.evidence import Finding


@dataclass
class ExtractedMetrics:
    """Structured data extracted from findings (BY LLM)."""

    # Market size metrics
    market_size_usd: Optional[float] = None  # Market size in USD
    growth_rate: Optional[float] = None  # Annual growth rate (0.0-1.0, e.g., 0.15 = 15%)

    # Accessibility metrics
    accessibility: Optional[int] = None  # 0-10 (how easy to enter market)

    # Competition metrics
    num_competitors: Optional[int] = None  # Number of competitors
    barriers: Optional[int] = None  # 0-10 (entry barriers)

    # Evidence
    source_findings: List[Finding] = None  # Findings used for extraction

    def is_complete(self) -> bool:
        """Check if all required metrics are present."""
        return all([
            self.market_size_usd is not None,
            self.growth_rate is not None,
            self.accessibility is not None,
            self.num_competitors is not None,
            self.barriers is not None
        ])


@dataclass
class DecisionScore:
    """Result of decision framework calculation."""

    score: Optional[float]  # Calculated score (or None if insufficient data)
    inputs: dict  # Input metrics used for calculation
    confidence: float  # Confidence in score (0.0-1.0)
    sources: List[str]  # Source URLs
    reason: Optional[str] = None  # Explanation (if score is None)


class MarketAttractivenessCalculator:
    """
    Calculate Market Attractiveness Score using code-based framework.

    Formula:
        score = (market_size * growth_rate * accessibility) / (num_competitors * barriers)

    Where:
    - market_size: USD (extracted from findings)
    - growth_rate: 0.0-1.0 (e.g., 0.15 = 15% annual growth)
    - accessibility: 0-10 (10 = very accessible, 0 = impossible to enter)
    - num_competitors: int (count of competitors)
    - barriers: 0-10 (10 = extremely high barriers, 0 = no barriers)

    HIGH score = attractive market (large, growing, accessible, low competition)
    LOW score = unattractive market (small, stagnant, hard to enter, high competition)
    """

    def __init__(self, llm_client):
        """
        Initialize calculator.

        Args:
            llm_client: LLM client for extraction ONLY (not calculation!)
        """
        self.llm_client = llm_client

    async def calculate(self, findings: List[Finding]) -> DecisionScore:
        """
        Calculate Market Attractiveness Score.

        Steps:
        1. LLM extracts structured metrics from findings (NO arithmetic)
        2. Python validates extracted data
        3. Python calculates score (deterministic arithmetic)
        4. Python calculates confidence based on source agreement

        Args:
            findings: List of findings to analyze

        Returns:
            DecisionScore with calculated score or reason for failure
        """

        # Step 1: Extract metrics via LLM (NO arithmetic!)
        extracted = await self._extract_metrics(findings)

        # Step 2: Validate
        if not extracted.is_complete():
            return DecisionScore(
                score=None,
                inputs=self._metrics_to_dict(extracted),
                confidence=0.0,
                sources=[f.source_url for f in findings],
                reason="Insufficient data: missing required metrics"
            )

        # Step 3: Python calculates (deterministic!)
        numerator = extracted.market_size_usd * extracted.growth_rate * extracted.accessibility
        denominator = max(extracted.num_competitors, 1) * max(extracted.barriers, 0.1)  # Avoid division by zero
        score = numerator / denominator

        # Step 4: Calculate confidence based on source agreement
        confidence = self._calculate_confidence(extracted)

        return DecisionScore(
            score=round(score, 2),
            inputs=self._metrics_to_dict(extracted),
            confidence=confidence,
            sources=[f.source_url for f in findings]
        )

    async def _extract_metrics(self, findings: List[Finding]) -> ExtractedMetrics:
        """
        Extract structured metrics from findings using LLM.

        CRITICAL: LLM does NO arithmetic. Only extraction.
        """

        # Build findings context
        findings_text = "\n\n".join([
            f"[Finding {i+1}] {f.title}\n{f.content}\nQuote: \"{f.extraction_span}\"\nSource: {f.source_url}"
            for i, f in enumerate(findings)
        ])

        extraction_prompt = f"""Extract market metrics from the following research findings.

**CRITICAL RULES**:
1. Extract ONLY what is explicitly stated in findings
2. Do NOT perform any calculations or arithmetic
3. Do NOT infer or estimate numbers
4. If a metric is not found, return null

**Findings**:
{findings_text}

**Extract these metrics**:
- market_size_usd: number (market size in USD, e.g., 500000000 for $500M)
- growth_rate: decimal (annual growth rate, e.g., 0.15 for 15%)
- accessibility: integer 0-10 (how easy to enter market)
- num_competitors: integer (number of competitors mentioned)
- barriers: integer 0-10 (entry barriers, 10 = very high, 0 = none)

Return JSON:
{{
  "market_size_usd": 500000000,
  "growth_rate": 0.15,
  "accessibility": 7,
  "num_competitors": 12,
  "barriers": 4
}}

If a metric is NOT found in findings, return null for that field.
"""

        response = await self.llm_client.complete(
            prompt=extraction_prompt,
            response_format="json"
        )

        # Parse response
        import json
        data = json.loads(response.content)

        return ExtractedMetrics(
            market_size_usd=data.get("market_size_usd"),
            growth_rate=data.get("growth_rate"),
            accessibility=data.get("accessibility"),
            num_competitors=data.get("num_competitors"),
            barriers=data.get("barriers"),
            source_findings=findings
        )

    def _calculate_confidence(self, extracted: ExtractedMetrics) -> float:
        """
        Calculate confidence in extracted metrics based on source agreement.

        Factors:
        - Number of sources (more = higher confidence)
        - Trust scores of sources (higher = higher confidence)
        - Consistency across sources (future enhancement)

        Returns:
            Confidence (0.0-1.0)
        """
        if not extracted.source_findings:
            return 0.0

        # Factor 1: Number of sources (60%)
        num_sources = len(extracted.source_findings)
        if num_sources >= 10:
            source_confidence = 1.0
        elif num_sources >= 5:
            source_confidence = 0.8
        elif num_sources >= 3:
            source_confidence = 0.6
        else:
            source_confidence = 0.4

        # Factor 2: Average trust score (40%)
        avg_trust = sum(f.trust_score for f in extracted.source_findings) / len(extracted.source_findings)
        trust_confidence = avg_trust / 3.0  # Normalize to 0.0-1.0

        # Weighted average
        confidence = 0.6 * source_confidence + 0.4 * trust_confidence

        return round(confidence, 2)

    def _metrics_to_dict(self, extracted: ExtractedMetrics) -> dict:
        """Convert ExtractedMetrics to dict for output."""
        return {
            "market_size_usd": extracted.market_size_usd,
            "growth_rate": extracted.growth_rate,
            "accessibility": extracted.accessibility,
            "num_competitors": extracted.num_competitors,
            "barriers": extracted.barriers
        }
```

### 3. Integration Test (End-to-End)

```python
# tests/test_end_to_end_github.py

import pytest
from datetime import datetime, timezone

from autopack.research.discovery.github_discovery import GitHubDiscoveryStrategy
from autopack.research.gathering.github_gatherer import GitHubGatherer
from autopack.research.analysis.decision_frameworks import MarketAttractivenessCalculator


@pytest.mark.asyncio
async def test_end_to_end_github_research():
    """
    End-to-end test: topic → discovery → gathering → decision score

    This is the CRITICAL validation test for Phase 0 Part 2.
    """

    # Setup
    topic = "file organization tools"
    llm_client = MockLLMClient()  # Mock for testing

    # Step 1: Discovery
    discovery = GitHubDiscoveryStrategy()
    sources = await discovery.discover_sources(
        topic=topic,
        max_results=10,
        min_stars=100
    )

    assert len(sources) > 0, "Discovery found no sources"
    print(f"✅ Discovered {len(sources)} GitHub repos")

    # Step 2: Gathering
    gatherer = GitHubGatherer(llm_client)
    all_findings = []
    for source in sources[:5]:  # Use top 5
        findings = await gatherer.gather_findings(source, topic, max_findings=3)
        all_findings.extend(findings)

    assert len(all_findings) > 0, "Gatherer extracted no findings"
    print(f"✅ Extracted {len(all_findings)} findings")

    # Validate evidence binding
    for finding in all_findings:
        finding.validate()  # Will raise if extraction_span is invalid
        assert len(finding.extraction_span) >= 20, "extraction_span too short"

    print("✅ All findings have valid evidence binding")

    # Step 3: Decision Framework
    calculator = MarketAttractivenessCalculator(llm_client)
    decision = await calculator.calculate(all_findings)

    # Validate deterministic calculation
    if decision.score is not None:
        # Recalculate manually to verify Python did arithmetic
        inputs = decision.inputs
        expected_score = (
            inputs["market_size_usd"] *
            inputs["growth_rate"] *
            inputs["accessibility"]
        ) / (
            max(inputs["num_competitors"], 1) *
            max(inputs["barriers"], 0.1)
        )

        assert abs(decision.score - expected_score) < 0.01, "Score calculation mismatch!"
        print(f"✅ Decision score: {decision.score} (deterministic)")
    else:
        print(f"⚠️  Insufficient data for score: {decision.reason}")

    # Check cost (mock, but real test should measure)
    # Target: <$5 for this end-to-end test

    print("✅ End-to-end test PASSED")
```

### 4. STOP/GO Validation Gate

After implementation, evaluate:

### ✅ GO Criteria (Proceed to Part 3)

- [ ] GitHub API integration works (5,000 req/hr limit not hit)
- [ ] Discovery finds ≥10 relevant repos for test topic
- [ ] Gatherer extracts ≥15 findings total (across 5 repos)
- [ ] All findings pass `validate()` (evidence binding enforced)
- [ ] Decision framework produces deterministic score (manual verification passes)
- [ ] Cost <$5 per topic (LLM API costs only, within budget)
- [ ] End-to-end test passes
- [ ] No critical bugs in integration tests

### ❌ STOP Criteria (Abort or Simplify)

If ANY occur:
- [ ] GitHub API rate limits block research (free tier insufficient)
- [ ] Discovery finds <5 relevant repos (low signal)
- [ ] Gatherer extracts <10 findings total (insufficient data)
- [ ] >20% of findings fail `validate()` (evidence binding not enforced)
- [ ] Decision score changes on re-run with same inputs (non-deterministic!)
- [ ] Cost >$8 per topic (exceeds budget, no room for Part 3)
- [ ] Implementation takes >40 hours (scope creep)

**If STOP**: Abort Phase 0, pivot to curated registry (simpler)

---

## Implementation Checklist

- [ ] Implement `GitHubDiscoveryStrategy` (discovery/github_discovery.py)
- [ ] Implement `GitHubGatherer` (gathering/github_gatherer.py)
- [ ] Implement `MarketAttractivenessCalculator` (analysis/decision_frameworks.py)
- [ ] Write 5-10 integration tests
- [ ] Run end-to-end test with real GitHub API
- [ ] Verify evidence binding (all findings have valid extraction_span)
- [ ] Verify deterministic calculation (manual check)
- [ ] Measure cost (<$5 target)
- [ ] Document in BUILD_HISTORY.md
- [ ] **STOP/GO Decision**: Proceed to Part 3?

---

## Cost Estimation

**Target**: <$5/topic (leaves $3 headroom for Part 3 within $8 budget)

**Breakdown**:
- GitHub API: FREE (5,000 req/hr)
- LLM extraction (10 READMEs × 3 findings each):
  - Input: ~30K tokens (10 READMEs @ 3K tokens each)
  - Output: ~3K tokens (30 findings @ 100 tokens each)
  - Cost: ~$0.50-$1.00 (depending on model)
- LLM metric extraction (1 call):
  - Input: ~2K tokens (30 findings)
  - Output: ~200 tokens (JSON metrics)
  - Cost: ~$0.05-$0.10

**Total Estimated Cost**: $0.55-$1.10/topic ✅ Well under $5 budget

---

## Related Documentation

- **Decision**: [DEC-012](../../docs/ARCHITECTURE_DECISIONS.md#DEC-012) - Code-Based Decision Frameworks
- **Build**: [BUILD-034](../../docs/BUILD_HISTORY.md#BUILD-034) - Phase 0 Research System
- **Part 1**: [Phase_0_Part_1_Evidence_Foundation.md](./Phase_0_Part_1_Evidence_Foundation.md) - Evidence binding
- **Analysis**: `C:\Users\hshk9\.claude\plans\sunny-booping-seahorse.md`

---

## Next Steps

**If GO**: Proceed to [Phase_0_Part_3_Synthesis_And_Evaluation.md](./Phase_0_Part_3_Synthesis_And_Evaluation.md)

**If STOP**: Abort Phase 0, create fallback spec for curated registry approach
