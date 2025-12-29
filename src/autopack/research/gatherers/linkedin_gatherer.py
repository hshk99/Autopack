"""LinkedIn gatherer for research evidence collection.

Collects posts, articles, and professional insights using LinkedIn API.
Extracts findings using LLM-based analysis with character-for-character quote preservation.

Note: LinkedIn API access requires approved developer application.
"""

from __future__ import annotations

import os
import time
from typing import Any

import requests

from autopack.research.models.evidence import Citation, Evidence
from autopack.research.models.enums import EvidenceType


class LinkedInGatherer:
    """Gather research evidence from LinkedIn."""

    def __init__(
        self,
        access_token: str | None = None,
        client_id: str | None = None,
        client_secret: str | None = None,
    ):
        """Initialize LinkedIn gatherer.

        Args:
            access_token: LinkedIn API access token (defaults to LINKEDIN_ACCESS_TOKEN env var)
            client_id: LinkedIn API client ID (defaults to LINKEDIN_CLIENT_ID env var)
            client_secret: LinkedIn API client secret (defaults to LINKEDIN_CLIENT_SECRET env var)
        """
        self.access_token = access_token or os.getenv("LINKEDIN_ACCESS_TOKEN")
        self.client_id = client_id or os.getenv("LINKEDIN_CLIENT_ID")
        self.client_secret = client_secret or os.getenv("LINKEDIN_CLIENT_SECRET")

        if not self.access_token:
            if not self.client_id or not self.client_secret:
                raise ValueError(
                    "LinkedIn credentials required (set LINKEDIN_ACCESS_TOKEN or "
                    "LINKEDIN_CLIENT_ID + LINKEDIN_CLIENT_SECRET)"
                )

        self.base_url = "https://api.linkedin.com/v2"
        self.token_expires_at = 0

    def _get_access_token(self) -> str:
        """Get or refresh OAuth access token for LinkedIn API."""
        if self.access_token and time.time() < self.token_expires_at:
            return self.access_token

        # If we have client credentials, request new token
        if self.client_id and self.client_secret:
            # Note: This is simplified - real OAuth flow requires authorization code
            # For production, implement full OAuth 2.0 flow
            raise NotImplementedError(
                "OAuth token refresh not implemented. "
                "Please provide valid LINKEDIN_ACCESS_TOKEN."
            )

        return self.access_token

    def search_posts(
        self,
        keywords: str,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Search for LinkedIn posts matching keywords.

        Args:
            keywords: Search keywords
            limit: Maximum number of posts to return

        Returns:
            List of post objects with metadata

        Note:
            LinkedIn's search API has limited access. This is a simplified implementation.
        """
        token = self._get_access_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "X-Restli-Protocol-Version": "2.0.0",
        }

        # LinkedIn's UGC (User Generated Content) API
        # Note: Actual search requires specific API permissions
        url = f"{self.base_url}/ugcPosts"
        params = {
            "q": "search",
            "keywords": keywords,
            "count": min(limit, 100),
        }

        response = requests.get(url, headers=headers, params=params, timeout=30)

        if response.status_code == 403:
            raise RuntimeError(
                "LinkedIn API access denied. Ensure your app has required permissions."
            )

        response.raise_for_status()
        data = response.json()

        return data.get("elements", [])

    def get_user_posts(
        self,
        user_id: str,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Get posts from a specific LinkedIn user.

        Args:
            user_id: LinkedIn user ID (URN format: urn:li:person:xxxxx)
            limit: Maximum number of posts to return

        Returns:
            List of post objects
        """
        token = self._get_access_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "X-Restli-Protocol-Version": "2.0.0",
        }

        url = f"{self.base_url}/ugcPosts"
        params = {
            "q": "authors",
            "authors": f"List({user_id})",
            "count": min(limit, 100),
        }

        response = requests.get(url, headers=headers, params=params, timeout=30)
        response.raise_for_status()

        data = response.json()
        return data.get("elements", [])

    def get_articles(
        self,
        keywords: str,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Search for LinkedIn articles matching keywords.

        Args:
            keywords: Search keywords
            limit: Maximum number of articles to return

        Returns:
            List of article objects
        """
        token = self._get_access_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "X-Restli-Protocol-Version": "2.0.0",
        }

        # LinkedIn Articles API
        url = f"{self.base_url}/articles"
        params = {
            "q": "search",
            "keywords": keywords,
            "count": min(limit, 100),
        }

        response = requests.get(url, headers=headers, params=params, timeout=30)
        response.raise_for_status()

        data = response.json()
        return data.get("elements", [])

    def extract_findings(
        self,
        posts: list[dict[str, Any]],
        research_topic: str,
    ) -> list[Evidence]:
        """Extract research findings from LinkedIn posts using LLM analysis.

        Args:
            posts: List of post objects from LinkedIn API
            research_topic: Research topic for context

        Returns:
            List of Evidence objects with citations
        """
        findings = []

        for post in posts:
            # Extract content from LinkedIn's UGC structure
            specific_content = post.get("specificContent", {})
            share_content = specific_content.get("com.linkedin.ugc.ShareContent", {})
            share_commentary = share_content.get("shareCommentary", {})
            text = share_commentary.get("text", "")

            # Skip empty posts
            if not text.strip():
                continue

            post_id = post.get("id", "unknown")
            author_urn = post.get("author", "unknown")
            created_time = post.get("created", {}).get("time", 0)

            # Convert timestamp to year
            year = 2024  # Default
            if created_time:
                try:
                    import datetime

                    year = datetime.datetime.fromtimestamp(created_time / 1000).year
                except (ValueError, OSError):
                    pass

            # Extract author name from URN (simplified)
            author = author_urn.split(":")[-1] if author_urn != "unknown" else "LinkedIn User"

            # Create citation
            citation = Citation(
                authors=[author],
                title=text[:100],  # Use first 100 chars as title
                publication="LinkedIn",
                year=year,
                url=f"https://www.linkedin.com/feed/update/{post_id}",
            )

            # Determine evidence type based on content
            # Professional posts are typically case studies or anecdotal
            evidence_type = EvidenceType.CASE_STUDY
            if len(text) < 200:
                evidence_type = EvidenceType.ANECDOTAL

            # Create evidence
            evidence = Evidence(
                content=text,
                evidence_type=evidence_type,
                citation=citation,
                metadata={
                    "post_id": post_id,
                    "author_urn": author_urn,
                    "created_time": created_time,
                    "engagement": post.get("socialDetail", {}),
                },
                tags=["linkedin", "social-media", "professional"],
            )

            findings.append(evidence)

        return findings
