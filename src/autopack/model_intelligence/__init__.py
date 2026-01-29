"""Model Intelligence module for catalog management and recommendations.

This module provides a Postgres-backed model catalog and recommendation system
to eliminate manual model bump hunts and persist explainable recommendations.

Key components:
- models.py: SQLAlchemy models for catalog, pricing, benchmarks, runtime stats, sentiment, recommendations
- db.py: Database session helpers and migration utilities
- catalog_ingest.py: Ingest config/models.yaml + config/pricing.yaml into DB
- runtime_stats.py: Aggregate llm_usage_events into model_runtime_stats
- sentiment_ingest.py: Capture community sentiment signals
- recommender.py: Generate model recommendations with evidence
- patcher.py: Generate proposed YAML patches for approved recommendations
"""

from .models import (
    ModelBenchmark,
    ModelCatalog,
    ModelPricing,
    ModelRecommendation,
    ModelRuntimeStats,
    ModelSentimentSignal,
)

__all__ = [
    "ModelCatalog",
    "ModelPricing",
    "ModelBenchmark",
    "ModelRuntimeStats",
    "ModelSentimentSignal",
    "ModelRecommendation",
]
