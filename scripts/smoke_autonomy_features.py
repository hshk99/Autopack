#!/usr/bin/env python3
"""Smoke test for Autopack autonomy features (BUILD-146 P17.3).

Validates that the environment is correctly configured for autonomous execution.
No LLM calls are made - this is a fast, deterministic health check.

Usage:
    python scripts/smoke_autonomy_features.py

Exit Codes:
    0: GO - All checks passed
    1: NO-GO - Critical failures detected
"""

import os
import sys
from pathlib import Path
from typing import Dict, List, Tuple

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def check_env_var(var_name: str, required: bool = False) -> Tuple[bool, str]:
    """Check if environment variable is set.

    Args:
        var_name: Name of environment variable
        required: Whether variable is required

    Returns:
        (success, message) tuple
    """
    value = os.getenv(var_name)
    if value:
        # Mask sensitive values
        if "KEY" in var_name or "TOKEN" in var_name:
            display_value = f"{value[:8]}..." if len(value) > 8 else "***"
        else:
            display_value = value
        return True, f"✓ {var_name}={display_value}"
    else:
        if required:
            return False, f"✗ {var_name} is REQUIRED but not set"
        else:
            return True, f"○ {var_name} not set (optional)"


def check_database_reachable() -> Tuple[bool, str]:
    """Check if database is reachable.

    Returns:
        (success, message) tuple
    """
    try:
        from autopack.database import SessionLocal
        from autopack.models import Run

        # Attempt to connect and query
        db = SessionLocal()
        try:
            # Simple query to verify DB is accessible
            count = db.query(Run).count()
            return True, f"✓ Database reachable ({count} runs found)"
        finally:
            db.close()
    except Exception as e:
        return False, f"✗ Database connection failed: {e}"


def check_database_schema() -> Tuple[bool, str]:
    """Check if database schema has required tables.

    Returns:
        (success, message) tuple
    """
    try:
        from autopack.database import SessionLocal
        from sqlalchemy import inspect

        db = SessionLocal()
        try:
            inspector = inspect(db.bind)
            tables = inspector.get_table_names()

            required_tables = [
                "runs",
                "tiers",
                "phases",
                "llm_usage_events",
                "token_efficiency_metrics",
                "phase6_metrics",
            ]

            missing_tables = [t for t in required_tables if t not in tables]

            if missing_tables:
                return False, f"✗ Missing DB tables: {', '.join(missing_tables)}"
            else:
                return True, f"✓ All required tables present ({len(required_tables)} tables)"
        finally:
            db.close()
    except Exception as e:
        return False, f"✗ Schema check failed: {e}"


def check_feature_toggles() -> Dict[str, bool]:
    """Check which features are enabled.

    Returns:
        Dict mapping feature name to enabled status
    """
    from autopack.config import settings

    return {
        "Telemetry Recording": getattr(settings, "telemetry_db_enabled", False),
        "History Pack": settings.artifact_history_pack_enabled,
        "SOT Substitution": settings.artifact_substitute_sot_docs,
        "Extended Contexts": settings.artifact_extended_contexts_enabled,
    }


def check_memory_backend() -> Tuple[bool, str]:
    """Check memory backend configuration.

    Returns:
        (success, message) tuple
    """
    try:
        from autopack.config import settings

        # Check if Qdrant is configured
        qdrant_host = os.getenv("QDRANT_HOST")
        embedding_model = os.getenv("EMBEDDING_MODEL")

        if qdrant_host and embedding_model:
            return True, f"✓ Memory backend configured (Qdrant: {qdrant_host})"
        else:
            return True, "○ Memory backend not configured (will use fallback)"
    except Exception as e:
        return False, f"✗ Memory backend check failed: {e}"


def main():
    """Run smoke tests and report results."""
    print("=" * 70)
    print("AUTOPACK AUTONOMY FEATURES SMOKE TEST")
    print("BUILD-146 Phase A P17.3")
    print("=" * 70)
    print()

    all_passed = True
    critical_failures: List[str] = []
    warnings: List[str] = []

    # 1. Check LLM Provider Keys
    print("1. LLM Provider Configuration")
    print("-" * 70)

    llm_checks = [
        ("GLM_API_KEY", True),  # Primary provider
        ("GLM_API_BASE", False),
        ("ANTHROPIC_API_KEY", False),  # Fallback
        ("OPENAI_API_KEY", False),  # Fallback
    ]

    has_llm_key = False
    for var, required in llm_checks:
        passed, msg = check_env_var(var, required)
        print(f"  {msg}")
        if not passed:
            critical_failures.append(msg)
            all_passed = False
        if passed and "KEY" in var and os.getenv(var):
            has_llm_key = True

    if not has_llm_key:
        msg = "No LLM provider keys found (GLM, Anthropic, or OpenAI required)"
        print(f"  ✗ {msg}")
        critical_failures.append(msg)
        all_passed = False

    print()

    # 2. Check API Configuration
    print("2. API Configuration")
    print("-" * 70)

    api_checks = [
        ("AUTOPACK_API_URL", False),
        ("AUTOPACK_API_KEY", False),
    ]

    for var, required in api_checks:
        passed, msg = check_env_var(var, required)
        print(f"  {msg}")
        if not passed and required:
            critical_failures.append(msg)
            all_passed = False

    print()

    # 3. Check Database
    print("3. Database Status")
    print("-" * 70)

    db_reachable, db_msg = check_database_reachable()
    print(f"  {db_msg}")
    if not db_reachable:
        critical_failures.append(db_msg)
        all_passed = False

    if db_reachable:
        schema_ok, schema_msg = check_database_schema()
        print(f"  {schema_msg}")
        if not schema_ok:
            critical_failures.append(schema_msg)
            all_passed = False

    print()

    # 4. Check Feature Toggles
    print("4. Feature Toggles")
    print("-" * 70)

    features = check_feature_toggles()
    for feature, enabled in features.items():
        status = "✓ ENABLED" if enabled else "○ disabled"
        print(f"  {status}: {feature}")

        # Warn if telemetry is disabled in production
        if feature == "Telemetry Recording" and not enabled:
            msg = "Telemetry disabled - no metrics will be collected"
            warnings.append(msg)

    print()

    # 5. Check Memory Backend
    print("5. Memory Backend")
    print("-" * 70)

    memory_ok, memory_msg = check_memory_backend()
    print(f"  {memory_msg}")
    if not memory_ok:
        # Memory backend is optional, so this is a warning not a critical failure
        warnings.append(memory_msg)

    print()

    # 6. Summary
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)

    if critical_failures:
        print(f"✗ NO-GO: {len(critical_failures)} critical failure(s) detected")
        print()
        for failure in critical_failures:
            print(f"  • {failure}")
        print()
        sys.exit(1)

    if warnings:
        print(f"⚠ GO (with warnings): {len(warnings)} warning(s)")
        print()
        for warning in warnings:
            print(f"  • {warning}")
        print()
    else:
        print("✓ GO: All checks passed")
        print()

    # Print recommended next steps
    print("NEXT STEPS")
    print("-" * 70)

    enabled_features = [k for k, v in features.items() if v]
    if not enabled_features:
        print("  Stage 0: Baseline (No autonomy features enabled)")
        print("  → Run: pytest -m 'not research and not aspirational'")
    elif features["Telemetry Recording"] and not features["History Pack"]:
        print("  Stage 1: Telemetry-Only")
        print("  → Safe to run with telemetry collection")
    elif features["History Pack"] and features["SOT Substitution"] and not features["Extended Contexts"]:
        print("  Stage 2: History Pack + SOT Substitution")
        print("  → Monitor token savings from artifacts")
    elif features["Extended Contexts"]:
        print("  Stage 3: Full Autonomy Features")
        print("  → Monitor all telemetry metrics")
    else:
        print("  Custom configuration detected")

    print()
    print("  See: docs/PRODUCTION_ROLLOUT_CHECKLIST.md for full rollout guide")
    print()

    sys.exit(0)


if __name__ == "__main__":
    main()
