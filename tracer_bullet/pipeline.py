"""End-to-end tracer bullet pipeline

Integrates web scraping, LLM extraction, and calculations into a single
validation pipeline that proves feasibility of the complete system.
"""

import logging
from typing import Dict, Any, Optional
from dataclasses import dataclass

from tracer_bullet.web_scraper import WebScraper, ScraperConfig
from tracer_bullet.llm_extractor import LLMExtractor, ExtractionResult
from tracer_bullet.calculator import Calculator, CalculationResult

logger = logging.getLogger(__name__)


@dataclass
class PipelineResult:
    """Result of complete pipeline execution"""
    success: bool
    scrape_success: bool = False
    extraction_success: bool = False
    calculation_success: bool = False
    raw_content: Optional[str] = None
    extracted_data: Optional[Dict[str, Any]] = None
    calculations: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    tokens_used: int = 0
    prompt_injection_detected: bool = False


class TracerBulletPipeline:
    """Complete end-to-end pipeline for validation"""
    
    def __init__(
        self,
        scraper_config: Optional[ScraperConfig] = None,
        llm_api_key: Optional[str] = None,
        llm_model: str = "claude-sonnet-4-5"
    ):
        """Initialize pipeline components
        
        Args:
            scraper_config: Web scraper configuration
            llm_api_key: Anthropic API key for LLM
            llm_model: Claude model to use
        """
        self.scraper = WebScraper(config=scraper_config)
        self.extractor = LLMExtractor(api_key=llm_api_key, model=llm_model)
        self.calculator = Calculator()
        logger.info("TracerBulletPipeline initialized")
    
    def execute(
        self,
        url: str,
        extraction_schema: Dict[str, Any],
        calculations: Optional[Dict[str, str]] = None,
        max_tokens: int = 4096
    ) -> PipelineResult:
        """Execute complete pipeline
        
        Args:
            url: URL to scrape
            extraction_schema: JSON schema for data extraction
            calculations: Optional dict of calculation specs
                         (e.g., {"total": "sum", "average": "avg"})
            max_tokens: Max tokens for LLM extraction
            
        Returns:
            PipelineResult with all stage results
        """
        logger.info(f"Starting pipeline execution for {url}")
        
        # Stage 1: Web Scraping
        logger.info("Stage 1: Web Scraping")
        raw_content = self.scraper.fetch(url)
        if raw_content is None:
            logger.error("Web scraping failed")
            return PipelineResult(
                success=False,
                scrape_success=False,
                error="Web scraping failed"
            )
        
        logger.info(f"Scraping successful ({len(raw_content)} bytes)")
        
        # Stage 2: LLM Extraction
        logger.info("Stage 2: LLM Extraction")
        extraction_result = self.extractor.extract(
            text=raw_content,
            schema=extraction_schema,
            max_tokens=max_tokens
        )
        
        if extraction_result.prompt_injection_detected:
            logger.error("Prompt injection detected - aborting pipeline")
            return PipelineResult(
                success=False,
                scrape_success=True,
                extraction_success=False,
                raw_content=raw_content,
                error="Prompt injection detected",
                prompt_injection_detected=True
            )
        
        if not extraction_result.success:
            logger.error(f"Extraction failed: {extraction_result.error}")
            return PipelineResult(
                success=False,
                scrape_success=True,
                extraction_success=False,
                raw_content=raw_content,
                error=f"Extraction failed: {extraction_result.error}",
                tokens_used=extraction_result.tokens_used
            )
        
        logger.info("Extraction successful")
        
        # Stage 3: Calculations (optional)
        calc_results = {}
        if calculations:
            logger.info("Stage 3: Calculations")
            for calc_name, calc_type in calculations.items():
                if calc_type == "sum" and "values" in extraction_result.data:
                    result = self.calculator.sum(extraction_result.data["values"])
                    calc_results[calc_name] = result.value if result.success else None
                elif calc_type == "avg" and "values" in extraction_result.data:
                    result = self.calculator.average(extraction_result.data["values"])
                    calc_results[calc_name] = result.value if result.success else None
                elif calc_type == "percentage" and "part" in extraction_result.data and "whole" in extraction_result.data:
                    result = self.calculator.percentage(
                        extraction_result.data["part"],
                        extraction_result.data["whole"]
                    )
                    calc_results[calc_name] = result.value if result.success else None
            
            logger.info(f"Calculations complete: {calc_results}")
        
        # Success!
        logger.info("Pipeline execution successful")
        return PipelineResult(
            success=True,
            scrape_success=True,
            extraction_success=True,
            calculation_success=bool(calculations),
            raw_content=raw_content,
            extracted_data=extraction_result.data,
            calculations=calc_results if calculations else None,
            tokens_used=extraction_result.tokens_used
        )
