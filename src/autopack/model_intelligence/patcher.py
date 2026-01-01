"""YAML patcher: Generate proposed config patches for approved recommendations.

This module generates YAML patches for config/models.yaml based on accepted
model recommendations.
"""

from pathlib import Path
from typing import Dict, List, Optional

import yaml
from sqlalchemy.orm import Session

from .models import ModelRecommendation


def generate_patch_for_recommendation(
    session: Session,
    recommendation_id: int,
    models_yaml_path: Optional[str] = None,
) -> str:
    """Generate YAML patch for a recommendation.

    Args:
        session: Database session.
        recommendation_id: Recommendation ID.
        models_yaml_path: Path to models.yaml (defaults to config/models.yaml).

    Returns:
        YAML patch as string.
    """
    # Get recommendation
    recommendation = (
        session.query(ModelRecommendation).filter_by(id=recommendation_id).first()
    )
    if not recommendation:
        raise ValueError(f"Recommendation {recommendation_id} not found")

    # Load current models.yaml
    if models_yaml_path is None:
        repo_root = Path(__file__).resolve().parents[3]
        models_yaml_path = str(repo_root / "config" / "models.yaml")

    with open(models_yaml_path, "r", encoding="utf-8") as f:
        models_config = yaml.safe_load(f)

    # Apply replacement based on use_case
    use_case = recommendation.use_case
    current_model = recommendation.current_model
    recommended_model = recommendation.recommended_model

    patch_lines = []
    patch_lines.append(f"# Recommendation ID: {recommendation_id}")
    patch_lines.append(f"# Use case: {use_case}")
    patch_lines.append(f"# Change: {current_model} → {recommended_model}")
    patch_lines.append(f"# Reasoning: {recommendation.reasoning}")
    patch_lines.append("")

    # Determine which section to patch
    if use_case.startswith("tidy_"):
        # tool_models section
        tool_key = use_case.replace("_", "_")
        if "tool_models" in models_config and tool_key in models_config["tool_models"]:
            patch_lines.append(f"tool_models:")
            patch_lines.append(f"  {tool_key}: {recommended_model}")
    elif use_case.startswith("builder_") or use_case.startswith("auditor_"):
        # complexity_models section
        parts = use_case.split("_")
        role = parts[0]  # builder or auditor
        tier = parts[1] if len(parts) > 1 else "low"  # low, medium, high

        if "complexity_models" in models_config and tier in models_config["complexity_models"]:
            patch_lines.append(f"complexity_models:")
            patch_lines.append(f"  {tier}:")
            patch_lines.append(f"    {role}: {recommended_model}")
    elif use_case.startswith("doctor_"):
        # doctor_models section
        doctor_tier = use_case.replace("doctor_", "")  # cheap or strong

        if "doctor_models" in models_config:
            patch_lines.append(f"doctor_models:")
            patch_lines.append(f"  {doctor_tier}: {recommended_model}")
    else:
        # Generic replacement - find and replace
        patch_lines.append(f"# Manual replacement needed for use case: {use_case}")
        patch_lines.append(f"# Search for '{current_model}' and replace with '{recommended_model}'")

    return "\n".join(patch_lines)


def apply_recommendations_batch(
    session: Session,
    recommendation_ids: List[int],
    models_yaml_path: Optional[str] = None,
) -> Dict[str, any]:
    """Apply multiple recommendations to generate a combined patch.

    Args:
        session: Database session.
        recommendation_ids: List of recommendation IDs to apply.
        models_yaml_path: Path to models.yaml (defaults to config/models.yaml).

    Returns:
        Dictionary with patch content and metadata.
    """
    if models_yaml_path is None:
        repo_root = Path(__file__).resolve().parents[3]
        models_yaml_path = str(repo_root / "config" / "models.yaml")

    # Load current models.yaml
    with open(models_yaml_path, "r", encoding="utf-8") as f:
        models_config = yaml.safe_load(f)

    # Track changes
    changes = []

    for rec_id in recommendation_ids:
        recommendation = (
            session.query(ModelRecommendation).filter_by(id=rec_id).first()
        )
        if not recommendation:
            continue

        changes.append({
            "recommendation_id": rec_id,
            "use_case": recommendation.use_case,
            "current_model": recommendation.current_model,
            "recommended_model": recommendation.recommended_model,
            "reasoning": recommendation.reasoning,
        })

        # Apply change to models_config
        use_case = recommendation.use_case
        current_model = recommendation.current_model
        recommended_model = recommendation.recommended_model

        if use_case.startswith("tidy_"):
            tool_key = use_case
            if "tool_models" in models_config and tool_key in models_config["tool_models"]:
                models_config["tool_models"][tool_key] = recommended_model

        elif use_case.startswith("builder_") or use_case.startswith("auditor_"):
            parts = use_case.split("_")
            role = parts[0]
            tier = parts[1] if len(parts) > 1 else "low"

            if "complexity_models" in models_config and tier in models_config["complexity_models"]:
                models_config["complexity_models"][tier][role] = recommended_model

        elif use_case.startswith("doctor_"):
            doctor_tier = use_case.replace("doctor_", "")
            if "doctor_models" in models_config:
                models_config["doctor_models"][doctor_tier] = recommended_model

    # Generate YAML output
    patched_yaml = yaml.dump(models_config, sort_keys=False, default_flow_style=False)

    return {
        "changes": changes,
        "patched_yaml": patched_yaml,
    }


def format_recommendation_report(
    session: Session,
    recommendation_id: int,
) -> str:
    """Format a human-readable recommendation report.

    Args:
        session: Database session.
        recommendation_id: Recommendation ID.

    Returns:
        Formatted report string.
    """
    recommendation = (
        session.query(ModelRecommendation).filter_by(id=recommendation_id).first()
    )
    if not recommendation:
        raise ValueError(f"Recommendation {recommendation_id} not found")

    lines = []
    lines.append("=" * 70)
    lines.append(f"Model Recommendation Report (ID: {recommendation_id})")
    lines.append("=" * 70)
    lines.append("")
    lines.append(f"Use Case:         {recommendation.use_case}")
    lines.append(f"Current Model:    {recommendation.current_model}")
    lines.append(f"Recommended:      {recommendation.recommended_model}")
    lines.append(f"Status:           {recommendation.status}")
    lines.append(f"Confidence:       {recommendation.confidence:.2%}")
    lines.append("")
    lines.append("Reasoning:")
    lines.append(f"  {recommendation.reasoning}")
    lines.append("")

    if recommendation.expected_cost_delta_pct is not None:
        delta = float(recommendation.expected_cost_delta_pct)
        sign = "+" if delta > 0 else ""
        lines.append(f"Expected Cost Change:    {sign}{delta:.1f}%")

    if recommendation.expected_quality_delta is not None:
        quality = float(recommendation.expected_quality_delta)
        sign = "+" if quality > 0 else ""
        lines.append(f"Expected Quality Change: {sign}{quality:.2%}")

    lines.append("")
    lines.append("Evidence:")

    evidence = recommendation.evidence or {}
    if evidence.get("pricing"):
        lines.append(f"  - Pricing records: {len(evidence['pricing'])} references")
    if evidence.get("benchmarks"):
        lines.append(f"  - Benchmark records: {len(evidence['benchmarks'])} references")
    if evidence.get("runtime_stats"):
        lines.append(f"  - Runtime stats: {len(evidence['runtime_stats'])} references")
    if evidence.get("sentiment"):
        lines.append(f"  - Sentiment signals: {len(evidence['sentiment'])} references")

    lines.append("")
    lines.append("=" * 70)

    return "\n".join(lines)
