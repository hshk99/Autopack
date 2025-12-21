"""Research Tracer Bullet - Minimal end-to-end pipeline.

This package provides a tracer bullet implementation that validates:
- Web scraping with robots.txt compliance and rate limiting
- LLM-based structured data extraction with prompt injection defenses
- Python calculators for data processing
- Token budget tracking
"""

from research_tracer.scraper import WebScraper
from research_tracer.extractor import StructuredExtractor, PromptInjectionDetector
from research_tracer.calculator import Calculator
from research_tracer.pipeline import ResearchPipeline, PipelineConfig, PipelineResult

__version__ = "0.1.0"

__all__ = [
    "WebScraper",
    "StructuredExtractor",
    "PromptInjectionDetector",
    "Calculator",
    "ResearchPipeline",
    "PipelineConfig",
    "PipelineResult",
]
