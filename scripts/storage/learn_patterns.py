"""
Pattern Learning CLI (BUILD-151 Phase 4)

Analyze approval history and suggest learned policy rules.

Usage:
    # Analyze patterns and suggest rules
    python scripts/storage/learn_patterns.py analyze

    # Analyze specific category
    python scripts/storage/learn_patterns.py analyze --category dev_caches

    # List pending learned rules
    python scripts/storage/learn_patterns.py list

    # Approve a learned rule
    python scripts/storage/learn_patterns.py approve 42 --by user@example.com

    # Reject a learned rule
    python scripts/storage/learn_patterns.py reject 42 --by user@example.com --reason "Too aggressive"

    # Get recommendations
    python scripts/storage/learn_patterns.py recommend

    # Full workflow: analyze → create rules → review
    python scripts/storage/learn_patterns.py workflow
"""

import sys
import argparse
import json
from pathlib import Path
from typing import List

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / 'src'))

from autopack.database import SessionLocal
from autopack.storage_optimizer import load_policy
from autopack.storage_optimizer.approval_pattern_analyzer import ApprovalPatternAnalyzer, Pattern
from autopack.storage_optimizer.recommendation_engine import RecommendationEngine
from autopack.models import LearnedRule


def analyze_patterns(args):
    """Analyze approval patterns and display detected patterns."""
    session = SessionLocal()

    try:
        policy = load_policy()
        analyzer = ApprovalPatternAnalyzer(
            db=session,
            policy=policy,
            min_samples=args.min_samples,
            min_confidence=args.min_confidence
        )

        print(f"\nAnalyzing approval patterns...")
        if args.category:
            print(f"  Category filter: {args.category}")

        patterns = analyzer.analyze_approval_patterns(
            category=args.category,
            max_patterns=args.max_patterns
        )

        if not patterns:
            print("\n✗ No patterns detected")
            print("  Need more approval history data (minimum 5 approvals per pattern)")
            return 1

        print(f"\n{'='*100}")
        print(f"Found {len(patterns)} patterns:")
        print(f"{'='*100}\n")

        for i, pattern in enumerate(patterns, 1):
            print(f"{i}. [{pattern.pattern_type}] {pattern.description}")
            print(f"   Category: {pattern.category}")
            print(f"   Confidence: {pattern.confidence:.1%} ({pattern.approvals} approvals, {pattern.rejections} rejections)")
            print(f"   Pattern: {pattern.pattern_value}")
            print(f"   Sample paths:")
            for path in pattern.sample_paths[:3]:
                print(f"     - {path}")
            print()

        # Option to create learned rules
        if not args.non_interactive:
            create = input(f"\nCreate learned rules from these patterns? [y/N]: ").lower()

            if create == 'y':
                reviewed_by = input("Enter your name/email: ").strip()

                if not reviewed_by:
                    print("✗ Reviewer name required")
                    return 1

                for pattern in patterns:
                    rule = analyzer.create_learned_rule(pattern, reviewed_by)
                    print(f"✓ Created learned rule #{rule.id}: {rule.description}")

                print(f"\n✓ Created {len(patterns)} learned rules")
                print(f"  Review with: python scripts/storage/learn_patterns.py list")

        return 0

    finally:
        session.close()


def list_rules(args):
    """List learned rules."""
    session = SessionLocal()

    try:
        query = session.query(LearnedRule)

        if args.status:
            query = query.filter(LearnedRule.status == args.status)

        rules = query.order_by(
            LearnedRule.confidence_score.desc(),
            LearnedRule.created_at.desc()
        ).all()

        if not rules:
            print(f"\n✗ No learned rules found")
            if args.status:
                print(f"  (status filter: {args.status})")
            return 1

        print(f"\n{'='*100}")
        print(f"Learned Rules ({len(rules)} total):")
        print(f"{'='*100}\n")

        for rule in rules:
            status_emoji = {
                'pending': '⏳',
                'approved': '✅',
                'rejected': '❌',
                'applied': '🎯'
            }.get(rule.status, '?')

            print(f"{status_emoji} Rule #{rule.id} - {rule.description}")
            print(f"   Status: {rule.status}")
            print(f"   Category: {rule.suggested_category}")
            print(f"   Confidence: {rule.confidence_score:.1%}")
            print(f"   Pattern: [{rule.pattern_type}] {rule.pattern_value}")
            print(f"   Evidence: {rule.based_on_approvals} approvals, {rule.based_on_rejections} rejections")

            if rule.reviewed_by:
                print(f"   Reviewed by: {rule.reviewed_by}")
            if rule.reviewed_at:
                print(f"   Reviewed at: {rule.reviewed_at}")
            if rule.notes:
                print(f"   Notes: {rule.notes}")

            print()

        return 0

    finally:
        session.close()


def approve_rule(args):
    """Approve a learned rule."""
    session = SessionLocal()

    try:
        policy = load_policy()
        analyzer = ApprovalPatternAnalyzer(db=session, policy=policy)

        rule = analyzer.approve_rule(args.rule_id, args.by)

        print(f"\n✓ Approved learned rule #{rule.id}")
        print(f"  Description: {rule.description}")
        print(f"  Status: {rule.status}")
        print(f"  Reviewed by: {rule.reviewed_by}")

        return 0

    except ValueError as e:
        print(f"\n✗ Error: {e}")
        return 1
    finally:
        session.close()


def reject_rule(args):
    """Reject a learned rule."""
    session = SessionLocal()

    try:
        policy = load_policy()
        analyzer = ApprovalPatternAnalyzer(db=session, policy=policy)

        rule = analyzer.reject_rule(args.rule_id, args.by, args.reason)

        print(f"\n✓ Rejected learned rule #{rule.id}")
        print(f"  Description: {rule.description}")
        print(f"  Status: {rule.status}")
        print(f"  Reviewed by: {rule.reviewed_by}")
        print(f"  Reason: {rule.notes}")

        return 0

    except ValueError as e:
        print(f"\n✗ Error: {e}")
        return 1
    finally:
        session.close()


def get_recommendations(args):
    """Get strategic recommendations."""
    session = SessionLocal()

    try:
        policy = load_policy()
        engine = RecommendationEngine(db=session, policy=policy)

        print(f"\nGenerating recommendations...")
        print(f"  Lookback period: {args.lookback_days} days")

        recommendations = engine.generate_recommendations(
            max_recommendations=args.max_recommendations,
            lookback_days=args.lookback_days
        )

        stats = engine.get_scan_statistics(lookback_days=args.lookback_days)

        print(f"\n{'='*100}")
        print(f"Scan Statistics:")
        print(f"{'='*100}")
        print(f"  Scans analyzed: {stats['scan_count']}")
        print(f"  Date range: {stats.get('date_range_days', 0)} days")
        print(f"  Total candidates: {stats.get('total_candidates', 0):,}")
        print(f"  Potential savings: {stats.get('total_potential_savings_gb', 0):.2f} GB")

        if not recommendations:
            print(f"\n✗ No recommendations generated")
            print(f"  Need at least 2 scans to generate recommendations")
            return 1

        print(f"\n{'='*100}")
        print(f"Recommendations ({len(recommendations)} total):")
        print(f"{'='*100}\n")

        priority_emoji = {
            'high': '🔴',
            'medium': '🟡',
            'low': '🟢'
        }

        for i, rec in enumerate(recommendations, 1):
            emoji = priority_emoji.get(rec.priority, '⚪')

            print(f"{emoji} {i}. {rec.title} [{rec.priority.upper()}]")
            print(f"   {rec.description}")
            print(f"   Action: {rec.action}")

            if rec.potential_savings_bytes:
                savings_gb = rec.potential_savings_bytes / (1024**3)
                print(f"   Potential savings: {savings_gb:.2f} GB")

            if args.verbose:
                print(f"   Evidence: {json.dumps(rec.evidence, indent=6)}")

            print()

        return 0

    finally:
        session.close()


def run_workflow(args):
    """Run full workflow: analyze → create rules → get recommendations."""
    print("\n" + "="*100)
    print("STORAGE OPTIMIZER INTELLIGENCE WORKFLOW")
    print("="*100)

    # Step 1: Analyze patterns
    print("\nStep 1: Analyzing approval patterns...")
    analyze_args = argparse.Namespace(
        category=None,
        max_patterns=10,
        min_samples=5,
        min_confidence=0.75,
        non_interactive=True
    )
    analyze_patterns(analyze_args)

    # Step 2: List pending rules
    print("\nStep 2: Listing pending learned rules...")
    list_args = argparse.Namespace(status='pending')
    list_rules(list_args)

    # Step 3: Get recommendations
    print("\nStep 3: Generating strategic recommendations...")
    rec_args = argparse.Namespace(
        max_recommendations=10,
        lookback_days=90,
        verbose=False
    )
    get_recommendations(rec_args)

    print("\n" + "="*100)
    print("WORKFLOW COMPLETE")
    print("="*100)
    print("\nNext steps:")
    print("  1. Review pending learned rules: python scripts/storage/learn_patterns.py list")
    print("  2. Approve/reject rules: python scripts/storage/learn_patterns.py approve <rule_id> --by <your_name>")
    print("  3. Run scans to collect more data for better recommendations")

    return 0


def main():
    parser = argparse.ArgumentParser(
        description="Learn policy rules from approval history",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    subparsers = parser.add_subparsers(dest='command', help='Command to execute')

    # Analyze command
    analyze_parser = subparsers.add_parser('analyze', help='Analyze approval patterns')
    analyze_parser.add_argument('--category', type=str, help='Filter by category')
    analyze_parser.add_argument('--max-patterns', type=int, default=10, help='Maximum patterns to detect')
    analyze_parser.add_argument('--min-samples', type=int, default=5, help='Minimum approval samples')
    analyze_parser.add_argument('--min-confidence', type=float, default=0.75, help='Minimum confidence threshold')
    analyze_parser.add_argument('--non-interactive', action='store_true', help='Non-interactive mode')

    # List command
    list_parser = subparsers.add_parser('list', help='List learned rules')
    list_parser.add_argument('--status', type=str, choices=['pending', 'approved', 'rejected', 'applied'],
                            help='Filter by status')

    # Approve command
    approve_parser = subparsers.add_parser('approve', help='Approve a learned rule')
    approve_parser.add_argument('rule_id', type=int, help='Rule ID to approve')
    approve_parser.add_argument('--by', type=str, required=True, help='Approver name/email')

    # Reject command
    reject_parser = subparsers.add_parser('reject', help='Reject a learned rule')
    reject_parser.add_argument('rule_id', type=int, help='Rule ID to reject')
    reject_parser.add_argument('--by', type=str, required=True, help='Rejector name/email')
    reject_parser.add_argument('--reason', type=str, required=True, help='Rejection reason')

    # Recommend command
    recommend_parser = subparsers.add_parser('recommend', help='Get strategic recommendations')
    recommend_parser.add_argument('--max-recommendations', type=int, default=10, help='Maximum recommendations')
    recommend_parser.add_argument('--lookback-days', type=int, default=90, help='Days of history to analyze')
    recommend_parser.add_argument('--verbose', action='store_true', help='Show detailed evidence')

    # Workflow command
    workflow_parser = subparsers.add_parser('workflow', help='Run full analysis workflow')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    # Execute command
    if args.command == 'analyze':
        return analyze_patterns(args)
    elif args.command == 'list':
        return list_rules(args)
    elif args.command == 'approve':
        return approve_rule(args)
    elif args.command == 'reject':
        return reject_rule(args)
    elif args.command == 'recommend':
        return get_recommendations(args)
    elif args.command == 'workflow':
        return run_workflow(args)
    else:
        parser.print_help()
        return 1


if __name__ == '__main__':
    sys.exit(main())
