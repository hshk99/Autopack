"""Model recommendation engine with scoring and DB persistence.

This module generates model upgrade recommendations using:
- Pricing data (objective)
- Benchmark scores (objective)
- Runtime telemetry (real-world outcomes)
- Sentiment signals (supporting evidence, low weight)

Recommendations are persisted to DB with full evidence references.
"""

from typing import Dict, List, Optional, Tuple

from sqlalchemy import and_
from sqlalchemy.orm import Session

from .models import (ModelBenchmark, ModelCatalog, ModelPricing,
                     ModelRecommendation, ModelRuntimeStats)
from .sentiment_ingest import compute_sentiment_score

# Scoring weights (per section 4.3 of plan)
WEIGHT_PRICE = 0.35
WEIGHT_BENCHMARK = 0.40
WEIGHT_RUNTIME = 0.20
WEIGHT_SENTIMENT = 0.05  # Low weight: supporting evidence only


def parse_provider_and_family(model_id: str) -> Tuple[str, str]:
    """Infer provider and family from a model_id.

    This is a lightweight helper used by ingestion/tests to keep model identifiers consistent.

    Examples:
        claude-sonnet-4-5 -> ("anthropic", "claude")
        gpt-4o            -> ("openai", "gpt")
        glm-4.7           -> ("zhipu_glm", "glm")
        gemini-2.5-flash  -> ("google", "gemini")

    Notes:
        - Prefer explicit catalog metadata when available; this is a best-effort heuristic.
        - Kept for backward compatibility with earlier BUILD-146/BUILD-147 tests/docs.
    """
    mid = (model_id or "").lower().strip()

    if mid.startswith("claude-"):
        return ("anthropic", "claude")
    if mid.startswith("gpt-") or mid.startswith("o1") or mid.startswith("o3"):
        return ("openai", "gpt")
    if mid.startswith("glm-"):
        return ("zhipu_glm", "glm")
    if mid.startswith("gemini-"):
        return ("google", "gemini")

    # Conservative fallback: unknown provider/family
    return ("unknown", "unknown")


def generate_recommendations(
    session: Session,
    use_case: str,
    current_model: str,
    max_candidates: int = 3,
) -> List[Dict[str, any]]:
    """Generate model recommendations for a use case.

    Args:
        session: Database session.
        use_case: Use case identifier (e.g., tidy_semantic, builder_low, doctor_cheap).
        current_model: Current model being used.
        max_candidates: Maximum number of candidates to return.

    Returns:
        List of recommendation dictionaries with scores and evidence.
    """
    # Get current model info
    current_catalog = session.query(ModelCatalog).filter_by(model_id=current_model).first()
    if not current_catalog:
        raise ValueError(f"Current model {current_model} not found in catalog")

    # Generate candidate models
    candidates = generate_candidates(session, current_catalog, use_case)

    # Score each candidate
    scored_candidates = []
    for candidate in candidates:
        score_data = compute_recommendation_score(
            session, current_model, candidate.model_id, use_case
        )
        scored_candidates.append(
            {
                "candidate": candidate,
                **score_data,
            }
        )

    # Sort by composite score (descending)
    scored_candidates.sort(key=lambda x: x["composite_score"], reverse=True)

    # Return top N candidates
    return scored_candidates[:max_candidates]


def generate_candidates(
    session: Session,
    current_model: ModelCatalog,
    use_case: str,
) -> List[ModelCatalog]:
    """Generate candidate models for upgrade.

    Prefers same provider/family upgrades first, then cross-provider if competitive.

    Args:
        session: Database session.
        current_model: Current model catalog entry.
        use_case: Use case identifier.

    Returns:
        List of candidate ModelCatalog entries.
    """
    candidates = []

    # Same family upgrades (e.g., glm-4.6 → glm-4.7, claude-3 → claude-4)
    same_family = (
        session.query(ModelCatalog)
        .filter(
            and_(
                ModelCatalog.provider == current_model.provider,
                ModelCatalog.family == current_model.family,
                ModelCatalog.model_id != current_model.model_id,
                not ModelCatalog.is_deprecated,
            )
        )
        .all()
    )
    candidates.extend(same_family)

    # Cross-provider candidates (if pricing is competitive)
    # For v1, only consider if same family has no upgrades
    if len(same_family) == 0:
        other_providers = (
            session.query(ModelCatalog)
            .filter(
                and_(
                    ModelCatalog.provider != current_model.provider,
                    not ModelCatalog.is_deprecated,
                )
            )
            .limit(5)  # Bounded search
            .all()
        )
        candidates.extend(other_providers)

    return candidates


def compute_recommendation_score(
    session: Session,
    current_model: str,
    candidate_model: str,
    use_case: str,
) -> Dict[str, any]:
    """Compute composite recommendation score for a candidate.

    Args:
        session: Database session.
        current_model: Current model ID.
        candidate_model: Candidate model ID.
        use_case: Use case identifier.

    Returns:
        Dictionary with score breakdown and evidence.
    """
    # Get pricing scores
    price_score, price_delta_pct, price_evidence = compute_price_score(
        session, current_model, candidate_model
    )

    # Get benchmark scores
    benchmark_score, quality_delta, benchmark_evidence = compute_benchmark_score(
        session, current_model, candidate_model
    )

    # Get runtime scores (if available)
    runtime_score, runtime_evidence = compute_runtime_score(
        session, current_model, candidate_model, use_case
    )

    # Get sentiment scores (low weight)
    sentiment_score, sentiment_evidence = compute_sentiment_score_comparison(
        session, current_model, candidate_model
    )

    # Composite score
    composite_score = (
        WEIGHT_PRICE * price_score
        + WEIGHT_BENCHMARK * benchmark_score
        + WEIGHT_RUNTIME * runtime_score
        + WEIGHT_SENTIMENT * sentiment_score
    )

    # Compute confidence (lower if runtime data unavailable)
    confidence = 0.9 if runtime_evidence else 0.6

    return {
        "composite_score": composite_score,
        "price_score": price_score,
        "benchmark_score": benchmark_score,
        "runtime_score": runtime_score,
        "sentiment_score": sentiment_score,
        "expected_cost_delta_pct": price_delta_pct,
        "expected_quality_delta": quality_delta,
        "confidence": confidence,
        "evidence": {
            "pricing": price_evidence,
            "benchmarks": benchmark_evidence,
            "runtime_stats": runtime_evidence,
            "sentiment": sentiment_evidence,
        },
    }


def compute_price_score(
    session: Session,
    current_model: str,
    candidate_model: str,
) -> Tuple[float, Optional[float], List[int]]:
    """Compute price score (higher is better, i.e., cheaper or similar cost).

    Args:
        session: Database session.
        current_model: Current model ID.
        candidate_model: Candidate model ID.

    Returns:
        Tuple of (score, delta_pct, evidence_ids).
    """
    # Get latest pricing for both models
    current_pricing = get_latest_pricing(session, current_model)
    candidate_pricing = get_latest_pricing(session, candidate_model)

    if not current_pricing or not candidate_pricing:
        return 0.5, None, []  # Neutral if pricing unavailable

    # Compute weighted average cost (input:output ratio roughly 2:1 for typical workloads)
    current_cost = float(current_pricing.input_per_1k * 2 + current_pricing.output_per_1k)
    candidate_cost = float(candidate_pricing.input_per_1k * 2 + candidate_pricing.output_per_1k)

    # Delta percentage
    delta_pct = ((candidate_cost - current_cost) / current_cost) * 100 if current_cost > 0 else 0

    # Score: 1.0 if cheaper, 0.5 if same, 0.0 if 2x more expensive
    if delta_pct <= 0:
        score = 1.0  # Cheaper is better
    elif delta_pct <= 50:
        score = 0.75  # Moderately more expensive
    elif delta_pct <= 100:
        score = 0.5  # Up to 2x more expensive
    else:
        score = 0.0  # More than 2x more expensive

    evidence = [current_pricing.id, candidate_pricing.id]
    return score, delta_pct, evidence


def compute_benchmark_score(
    session: Session,
    current_model: str,
    candidate_model: str,
) -> Tuple[float, Optional[float], List[int]]:
    """Compute benchmark score (higher is better).

    Args:
        session: Database session.
        current_model: Current model ID.
        candidate_model: Candidate model ID.

    Returns:
        Tuple of (score, quality_delta, evidence_ids).
    """
    # Get coding benchmarks (prioritize SWE-bench, HumanEval)
    current_benchmarks = get_coding_benchmarks(session, current_model)
    candidate_benchmarks = get_coding_benchmarks(session, candidate_model)

    if not current_benchmarks or not candidate_benchmarks:
        return 0.5, None, []  # Neutral if benchmarks unavailable

    # Compute average score for each
    current_avg = sum(b.score for b in current_benchmarks) / len(current_benchmarks)
    candidate_avg = sum(b.score for b in candidate_benchmarks) / len(candidate_benchmarks)

    # Quality delta (normalized 0..1)
    quality_delta = float((candidate_avg - current_avg) / max(current_avg, 1.0))

    # Score: 1.0 if 20%+ better, 0.5 if similar, 0.0 if worse
    if quality_delta >= 0.2:
        score = 1.0
    elif quality_delta >= 0:
        score = 0.75
    elif quality_delta >= -0.1:
        score = 0.5
    else:
        score = 0.0

    evidence = [b.id for b in current_benchmarks + candidate_benchmarks]
    return score, quality_delta, evidence


def compute_runtime_score(
    session: Session,
    current_model: str,
    candidate_model: str,
    use_case: str,
) -> Tuple[float, List[int]]:
    """Compute runtime score from telemetry (higher is better).

    Args:
        session: Database session.
        current_model: Current model ID.
        candidate_model: Candidate model ID.
        use_case: Use case identifier.

    Returns:
        Tuple of (score, evidence_ids).
    """
    # Infer role from use_case (e.g., builder_low → builder, doctor_cheap → doctor)
    role = infer_role_from_use_case(use_case)

    # Get latest runtime stats for both models
    current_stats = get_latest_runtime_stats(session, current_model, role)
    candidate_stats = get_latest_runtime_stats(session, candidate_model, role)

    if not current_stats:
        return 0.5, []  # Neutral if no data

    if not candidate_stats:
        return 0.5, []  # Neutral if candidate has no data

    # Compare success_rate (if available)
    if current_stats.success_rate and candidate_stats.success_rate:
        success_delta = float(candidate_stats.success_rate - current_stats.success_rate)
        if success_delta >= 0.1:
            score = 1.0  # 10%+ better success
        elif success_delta >= 0:
            score = 0.75  # Similar or slightly better
        else:
            score = 0.5  # Worse success rate
    else:
        # Fall back to cost efficiency (lower cost per token is better)
        current_eff = (
            float(current_stats.est_cost_usd / current_stats.total_tokens)
            if current_stats.est_cost_usd and current_stats.total_tokens
            else 0
        )
        candidate_eff = (
            float(candidate_stats.est_cost_usd / candidate_stats.total_tokens)
            if candidate_stats.est_cost_usd and candidate_stats.total_tokens
            else 0
        )

        if current_eff == 0 or candidate_eff == 0:
            score = 0.5
        elif candidate_eff < current_eff:
            score = 1.0  # More cost-efficient
        else:
            score = 0.5

    evidence = [current_stats.id, candidate_stats.id] if candidate_stats else [current_stats.id]
    return score, evidence


def compute_sentiment_score_comparison(
    session: Session,
    current_model: str,
    candidate_model: str,
) -> Tuple[float, List[int]]:
    """Compute sentiment score comparison (higher is better).

    Args:
        session: Database session.
        current_model: Current model ID.
        candidate_model: Candidate model ID.

    Returns:
        Tuple of (score, evidence_ids).
    """
    current_sentiment = compute_sentiment_score(session, current_model)
    candidate_sentiment = compute_sentiment_score(session, candidate_model)

    # Score based on delta
    delta = candidate_sentiment - current_sentiment
    if delta >= 0.2:
        score = 1.0
    elif delta >= 0:
        score = 0.75
    else:
        score = 0.5

    # Get evidence IDs (sentiment signal IDs)
    from .models import ModelSentimentSignal

    evidence = [
        sig.id
        for sig in session.query(ModelSentimentSignal)
        .filter(ModelSentimentSignal.model_id.in_([current_model, candidate_model]))
        .all()
    ]

    return score, evidence


# Helper functions


def get_latest_pricing(session: Session, model_id: str) -> Optional[ModelPricing]:
    """Get latest pricing record for a model."""
    return (
        session.query(ModelPricing)
        .filter(ModelPricing.model_id == model_id)
        .order_by(ModelPricing.effective_at.desc())
        .first()
    )


def get_coding_benchmarks(session: Session, model_id: str) -> List[ModelBenchmark]:
    """Get coding-related benchmarks for a model."""
    return (
        session.query(ModelBenchmark)
        .filter(
            and_(
                ModelBenchmark.model_id == model_id,
                ModelBenchmark.task_type.in_(["code", "reasoning"]),
            )
        )
        .all()
    )


def get_latest_runtime_stats(
    session: Session, model: str, role: str
) -> Optional[ModelRuntimeStats]:
    """Get latest runtime stats for a model and role."""
    return (
        session.query(ModelRuntimeStats)
        .filter(
            and_(
                ModelRuntimeStats.model == model,
                ModelRuntimeStats.role == role,
            )
        )
        .order_by(ModelRuntimeStats.window_end.desc())
        .first()
    )


def infer_role_from_use_case(use_case: str) -> str:
    """Infer role from use case identifier.

    Args:
        use_case: Use case identifier (e.g., tidy_semantic, builder_low, doctor_cheap).

    Returns:
        Role string (builder, auditor, doctor, etc.).
    """
    if "builder" in use_case:
        return "builder"
    elif "auditor" in use_case:
        return "auditor"
    elif "doctor" in use_case:
        return "doctor"
    elif "tidy" in use_case:
        return "tidy"
    else:
        return "builder"  # Default


def persist_recommendation(
    session: Session,
    use_case: str,
    current_model: str,
    recommended_model: str,
    reasoning: str,
    score_data: Dict[str, any],
) -> ModelRecommendation:
    """Persist recommendation to database.

    Args:
        session: Database session.
        use_case: Use case identifier.
        current_model: Current model ID.
        recommended_model: Recommended model ID.
        reasoning: Human-readable rationale.
        score_data: Score data from compute_recommendation_score.

    Returns:
        Created ModelRecommendation instance.
    """
    recommendation = ModelRecommendation(
        use_case=use_case,
        current_model=current_model,
        recommended_model=recommended_model,
        reasoning=reasoning,
        expected_cost_delta_pct=score_data.get("expected_cost_delta_pct"),
        expected_quality_delta=score_data.get("expected_quality_delta"),
        confidence=score_data.get("confidence", 0.5),
        evidence=score_data.get("evidence", {}),
        status="proposed",
    )
    session.add(recommendation)
    session.commit()
    return recommendation
