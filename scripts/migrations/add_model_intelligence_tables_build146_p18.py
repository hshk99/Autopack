"""
BUILD-146 Phase A P18: Database Migration - Add Model Intelligence Tables

Creates the Postgres-backed model catalog and recommendation system tables:
- models_catalog: Model identity and metadata
- model_pricing: Time-series pricing records
- model_benchmarks: Benchmark records from multiple sources
- model_runtime_stats: Aggregated telemetry from llm_usage_events
- model_sentiment_signals: Community sentiment evidence
- model_recommendations: Recommendation objects with evidence

These tables enable:
1. Single source of truth for model definitions
2. Explainable, evidence-backed model recommendations
3. No silent auto-upgrades (recommendations require approval)
4. Objective metrics (price, benchmarks, real-world telemetry)

Usage:
    python scripts/migrations/add_model_intelligence_tables_build146_p18.py upgrade
    python scripts/migrations/add_model_intelligence_tables_build146_p18.py downgrade
"""

import os
import sys
from sqlalchemy import create_engine, text, inspect
from sqlalchemy.engine import Engine


def get_database_url() -> str:
    """Get DATABASE_URL from environment (production safety requirement)."""
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise ValueError(
            "DATABASE_URL environment variable not set. "
            "Model intelligence migrations require explicit database configuration."
        )
    return db_url


def check_table_exists(engine: Engine, table_name: str) -> bool:
    """Check if a table exists in the database."""
    inspector = inspect(engine)
    return table_name in inspector.get_table_names()


def upgrade(engine: Engine) -> None:
    """Create model intelligence tables."""
    print("=" * 70)
    print("BUILD-146 Phase A P18: Add Model Intelligence Tables")
    print("=" * 70)

    with engine.begin() as conn:
        # Check if tables already exist
        if check_table_exists(engine, "models_catalog"):
            print("✓ Model intelligence tables already exist, skipping migration")
            return

        print("\n[1/6] Creating table: models_catalog")
        print("      Purpose: Model identity and metadata (SOT for model definitions)")
        conn.execute(
            text("""
            CREATE TABLE models_catalog (
                model_id VARCHAR PRIMARY KEY,
                provider VARCHAR NOT NULL,
                family VARCHAR NOT NULL,
                display_name VARCHAR NOT NULL,
                context_window_tokens INTEGER,
                notes TEXT,
                released_at TIMESTAMP WITH TIME ZONE,
                is_deprecated BOOLEAN NOT NULL DEFAULT FALSE,
                created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        )
        conn.execute(text("CREATE INDEX idx_catalog_provider ON models_catalog (provider)"))
        conn.execute(text("CREATE INDEX idx_catalog_family ON models_catalog (family)"))
        conn.execute(text("CREATE INDEX idx_catalog_deprecated ON models_catalog (is_deprecated)"))
        print("      ✓ Table 'models_catalog' created with indexes")

        print("\n[2/6] Creating table: model_pricing")
        print("      Purpose: Time-series pricing records (USD per 1K tokens)")
        conn.execute(
            text("""
            CREATE TABLE model_pricing (
                id SERIAL PRIMARY KEY,
                model_id VARCHAR NOT NULL REFERENCES models_catalog(model_id) ON DELETE CASCADE,
                input_per_1k NUMERIC(10, 6) NOT NULL,
                output_per_1k NUMERIC(10, 6) NOT NULL,
                currency VARCHAR NOT NULL DEFAULT 'USD',
                effective_at TIMESTAMP WITH TIME ZONE NOT NULL,
                source VARCHAR NOT NULL,
                source_url TEXT,
                retrieved_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT uq_pricing_model_effective_source UNIQUE (model_id, effective_at, source)
            )
        """)
        )
        conn.execute(text("CREATE INDEX idx_pricing_model ON model_pricing (model_id)"))
        conn.execute(text("CREATE INDEX idx_pricing_effective ON model_pricing (effective_at)"))
        print("      ✓ Table 'model_pricing' created with indexes")

        print("\n[3/6] Creating table: model_benchmarks")
        print("      Purpose: Benchmark records from official/third-party sources")
        conn.execute(
            text("""
            CREATE TABLE model_benchmarks (
                id SERIAL PRIMARY KEY,
                model_id VARCHAR NOT NULL REFERENCES models_catalog(model_id) ON DELETE CASCADE,
                benchmark_name VARCHAR NOT NULL,
                score NUMERIC(10, 4) NOT NULL,
                unit VARCHAR NOT NULL,
                task_type VARCHAR NOT NULL,
                dataset_version VARCHAR,
                source VARCHAR NOT NULL,
                source_url TEXT NOT NULL,
                retrieved_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT uq_benchmark_model_name_version_url UNIQUE (model_id, benchmark_name, dataset_version, source_url)
            )
        """)
        )
        conn.execute(text("CREATE INDEX idx_benchmark_model ON model_benchmarks (model_id)"))
        conn.execute(text("CREATE INDEX idx_benchmark_name ON model_benchmarks (benchmark_name)"))
        conn.execute(text("CREATE INDEX idx_benchmark_task_type ON model_benchmarks (task_type)"))
        print("      ✓ Table 'model_benchmarks' created with indexes")

        print("\n[4/6] Creating table: model_runtime_stats")
        print("      Purpose: Aggregated telemetry from llm_usage_events (rolling window)")
        conn.execute(
            text("""
            CREATE TABLE model_runtime_stats (
                id SERIAL PRIMARY KEY,
                window_start TIMESTAMP WITH TIME ZONE NOT NULL,
                window_end TIMESTAMP WITH TIME ZONE NOT NULL,
                provider VARCHAR NOT NULL,
                model VARCHAR NOT NULL,
                role VARCHAR NOT NULL,
                calls INTEGER NOT NULL DEFAULT 0,
                total_tokens BIGINT NOT NULL DEFAULT 0,
                prompt_tokens BIGINT,
                completion_tokens BIGINT,
                est_cost_usd NUMERIC(12, 6),
                success_rate NUMERIC(5, 4),
                p50_tokens BIGINT,
                p90_tokens BIGINT,
                notes TEXT,
                CONSTRAINT uq_runtime_stats_window_provider_model_role
                    UNIQUE (window_start, window_end, provider, model, role)
            )
        """)
        )
        conn.execute(
            text(
                "CREATE INDEX idx_runtime_stats_window_start ON model_runtime_stats (window_start)"
            )
        )
        conn.execute(
            text("CREATE INDEX idx_runtime_stats_window_end ON model_runtime_stats (window_end)")
        )
        conn.execute(
            text("CREATE INDEX idx_runtime_stats_provider ON model_runtime_stats (provider)")
        )
        conn.execute(text("CREATE INDEX idx_runtime_stats_model ON model_runtime_stats (model)"))
        conn.execute(text("CREATE INDEX idx_runtime_stats_role ON model_runtime_stats (role)"))
        print("      ✓ Table 'model_runtime_stats' created with indexes")

        print("\n[5/6] Creating table: model_sentiment_signals")
        print("      Purpose: Community sentiment evidence (supporting, not primary)")
        conn.execute(
            text("""
            CREATE TABLE model_sentiment_signals (
                id SERIAL PRIMARY KEY,
                model_id VARCHAR NOT NULL REFERENCES models_catalog(model_id) ON DELETE CASCADE,
                source VARCHAR NOT NULL,
                source_url TEXT NOT NULL,
                title VARCHAR,
                snippet TEXT NOT NULL,
                sentiment VARCHAR NOT NULL,
                tags JSONB,
                retrieved_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT uq_sentiment_model_url UNIQUE (model_id, source_url)
            )
        """)
        )
        conn.execute(text("CREATE INDEX idx_sentiment_model ON model_sentiment_signals (model_id)"))
        conn.execute(text("CREATE INDEX idx_sentiment_source ON model_sentiment_signals (source)"))
        conn.execute(
            text("CREATE INDEX idx_sentiment_sentiment ON model_sentiment_signals (sentiment)")
        )
        print("      ✓ Table 'model_sentiment_signals' created with indexes")

        print("\n[6/6] Creating table: model_recommendations")
        print("      Purpose: Recommendation objects with evidence references")
        conn.execute(
            text("""
            CREATE TABLE model_recommendations (
                id SERIAL PRIMARY KEY,
                created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
                status VARCHAR NOT NULL DEFAULT 'proposed',
                use_case VARCHAR NOT NULL,
                current_model VARCHAR NOT NULL,
                recommended_model VARCHAR NOT NULL,
                reasoning TEXT NOT NULL,
                expected_cost_delta_pct NUMERIC(6, 2),
                expected_quality_delta NUMERIC(5, 4),
                confidence NUMERIC(5, 4) NOT NULL,
                evidence JSONB NOT NULL,
                proposed_patch TEXT,
                CONSTRAINT uq_recommendation_usecase_models_created
                    UNIQUE (use_case, current_model, recommended_model, created_at)
            )
        """)
        )
        conn.execute(
            text("CREATE INDEX idx_recommendation_created ON model_recommendations (created_at)")
        )
        conn.execute(
            text("CREATE INDEX idx_recommendation_status ON model_recommendations (status)")
        )
        conn.execute(
            text("CREATE INDEX idx_recommendation_usecase ON model_recommendations (use_case)")
        )
        print("      ✓ Table 'model_recommendations' created with indexes")

        print("\n✓ Migration complete!")
        print("  - 6 tables created: models_catalog, model_pricing, model_benchmarks,")
        print("    model_runtime_stats, model_sentiment_signals, model_recommendations")
        print("  - All indexes and constraints applied")

    print("\n" + "=" * 70)
    print("BUILD-146 Phase A P18 Migration: SUCCESS")
    print("=" * 70)


def downgrade(engine: Engine) -> None:
    """Drop model intelligence tables."""
    print("=" * 70)
    print("BUILD-146 Phase A P18 Rollback: Remove Model Intelligence Tables")
    print("=" * 70)

    with engine.begin() as conn:
        # Check if tables exist before trying to drop
        if not check_table_exists(engine, "models_catalog"):
            print("✓ Model intelligence tables already removed, nothing to rollback")
            return

        print("\n[1/6] Dropping table: model_recommendations")
        conn.execute(text("DROP TABLE IF EXISTS model_recommendations CASCADE"))
        print("      ✓ Table 'model_recommendations' dropped")

        print("\n[2/6] Dropping table: model_sentiment_signals")
        conn.execute(text("DROP TABLE IF EXISTS model_sentiment_signals CASCADE"))
        print("      ✓ Table 'model_sentiment_signals' dropped")

        print("\n[3/6] Dropping table: model_runtime_stats")
        conn.execute(text("DROP TABLE IF EXISTS model_runtime_stats CASCADE"))
        print("      ✓ Table 'model_runtime_stats' dropped")

        print("\n[4/6] Dropping table: model_benchmarks")
        conn.execute(text("DROP TABLE IF EXISTS model_benchmarks CASCADE"))
        print("      ✓ Table 'model_benchmarks' dropped")

        print("\n[5/6] Dropping table: model_pricing")
        conn.execute(text("DROP TABLE IF EXISTS model_pricing CASCADE"))
        print("      ✓ Table 'model_pricing' dropped")

        print("\n[6/6] Dropping table: models_catalog")
        conn.execute(text("DROP TABLE IF EXISTS models_catalog CASCADE"))
        print("      ✓ Table 'models_catalog' dropped")

    print("\n" + "=" * 70)
    print("BUILD-146 Phase A P18 Rollback: SUCCESS")
    print("=" * 70)


def main():
    """Main entry point for migration script."""
    if len(sys.argv) < 2:
        print("Usage: python add_model_intelligence_tables_build146_p18.py [upgrade|downgrade]")
        sys.exit(1)

    command = sys.argv[1].lower()

    if command not in ["upgrade", "downgrade"]:
        print(f"Error: Invalid command '{command}'")
        print("Usage: python add_model_intelligence_tables_build146_p18.py [upgrade|downgrade]")
        sys.exit(1)

    try:
        db_url = get_database_url()
        print(f"\nConnecting to database: {db_url.split('@')[1] if '@' in db_url else 'local'}")

        engine = create_engine(db_url)

        # Test connection
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1"))
            result.fetchone()

        print("✓ Database connection successful\n")

        if command == "upgrade":
            upgrade(engine)
        else:
            downgrade(engine)

        print("\n✓ Migration script completed successfully")

    except Exception as e:
        print(f"\n✗ Migration failed: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
