"""Tracer bullet pipeline package (test-facing shim).

Unit tests import `tracer_bullet.gatherer` and `tracer_bullet.orchestrator`.
We provide a small, deterministic implementation here to avoid network/LLM
dependencies during CI collection and tests.
"""

"""Tracer Bullet - Minimal end-to-end pipeline validation

This package implements a complete pipeline to validate:
- Web scraping (robots.txt, rate limits)
- LLM extraction (structured data, prompt injection defenses)
- Python calculators (safe math operations)
- Token budget tracking
"""

from tracer_bullet.web_scraper import WebScraper, ScraperConfig
from tracer_bullet.llm_extractor import LLMExtractor, ExtractionResult
from tracer_bullet.calculator import Calculator, CalculationResult
from tracer_bullet.pipeline import TracerBulletPipeline, PipelineResult

__all__ = [
    "WebScraper",
    "ScraperConfig",
    "LLMExtractor",
    "ExtractionResult",
    "Calculator",
    "CalculationResult",
    "TracerBulletPipeline",
    "PipelineResult",
]
