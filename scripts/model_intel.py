"""Model Intelligence CLI - Model catalog and recommendation system.

This CLI provides commands to manage the Postgres-backed model catalog and
generate evidence-based model recommendations.

Commands:
- ingest-catalog: Load models from config/models.yaml and config/pricing.yaml
- compute-runtime-stats: Aggregate llm_usage_events into model_runtime_stats
- ingest-sentiment: Add sentiment signals from URLs
- recommend: Generate recommendations for a use case
- report: Display latest recommendations
- propose-patch: Generate YAML patch for a recommendation
- refresh-all: Refresh catalog + runtime stats in one command

Usage:
    python scripts/model_intel.py ingest-catalog
    python scripts/model_intel.py compute-runtime-stats --window-days 30
    python scripts/model_intel.py ingest-sentiment --model glm-4.7 --source reddit --url <url> --snippet "..." --sentiment positive
    python scripts/model_intel.py recommend --use-case tidy_semantic
    python scripts/model_intel.py report --latest
    python scripts/model_intel.py propose-patch --recommendation-id <id>
    python scripts/model_intel.py refresh-all --window-days 30
"""

import argparse
import sys
from pathlib import Path

# Add src to path
repo_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(repo_root / "src"))

from autopack.model_intelligence.db import get_model_intelligence_session
from autopack.model_intelligence.catalog_ingest import ingest_all
from autopack.model_intelligence.runtime_stats import compute_runtime_stats
from autopack.model_intelligence.sentiment_ingest import ingest_sentiment_signal
from autopack.model_intelligence.recommender import (
    generate_recommendations,
    persist_recommendation,
)
from autopack.model_intelligence.patcher import (
    generate_patch_for_recommendation,
    format_recommendation_report,
)
from autopack.model_intelligence.models import ModelRecommendation


def cmd_ingest_catalog(args):
    """Ingest catalog from models.yaml and pricing.yaml."""
    print("=" * 70)
    print("Model Intelligence: Ingest Catalog")
    print("=" * 70)

    try:
        results = ingest_all()
        print(f"\n✓ Catalog ingestion complete:")
        print(f"  - Models ingested: {results['catalog']}")
        print(f"  - Pricing records ingested: {results['pricing']}")
    except Exception as e:
        print(f"\n✗ Catalog ingestion failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


def cmd_compute_runtime_stats(args):
    """Compute runtime statistics from telemetry."""
    print("=" * 70)
    print("Model Intelligence: Compute Runtime Stats")
    print("=" * 70)

    try:
        with get_model_intelligence_session() as session:
            count = compute_runtime_stats(session, window_days=args.window_days)
            print(f"\n✓ Runtime stats computation complete:")
            print(f"  - Stats records created: {count}")
            print(f"  - Window: {args.window_days} days")
    except Exception as e:
        print(f"\n✗ Runtime stats computation failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


def cmd_ingest_sentiment(args):
    """Ingest a sentiment signal."""
    print("=" * 70)
    print("Model Intelligence: Ingest Sentiment Signal")
    print("=" * 70)

    try:
        with get_model_intelligence_session() as session:
            was_created = ingest_sentiment_signal(
                session,
                model_id=args.model,
                source=args.source,
                source_url=args.url,
                snippet=args.snippet,
                sentiment=args.sentiment,
                title=args.title,
                tags=None,  # TODO: Support tags via JSON arg
            )
            if was_created:
                print(f"\n✓ Sentiment signal created for {args.model}")
            else:
                print(f"\n✓ Sentiment signal updated for {args.model}")
    except Exception as e:
        print(f"\n✗ Sentiment ingestion failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


def cmd_recommend(args):
    """Generate recommendations for a use case."""
    print("=" * 70)
    print(f"Model Intelligence: Generate Recommendations")
    print(f"Use Case: {args.use_case}")
    print("=" * 70)

    try:
        with get_model_intelligence_session() as session:
            # Generate recommendations
            candidates = generate_recommendations(
                session,
                use_case=args.use_case,
                current_model=args.current_model,
                max_candidates=args.max_candidates,
            )

            if not candidates:
                print(f"\n✗ No recommendations found for use case: {args.use_case}")
                sys.exit(1)

            print(f"\n✓ Found {len(candidates)} recommendation(s):\n")

            for i, candidate in enumerate(candidates, 1):
                model = candidate["candidate"]
                print(f"[{i}] {model.model_id}")
                print(f"    Provider: {model.provider}")
                print(f"    Composite Score: {candidate['composite_score']:.3f}")
                print(f"    Confidence: {candidate['confidence']:.2%}")
                print(f"    Cost Delta: {candidate.get('expected_cost_delta_pct', 'N/A')}")
                print(f"    Quality Delta: {candidate.get('expected_quality_delta', 'N/A')}")
                print()

                # Persist recommendation if --persist flag set
                if args.persist and i == 1:
                    reasoning = (
                        f"Recommended {model.model_id} for {args.use_case}. "
                        f"Composite score: {candidate['composite_score']:.3f}. "
                        f"Evidence: pricing, benchmarks, runtime stats, sentiment."
                    )
                    rec = persist_recommendation(
                        session,
                        use_case=args.use_case,
                        current_model=args.current_model,
                        recommended_model=model.model_id,
                        reasoning=reasoning,
                        score_data=candidate,
                    )
                    print(f"    ✓ Recommendation persisted (ID: {rec.id})")

    except Exception as e:
        print(f"\n✗ Recommendation generation failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


def cmd_report(args):
    """Display latest recommendations."""
    print("=" * 70)
    print("Model Intelligence: Recommendation Report")
    print("=" * 70)

    try:
        with get_model_intelligence_session() as session:
            query = session.query(ModelRecommendation).order_by(
                ModelRecommendation.created_at.desc()
            )

            if args.use_case:
                query = query.filter(ModelRecommendation.use_case == args.use_case)
            if args.status:
                query = query.filter(ModelRecommendation.status == args.status)

            recommendations = query.limit(args.limit).all()

            if not recommendations:
                print("\n✗ No recommendations found")
                sys.exit(1)

            print(f"\n✓ Found {len(recommendations)} recommendation(s):\n")

            for rec in recommendations:
                print(f"ID: {rec.id}")
                print(f"  Use Case: {rec.use_case}")
                print(f"  Current → Recommended: {rec.current_model} → {rec.recommended_model}")
                print(f"  Status: {rec.status}")
                print(f"  Confidence: {rec.confidence:.2%}")
                print(f"  Created: {rec.created_at.isoformat()}")
                print()

    except Exception as e:
        print(f"\n✗ Report generation failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


def cmd_propose_patch(args):
    """Generate YAML patch for a recommendation."""
    print("=" * 70)
    print(f"Model Intelligence: Propose Patch (ID: {args.recommendation_id})")
    print("=" * 70)

    try:
        with get_model_intelligence_session() as session:
            # Generate report
            report = format_recommendation_report(session, args.recommendation_id)
            print(report)

            # Generate patch
            patch = generate_patch_for_recommendation(session, args.recommendation_id)
            print("\nProposed YAML Patch:")
            print("-" * 70)
            print(patch)
            print("-" * 70)

            # Optionally write to file
            if args.output:
                with open(args.output, "w", encoding="utf-8") as f:
                    f.write(patch)
                print(f"\n✓ Patch written to: {args.output}")

    except Exception as e:
        print(f"\n✗ Patch generation failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


def cmd_refresh_all(args):
    """Refresh all model intelligence data (catalog + runtime stats)."""
    print("=" * 70)
    print("Model Intelligence: Refresh All")
    print("=" * 70)

    # Step 1: Ingest catalog
    print("\n[1/2] Ingesting catalog...")
    try:
        results = ingest_all()
        print(f"  ✓ Models ingested: {results['catalog']}")
        print(f"  ✓ Pricing records ingested: {results['pricing']}")
    except Exception as e:
        print(f"  ✗ Catalog ingestion failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    # Step 2: Compute runtime stats
    print(f"\n[2/2] Computing runtime stats (window: {args.window_days} days)...")
    try:
        with get_model_intelligence_session() as session:
            count = compute_runtime_stats(session, window_days=args.window_days)
            print(f"  ✓ Stats records created: {count}")
    except Exception as e:
        print(f"  ✗ Runtime stats computation failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    print("\n✓ Refresh complete!")
    print(f"  - Next steps:")
    print(f"    • Review recommendations: python scripts/model_intel.py report --latest")
    print(f"    • Generate new recommendations: python scripts/model_intel.py recommend --use-case <use_case> --current-model <model>")


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Model Intelligence CLI - Model catalog and recommendation system"
    )
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # ingest-catalog command
    parser_ingest = subparsers.add_parser(
        "ingest-catalog", help="Ingest models and pricing from YAML configs"
    )

    # compute-runtime-stats command
    parser_stats = subparsers.add_parser(
        "compute-runtime-stats", help="Compute runtime stats from telemetry"
    )
    parser_stats.add_argument(
        "--window-days", type=int, default=30, help="Rolling window in days (default: 30)"
    )

    # ingest-sentiment command
    parser_sentiment = subparsers.add_parser(
        "ingest-sentiment", help="Ingest a sentiment signal"
    )
    parser_sentiment.add_argument("--model", required=True, help="Model ID")
    parser_sentiment.add_argument(
        "--source", required=True, help="Source type (reddit, hn, twitter, blog)"
    )
    parser_sentiment.add_argument("--url", required=True, help="Source URL")
    parser_sentiment.add_argument("--snippet", required=True, help="Quote or summary")
    parser_sentiment.add_argument(
        "--sentiment",
        required=True,
        choices=["positive", "neutral", "negative", "mixed"],
        help="Sentiment label",
    )
    parser_sentiment.add_argument("--title", help="Optional title")

    # recommend command
    parser_recommend = subparsers.add_parser(
        "recommend", help="Generate recommendations for a use case"
    )
    parser_recommend.add_argument("--use-case", required=True, help="Use case identifier")
    parser_recommend.add_argument("--current-model", required=True, help="Current model ID")
    parser_recommend.add_argument(
        "--max-candidates", type=int, default=3, help="Max candidates (default: 3)"
    )
    parser_recommend.add_argument(
        "--persist", action="store_true", help="Persist top recommendation to DB"
    )

    # report command
    parser_report = subparsers.add_parser(
        "report", help="Display latest recommendations"
    )
    parser_report.add_argument("--use-case", help="Filter by use case")
    parser_report.add_argument("--status", help="Filter by status")
    parser_report.add_argument("--limit", type=int, default=10, help="Max records (default: 10)")
    parser_report.add_argument("--latest", action="store_true", help="Show latest only")

    # propose-patch command
    parser_patch = subparsers.add_parser(
        "propose-patch", help="Generate YAML patch for a recommendation"
    )
    parser_patch.add_argument("--recommendation-id", type=int, required=True, help="Recommendation ID")
    parser_patch.add_argument("--output", help="Write patch to file")

    # refresh-all command
    parser_refresh = subparsers.add_parser(
        "refresh-all", help="Refresh all model intelligence data (catalog + runtime stats)"
    )
    parser_refresh.add_argument(
        "--window-days", type=int, default=30, help="Rolling window in days for runtime stats (default: 30)"
    )

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    # Dispatch to command handler
    if args.command == "ingest-catalog":
        cmd_ingest_catalog(args)
    elif args.command == "compute-runtime-stats":
        cmd_compute_runtime_stats(args)
    elif args.command == "ingest-sentiment":
        cmd_ingest_sentiment(args)
    elif args.command == "recommend":
        cmd_recommend(args)
    elif args.command == "report":
        cmd_report(args)
    elif args.command == "propose-patch":
        cmd_propose_patch(args)
    elif args.command == "refresh-all":
        cmd_refresh_all(args)


if __name__ == "__main__":
    main()
