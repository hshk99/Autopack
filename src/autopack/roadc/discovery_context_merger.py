"""Discovery Context Merger for ROAD-C (IMP-DISC-001).

Merges and ranks discovery insights from GitHub, Reddit, and Web sources
to provide contextual information for phase prompt injection.
"""

import logging
from dataclasses import dataclass
from typing import List, Optional

logger = logging.getLogger(__name__)


@dataclass
class DiscoveryInsight:
    """A single discovery insight from an external source."""

    content: str
    source: str  # 'github', 'reddit', 'web'
    relevance_score: float = 0.0
    url: Optional[str] = None
    metadata: Optional[dict] = None


class DiscoveryContextMerger:
    """Merges discovery insights from multiple research sources (IMP-DISC-001).

    Combines results from GitHub, Reddit, and Web discovery modules,
    deduplicates overlapping insights, and ranks them by relevance
    to the current phase context.
    """

    def __init__(
        self,
        github_token: Optional[str] = None,
        reddit_client_id: Optional[str] = None,
        reddit_client_secret: Optional[str] = None,
    ):
        """Initialize the merger with optional API credentials.

        Args:
            github_token: GitHub API token (uses env var if not provided)
            reddit_client_id: Reddit API client ID (uses env var if not provided)
            reddit_client_secret: Reddit API secret (uses env var if not provided)
        """
        self._github_token = github_token
        self._reddit_client_id = reddit_client_id
        self._reddit_client_secret = reddit_client_secret
        self._cached_insights: List[DiscoveryInsight] = []

    def merge_sources(
        self,
        query: str,
        limit: int = 10,
        sources: Optional[List[str]] = None,
    ) -> List[DiscoveryInsight]:
        """Merge discovery results from multiple sources.

        Args:
            query: Search query for discovery
            limit: Maximum number of results per source
            sources: List of sources to query ('github', 'reddit', 'web').
                    Defaults to all sources.

        Returns:
            List of merged DiscoveryInsight objects
        """
        if sources is None:
            sources = ["github", "reddit", "web"]

        all_insights: List[DiscoveryInsight] = []

        for source in sources:
            try:
                if source == "github":
                    insights = self._fetch_github_insights(query, limit)
                elif source == "reddit":
                    insights = self._fetch_reddit_insights(query, limit)
                elif source == "web":
                    insights = self._fetch_web_insights(query, limit)
                else:
                    logger.warning(f"[DiscoveryMerger] Unknown source: {source}")
                    continue

                all_insights.extend(insights)
                logger.debug(f"[DiscoveryMerger] Retrieved {len(insights)} insights from {source}")

            except Exception as e:
                logger.warning(f"[DiscoveryMerger] Failed to fetch from {source}: {e}")
                continue

        # Deduplicate insights
        deduplicated = self.deduplicate(all_insights)

        logger.info(
            f"[DiscoveryMerger] Merged {len(deduplicated)} insights from "
            f"{len(sources)} sources (before dedup: {len(all_insights)})"
        )

        return deduplicated

    def deduplicate(self, insights: List[DiscoveryInsight]) -> List[DiscoveryInsight]:
        """Remove duplicate insights based on content similarity.

        Uses simple content normalization and comparison. Insights with
        similar content (>80% overlap) are merged, keeping the one with
        highest relevance score.

        Args:
            insights: List of insights to deduplicate

        Returns:
            Deduplicated list of insights
        """
        if not insights:
            return []

        seen_content: dict[str, DiscoveryInsight] = {}

        for insight in insights:
            # Normalize content for comparison
            normalized = self._normalize_content(insight.content)

            # Check for similar content
            is_duplicate = False
            for seen_normalized, seen_insight in seen_content.items():
                if self._content_similarity(normalized, seen_normalized) > 0.8:
                    # Keep the one with higher relevance
                    if insight.relevance_score > seen_insight.relevance_score:
                        seen_content[seen_normalized] = insight
                    is_duplicate = True
                    break

            if not is_duplicate:
                seen_content[normalized] = insight

        return list(seen_content.values())

    def rank_by_relevance(
        self,
        insights: List[DiscoveryInsight],
        context: str,
    ) -> List[str]:
        """Rank insights by relevance to the given context.

        Calculates relevance scores based on keyword overlap with the
        context and returns insights sorted by relevance, as strings
        suitable for prompt injection.

        Args:
            insights: List of insights to rank
            context: The context string (e.g., phase goal) to rank against

        Returns:
            List of insight content strings, sorted by relevance
        """
        if not insights:
            return []

        # Calculate relevance scores
        context_keywords = set(self._normalize_content(context).split())

        for insight in insights:
            insight_keywords = set(self._normalize_content(insight.content).split())
            overlap = len(context_keywords & insight_keywords)
            total = len(context_keywords | insight_keywords)

            if total > 0:
                insight.relevance_score = overlap / total
            else:
                insight.relevance_score = 0.0

        # Sort by relevance score (descending)
        ranked = sorted(insights, key=lambda x: x.relevance_score, reverse=True)

        # Return content strings with source attribution
        return [f"[{insight.source.upper()}] {insight.content[:200]}" for insight in ranked]

    def _fetch_github_insights(self, query: str, limit: int) -> List[DiscoveryInsight]:
        """Fetch insights from GitHub discovery module.

        Args:
            query: Search query
            limit: Maximum results

        Returns:
            List of DiscoveryInsight from GitHub
        """
        insights = []

        try:
            import os

            from ..research.discovery.github_discovery import GitHubDiscovery

            token = self._github_token or os.environ.get("GITHUB_TOKEN")
            if not token:
                logger.debug("[DiscoveryMerger] No GitHub token available")
                return []

            github = GitHubDiscovery(access_token=token)

            # Search issues for solutions
            issues = github.search_issues(query)
            for issue in issues[:limit]:
                insights.append(
                    DiscoveryInsight(
                        content=issue.get("title", ""),
                        source="github",
                        url=issue.get("url"),
                        metadata={"type": "issue"},
                    )
                )

            # Search code for patterns
            code_results = github.search_code(query)
            for code in code_results[:limit]:
                insights.append(
                    DiscoveryInsight(
                        content=f"Code pattern in {code.get('path', 'unknown')}",
                        source="github",
                        url=code.get("url"),
                        metadata={"type": "code", "path": code.get("path")},
                    )
                )

        except ImportError:
            logger.debug("[DiscoveryMerger] GitHub discovery module not available")
        except Exception as e:
            logger.warning(f"[DiscoveryMerger] GitHub fetch error: {e}")

        return insights

    def _fetch_reddit_insights(self, query: str, limit: int) -> List[DiscoveryInsight]:
        """Fetch insights from Reddit discovery module.

        Args:
            query: Search query
            limit: Maximum results

        Returns:
            List of DiscoveryInsight from Reddit
        """
        insights = []

        try:
            import os

            from ..research.discovery.reddit_discovery import RedditDiscovery

            client_id = self._reddit_client_id or os.environ.get("REDDIT_CLIENT_ID")
            client_secret = self._reddit_client_secret or os.environ.get("REDDIT_CLIENT_SECRET")

            if not client_id or not client_secret:
                logger.debug("[DiscoveryMerger] No Reddit credentials available")
                return []

            reddit = RedditDiscovery(
                client_id=client_id,
                client_secret=client_secret,
                user_agent="autopack-discovery/1.0",
            )

            # Search relevant subreddits for programming solutions
            subreddits = ["programming", "Python", "learnpython", "devops"]
            for subreddit in subreddits:
                try:
                    submissions = reddit.search_submissions(query, subreddit)
                    for submission in submissions[: limit // len(subreddits)]:
                        insights.append(
                            DiscoveryInsight(
                                content=submission.get("title", ""),
                                source="reddit",
                                url=submission.get("url"),
                                metadata={"subreddit": subreddit},
                            )
                        )
                except Exception:
                    continue

        except ImportError:
            logger.debug("[DiscoveryMerger] Reddit discovery module not available")
        except Exception as e:
            logger.warning(f"[DiscoveryMerger] Reddit fetch error: {e}")

        return insights

    def _fetch_web_insights(self, query: str, limit: int) -> List[DiscoveryInsight]:
        """Fetch insights from Web discovery module.

        Args:
            query: Search query
            limit: Maximum results

        Returns:
            List of DiscoveryInsight from web search
        """
        insights = []

        try:
            from ..research.discovery.web_discovery import WebDiscovery

            web = WebDiscovery()
            results = web.search_web(query)

            for result in results[:limit]:
                insights.append(
                    DiscoveryInsight(
                        content=result.get("title", ""),
                        source="web",
                        url=result.get("url"),
                    )
                )

        except ImportError:
            logger.debug("[DiscoveryMerger] Web discovery module not available")
        except Exception as e:
            logger.warning(f"[DiscoveryMerger] Web fetch error: {e}")

        return insights

    def _normalize_content(self, content: str) -> str:
        """Normalize content for comparison.

        Args:
            content: Raw content string

        Returns:
            Normalized lowercase string with extra whitespace removed
        """
        return " ".join(content.lower().split())

    def _content_similarity(self, content1: str, content2: str) -> float:
        """Calculate similarity between two content strings.

        Uses simple word overlap ratio.

        Args:
            content1: First content string (normalized)
            content2: Second content string (normalized)

        Returns:
            Similarity score between 0.0 and 1.0
        """
        words1 = set(content1.split())
        words2 = set(content2.split())

        if not words1 or not words2:
            return 0.0

        overlap = len(words1 & words2)
        total = len(words1 | words2)

        return overlap / total if total > 0 else 0.0
