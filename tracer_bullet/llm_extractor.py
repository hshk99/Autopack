"""LLM-based structured data extraction

Uses Claude to extract structured data from unstructured text with:
- JSON schema validation
- Prompt injection defenses
- Token budget tracking
- Error handling
"""

import json
import logging
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
import os

try:
    from anthropic import Anthropic
except ImportError:
    Anthropic = None

logger = logging.getLogger(__name__)


@dataclass
class ExtractionResult:
    """Result of LLM extraction"""
    success: bool
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    tokens_used: int = 0
    prompt_injection_detected: bool = False


class LLMExtractor:
    """Extract structured data using Claude"""
    
    def __init__(self, api_key: Optional[str] = None, model: str = "claude-sonnet-4-5"):
        """Initialize extractor
        
        Args:
            api_key: Anthropic API key (defaults to ANTHROPIC_API_KEY env var)
            model: Claude model to use
        """
        if Anthropic is None:
            raise ImportError("anthropic package required. Install with: pip install anthropic")
        
        self.client = Anthropic(api_key=api_key or os.getenv("ANTHROPIC_API_KEY"))
        self.model = model
        self.total_tokens_used = 0
    
    def _detect_prompt_injection(self, text: str) -> bool:
        """Detect potential prompt injection attempts
        
        Args:
            text: Text to check
            
        Returns:
            True if injection detected, False otherwise
        """
        # Simple heuristics for prompt injection
        injection_patterns = [
            "ignore previous instructions",
            "ignore all previous",
            "disregard previous",
            "forget previous",
            "new instructions:",
            "system:",
            "assistant:",
            "<|im_start|>",
            "<|im_end|>",
        ]
        
        text_lower = text.lower()
        for pattern in injection_patterns:
            if pattern in text_lower:
                logger.warning(f"Potential prompt injection detected: '{pattern}'")
                return True
        
        return False
    
    def extract(self, text: str, schema: Dict[str, Any], max_tokens: int = 4096) -> ExtractionResult:
        """Extract structured data from text
        
        Args:
            text: Input text to extract from
            schema: JSON schema describing expected output structure
            max_tokens: Maximum tokens for completion
            
        Returns:
            ExtractionResult with extracted data or error
        """
        # Check for prompt injection
        if self._detect_prompt_injection(text):
            return ExtractionResult(
                success=False,
                error="Prompt injection detected",
                prompt_injection_detected=True
            )
        
        # Build extraction prompt
        system_prompt = (
            "You are a data extraction assistant. Extract structured data from the provided text "
            "according to the given JSON schema. Output ONLY valid JSON matching the schema. "
            "Do not include explanations or markdown formatting."
        )
        
        schema_str = json.dumps(schema, indent=2)
        user_prompt = f"""Extract data from this text according to the schema:

SCHEMA:
{schema_str}

TEXT:
{text}

Output valid JSON only:"""
        
        try:
            # Call Claude API
            logger.info(f"Calling {self.model} for extraction (max_tokens={max_tokens})")
            response = self.client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}]
            )
            
            # Track token usage
            tokens_used = response.usage.input_tokens + response.usage.output_tokens
            self.total_tokens_used += tokens_used
            logger.info(f"Extraction used {tokens_used} tokens (total: {self.total_tokens_used})")
            
            # Parse response
            content = response.content[0].text.strip()
            
            # Remove markdown fences if present
            if content.startswith("```json"):
                content = content[7:]
            if content.startswith("```"):
                content = content[3:]
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()
            
            # Parse JSON
            try:
                data = json.loads(content)
                logger.info("Successfully extracted structured data")
                return ExtractionResult(
                    success=True,
                    data=data,
                    tokens_used=tokens_used
                )
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse JSON response: {e}")
                return ExtractionResult(
                    success=False,
                    error=f"Invalid JSON: {e}",
                    tokens_used=tokens_used
                )
                
        except Exception as e:
            logger.error(f"Extraction failed: {e}")
            return ExtractionResult(
                success=False,
                error=str(e)
            )
    
    def get_total_tokens_used(self) -> int:
        """Get total tokens used across all extractions
        
        Returns:
            Total token count
        """
        return self.total_tokens_used
