"""IdeaParser for Project Bootstrap (Phase 0).

Parse rough idea documents and extract distinct project specifications.
Foundation for research-to-anchor pipeline.
"""

from __future__ import annotations

import logging
import re
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class ProjectType(str, Enum):
    """Enumeration of supported project types."""

    ECOMMERCE = "ecommerce"
    TRADING = "trading"
    CONTENT = "content"
    AUTOMATION = "automation"
    OTHER = "other"


class RiskProfile(str, Enum):
    """Risk profile classification for projects."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ParsedIdea(BaseModel):
    """Parsed idea output representing a distinct project specification."""

    title: str = Field(..., description="Project title extracted from the idea")
    description: str = Field(..., description="Project description")
    raw_requirements: list[str] = Field(
        default_factory=list, description="List of raw requirements extracted"
    )
    detected_project_type: ProjectType = Field(
        default=ProjectType.OTHER, description="Detected project type"
    )
    risk_profile: RiskProfile = Field(
        default=RiskProfile.MEDIUM, description="Risk profile for the project"
    )
    dependencies: list[str] = Field(
        default_factory=list, description="External dependencies or integrations"
    )
    confidence_score: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Confidence in the parsing result"
    )
    raw_text: str = Field(default="", description="Original raw text for this idea")


# Keywords for project type detection
_PROJECT_TYPE_KEYWORDS: dict[ProjectType, list[str]] = {
    ProjectType.ECOMMERCE: [
        "e-commerce",
        "ecommerce",
        "shop",
        "store",
        "cart",
        "checkout",
        "payment",
        "product",
        "catalog",
        "inventory",
        "order",
        "shipping",
        "merchant",
        "retail",
        "sell",
        "buy",
        "purchase",
        "marketplace",
        "storefront",
    ],
    ProjectType.TRADING: [
        "trading",
        "trade",
        "stock",
        "forex",
        "crypto",
        "cryptocurrency",
        "bitcoin",
        "ethereum",
        "exchange",
        "broker",
        "portfolio",
        "investment",
        "market",
        "algorithm",
        "algo",
        "quant",
        "hedge",
        "arbitrage",
        "futures",
        "options",
        "derivatives",
    ],
    ProjectType.CONTENT: [
        "content",
        "blog",
        "article",
        "post",
        "cms",
        "publish",
        "media",
        "video",
        "audio",
        "podcast",
        "streaming",
        "social",
        "creator",
        "writer",
        "editor",
        "magazine",
        "news",
        "newsletter",
    ],
    ProjectType.AUTOMATION: [
        "automation",
        "automate",
        "bot",
        "script",
        "workflow",
        "pipeline",
        "ci/cd",
        "cron",
        "scheduler",
        "task",
        "job",
        "background",
        "batch",
        "etl",
        "integration",
        "webhook",
        "trigger",
    ],
}

# Risk profiles by project type
_DEFAULT_RISK_PROFILES: dict[ProjectType, RiskProfile] = {
    ProjectType.TRADING: RiskProfile.HIGH,  # Financial risk
    ProjectType.ECOMMERCE: RiskProfile.MEDIUM,  # Payment processing risk
    ProjectType.CONTENT: RiskProfile.LOW,  # Generally low risk
    ProjectType.AUTOMATION: RiskProfile.MEDIUM,  # Depends on what's automated
    ProjectType.OTHER: RiskProfile.MEDIUM,  # Default to medium
}

# High-risk keywords that elevate risk profile
_HIGH_RISK_KEYWORDS: list[str] = [
    "financial",
    "money",
    "payment",
    "credit card",
    "bank",
    "wallet",
    "transaction",
    "sensitive",
    "personal data",
    "pii",
    "hipaa",
    "gdpr",
    "compliance",
    "regulated",
    "api key",
    "secret",
    "credential",
    "authentication",
    "authorization",
]

# Patterns for splitting multi-project documents
_PROJECT_DELIMITER_PATTERNS: list[str] = [
    r"(?:^|\n)\s*#{1,3}\s+(?:Project|Idea)\s*[:\-]?\s*",  # ## Project: or ### Idea -
    r"(?:^|\n)\s*\d+\.\s+(?:Project|Idea)\s*[:\-]?\s*",  # 1. Project: or 2. Idea -
    r"(?:^|\n)\s*(?:Project|Idea)\s+\d+\s*[:\-]?\s*",  # Project 1: or Idea 2 -
    r"(?:^|\n)\s*---+\s*(?:\n|$)",  # Horizontal rule separator
    r"(?:^|\n)\s*\*{3,}\s*(?:\n|$)",  # Asterisk separator
]


class IdeaParser:
    """Parser for extracting project specifications from idea documents.

    Supports parsing multi-project documents and extracting distinct
    ParsedIdea objects with project type detection and risk profiling.
    """

    def __init__(
        self,
        llm_fallback_enabled: bool = True,
        confidence_threshold: float = 0.7,
    ):
        """Initialize the IdeaParser.

        Args:
            llm_fallback_enabled: Whether to use LLM for ambiguous cases
            confidence_threshold: Minimum confidence for regex parsing
        """
        self.llm_fallback_enabled = llm_fallback_enabled
        self.confidence_threshold = confidence_threshold

    def parse(self, raw_text: str) -> list[ParsedIdea]:
        """Parse raw idea text into list of ParsedIdea objects.

        First attempts regex-based extraction. Falls back to LLM
        if confidence is below threshold and LLM fallback is enabled.

        Args:
            raw_text: Raw unstructured idea document text

        Returns:
            List of ParsedIdea objects, one per distinct project
        """
        if not raw_text or not raw_text.strip():
            logger.warning("Empty raw_text provided to IdeaParser")
            return []

        # Split into potential separate project sections
        sections = self._split_into_sections(raw_text)

        ideas: list[ParsedIdea] = []
        for section in sections:
            idea = self._parse_section(section)
            if idea:
                # Check if LLM fallback is needed
                if idea.confidence_score < self.confidence_threshold and self.llm_fallback_enabled:
                    enhanced_idea = self._llm_enhance(idea)
                    if enhanced_idea:
                        idea = enhanced_idea

                ideas.append(idea)

        logger.info(f"[IdeaParser] Parsed {len(ideas)} ideas from document")
        return ideas

    def parse_single(self, raw_text: str) -> Optional[ParsedIdea]:
        """Parse a single idea from text.

        Convenience method for when only one project is expected.

        Args:
            raw_text: Raw idea text for a single project

        Returns:
            ParsedIdea or None if parsing fails
        """
        ideas = self.parse(raw_text)
        return ideas[0] if ideas else None

    def _split_into_sections(self, raw_text: str) -> list[str]:
        """Split document into separate project sections.

        Args:
            raw_text: Full document text

        Returns:
            List of section strings
        """
        # Try each delimiter pattern
        for pattern in _PROJECT_DELIMITER_PATTERNS:
            parts = re.split(pattern, raw_text, flags=re.IGNORECASE)
            # Filter out empty parts
            parts = [p.strip() for p in parts if p and p.strip()]
            if len(parts) > 1:
                logger.debug(f"Split document into {len(parts)} sections using pattern: {pattern}")
                return parts

        # No delimiters found, treat as single project
        return [raw_text.strip()]

    def _parse_section(self, section: str) -> Optional[ParsedIdea]:
        """Parse a single section into a ParsedIdea.

        Args:
            section: Section text to parse

        Returns:
            ParsedIdea or None if parsing fails
        """
        if not section.strip():
            return None

        # Extract title (first line or heading)
        title = self._extract_title(section)

        # Extract description (first paragraph after title)
        description = self._extract_description(section, title)

        # Extract requirements
        requirements = self._extract_requirements(section)

        # Detect project type
        project_type, type_confidence = self._detect_project_type(section)

        # Determine risk profile
        risk_profile = self._determine_risk_profile(section, project_type)

        # Extract dependencies
        dependencies = self._extract_dependencies(section)

        # Calculate overall confidence
        confidence = self._calculate_confidence(
            title=title,
            description=description,
            requirements=requirements,
            type_confidence=type_confidence,
        )

        return ParsedIdea(
            title=title,
            description=description,
            raw_requirements=requirements,
            detected_project_type=project_type,
            risk_profile=risk_profile,
            dependencies=dependencies,
            confidence_score=confidence,
            raw_text=section,
        )

    def _extract_title(self, section: str) -> str:
        """Extract project title from section.

        Args:
            section: Section text

        Returns:
            Extracted title or default
        """
        lines = section.strip().split("\n")

        for line in lines[:3]:  # Check first 3 lines
            line = line.strip()
            # Skip empty lines
            if not line:
                continue

            # Remove markdown heading markers
            if line.startswith("#"):
                line = re.sub(r"^#+\s*", "", line)

            # Remove common prefixes
            line = re.sub(r"^(?:Project|Idea|Title)\s*[:\-]\s*", "", line, flags=re.IGNORECASE)

            if line and len(line) < 200:  # Reasonable title length
                return line.strip()

        # Fallback: use first 50 chars of content
        clean_text = re.sub(r"\s+", " ", section).strip()
        return clean_text[:50] + "..." if len(clean_text) > 50 else clean_text

    def _extract_description(self, section: str, title: str) -> str:
        """Extract project description from section.

        Args:
            section: Section text
            title: Already extracted title

        Returns:
            Extracted description
        """
        # Remove title from section
        remaining = section.replace(title, "", 1).strip()

        # Find first paragraph
        paragraphs = re.split(r"\n\s*\n", remaining)

        for para in paragraphs:
            para = para.strip()
            # Skip empty or very short paragraphs
            if len(para) < 20:
                continue
            # Skip lines that look like list items or requirements
            if re.match(r"^[-*\d]", para):
                continue

            # Clean up the paragraph
            para = re.sub(r"\s+", " ", para)
            return para[:500]  # Limit description length

        # Fallback to remaining content
        clean = re.sub(r"\s+", " ", remaining).strip()
        return clean[:500] if clean else "No description provided"

    def _extract_requirements(self, section: str) -> list[str]:
        """Extract requirements from section.

        Args:
            section: Section text

        Returns:
            List of requirement strings
        """
        requirements: list[str] = []

        # Look for bullet points (allow leading whitespace)
        bullet_pattern = r"^\s*[-*]\s+(.+?)$"
        for match in re.finditer(bullet_pattern, section, re.MULTILINE):
            req = match.group(1).strip()
            if req and len(req) > 5:  # Skip very short items
                requirements.append(req)

        # Look for numbered lists (allow leading whitespace)
        numbered_pattern = r"^\s*\d+[.)]\s+(.+?)$"
        for match in re.finditer(numbered_pattern, section, re.MULTILINE):
            req = match.group(1).strip()
            if req and len(req) > 5:
                requirements.append(req)

        # Look for "must", "should", "need to" patterns
        modal_pattern = r"(?:must|should|need to|has to|require[sd]?)\s+(.+?)(?:\.|$)"
        for match in re.finditer(modal_pattern, section, re.IGNORECASE):
            req = match.group(1).strip()
            if req and len(req) > 5 and req not in requirements:
                requirements.append(req)

        # Deduplicate while preserving order
        seen: set[str] = set()
        unique_requirements: list[str] = []
        for req in requirements:
            req_lower = req.lower()
            if req_lower not in seen:
                seen.add(req_lower)
                unique_requirements.append(req)

        return unique_requirements

    def _detect_project_type(self, section: str) -> tuple[ProjectType, float]:
        """Detect project type from section content.

        Args:
            section: Section text

        Returns:
            Tuple of (ProjectType, confidence_score)
        """
        section_lower = section.lower()
        type_scores: dict[ProjectType, int] = {}

        for project_type, keywords in _PROJECT_TYPE_KEYWORDS.items():
            score = 0
            for keyword in keywords:
                if keyword in section_lower:
                    score += 1
            if score > 0:
                type_scores[project_type] = score

        if not type_scores:
            return ProjectType.OTHER, 0.5

        # Get type with highest score
        best_type = max(type_scores, key=lambda t: type_scores[t])
        best_score = type_scores[best_type]

        # Calculate confidence based on keyword matches
        total_keywords = len(_PROJECT_TYPE_KEYWORDS[best_type])
        confidence = min(0.95, 0.5 + (best_score / total_keywords) * 0.5)

        return best_type, confidence

    def _determine_risk_profile(self, section: str, project_type: ProjectType) -> RiskProfile:
        """Determine risk profile for the project.

        Args:
            section: Section text
            project_type: Detected project type

        Returns:
            RiskProfile
        """
        section_lower = section.lower()

        # Check for high-risk keywords
        high_risk_count = sum(1 for kw in _HIGH_RISK_KEYWORDS if kw in section_lower)

        if high_risk_count >= 3:
            return RiskProfile.HIGH

        # Use default for project type
        base_risk = _DEFAULT_RISK_PROFILES.get(project_type, RiskProfile.MEDIUM)

        # Elevate risk if any high-risk keywords found
        if high_risk_count >= 1 and base_risk == RiskProfile.LOW:
            return RiskProfile.MEDIUM

        return base_risk

    def _extract_dependencies(self, section: str) -> list[str]:
        """Extract external dependencies from section.

        Args:
            section: Section text

        Returns:
            List of dependency strings
        """
        dependencies: list[str] = []

        # Look for common dependency patterns
        patterns = [
            r"(?:integrate|integration)\s+(?:with\s+)?([A-Za-z0-9\-_\.]+)",
            r"(?:use|using)\s+([A-Za-z0-9\-_\.]+(?:\s+API)?)",
            r"([A-Za-z0-9\-_\.]+)\s+(?:API|SDK|library|package)",
            r"connect(?:ion)?\s+(?:to\s+)?([A-Za-z0-9\-_\.]+)",
        ]

        for pattern in patterns:
            for match in re.finditer(pattern, section, re.IGNORECASE):
                dep = match.group(1).strip()
                # Filter out common words
                if dep.lower() not in ["the", "a", "an", "this", "that", "with", "for"]:
                    if dep not in dependencies:
                        dependencies.append(dep)

        return dependencies

    def _calculate_confidence(
        self,
        title: str,
        description: str,
        requirements: list[str],
        type_confidence: float,
    ) -> float:
        """Calculate overall parsing confidence.

        Args:
            title: Extracted title
            description: Extracted description
            requirements: Extracted requirements
            type_confidence: Confidence in project type detection

        Returns:
            Confidence score between 0 and 1
        """
        scores: list[float] = []

        # Title quality (not default/generic)
        if title and not title.endswith("...") and len(title) > 10:
            scores.append(0.9)
        elif title:
            scores.append(0.6)
        else:
            scores.append(0.2)

        # Description quality
        if description and len(description) > 50:
            scores.append(0.9)
        elif description:
            scores.append(0.6)
        else:
            scores.append(0.3)

        # Requirements extraction
        if len(requirements) >= 3:
            scores.append(0.9)
        elif len(requirements) >= 1:
            scores.append(0.7)
        else:
            scores.append(0.4)

        # Type detection confidence
        scores.append(type_confidence)

        return sum(scores) / len(scores) if scores else 0.5

    def _llm_enhance(self, idea: ParsedIdea) -> Optional[ParsedIdea]:
        """Use LLM to enhance parsing for ambiguous cases.

        Args:
            idea: Partially parsed idea

        Returns:
            Enhanced ParsedIdea or None if LLM fails
        """
        # Placeholder for LLM integration
        # In production, this would call an LLM to:
        # 1. Better extract title/description
        # 2. More accurately classify project type
        # 3. Extract additional requirements
        # 4. Identify dependencies
        logger.debug(f"LLM enhancement requested for idea: {idea.title}")
        # For now, return None to indicate no enhancement
        # Future: integrate with autopack LLM infrastructure
        return None

    def get_supported_project_types(self) -> list[ProjectType]:
        """Get list of supported project types.

        Returns:
            List of ProjectType enum values
        """
        return list(ProjectType)

    def get_risk_profile_for_type(self, project_type: ProjectType) -> RiskProfile:
        """Get default risk profile for a project type.

        Args:
            project_type: Project type to query

        Returns:
            Default RiskProfile for the type
        """
        return _DEFAULT_RISK_PROFILES.get(project_type, RiskProfile.MEDIUM)
