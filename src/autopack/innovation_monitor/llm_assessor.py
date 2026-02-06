"""
LLM-based assessment of AI innovations.

This is the only component that uses tokens - only for top candidates.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import List, Optional

from .models import ImprovementAssessment, ScoredInnovation, SourceType

logger = logging.getLogger(__name__)


# Concise system prompt to minimize tokens
SYSTEM_PROMPT = """You assess AI innovations for Autopack (an LLM-based codebase builder).

Autopack uses:
- Qdrant/FAISS vector memory with OpenAI embeddings
- Context injection from historical data
- Self-improvement loop via telemetry
- Phase-based autonomous execution

Output JSON only. Be conservative - only estimate >10% if evidence is strong."""


# Concise user prompt template
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


class LLMAssessor:
    """
    LLM-based assessment - ONLY for top candidates after rule-based filtering.

    Optimized for minimal tokens:
    - Concise prompt (~500 tokens)
    - Structured JSON output (~100 tokens)
    - ~600 tokens per assessment
    """

    def __init__(
        self,
        improvement_threshold: float = 0.10,
        model: str = "claude-sonnet-4-20250514",
        max_tokens: int = 200,
    ):
        """
        Initialize LLM assessor.

        Args:
            improvement_threshold: Threshold for notification (default 10%)
            model: Model to use for assessment
            max_tokens: Max output tokens (keeps responses concise)
        """
        self.threshold = improvement_threshold
        self.model = model
        self.max_tokens = max_tokens
        self._client = None

    def _get_client(self):
        """Lazy-load Anthropic client."""
        if self._client is None:
            try:
                import anthropic

                self._client = anthropic.Anthropic()
            except ImportError:
                logger.error("anthropic package not installed")
                raise
        return self._client

    async def assess(
        self,
        candidates: List[ScoredInnovation],
        max_candidates: int = 10,
    ) -> List[ImprovementAssessment]:
        """
        Assess top candidates using LLM.

        Only processes top N to minimize token usage.

        Args:
            candidates: Scored innovations to assess
            max_candidates: Maximum number to assess (default 10)

        Returns:
            List of ImprovementAssessment objects
        """
        assessments = []

        for candidate in candidates[:max_candidates]:
            try:
                assessment = await self._assess_one(candidate)
                assessments.append(assessment)
            except Exception as e:
                logger.warning(f"[LLMAssessor] Failed to assess '{candidate.title[:50]}': {e}")
                # Create a minimal assessment on failure
                assessments.append(self._create_failed_assessment(candidate, str(e)))

        logger.info(
            f"[LLMAssessor] Assessed {len(assessments)} candidates, "
            f"{sum(1 for a in assessments if a.meets_threshold)} meet threshold"
        )

        return assessments

    async def _assess_one(
        self,
        candidate: ScoredInnovation,
    ) -> ImprovementAssessment:
        """Assess single innovation (~600 tokens)."""
        prompt = USER_TEMPLATE.format(
            title=candidate.raw.title,
            source=candidate.raw.source.value,
            summary=candidate.raw.body_text[:1000],  # Truncate
        )

        try:
            client = self._get_client()

            # Use sync client in async context (simpler for now)
            response = client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )

            # Extract JSON from response
            response_text = response.content[0].text
            data = self._parse_response(response_text)

            return self._create_assessment(candidate, data)

        except Exception as e:
            logger.warning(f"[LLMAssessor] API error: {e}")
            raise

    def _parse_response(self, response_text: str) -> dict:
        """Parse JSON response, handling common issues."""
        # Try to extract JSON from response
        text = response_text.strip()

        # Handle markdown code blocks
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # Try to find JSON object in response
            import re

            match = re.search(r"\{[^{}]*\}", text, re.DOTALL)
            if match:
                return json.loads(match.group())
            raise

    def _create_assessment(
        self,
        candidate: ScoredInnovation,
        data: dict,
    ) -> ImprovementAssessment:
        """Create assessment from parsed LLM response."""
        # Extract values with defaults
        capability = int(data.get("capability", 0))
        efficiency = int(data.get("efficiency", 0))
        token_efficiency = int(data.get("token_efficiency", 0))
        speed = int(data.get("speed", 0))

        # Compute overall (weighted average)
        overall = (
            capability * 0.3 + efficiency * 0.2 + token_efficiency * 0.3 + speed * 0.2
        ) / 100.0

        return ImprovementAssessment(
            innovation_id=candidate.raw.id,
            innovation_title=candidate.raw.title,
            innovation_url=candidate.raw.url,
            source=candidate.raw.source,
            capability_improvement=capability,
            efficiency_improvement=efficiency,
            token_efficiency_improvement=token_efficiency,
            speed_improvement=speed,
            overall_improvement=overall,
            meets_threshold=overall >= self.threshold,
            applicable_components=data.get("components", []),
            rationale=data.get("rationale", ""),
            implementation_effort=data.get("effort", "medium"),
            assessed_at=datetime.now(timezone.utc),
            confidence=0.7,  # Default confidence
        )

    def _create_failed_assessment(
        self,
        candidate: ScoredInnovation,
        error: str,
    ) -> ImprovementAssessment:
        """Create minimal assessment when LLM call fails."""
        return ImprovementAssessment(
            innovation_id=candidate.raw.id,
            innovation_title=candidate.raw.title,
            innovation_url=candidate.raw.url,
            source=candidate.raw.source,
            capability_improvement=0,
            efficiency_improvement=0,
            token_efficiency_improvement=0,
            speed_improvement=0,
            overall_improvement=0.0,
            meets_threshold=False,
            applicable_components=[],
            rationale=f"Assessment failed: {error}",
            implementation_effort="unknown",
            assessed_at=datetime.now(timezone.utc),
            confidence=0.0,
        )

    def assess_sync(
        self,
        candidates: List[ScoredInnovation],
        max_candidates: int = 10,
    ) -> List[ImprovementAssessment]:
        """Synchronous version of assess() for non-async contexts."""
        import asyncio

        return asyncio.run(self.assess(candidates, max_candidates))
