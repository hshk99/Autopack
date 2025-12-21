"""End-to-end research pipeline integrating scraping, extraction, and calculation.

This module provides the main pipeline that:
- Orchestrates web scraping with safety checks
- Extracts structured data using LLM
- Performs calculations on extracted data
- Validates results at each stage
- Tracks token usage and budgets
"""

import logging
import time
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field

from research_tracer.scraper import WebScraper
from research_tracer.extractor import StructuredExtractor
from research_tracer.calculator import Calculator

logger = logging.getLogger(__name__)


@dataclass
class PipelineConfig:
    """Configuration for research pipeline."""

    # Scraping config
    user_agent: str = "AutopackTracerBot/1.0"
    rate_limit_seconds: float = 1.0
    scrape_timeout: int = 10

    # Extraction config
    max_input_length: int = 10000
    enable_injection_detection: bool = True

    # Token budget
    max_tokens_per_extraction: int = 4000
    total_token_budget: int = 50000

    # Validation
    require_schema_validation: bool = True


@dataclass
class PipelineResult:
    """Result from pipeline execution."""

    success: bool
    data: Optional[Dict[str, Any]] = None
    metrics: Optional[Dict[str, float]] = None
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    token_usage: int = 0
    execution_time_seconds: float = 0.0


class ResearchPipeline:
    """End-to-end research pipeline with safety checks and token tracking."""

    def __init__(self, config: Optional[PipelineConfig] = None, llm_client: Optional[Any] = None):
        """Initialize pipeline.

        Args:
            config: Pipeline configuration
            llm_client: LLM client for extraction (optional, uses mock if None)
        """
        self.config = config or PipelineConfig()
        self.scraper = WebScraper(
            user_agent=self.config.user_agent, rate_limit_seconds=self.config.rate_limit_seconds
        )
        self.extractor = StructuredExtractor(llm_client=llm_client)
        self.calculator = Calculator()
        self.total_tokens_used = 0

    def run(self, url: str, extraction_schema: Dict[str, Any], calculations: Optional[List[str]] = None) -> PipelineResult:
        """Run complete pipeline on a URL.

        Args:
            url: URL to scrape
            extraction_schema: JSON schema for data extraction
            calculations: List of calculation types to perform (e.g., ['average', 'percentage'])

        Returns:
            PipelineResult with data, metrics, and status
        """
        start_time = time.time()
        result = PipelineResult(success=False)

        try:
            # Step 1: Scrape web content
            logger.info(f"Step 1: Scraping {url}")
            content = self._scrape(url, result)
            if not content:
                result.errors.append("Scraping failed")
                return result

            # Step 2: Extract structured data
            logger.info("Step 2: Extracting structured data")
            extracted_data = self._extract(content, extraction_schema, result)
            if not extracted_data:
                result.errors.append("Extraction failed")
                return result

            # Step 3: Perform calculations
            logger.info("Step 3: Performing calculations")
            metrics = self._calculate(extracted_data, calculations or [], result)

            # Step 4: Validate results
            logger.info("Step 4: Validating results")
            if not self._validate(extracted_data, extraction_schema, result):
                result.errors.append("Validation failed")
                return result

            # Success
            result.success = True
            result.data = extracted_data
            result.metrics = metrics
            result.execution_time_seconds = time.time() - start_time

            logger.info(f"Pipeline completed successfully in {result.execution_time_seconds:.2f}s")
            return result

        except Exception as e:
            logger.error(f"Pipeline failed with exception: {e}")
            result.errors.append(f"Unexpected error: {str(e)}")
            result.execution_time_seconds = time.time() - start_time
            return result

    def _scrape(self, url: str, result: PipelineResult) -> Optional[str]:
        """Scrape content from URL with safety checks.

        Args:
            url: URL to scrape
            result: Result object to update with warnings/errors

        Returns:
            Scraped content or None
        """
        # Check metadata first
        metadata = self.scraper.get_metadata(url)
        if not metadata["allowed_by_robots"]:
            result.warnings.append(f"URL blocked by robots.txt: {url}")
            return None

        # Fetch content
        content = self.scraper.fetch(url, timeout=self.config.scrape_timeout)
        if not content:
            result.errors.append(f"Failed to fetch content from {url}")
            return None

        # Truncate if too long
        if len(content) > self.config.max_input_length:
            result.warnings.append(f"Content truncated from {len(content)} to {self.config.max_input_length} chars")
            content = content[: self.config.max_input_length]

        return content

    def _extract(self, content: str, schema: Dict[str, Any], result: PipelineResult) -> Optional[Dict[str, Any]]:
        """Extract structured data from content.

        Args:
            content: Text content
            schema: JSON schema
            result: Result object to update

        Returns:
            Extracted data or None
        """
        # Check token budget
        estimated_tokens = len(content.split()) * 1.3  # Rough estimate
        if self.total_tokens_used + estimated_tokens > self.config.total_token_budget:
            result.errors.append(f"Token budget exceeded: {self.total_tokens_used}/{self.config.total_token_budget}")
            return None

        # Extract
        extracted = self.extractor.extract(content, schema)
        if not extracted:
            result.errors.append("Extraction returned no data")
            return None

        # Update token usage (mock - real implementation would get from LLM)
        tokens_used = int(estimated_tokens)
        self.total_tokens_used += tokens_used
        result.token_usage = self.total_tokens_used

        return extracted

    def _calculate(self, data: Dict[str, Any], calculation_types: List[str], result: PipelineResult) -> Dict[str, float]:
        """Perform calculations on extracted data.

        Args:
            data: Extracted data
            calculation_types: Types of calculations to perform
            result: Result object to update

        Returns:
            Dictionary of calculated metrics
        """
        metrics = {}

        try:
            # Extract numeric values for calculations
            numeric_values = []
            for key, value in data.items():
                if isinstance(value, (int, float)):
                    numeric_values.append(value)
                elif isinstance(value, list):
                    numeric_values.extend([v for v in value if isinstance(v, (int, float))])

            if not numeric_values:
                result.warnings.append("No numeric values found for calculations")
                return metrics

            # Perform requested calculations
            if "average" in calculation_types:
                metrics["average"] = self.calculator.average(numeric_values)

            if "median" in calculation_types:
                metrics["median"] = self.calculator.median(numeric_values)

            if "std" in calculation_types:
                metrics["std"] = self.calculator.standard_deviation(numeric_values)

            if "min" in calculation_types:
                metrics["min"] = min(numeric_values)

            if "max" in calculation_types:
                metrics["max"] = max(numeric_values)

            logger.info(f"Calculated {len(metrics)} metrics")

        except Exception as e:
            logger.error(f"Calculation failed: {e}")
            result.warnings.append(f"Some calculations failed: {str(e)}")

        return metrics

    def _validate(self, data: Dict[str, Any], schema: Dict[str, Any], result: PipelineResult) -> bool:
        """Validate extracted data.

        Args:
            data: Extracted data
            schema: JSON schema
            result: Result object to update

        Returns:
            True if valid, False otherwise
        """
        if not self.config.require_schema_validation:
            return True

        is_valid = self.extractor.validate_output(data, schema)
        if not is_valid:
            result.errors.append("Schema validation failed")

        return is_valid

    def get_token_usage_summary(self) -> Dict[str, Any]:
        """Get summary of token usage.

        Returns:
            Dictionary with token usage statistics
        """
        return {
            "total_tokens_used": self.total_tokens_used,
            "total_budget": self.config.total_token_budget,
            "remaining": self.config.total_token_budget - self.total_tokens_used,
            "usage_percentage": (self.total_tokens_used / self.config.total_token_budget) * 100,
        }
