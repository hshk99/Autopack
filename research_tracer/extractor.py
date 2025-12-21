"""LLM-based structured data extraction with prompt injection defenses.

This module provides safe LLM extraction that:
- Validates and sanitizes input text
- Detects and blocks prompt injection attempts
- Extracts structured data using LLM
- Validates output schema
"""

import json
import logging
import re
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)


class PromptInjectionDetector:
    """Detects potential prompt injection attempts in user input."""

    # Patterns that indicate prompt injection attempts
    INJECTION_PATTERNS = [
        r"ignore (previous|above|all) (instructions|prompts|rules)",
        r"disregard (previous|above|all) (instructions|prompts|rules)",
        r"forget (previous|above|all) (instructions|prompts|rules)",
        r"new (instructions|prompt|system message)",
        r"you are now",
        r"act as (a |an )?(different|new)",
        r"pretend (you are|to be)",
        r"roleplay as",
        r"system:\s*",
        r"assistant:\s*",
        r"<\|im_start\|>",
        r"<\|im_end\|>",
    ]

    def __init__(self):
        """Initialize detector with compiled patterns."""
        self.patterns = [re.compile(p, re.IGNORECASE) for p in self.INJECTION_PATTERNS]

    def detect(self, text: str) -> bool:
        """Check if text contains prompt injection patterns.

        Args:
            text: Text to check

        Returns:
            True if injection detected, False otherwise
        """
        if not text:
            return False

        for pattern in self.patterns:
            if pattern.search(text):
                logger.warning(f"Prompt injection detected: pattern={pattern.pattern}")
                return True

        return False

    def sanitize(self, text: str, max_length: int = 10000) -> str:
        """Sanitize text by removing potential injection vectors.

        Args:
            text: Text to sanitize
            max_length: Maximum allowed length

        Returns:
            Sanitized text
        """
        if not text:
            return ""

        # Truncate to max length
        text = text[:max_length]

        # Remove special tokens
        text = re.sub(r"<\|im_start\|>", "", text)
        text = re.sub(r"<\|im_end\|>", "", text)

        # Remove system/assistant markers
        text = re.sub(r"^(system|assistant|user):\s*", "", text, flags=re.MULTILINE)

        return text.strip()


class StructuredExtractor:
    """Extract structured data from text using LLM with safety checks."""

    def __init__(self, llm_client: Optional[Any] = None):
        """Initialize extractor.

        Args:
            llm_client: LLM client (e.g., OpenAI, Anthropic). If None, uses mock extraction.
        """
        self.llm_client = llm_client
        self.injection_detector = PromptInjectionDetector()

    def extract(self, text: str, schema: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Extract structured data from text according to schema.

        Args:
            text: Input text to extract from
            schema: JSON schema describing expected output structure

        Returns:
            Extracted data as dictionary, or None if extraction failed
        """
        # Safety check: detect prompt injection
        if self.injection_detector.detect(text):
            logger.error("Prompt injection detected - extraction blocked")
            return None

        # Sanitize input
        sanitized_text = self.injection_detector.sanitize(text)

        if not sanitized_text:
            logger.error("Empty text after sanitization")
            return None

        # Extract using LLM or mock
        if self.llm_client:
            return self._extract_with_llm(sanitized_text, schema)
        else:
            return self._mock_extract(sanitized_text, schema)

    def _extract_with_llm(self, text: str, schema: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Extract using real LLM client.

        Args:
            text: Sanitized input text
            schema: JSON schema

        Returns:
            Extracted data or None
        """
        # Build extraction prompt
        prompt = self._build_extraction_prompt(text, schema)

        try:
            # Call LLM (implementation depends on client type)
            # This is a placeholder - actual implementation would call the LLM
            logger.info("LLM extraction not implemented - using mock")
            return self._mock_extract(text, schema)
        except Exception as e:
            logger.error(f"LLM extraction failed: {e}")
            return None

    def _mock_extract(self, text: str, schema: Dict[str, Any]) -> Dict[str, Any]:
        """Mock extraction for testing (extracts simple patterns).

        Args:
            text: Input text
            schema: JSON schema

        Returns:
            Mock extracted data
        """
        result = {}

        # Extract based on schema properties
        properties = schema.get("properties", {})

        for field, field_schema in properties.items():
            field_type = field_schema.get("type", "string")

            if field_type == "string":
                # Extract first sentence as mock string
                sentences = text.split(".")
                result[field] = sentences[0].strip() if sentences else ""
            elif field_type == "number":
                # Extract first number found
                numbers = re.findall(r"\d+", text)
                result[field] = int(numbers[0]) if numbers else 0
            elif field_type == "array":
                # Extract comma-separated items
                result[field] = [item.strip() for item in text.split(",")[:3]]
            else:
                result[field] = None

        logger.info(f"Mock extraction completed: {len(result)} fields")
        return result

    def _build_extraction_prompt(self, text: str, schema: Dict[str, Any]) -> str:
        """Build extraction prompt for LLM.

        Args:
            text: Input text
            schema: JSON schema

        Returns:
            Formatted prompt
        """
        schema_str = json.dumps(schema, indent=2)

        prompt = f"""Extract structured data from the following text according to the JSON schema.

JSON Schema:
{schema_str}

Input Text:
{text}

Output the extracted data as valid JSON matching the schema. Do not include any explanations or markdown formatting.
"""

        return prompt

    def validate_output(self, data: Dict[str, Any], schema: Dict[str, Any]) -> bool:
        """Validate extracted data against schema.

        Args:
            data: Extracted data
            schema: JSON schema

        Returns:
            True if valid, False otherwise
        """
        if not data:
            return False

        # Basic validation: check required fields
        required = schema.get("required", [])
        for field in required:
            if field not in data:
                logger.error(f"Missing required field: {field}")
                return False

        # Type validation
        properties = schema.get("properties", {})
        for field, value in data.items():
            if field in properties:
                expected_type = properties[field].get("type")
                if expected_type == "string" and not isinstance(value, str):
                    logger.error(f"Field {field} should be string, got {type(value)}")
                    return False
                elif expected_type == "number" and not isinstance(value, (int, float)):
                    logger.error(f"Field {field} should be number, got {type(value)}")
                    return False
                elif expected_type == "array" and not isinstance(value, list):
                    logger.error(f"Field {field} should be array, got {type(value)}")
                    return False

        return True
