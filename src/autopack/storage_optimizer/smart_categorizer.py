"""
Smart Categorizer (BUILD-151 Phase 4)

LLM-powered categorization for edge cases that don't match policy rules.

Handles the 5-10% of files that deterministic policy can't classify:
- Unusual file types in unexpected locations
- Ambiguous directory names
- Mixed-purpose folders
- Custom application data

Uses LLM only when needed, falling back to 'unknown' category if LLM fails.
Token cost: ~500-2K tokens per 100 files (only for edge cases).
"""

import json
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass

from autopack.storage_optimizer.policy import StoragePolicy, CategoryDefinition
from autopack.storage_optimizer.models import ScanResult


@dataclass
class SmartCategorizationResult:
    """Result of LLM-powered categorization."""

    category: str
    reason: str
    confidence: float
    llm_used: bool
    tokens_used: int


class SmartCategorizer:
    """
    LLM-powered categorizer for edge cases.

    Workflow:
        1. Classifier tries deterministic policy rules first
        2. If no match → categorized as 'unknown'
        3. SmartCategorizer invoked on 'unknown' items
        4. LLM analyzes file context and suggests category
        5. High-confidence suggestions used, low-confidence → stay 'unknown'
    """

    def __init__(
        self,
        policy: StoragePolicy,
        llm_provider: Optional[str] = None,
        min_confidence: float = 0.7,
        max_batch_size: int = 20,
    ):
        """
        Initialize smart categorizer.

        Args:
            policy: Storage policy with category definitions
            llm_provider: LLM provider to use ('anthropic', 'openai', 'glm'), None to auto-detect
            min_confidence: Minimum confidence to accept LLM suggestion (default 0.7)
            max_batch_size: Maximum files to batch in single LLM call (default 20)
        """
        self.policy = policy
        self.llm_provider = llm_provider
        self.min_confidence = min_confidence
        self.max_batch_size = max_batch_size

    def categorize_unknowns(
        self, unknown_items: List[ScanResult], use_llm: bool = True
    ) -> List[SmartCategorizationResult]:
        """
        Categorize unknown items using LLM.

        Args:
            unknown_items: List of items that couldn't be categorized by policy
            use_llm: Whether to use LLM (False = return all as 'unknown')

        Returns:
            List of categorization results
        """
        if not use_llm or not unknown_items:
            return [
                SmartCategorizationResult(
                    category="unknown",
                    reason="LLM categorization disabled",
                    confidence=0.0,
                    llm_used=False,
                    tokens_used=0,
                )
                for _ in unknown_items
            ]

        results = []

        # Process in batches to avoid token limits
        for i in range(0, len(unknown_items), self.max_batch_size):
            batch = unknown_items[i : i + self.max_batch_size]
            batch_results = self._categorize_batch(batch)
            results.extend(batch_results)

        return results

    def _categorize_batch(self, items: List[ScanResult]) -> List[SmartCategorizationResult]:
        """Categorize a batch of items with single LLM call."""
        try:
            # Build LLM prompt
            prompt = self._build_categorization_prompt(items)

            # Call LLM
            response, tokens_used = self._call_llm(prompt)

            # Parse response
            categorizations = self._parse_llm_response(response, len(items))

            # Build results
            results = []
            for i, item in enumerate(items):
                if i < len(categorizations):
                    cat = categorizations[i]
                    results.append(
                        SmartCategorizationResult(
                            category=cat["category"],
                            reason=cat["reason"],
                            confidence=cat["confidence"],
                            llm_used=True,
                            tokens_used=tokens_used // len(items),  # Approximate per-item cost
                        )
                    )
                else:
                    # Fallback if parsing failed
                    results.append(
                        SmartCategorizationResult(
                            category="unknown",
                            reason="LLM parsing failed",
                            confidence=0.0,
                            llm_used=True,
                            tokens_used=tokens_used // len(items),
                        )
                    )

            return results

        except Exception as e:
            # Fallback to unknown on any error
            return [
                SmartCategorizationResult(
                    category="unknown",
                    reason=f"LLM categorization failed: {str(e)}",
                    confidence=0.0,
                    llm_used=False,
                    tokens_used=0,
                )
                for _ in items
            ]

    def _build_categorization_prompt(self, items: List[ScanResult]) -> str:
        """Build LLM prompt for categorizing items."""
        # Get category definitions from policy
        category_descriptions = {}
        for cat_name, cat_def in self.policy.categories.items():
            category_descriptions[cat_name] = {
                "description": self._infer_category_description(cat_name, cat_def),
                "examples": cat_def.patterns[:3] if cat_def.patterns else [],
            }

        prompt = f"""You are a storage optimizer assistant. Categorize these files/folders into the most appropriate category.

Available categories:
{json.dumps(category_descriptions, indent=2)}

Files to categorize:
"""

        for i, item in enumerate(items):
            Path(item.path)
            prompt += f"""
{i + 1}. Path: {item.path}
   Size: {item.size_bytes / (1024**2):.2f} MB
   Age: {item.age_days} days
   Type: {'Directory' if item.is_directory else 'File'}
"""

        prompt += """
For each file, respond with JSON array:
[
  {
    "index": 1,
    "category": "dev_caches",
    "reason": "npm cache directory in temporary location",
    "confidence": 0.85
  },
  ...
]

Rules:
- confidence must be 0.0 to 1.0 (use 0.5 or lower if uncertain)
- category must be one of the available categories or "unknown"
- reason should explain why this category fits
- consider file path, size, age, and type
- prefer specific categories over "unknown" when reasonably confident

Respond with ONLY the JSON array, no other text.
"""

        return prompt

    def _infer_category_description(
        self, category_name: str, category_def: CategoryDefinition
    ) -> str:
        """Infer human-readable description from category definition."""
        descriptions = {
            "dev_caches": "Development caches (node_modules, pip cache, build artifacts)",
            "diagnostics_logs": "Diagnostic logs and error reports",
            "runs": "Autonomous run data and execution logs",
            "archive_buckets": "Archived superseded files",
            "steam_games": "Steam game installations",
            "browser_caches": "Web browser caches and temporary files",
            "downloads": "Downloaded files",
            "temp_files": "Temporary files and system temp directories",
        }

        return descriptions.get(category_name, f"Category: {category_name}")

    def _call_llm(self, prompt: str) -> Tuple[str, int]:
        """
        Call LLM provider with prompt.

        Returns:
            Tuple of (response text, tokens used)
        """
        # Import LLM utilities
        try:
            from autopack.llm import get_llm_client
            from autopack.config import settings

            # Determine provider
            provider = self.llm_provider or settings.llm_provider

            # Get client
            client = get_llm_client(provider)

            # Call LLM
            response = client.complete(
                prompt=prompt,
                max_tokens=1000,
                temperature=0.3,  # Lower temperature for more consistent categorization
            )

            # Extract response text and token count
            response_text = response.get("text", "")
            tokens_used = response.get("usage", {}).get("total_tokens", 0)

            return response_text, tokens_used

        except Exception as e:
            # Fallback: return empty response
            raise RuntimeError(f"LLM call failed: {str(e)}")

    def _parse_llm_response(self, response: str, expected_count: int) -> List[Dict]:
        """
        Parse LLM JSON response.

        Args:
            response: LLM response text
            expected_count: Expected number of categorizations

        Returns:
            List of categorization dicts
        """
        try:
            # Extract JSON from response (may have markdown code blocks)
            json_text = response.strip()

            # Remove markdown code blocks if present
            if json_text.startswith("```"):
                lines = json_text.split("\n")
                json_text = "\n".join(lines[1:-1]) if len(lines) > 2 else json_text

            # Parse JSON
            categorizations = json.loads(json_text)

            if not isinstance(categorizations, list):
                raise ValueError("Response is not a JSON array")

            # Validate structure
            validated = []
            for cat in categorizations:
                if not all(k in cat for k in ["index", "category", "reason", "confidence"]):
                    continue

                # Validate category exists in policy
                if cat["category"] not in self.policy.categories and cat["category"] != "unknown":
                    cat["category"] = "unknown"
                    cat["confidence"] = 0.0

                # Validate confidence threshold
                if cat["confidence"] < self.min_confidence and cat["category"] != "unknown":
                    cat["category"] = "unknown"
                    cat["confidence"] = 0.0

                validated.append(cat)

            return validated

        except Exception:
            # Return empty list on parse error
            return []

    def categorize_single(
        self, item: ScanResult, use_llm: bool = True
    ) -> SmartCategorizationResult:
        """
        Categorize a single item (convenience method).

        Args:
            item: Item to categorize
            use_llm: Whether to use LLM

        Returns:
            Categorization result
        """
        results = self.categorize_unknowns([item], use_llm=use_llm)
        return (
            results[0]
            if results
            else SmartCategorizationResult(
                category="unknown",
                reason="Categorization failed",
                confidence=0.0,
                llm_used=False,
                tokens_used=0,
            )
        )

    def get_token_estimate(self, item_count: int) -> int:
        """
        Estimate token cost for categorizing N items.

        Args:
            item_count: Number of items to categorize

        Returns:
            Estimated token count (input + output)
        """
        # Rough estimates:
        # - Prompt base: ~400 tokens (category definitions)
        # - Per item: ~50 tokens (path + metadata)
        # - Response per item: ~40 tokens (JSON object)

        base_tokens = 400
        per_item_input = 50
        per_item_output = 40

        total_input = base_tokens + (item_count * per_item_input)
        total_output = item_count * per_item_output

        return total_input + total_output
