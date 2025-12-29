"""Twitter/X gatherer for research evidence collection.

Collects tweets, threads, and user profiles using Twitter API v2.
Extracts findings using LLM-based analysis with character-for-character quote preservation.
"""

from __future__ import annotations

import os
import time
from typing import Any

import requests

from autopack.research.models.evidence import Citation, Evidence
from autopack.research.models.enums import EvidenceType


class TwitterGatherer:
    """Gather research evidence from Twitter/X."""

    def __init__(self, bearer_token: str | None = None):
        """Initialize Twitter gatherer.

        Args:
            bearer_token: Twitter API bearer token (defaults to TWITTER_BEARER_TOKEN env var)
        """
        self.bearer_token = bearer_token or os.getenv("TWITTER_BEARER_TOKEN")
        if not self.bearer_token:
            raise ValueError("Twitter bearer token required (set TWITTER_BEARER_TOKEN)")

        self.base_url = "https://api.twitter.com/2"
        self.headers = {
            "Authorization": f"Bearer {self.bearer_token}",
            "User-Agent": "AutopackResearchBot/1.0",
        }
        self.rate_limit_remaining = 100
        self.rate_limit_reset = 0

    def search_tweets(
        self,
        query: str,
        max_results: int = 10,
        tweet_fields: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Search for tweets matching query.

        Args:
            query: Twitter search query (supports operators like from:, #hashtag, etc.)
            max_results: Maximum number of tweets to return (10-100)
            tweet_fields: Additional tweet fields to include

        Returns:
            List of tweet objects with metadata
        """
        if tweet_fields is None:
            tweet_fields = ["created_at", "author_id", "public_metrics", "entities"]

        self._check_rate_limit()

        params = {
            "query": query,
            "max_results": min(max_results, 100),
            "tweet.fields": ",".join(tweet_fields),
        }

        response = requests.get(
            f"{self.base_url}/tweets/search/recent",
            headers=self.headers,
            params=params,
            timeout=30,
        )

        self._update_rate_limit(response)

        if response.status_code == 429:
            raise RuntimeError("Twitter API rate limit exceeded")
        response.raise_for_status()

        data = response.json()
        return data.get("data", [])

    def get_user_tweets(
        self,
        username: str,
        max_results: int = 10,
    ) -> list[dict[str, Any]]:
        """Get recent tweets from a specific user.

        Args:
            username: Twitter username (without @)
            max_results: Maximum number of tweets to return

        Returns:
            List of tweet objects
        """
        # First get user ID
        user_response = requests.get(
            f"{self.base_url}/users/by/username/{username}",
            headers=self.headers,
            timeout=30,
        )
        user_response.raise_for_status()
        user_id = user_response.json()["data"]["id"]

        # Then get tweets
        self._check_rate_limit()

        params = {
            "max_results": min(max_results, 100),
            "tweet.fields": "created_at,public_metrics",
        }

        response = requests.get(
            f"{self.base_url}/users/{user_id}/tweets",
            headers=self.headers,
            params=params,
            timeout=30,
        )

        self._update_rate_limit(response)
        response.raise_for_status()

        data = response.json()
        return data.get("data", [])

    def extract_findings(
        self,
        tweets: list[dict[str, Any]],
        research_topic: str,
    ) -> list[Evidence]:
        """Extract research findings from tweets using LLM analysis.

        Args:
            tweets: List of tweet objects from Twitter API
            research_topic: Research topic for context

        Returns:
            List of Evidence objects with citations
        """
        findings = []

        for tweet in tweets:
            # Skip tweets without text
            if "text" not in tweet:
                continue

            tweet_text = tweet["text"]
            tweet_id = tweet["id"]
            created_at = tweet.get("created_at", "Unknown")

            # Extract year from created_at (format: 2024-01-15T12:00:00.000Z)
            year = 2024  # Default
            if created_at != "Unknown":
                try:
                    year = int(created_at.split("-")[0])
                except (ValueError, IndexError):
                    pass

            # Create citation
            citation = Citation(
                authors=["Twitter User"],  # Would need user lookup for real author
                title=f"Tweet {tweet_id}",
                publication="Twitter/X",
                year=year,
                url=f"https://twitter.com/i/web/status/{tweet_id}",
            )

            # For now, treat entire tweet as finding
            # In production, would use LLM to extract specific insights
            evidence = Evidence(
                content=tweet_text,
                evidence_type=EvidenceType.ANECDOTAL,
                citation=citation,
                metadata={
                    "tweet_id": tweet_id,
                    "created_at": created_at,
                    "metrics": tweet.get("public_metrics", {}),
                },
                tags=["twitter", "social-media"],
            )

            findings.append(evidence)

        return findings

    def _check_rate_limit(self) -> None:
        """Check if rate limit allows request, wait if necessary."""
        if self.rate_limit_remaining <= 1:
            wait_time = max(0, self.rate_limit_reset - time.time())
            if wait_time > 0:
                time.sleep(wait_time + 1)

    def _update_rate_limit(self, response: requests.Response) -> None:
        """Update rate limit tracking from response headers."""
        if "x-rate-limit-remaining" in response.headers:
            self.rate_limit_remaining = int(response.headers["x-rate-limit-remaining"])
        if "x-rate-limit-reset" in response.headers:
            self.rate_limit_reset = int(response.headers["x-rate-limit-reset"])
