"""Human Response Parser for Evidence Ingestion.

This module provides functionality for parsing and ingesting human responses
to evidence requests without causing token blowups. It implements compact
parsing strategies and content normalization.

Design Goals:
- Parse various response formats (plain text, JSON, markdown)
- Normalize and compress responses to minimize token usage
- Extract structured information from unstructured responses
- Validate responses against original requests
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Tuple
from enum import Enum
import re
import json

from .evidence_requests import (
    EvidenceRequest,
    EvidenceRequestBatch,
    EvidenceType,
    EvidencePriority,
)


class ResponseFormat(Enum):
    """Detected format of human response."""
    PLAIN_TEXT = "plain_text"
    JSON = "json"
    MARKDOWN = "markdown"
    STRUCTURED = "structured"  # Our expected format
    UNKNOWN = "unknown"


class ResponseQuality(Enum):
    """Quality assessment of a response."""
    COMPLETE = "complete"      # Fully addresses the request
    PARTIAL = "partial"        # Partially addresses the request
    INSUFFICIENT = "insufficient"  # Does not address the request
    INVALID = "invalid"        # Cannot be parsed or understood


@dataclass
class ParsedEvidence:
    """A single piece of parsed evidence.
    
    Attributes:
        request_index: Index of the original request this responds to
        evidence_type: Type of evidence provided
        content: The actual evidence content
        content_compressed: Token-efficient version of content
        quality: Quality assessment of the response
        token_estimate: Estimated token count
        metadata: Additional metadata extracted
    """
    request_index: int
    evidence_type: EvidenceType
    content: str
    content_compressed: str
    quality: ResponseQuality
    token_estimate: int
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_prompt_context(self) -> str:
        """Convert to a compact context string for prompt injection.
        
        Returns:
            A compact string suitable for prompt context.
        """
        return f"[{self.evidence_type.value}] {self.content_compressed}"


@dataclass
class ParsedResponseBatch:
    """A batch of parsed evidence responses.
    
    Attributes:
        phase_id: The phase these responses relate to
        original_requests: The original evidence request batch
        parsed_evidence: List of parsed evidence items
        total_token_estimate: Total estimated tokens for all evidence
        missing_evidence: Indices of requests not addressed
        parse_errors: Any errors encountered during parsing
    """
    phase_id: str
    original_requests: Optional[EvidenceRequestBatch] = None
    parsed_evidence: List[ParsedEvidence] = field(default_factory=list)
    total_token_estimate: int = 0
    missing_evidence: List[int] = field(default_factory=list)
    parse_errors: List[str] = field(default_factory=list)
    
    def get_context_for_prompt(self, max_tokens: int = 2000) -> str:
        """Generate a token-efficient context string for prompt injection.
        
        Args:
            max_tokens: Maximum tokens to use for context
        
        Returns:
            A compact context string within token budget.
        """
        if not self.parsed_evidence:
            return "[No evidence provided]"
        
        lines = [f"--- EVIDENCE FOR {self.phase_id} ---"]
        current_tokens = 10  # Header overhead
        
        # Sort by quality (complete first) then by request index
        sorted_evidence = sorted(
            self.parsed_evidence,
            key=lambda e: (e.quality.value, e.request_index)
        )
        
        for evidence in sorted_evidence:
            evidence_str = evidence.to_prompt_context()
            evidence_tokens = evidence.token_estimate
            
            if current_tokens + evidence_tokens > max_tokens:
                # Truncate if over budget
                remaining = max_tokens - current_tokens - 20
                if remaining > 50:  # Only include if meaningful
                    truncated = self._truncate_to_tokens(evidence_str, remaining)
                    lines.append(f"{truncated} [TRUNCATED]")
                break
            
            lines.append(evidence_str)
            current_tokens += evidence_tokens
        
        if self.missing_evidence:
            lines.append(f"[Missing: requests {self.missing_evidence}]")
        
        lines.append("--- END EVIDENCE ---")
        return "\n".join(lines)
    
    def _truncate_to_tokens(self, text: str, max_tokens: int) -> str:
        """Truncate text to approximately max_tokens."""
        # Rough estimate: 4 chars per token
        max_chars = max_tokens * 4
        if len(text) <= max_chars:
            return text
        return text[:max_chars - 3] + "..."
    
    def is_complete(self) -> bool:
        """Check if all requests have been addressed."""
        return len(self.missing_evidence) == 0 and len(self.parse_errors) == 0
    
    def get_quality_summary(self) -> Dict[str, int]:
        """Get a summary of response quality."""
        summary = {q.value: 0 for q in ResponseQuality}
        for evidence in self.parsed_evidence:
            summary[evidence.quality.value] += 1
        return summary


class HumanResponseParser:
    """Parser for human responses to evidence requests.
    
    This parser handles various input formats and normalizes them
    into a structured format suitable for prompt injection.
    """
    
    # Token estimation: ~4 characters per token
    CHARS_PER_TOKEN = 4
    
    # Maximum content length before compression
    MAX_CONTENT_LENGTH = 8000  # ~2000 tokens
    
    def __init__(self, max_tokens_per_evidence: int = 500):
        """Initialize parser.
        
        Args:
            max_tokens_per_evidence: Maximum tokens per evidence item
        """
        self.max_tokens_per_evidence = max_tokens_per_evidence
    
    def parse_response(
        self,
        response_text: str,
        original_requests: Optional[EvidenceRequestBatch] = None
    ) -> ParsedResponseBatch:
        """Parse a human response to evidence requests.
        
        Args:
            response_text: The raw response text from human
            original_requests: The original evidence request batch
        
        Returns:
            A ParsedResponseBatch with extracted evidence
        """
        phase_id = original_requests.phase_id if original_requests else "unknown"
        result = ParsedResponseBatch(
            phase_id=phase_id,
            original_requests=original_requests,
        )
        
        # Detect response format
        response_format = self._detect_format(response_text)
        
        # Parse based on format
        if response_format == ResponseFormat.JSON:
            self._parse_json_response(response_text, result)
        elif response_format == ResponseFormat.STRUCTURED:
            self._parse_structured_response(response_text, result)
        elif response_format == ResponseFormat.MARKDOWN:
            self._parse_markdown_response(response_text, result)
        else:
            self._parse_plain_text_response(response_text, result)
        
        # Validate against original requests
        if original_requests:
            self._validate_against_requests(result, original_requests)
        
        # Calculate total tokens
        result.total_token_estimate = sum(
            e.token_estimate for e in result.parsed_evidence
        )
        
        return result
    
    def _detect_format(self, text: str) -> ResponseFormat:
        """Detect the format of the response text."""
        text_stripped = text.strip()
        
        # Check for JSON
        if text_stripped.startswith('{') or text_stripped.startswith('['):
            try:
                json.loads(text_stripped)
                return ResponseFormat.JSON
            except json.JSONDecodeError:
                pass
        
        # Check for our structured format
        if "--- EVIDENCE" in text or re.search(r'^\d+\.\s*\[', text, re.MULTILINE):
            return ResponseFormat.STRUCTURED
        
        # Check for markdown
        if re.search(r'^#{1,3}\s|```|\*\*|__', text, re.MULTILINE):
            return ResponseFormat.MARKDOWN
        
        return ResponseFormat.PLAIN_TEXT
    
    def _parse_json_response(self, text: str, result: ParsedResponseBatch) -> None:
        """Parse a JSON-formatted response."""
        try:
            data = json.loads(text.strip())
            
            # Handle array of evidence items
            if isinstance(data, list):
                for i, item in enumerate(data):
                    self._add_evidence_from_dict(i, item, result)
            
            # Handle object with evidence key
            elif isinstance(data, dict):
                if 'evidence' in data:
                    for i, item in enumerate(data['evidence']):
                        self._add_evidence_from_dict(i, item, result)
                else:
                    # Treat the whole object as a single evidence item
                    self._add_evidence_from_dict(0, data, result)
        
        except json.JSONDecodeError as e:
            result.parse_errors.append(f"JSON parse error: {e}")
    
    def _add_evidence_from_dict(
        self,
        index: int,
        item: Dict[str, Any],
        result: ParsedResponseBatch
    ) -> None:
        """Add evidence from a dictionary item."""
        content = item.get('content', item.get('value', str(item)))
        evidence_type_str = item.get('type', 'custom')
        
        try:
            evidence_type = EvidenceType(evidence_type_str)
        except ValueError:
            evidence_type = EvidenceType.CUSTOM
        
        compressed = self._compress_content(content)
        
        result.parsed_evidence.append(ParsedEvidence(
            request_index=item.get('request_index', index),
            evidence_type=evidence_type,
            content=content,
            content_compressed=compressed,
            quality=self._assess_quality(content),
            token_estimate=self._estimate_tokens(compressed),
            metadata=item.get('metadata', {}),
        ))
    
    def _parse_structured_response(self, text: str, result: ParsedResponseBatch) -> None:
        """Parse our structured response format."""
        # Pattern: "1. [type] content" or numbered items
        pattern = r'^(\d+)\.\s*(?:\[([^\]]+)\])?\s*(.+?)(?=^\d+\.|--- END|$)'
        
        matches = re.findall(pattern, text, re.MULTILINE | re.DOTALL)
        
        for match in matches:
            index = int(match[0]) - 1
            type_str = match[1] if match[1] else 'custom'
            content = match[2].strip()
            
            try:
                evidence_type = EvidenceType(type_str.lower().replace(' ', '_'))
            except ValueError:
                evidence_type = EvidenceType.CUSTOM
            
            compressed = self._compress_content(content)
            
            result.parsed_evidence.append(ParsedEvidence(
                request_index=index,
                evidence_type=evidence_type,
                content=content,
                content_compressed=compressed,
                quality=self._assess_quality(content),
                token_estimate=self._estimate_tokens(compressed),
            ))
        
        # If no structured matches, fall back to plain text
        if not matches:
            self._parse_plain_text_response(text, result)
    
    def _parse_markdown_response(self, text: str, result: ParsedResponseBatch) -> None:
        """Parse a markdown-formatted response."""
        # Extract content from code blocks
        code_blocks = re.findall(r'```(?:\w+)?\n(.+?)```', text, re.DOTALL)
        
        # Extract content from headers
        sections = re.split(r'^#{1,3}\s+(.+)$', text, flags=re.MULTILINE)
        
        evidence_items = []
        
        # Process code blocks as evidence
        for i, block in enumerate(code_blocks):
            evidence_items.append(('code_block', block.strip()))
        
        # Process sections
        for i in range(1, len(sections), 2):
            if i + 1 < len(sections):
                header = sections[i]
                content = sections[i + 1].strip()
                # Remove code blocks already processed
                for block in code_blocks:
                    content = content.replace(f'```{block}```', '').strip()
                if content:
                    evidence_items.append((header, content))
        
        # Add parsed evidence
        for i, (header, content) in enumerate(evidence_items):
            compressed = self._compress_content(content)
            
            result.parsed_evidence.append(ParsedEvidence(
                request_index=i,
                evidence_type=EvidenceType.CUSTOM,
                content=content,
                content_compressed=compressed,
                quality=self._assess_quality(content),
                token_estimate=self._estimate_tokens(compressed),
                metadata={'header': header},
            ))
        
        # If no structured content found, treat as plain text
        if not evidence_items:
            self._parse_plain_text_response(text, result)
    
    def _parse_plain_text_response(self, text: str, result: ParsedResponseBatch) -> None:
        """Parse a plain text response as a single evidence item."""
        content = text.strip()
        if not content:
            result.parse_errors.append("Empty response")
            return
        
        compressed = self._compress_content(content)
        
        result.parsed_evidence.append(ParsedEvidence(
            request_index=0,
            evidence_type=EvidenceType.CUSTOM,
            content=content,
            content_compressed=compressed,
            quality=self._assess_quality(content),
            token_estimate=self._estimate_tokens(compressed),
        ))
    
    def _compress_content(self, content: str) -> str:
        """Compress content to reduce token usage.
        
        Strategies:
        - Remove excessive whitespace
        - Truncate very long content
        - Remove redundant information
        """
        if not content:
            return ""
        
        # Normalize whitespace
        compressed = re.sub(r'\s+', ' ', content)
        compressed = re.sub(r'\n\s*\n', '\n', compressed)
        
        # Remove common noise patterns
        noise_patterns = [
            r'={3,}',  # Separator lines
            r'-{3,}',  # Separator lines
            r'\[\d+:\d+:\d+\]',  # Timestamps (keep content)
        ]
        for pattern in noise_patterns:
            compressed = re.sub(pattern, '', compressed)
        
        # Truncate if too long
        max_chars = self.max_tokens_per_evidence * self.CHARS_PER_TOKEN
        if len(compressed) > max_chars:
            # Keep beginning and end
            half = max_chars // 2 - 10
            compressed = compressed[:half] + " [...] " + compressed[-half:]
        
        return compressed.strip()
    
    def _estimate_tokens(self, text: str) -> int:
        """Estimate token count for text."""
        return len(text) // self.CHARS_PER_TOKEN + 1
    
    def _assess_quality(self, content: str) -> ResponseQuality:
        """Assess the quality of evidence content."""
        if not content or len(content.strip()) < 10:
            return ResponseQuality.INVALID
        
        # Check for meaningful content
        word_count = len(content.split())
        
        if word_count < 5:
            return ResponseQuality.INSUFFICIENT
        elif word_count < 20:
            return ResponseQuality.PARTIAL
        else:
            return ResponseQuality.COMPLETE
    
    def _validate_against_requests(
        self,
        result: ParsedResponseBatch,
        requests: EvidenceRequestBatch
    ) -> None:
        """Validate parsed evidence against original requests."""
        addressed_indices = {e.request_index for e in result.parsed_evidence}
        all_indices = set(range(len(requests.requests)))
        
        result.missing_evidence = list(all_indices - addressed_indices)


def parse_human_response(
    response_text: str,
    original_requests: Optional[EvidenceRequestBatch] = None,
    max_tokens: int = 2000
) -> Tuple[str, ParsedResponseBatch]:
    """Convenience function to parse human response and get prompt context.
    
    Args:
        response_text: The raw response from human
        original_requests: The original evidence request batch
        max_tokens: Maximum tokens for the context output
    
    Returns:
        Tuple of (context_string, parsed_batch)
    """
    parser = HumanResponseParser()
    parsed = parser.parse_response(response_text, original_requests)
    context = parsed.get_context_for_prompt(max_tokens)
    return context, parsed


def compress_evidence_for_prompt(
    evidence_items: List[Dict[str, str]],
    max_tokens: int = 1500
) -> str:
    """Compress multiple evidence items into a token-efficient prompt context.
    
    Args:
        evidence_items: List of dicts with 'type' and 'content' keys
        max_tokens: Maximum tokens for output
    
    Returns:
        A compact context string
    """
    parser = HumanResponseParser(max_tokens_per_evidence=max_tokens // max(len(evidence_items), 1))
    
    lines = ["--- EVIDENCE ---"]
    current_tokens = 5
    
    for item in evidence_items:
        content = item.get('content', '')
        evidence_type = item.get('type', 'custom')
        
        compressed = parser._compress_content(content)
        tokens = parser._estimate_tokens(compressed)
        
        if current_tokens + tokens > max_tokens:
            remaining = max_tokens - current_tokens - 10
            if remaining > 20:
                truncated = compressed[:remaining * 4]
                lines.append(f"[{evidence_type}] {truncated}...")
            break
        
        lines.append(f"[{evidence_type}] {compressed}")
        current_tokens += tokens
    
    lines.append("--- END ---")
    return "\n".join(lines)
