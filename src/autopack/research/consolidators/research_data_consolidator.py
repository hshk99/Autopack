"""Research Data Consolidator

This module consolidates research findings through a multi-stage sanitization pipeline:
1. Content sanitization (removes dangerous patterns)
2. Prompt injection prevention (escapes LLM-unsafe content)
3. Deduplication (fuzzy matching to remove similar findings)
4. Categorization (organizes findings by type)
5. Citation preservation (maintains source attribution)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

from autopack.research.security.content_sanitizer import ContentSanitizer
from autopack.research.security.prompt_sanitizer import PromptSanitizer, RiskLevel
from autopack.research.agents.compilation_agent import CompilationAgent

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ConsolidatedFinding:
    """Represents a consolidated research finding with sanitization applied."""

    type: str
    content: str
    original_content: str
    source_url: Optional[str] = None
    trust_tier: Optional[int] = None
    extracted_at: Optional[str] = None
    is_sanitized: bool = False
    sanitization_flags: List[str] = field(default_factory=list)


@dataclass
class ConsolidationResult:
    """Result of research data consolidation."""

    consolidated_findings: List[ConsolidatedFinding]
    original_count: int
    deduplicated_count: int
    categorized_findings: Dict[str, List[ConsolidatedFinding]]
    sanitization_summary: Dict[str, Any] = field(default_factory=dict)
    processing_time_ms: float = 0.0


class ResearchDataConsolidator:
    """Consolidates research findings through sanitization and deduplication.

    This class orchestrates the research data consolidation pipeline:
    - Sanitizes content for dangerous patterns (malware, phishing, etc.)
    - Prevents LLM prompt injection attacks
    - Deduplicates findings using fuzzy matching
    - Categorizes findings by type
    - Preserves source citations

    Example:
        >>> consolidator = ResearchDataConsolidator()
        >>> findings = [
        ...     {"type": "web", "content": "API latency concerns", "source_url": "..."},
        ...     {"type": "web", "content": "API latency issues", "source_url": "..."},
        ... ]
        >>> result = consolidator.consolidate(findings)
        >>> print(f"Consolidated {result.deduplicated_count} findings from {result.original_count}")
    """

    # Default deduplication threshold (80% similarity)
    DEFAULT_DEDUP_THRESHOLD = 80

    # Categorization keywords for research findings
    CATEGORY_KEYWORDS = {
        "technical": ["latency", "architecture", "api", "database", "scalability", "performance"],
        "ux": ["ux", "user experience", "onboarding", "ui", "workflow", "usability"],
        "market": ["market", "pricing", "demand", "segment", "opportunity"],
        "competition": ["competitor", "competitive", "alternative", "market share"],
    }

    def __init__(
        self,
        dedup_threshold: int = DEFAULT_DEDUP_THRESHOLD,
        content_sanitizer: Optional[ContentSanitizer] = None,
        prompt_sanitizer: Optional[PromptSanitizer] = None,
        compilation_agent: Optional[CompilationAgent] = None,
    ):
        """Initialize the research data consolidator.

        Args:
            dedup_threshold: Fuzzy matching threshold for deduplication (0-100)
            content_sanitizer: ContentSanitizer instance for dangerous pattern detection
            prompt_sanitizer: PromptSanitizer instance for LLM injection prevention
            compilation_agent: CompilationAgent instance for categorization and deduplication
        """
        self.dedup_threshold = dedup_threshold
        self.content_sanitizer = content_sanitizer or ContentSanitizer()
        self.prompt_sanitizer = prompt_sanitizer or PromptSanitizer()
        self.compilation_agent = compilation_agent or CompilationAgent()

    def consolidate(
        self,
        findings: Iterable[Mapping[str, Any]],
        apply_deduplication: bool = True,
        apply_categorization: bool = True,
    ) -> ConsolidationResult:
        """Consolidate research findings through sanitization pipeline.

        Args:
            findings: Iterable of finding dictionaries to consolidate
            apply_deduplication: Whether to deduplicate findings
            apply_categorization: Whether to categorize findings

        Returns:
            ConsolidationResult with consolidated findings and metadata
        """
        import time

        start_time = time.time()

        # Convert findings to list for processing
        findings_list = [dict(f) for f in findings]
        original_count = len(findings_list)

        logger.debug(f"Starting consolidation of {original_count} findings")

        # Stage 1: Sanitize findings
        sanitized_findings = self._sanitize_findings(findings_list)

        # Stage 2: Deduplicate if requested
        if apply_deduplication:
            deduplicated = self.compilation_agent.deduplicate_findings(
                sanitized_findings, threshold=self.dedup_threshold
            )
        else:
            deduplicated = sanitized_findings

        deduplicated_count = len(deduplicated)

        # Convert to ConsolidatedFinding objects
        consolidated = [self._to_consolidated_finding(f) for f in deduplicated]

        # Stage 3: Categorize if requested
        categorized = {}
        if apply_categorization:
            categorized = self._categorize_findings(consolidated)

        end_time = time.time()
        processing_time_ms = (end_time - start_time) * 1000

        result = ConsolidationResult(
            consolidated_findings=consolidated,
            original_count=original_count,
            deduplicated_count=deduplicated_count,
            categorized_findings=categorized,
            sanitization_summary={
                "safe_findings": sum(1 for f in consolidated if not f.is_sanitized),
                "sanitized_findings": sum(1 for f in consolidated if f.is_sanitized),
                "deduplication_ratio": (
                    1.0 - (deduplicated_count / original_count) if original_count > 0 else 0.0
                ),
            },
            processing_time_ms=processing_time_ms,
        )

        logger.info(
            f"Consolidation complete: {original_count} → {deduplicated_count} "
            f"(ratio: {result.sanitization_summary['deduplication_ratio']:.1%})"
        )

        return result

    def _sanitize_findings(
        self, findings: List[Mapping[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Apply sanitization to all findings.

        Sanitization stages:
        1. Check for dangerous content patterns
        2. Apply prompt injection prevention
        3. Preserve original content for reference

        Args:
            findings: List of findings to sanitize

        Returns:
            List of sanitized findings with metadata
        """
        sanitized = []

        for finding in findings:
            content = str(finding.get("content", ""))

            # Stage 1: Check for dangerous patterns
            is_safe = self.content_sanitizer.is_safe(content)
            sanitization_flags = []

            if not is_safe:
                sanitized_content = self.content_sanitizer.sanitize(content)
                sanitization_flags.append("content_pattern_detected")
            else:
                sanitized_content = content

            # Stage 2: Apply prompt injection prevention
            # Use MEDIUM risk level for research findings (balanced security)
            safe_for_prompt = self.prompt_sanitizer.sanitize_for_prompt(
                sanitized_content, risk_level=RiskLevel.MEDIUM
            )

            # Check if prompt sanitization made changes
            if safe_for_prompt != sanitized_content:
                sanitization_flags.append("prompt_injection_prevention")

            # Create sanitized finding with metadata
            sanitized_finding = dict(finding)
            sanitized_finding["content"] = safe_for_prompt
            sanitized_finding["_original_content"] = content
            sanitized_finding["_is_sanitized"] = not is_safe or (
                safe_for_prompt != sanitized_content
            )
            sanitized_finding["_sanitization_flags"] = sanitization_flags

            sanitized.append(sanitized_finding)

        logger.debug(f"Sanitized {len(sanitized)} findings")
        return sanitized

    def _to_consolidated_finding(self, finding: Mapping[str, Any]) -> ConsolidatedFinding:
        """Convert a finding dictionary to a ConsolidatedFinding object.

        Args:
            finding: Finding dictionary with optional sanitization metadata

        Returns:
            ConsolidatedFinding object
        """
        return ConsolidatedFinding(
            type=str(finding.get("type", "unknown")),
            content=str(finding.get("content", "")),
            original_content=str(finding.get("_original_content", "")),
            source_url=finding.get("source_url"),
            trust_tier=finding.get("trust_tier"),
            extracted_at=finding.get("extracted_at"),
            is_sanitized=finding.get("_is_sanitized", False),
            sanitization_flags=finding.get("_sanitization_flags", []),
        )

    def _categorize_findings(
        self, findings: List[ConsolidatedFinding]
    ) -> Dict[str, List[ConsolidatedFinding]]:
        """Categorize findings by type using keyword matching.

        Args:
            findings: List of consolidated findings to categorize

        Returns:
            Dictionary mapping category names to lists of findings
        """
        categories: Dict[str, List[ConsolidatedFinding]] = {
            "technical": [],
            "ux": [],
            "market": [],
            "competition": [],
            "other": [],
        }

        for finding in findings:
            content_lower = finding.content.lower()
            categorized = False

            # Check each category
            for category, keywords in self.CATEGORY_KEYWORDS.items():
                if any(keyword in content_lower for keyword in keywords):
                    categories[category].append(finding)
                    categorized = True
                    break

            # If no category matched, put in 'other'
            if not categorized:
                categories["other"].append(finding)

        logger.debug(
            f"Categorized {len(findings)} findings into categories: "
            f"{', '.join(f'{k}={len(v)}' for k, v in categories.items() if v)}"
        )

        return categories

    def get_categorized_report(self, result: ConsolidationResult) -> str:
        """Generate a human-readable categorized report from consolidation result.

        Args:
            result: ConsolidationResult from consolidate()

        Returns:
            Formatted report string
        """
        lines = [
            "Research Data Consolidation Report",
            "=" * 40,
            f"Original Findings: {result.original_count}",
            f"Deduplicated: {result.deduplicated_count}",
            f"Deduplication Ratio: {result.sanitization_summary['deduplication_ratio']:.1%}",
            f"Processing Time: {result.processing_time_ms:.2f}ms",
            "",
            "Sanitization Summary:",
            f"  Safe Findings: {result.sanitization_summary['safe_findings']}",
            f"  Sanitized Findings: {result.sanitization_summary['sanitized_findings']}",
            "",
            "Findings by Category:",
        ]

        for category, findings in result.categorized_findings.items():
            if findings:
                lines.append(f"  {category.upper()}: {len(findings)} findings")

        return "\n".join(lines)
