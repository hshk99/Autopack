#!/usr/bin/env python3
"""
Analyze Implementation Plan

Autonomous pre-flight analysis of any implementation plan.

Usage:
    python scripts/analyze_plan.py <plan_file> [--run-id <id>] [--output <file>]

Example:
    python scripts/analyze_plan.py .autonomous_runs/my-feature/plan.json --output analysis.json
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from autopack.plan_analyzer import analyze_implementation_plan, PlanAnalysisResult


def print_analysis_summary(result: PlanAnalysisResult):
    """Print human-readable summary of analysis"""

    print("\n" + "=" * 80)
    print("IMPLEMENTATION PLAN ANALYSIS")
    print("=" * 80)

    print(f"\nRun ID: {result.run_id}")
    print(f"Total Phases: {result.total_phases}")

    print(f"\n{'=' * 80}")
    print("FEASIBILITY ASSESSMENT")
    print("=" * 80)

    print(
        f"\n✅ CAN IMPLEMENT: {result.can_implement_count} phases ({result.can_implement_count / result.total_phases * 100:.0f}%)"
    )
    print(
        f"⚠️  RISKY: {result.risky_count} phases ({result.risky_count / result.total_phases * 100:.0f}%)"
    )
    print(
        f"❌ MANUAL REQUIRED: {result.manual_required_count} phases ({result.manual_required_count / result.total_phases * 100:.0f}%)"
    )

    print(f"\nOverall Feasibility: {result.overall_feasibility.value}")
    print(f"Overall Confidence: {result.overall_confidence:.1%}")
    print(
        f"Estimated Duration: {result.estimated_total_duration_days:.1f} days ({result.estimated_total_duration_days / 5:.1f} weeks)"
    )

    # Critical blockers
    if result.critical_blockers:
        print(f"\n{'=' * 80}")
        print("⛔ CRITICAL BLOCKERS")
        print("=" * 80)
        for i, blocker in enumerate(result.critical_blockers, 1):
            print(f"{i}. {blocker}")

    # Infrastructure requirements
    if result.infrastructure_requirements:
        print(f"\n{'=' * 80}")
        print("📦 INFRASTRUCTURE REQUIREMENTS")
        print("=" * 80)
        for req in result.infrastructure_requirements:
            print(f"  - {req}")

    # Phase breakdown
    print(f"\n{'=' * 80}")
    print("PHASE BREAKDOWN")
    print("=" * 80)

    for phase in result.phases:
        # Icon based on feasibility
        if phase.feasibility.value == "CAN_IMPLEMENT":
            icon = "✅"
        elif phase.feasibility.value == "RISKY":
            icon = "⚠️"
        else:
            icon = "❌"

        print(f"\n{icon} {phase.phase_name}")
        print(f"   ID: {phase.phase_id}")
        print(f"   Feasibility: {phase.feasibility.value} ({phase.confidence:.0%} confidence)")
        print(f"   Risk: {phase.risk_level.value} | Decision: {phase.decision_category.value}")
        print(f"   Auto-apply: {'Yes' if phase.auto_apply else 'No'}")
        print(
            f"   Duration: {phase.estimated_duration_days:.1f} days | Complexity: {phase.complexity_score}/10"
        )
        print(f"   Files to modify: ~{phase.estimated_files_modified}")

        if phase.core_files_affected:
            print(f"   Core files: {', '.join(phase.core_files_affected[:3])}")
            if len(phase.core_files_affected) > 3:
                print(f"               ... and {len(phase.core_files_affected) - 3} more")

        if phase.blockers:
            print("   ⛔ Blockers:")
            for blocker in phase.blockers:
                print(f"      - {blocker}")

        if phase.dependencies:
            print(f"   🔗 Dependencies: {', '.join(phase.dependencies)}")

    # Recommended execution order
    print(f"\n{'=' * 80}")
    print("RECOMMENDED EXECUTION ORDER")
    print("=" * 80)

    for i, phase_id in enumerate(result.recommended_execution_order, 1):
        phase = next(p for p in result.phases if p.phase_id == phase_id)
        icon = (
            "✅"
            if phase.feasibility.value == "CAN_IMPLEMENT"
            else "⚠️"
            if phase.feasibility.value == "RISKY"
            else "❌"
        )
        print(f"{i:2d}. {icon} {phase_id} ({phase.estimated_duration_days:.1f} days)")

    # Manual phases
    if result.phases_requiring_manual_implementation:
        print(f"\n{'=' * 80}")
        print("❌ PHASES REQUIRING MANUAL IMPLEMENTATION")
        print("=" * 80)
        for phase_id in result.phases_requiring_manual_implementation:
            phase = next(p for p in result.phases if p.phase_id == phase_id)
            print(f"  - {phase_id}: {phase.phase_name}")
            if phase.blockers:
                for blocker in phase.blockers:
                    print(f"    ⛔ {blocker}")

    # Governance scope
    print(f"\n{'=' * 80}")
    print("GOVERNANCE SCOPE")
    print("=" * 80)

    print(f"\nAllowed Paths ({len(result.global_allowed_paths)}):")
    for path in result.global_allowed_paths[:10]:
        print(f"  ✓ {path}")
    if len(result.global_allowed_paths) > 10:
        print(f"  ... and {len(result.global_allowed_paths) - 10} more")

    print(f"\nProtected Paths ({len(result.protected_paths)}):")
    for path in result.protected_paths:
        print(f"  🔒 {path}")

    print(f"\n{'=' * 80}")
    print("ANALYSIS COMPLETE")
    print("=" * 80)


async def main():
    parser = argparse.ArgumentParser(description="Analyze implementation plan")
    parser.add_argument("plan_file", help="Path to implementation plan (JSON/YAML)")
    parser.add_argument("--run-id", help="Run ID (default: auto-generated from plan file)")
    parser.add_argument("--output", "-o", help="Output file for JSON results")
    parser.add_argument("--workspace", help="Project workspace directory (default: current dir)")

    args = parser.parse_args()

    plan_file = Path(args.plan_file)
    if not plan_file.exists():
        print(f"❌ Plan file not found: {plan_file}")
        sys.exit(1)

    # Auto-generate run ID if not provided
    run_id = args.run_id or plan_file.stem

    # Workspace
    workspace = Path(args.workspace) if args.workspace else Path.cwd()

    # Output file
    output_file = Path(args.output) if args.output else None

    print(f"🔍 Analyzing implementation plan: {plan_file}")
    print(f"📁 Workspace: {workspace}")

    # Run analysis
    try:
        result = await analyze_implementation_plan(
            run_id=run_id,
            plan_file=plan_file,
            workspace=workspace,
            output_file=output_file,
        )

        # Print summary
        print_analysis_summary(result)

        if output_file:
            print(f"\n✅ Full analysis saved to: {output_file}")

        # Exit code based on feasibility
        if result.overall_feasibility.value == "MANUAL_REQUIRED":
            print("\n⚠️  WARNING: Plan requires significant manual implementation")
            sys.exit(2)
        elif result.overall_feasibility.value == "RISKY":
            print("\n⚠️  WARNING: Plan has risky phases - proceed with caution")
            sys.exit(1)
        else:
            print("\n✅ Plan is feasible for autonomous implementation")
            sys.exit(0)

    except Exception as e:
        print(f"\n❌ Analysis failed: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
