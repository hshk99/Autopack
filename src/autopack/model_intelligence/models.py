"""SQLAlchemy models for model intelligence tables.

These models implement the schema defined in docs/MODEL_RECOMMENDER_SYSTEM_PLAN.md section 3.
"""

from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from ..database import Base


class ModelCatalog(Base):
    """Model catalog: stores model identity and metadata."""

    __tablename__ = "models_catalog"

    model_id = Column(String, primary_key=True, index=True)  # e.g., claude-sonnet-4-5, glm-4.7
    provider = Column(String, nullable=False, index=True)  # anthropic, openai, google, zhipu_glm
    family = Column(String, nullable=False, index=True)  # claude, gpt, gemini, glm
    display_name = Column(String, nullable=False)
    context_window_tokens = Column(Integer, nullable=True)
    notes = Column(Text, nullable=True)
    released_at = Column(DateTime, nullable=True)
    is_deprecated = Column(Boolean, nullable=False, default=False, index=True)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    pricing_records = relationship(
        "ModelPricing", back_populates="model", cascade="all, delete-orphan"
    )
    benchmarks = relationship(
        "ModelBenchmark", back_populates="model", cascade="all, delete-orphan"
    )
    sentiment_signals = relationship(
        "ModelSentimentSignal", back_populates="model", cascade="all, delete-orphan"
    )


class ModelPricing(Base):
    """Model pricing: time-series pricing records."""

    __tablename__ = "model_pricing"

    id = Column(Integer, primary_key=True, index=True)
    model_id = Column(String, ForeignKey("models_catalog.model_id"), nullable=False, index=True)
    input_per_1k = Column(Numeric(10, 6), nullable=False)  # USD per 1K tokens
    output_per_1k = Column(Numeric(10, 6), nullable=False)  # USD per 1K tokens
    currency = Column(String, nullable=False, default="USD")
    effective_at = Column(DateTime, nullable=False, index=True)
    source = Column(String, nullable=False)  # e.g., anthropic_pricing_page, openai_pricing_page
    source_url = Column(Text, nullable=True)
    retrieved_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    # Relationship
    model = relationship("ModelCatalog", back_populates="pricing_records")

    __table_args__ = (
        UniqueConstraint(
            "model_id", "effective_at", "source", name="uq_pricing_model_effective_source"
        ),
    )


class ModelBenchmark(Base):
    """Model benchmarks: time-series benchmark records from multiple sources."""

    __tablename__ = "model_benchmarks"

    id = Column(Integer, primary_key=True, index=True)
    model_id = Column(String, ForeignKey("models_catalog.model_id"), nullable=False, index=True)
    benchmark_name = Column(
        String, nullable=False, index=True
    )  # e.g., SWE-bench Verified, MMLU, HumanEval
    score = Column(Numeric(10, 4), nullable=False)
    unit = Column(String, nullable=False)  # percent, pass@1, etc.
    task_type = Column(
        String, nullable=False, index=True
    )  # code, reasoning, math, multimodal, etc.
    dataset_version = Column(String, nullable=True)
    source = Column(String, nullable=False)  # official, lmsys, third_party
    source_url = Column(Text, nullable=False)
    retrieved_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    # Relationship
    model = relationship("ModelCatalog", back_populates="benchmarks")

    __table_args__ = (
        UniqueConstraint(
            "model_id",
            "benchmark_name",
            "dataset_version",
            "source_url",
            name="uq_benchmark_model_name_version_url",
        ),
    )


class ModelRuntimeStats(Base):
    """Model runtime statistics: aggregated from real telemetry (rolling window)."""

    __tablename__ = "model_runtime_stats"

    id = Column(Integer, primary_key=True, index=True)
    window_start = Column(DateTime, nullable=False, index=True)
    window_end = Column(DateTime, nullable=False, index=True)
    provider = Column(String, nullable=False, index=True)
    model = Column(String, nullable=False, index=True)
    role = Column(
        String, nullable=False, index=True
    )  # builder, auditor, doctor, agent:planner, etc.
    calls = Column(Integer, nullable=False, default=0)
    total_tokens = Column(Integer, nullable=False, default=0)
    prompt_tokens = Column(Integer, nullable=True)
    completion_tokens = Column(Integer, nullable=True)
    est_cost_usd = Column(Numeric(12, 6), nullable=True)  # computed using pricing table
    success_rate = Column(Numeric(5, 4), nullable=True)  # 0.0-1.0, nullable if unavailable
    p50_tokens = Column(Integer, nullable=True)
    p90_tokens = Column(Integer, nullable=True)
    notes = Column(Text, nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "window_start",
            "window_end",
            "provider",
            "model",
            "role",
            name="uq_runtime_stats_window_provider_model_role",
        ),
    )


class ModelSentimentSignal(Base):
    """Model sentiment signals: community experience evidence (supporting, not primary)."""

    __tablename__ = "model_sentiment_signals"

    id = Column(Integer, primary_key=True, index=True)
    model_id = Column(String, ForeignKey("models_catalog.model_id"), nullable=False, index=True)
    source = Column(String, nullable=False, index=True)  # reddit, hn, twitter, blog
    source_url = Column(Text, nullable=False)
    title = Column(String, nullable=True)
    snippet = Column(Text, nullable=False)  # short quote or extracted summary
    sentiment = Column(String, nullable=False, index=True)  # positive, neutral, negative, mixed
    tags = Column(JSON, nullable=True)  # e.g., {"topic": "coding", "issue": "hallucination"}
    retrieved_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    # Relationship
    model = relationship("ModelCatalog", back_populates="sentiment_signals")

    __table_args__ = (UniqueConstraint("model_id", "source_url", name="uq_sentiment_model_url"),)


class ModelRecommendation(Base):
    """Model recommendations: persisted recommendation objects with evidence."""

    __tablename__ = "model_recommendations"

    id = Column(Integer, primary_key=True, index=True)
    created_at = Column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), index=True
    )
    status = Column(
        String, nullable=False, default="proposed", index=True
    )  # proposed, accepted, rejected, implemented
    use_case = Column(
        String, nullable=False, index=True
    )  # e.g., tidy_semantic, builder_low, doctor_cheap
    current_model = Column(String, nullable=False)
    recommended_model = Column(String, nullable=False)
    reasoning = Column(Text, nullable=False)  # concise human-readable rationale
    expected_cost_delta_pct = Column(Numeric(6, 2), nullable=True)  # percentage change
    expected_quality_delta = Column(Numeric(5, 4), nullable=True)  # normalized 0..1
    confidence = Column(Numeric(5, 4), nullable=False)  # 0..1
    evidence = Column(
        JSON, nullable=False
    )  # IDs/refs to pricing/benchmarks/runtime_stats/sentiment
    proposed_patch = Column(Text, nullable=True)  # optional YAML patch or diff excerpt

    __table_args__ = (
        UniqueConstraint(
            "use_case",
            "current_model",
            "recommended_model",
            "created_at",
            name="uq_recommendation_usecase_models_created",
        ),
    )
