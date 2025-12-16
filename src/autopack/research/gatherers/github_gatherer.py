"""
GitHub repository gatherer for research system.

Discovers repositories by topic and extracts findings from README files
using the GitHub API and Claude for intelligent extraction.
"""

import base64
import hashlib
import json
import logging
import os
import re
from typing import Dict, List, Optional

import anthropic
import requests

from src.autopack.research.models.validators import Finding

logger = logging.getLogger(__name__)


class GitHubGatherer:
    """Gathers research findings from GitHub repositories."""

    GITHUB_API_BASE = "https://api.github.com"

    def __init__(self, github_token: Optional[str] = None):
        """
        Initialize the GitHub gatherer.

        Args:
            github_token: Optional GitHub personal access token for higher rate limits.
                         Falls back to GITHUB_TOKEN environment variable.
        """
        self.github_token = github_token or os.getenv("GITHUB_TOKEN")
        self.headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "Autopack-Research-Gatherer",
        }
        if self.github_token:
            self.headers["Authorization"] = f"token {self.github_token}"

        # Initialize Anthropic client for finding extraction
        self.anthropic_client = anthropic.Anthropic()

    def discover_repositories(self, topic: str, max_repos: int = 10) -> List[Dict]:
        """
        Discover repositories related to a topic.

        Args:
            topic: Search topic/query for repositories.
            max_repos: Maximum number of repositories to return.

        Returns:
            List of repository metadata dictionaries.
        """
        url = f"{self.GITHUB_API_BASE}/search/repositories"
        params = {
            "q": topic,
            "sort": "stars",
            "order": "desc",
            "per_page": min(max_repos, 100),
        }

        try:
            response = requests.get(url, headers=self.headers, params=params, timeout=30)

            # Handle rate limiting
            if response.status_code == 403:
                remaining = response.headers.get("X-RateLimit-Remaining", "unknown")
                logger.warning(f"GitHub API rate limit hit. Remaining: {remaining}")
                return []

            response.raise_for_status()
            data = response.json()

            repositories = []
            for item in data.get("items", [])[:max_repos]:
                repositories.append({
                    "full_name": item.get("full_name"),
                    "description": item.get("description"),
                    "stars": item.get("stargazers_count"),
                    "url": item.get("html_url"),
                    "topics": item.get("topics", []),
                })

            return repositories

        except requests.RequestException as e:
            logger.error(f"Error discovering repositories for topic '{topic}': {e}")
            return []

    def fetch_readme(self, repo_full_name: str) -> str:
        """
        Fetch the README content for a repository.

        Args:
            repo_full_name: Full repository name (owner/repo).

        Returns:
            README content as string, or empty string if not found.
        """
        url = f"{self.GITHUB_API_BASE}/repos/{repo_full_name}/readme"

        try:
            response = requests.get(url, headers=self.headers, timeout=30)

            # Handle rate limiting
            if response.status_code == 403:
                remaining = response.headers.get("X-RateLimit-Remaining", "unknown")
                logger.warning(f"GitHub API rate limit hit. Remaining: {remaining}")
                return ""

            if response.status_code == 404:
                logger.info(f"No README found for {repo_full_name}")
                return ""

            response.raise_for_status()
            data = response.json()

            # README content is base64 encoded
            content = data.get("content", "")
            if content:
                return base64.b64decode(content).decode("utf-8")
            return ""

        except requests.RequestException as e:
            logger.error(f"Error fetching README for {repo_full_name}: {e}")
            return ""

    def extract_findings(
        self, readme_content: str, topic: str, max_findings: int = 5
    ) -> List[Finding]:
        """
        Extract research findings from README content using Claude.

        Args:
            readme_content: The README content to analyze.
            topic: The research topic for context.
            max_findings: Maximum number of findings to extract.

        Returns:
            List of Finding objects extracted from the content.
        """
        if not readme_content or len(readme_content) < 50:
            return []

        # Generate source hash for findings
        source_hash = hashlib.sha256(readme_content.encode()).hexdigest()[:16]

        prompt = f"""Analyze this README and extract up to {max_findings} research findings related to "{topic}".
For each finding, provide:
- title: Brief descriptive title
- content: Your interpretation and analysis of the finding
- extraction_span: A CHARACTER-FOR-CHARACTER exact quote from the README (minimum 20 characters)
- category: One of "market_intelligence", "competitive_analysis", or "technical_analysis"
- relevance_score: Float between 0.0 and 1.0
CRITICAL REQUIREMENTS FOR extraction_span:
- extraction_span MUST be a DIRECT, VERBATIM quote copied exactly from the README
- Do NOT paraphrase, summarize, or modify the text in any way
- The extraction_span is the SOURCE EVIDENCE; content is YOUR interpretation
EXAMPLES:
- GOOD extraction_span: "The library has been downloaded over 10 million times and is used by 500+ companies"
- BAD extraction_span: "Downloaded millions of times by many companies" (this is paraphrased!)
For market_intelligence and competitive_analysis categories:
- extraction_span MUST contain specific numbers, statistics, or metrics
- Examples: user counts, download numbers, market share percentages, revenue figures
Return a JSON array of findings:
[
  {{
    "title": "string",
    "content": "string",
    "extraction_span": "exact quote from README",
    "category": "market_intelligence|competitive_analysis|technical_analysis",
    "relevance_score": 0.0-1.0
  }}
]
README CONTENT:
{readme_content[:8000]}"""
        try:
            response = self.anthropic_client.messages.create(
                model="claude-sonnet-4-5",
                max_tokens=2000,
                messages=[{"role": "user", "content": prompt}],
            )

            response_text = response.content[0].text

            # Parse JSON response
            findings_data = self._parse_json_response(response_text)

            # Convert to Finding objects
            findings = []
            for item in findings_data[:max_findings]:
                try:
                    finding = Finding(
                        title=item.get("title", "Untitled"),
                        content=item.get("content", ""),
                        extraction_span=item.get("extraction_span", ""),
                        category=item.get("category", "technical_analysis"),
                        relevance_score=float(item.get("relevance_score", 0.5)),
                        source_hash=source_hash,
                    )
                    findings.append(finding)
                except Exception as e:
                    logger.warning(f"Failed to create Finding object: {e}")
                    continue

            return findings

        except Exception as e:
            logger.error(f"Error extracting findings: {e}")
            return []

    def _parse_json_response(self, response_text: str) -> List[Dict]:
        """
        Parse JSON from LLM response, handling markdown code blocks.

        Args:
            response_text: Raw response text from LLM.

        Returns:
            Parsed list of finding dictionaries.
        """
        # Try direct JSON parsing first
        try:
            return json.loads(response_text)
        except json.JSONDecodeError:
            pass

        # Try extracting from markdown code block
        pattern = r"```json\n(.+?)\n```"
        match = re.search(pattern, response_text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError as e:
                logger.warning(f"Failed to parse JSON from markdown block: {e}")

        # Try extracting any JSON array
        array_pattern = r"\[[\s\S]*\]"
        match = re.search(array_pattern, response_text)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError as e:
                logger.warning(f"Failed to parse JSON array: {e}")

        logger.warning("Could not parse any JSON from response")
        return []
