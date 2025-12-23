#!/usr/bin/env python3
"""
Run Autonomous Implementation with Pre-Flight Analysis

This wrapper script:
1. Analyzes the implementation plan using plan_analyzer
2. Generates feasibility assessment, quality gates, governance scope
3. Saves analysis results
4. Executes autonomous_executor with the analyzed plan

Usage:
    python scripts/run_with_analysis.py <plan_file> [--run-id <id>] [--skip-analysis]
"""

import argparse
import asyncio
import json
import subprocess
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from autopack.plan_analyzer import analyze_implementation_plan


async def main():
    parser = argparse.ArgumentParser(description="Run autonomous implementation with pre-flight analysis")
    parser.add_argument("plan_file", help="Path to implementation plan (JSON/YAML)")
    parser.add_argument("--run-id", help="Run ID (default: auto-generated from plan file)")
    parser.add_argument("--skip-analysis", action="store_true", help="Skip pre-flight analysis")
    parser.add_argument("--workspace", help="Project workspace directory (default: current dir)")
    parser.add_argument("--max-iterations", type=int, default=10, help="Max iterations per phase")

    args = parser.parse_args()

    plan_file = Path(args.plan_file)
    if not plan_file.exists():
        print(f"❌ Plan file not found: {plan_file}")
        sys.exit(1)

    # Auto-generate run ID if not provided
    run_id = args.run_id or plan_file.stem

    # Workspace
    workspace = Path(args.workspace) if args.workspace else Path.cwd()

    # Analysis output
    analysis_file = plan_file.parent / f"{plan_file.stem}_analysis.json"

    # Step 1: Pre-flight analysis
    if not args.skip_analysis:
        print("\n" + "="*80)
        print("STEP 1: PRE-FLIGHT ANALYSIS")
        print("="*80)

        print(f"\n🔍 Analyzing implementation plan: {plan_file}")

        try:
            result = await analyze_implementation_plan(
                run_id=run_id,
                plan_file=plan_file,
                workspace=workspace,
                output_file=analysis_file,
            )

            # Print summary
            print(f"\n✅ Analysis complete")
            print(f"   Overall Feasibility: {result.overall_feasibility.value}")
            print(f"   Overall Confidence: {result.overall_confidence:.1%}")
            print(f"   Estimated Duration: {result.estimated_total_duration_days:.1f} days")
            print(f"   ✅ CAN IMPLEMENT: {result.can_implement_count} phases")
            print(f"   ⚠️  RISKY: {result.risky_count} phases")
            print(f"   ❌ MANUAL REQUIRED: {result.manual_required_count} phases")

            if result.critical_blockers:
                print(f"\n⛔ CRITICAL BLOCKERS:")
                for blocker in result.critical_blockers:
                    print(f"   - {blocker}")

                response = input("\nBlockers detected. Continue anyway? [y/N]: ")
                if response.lower() != 'y':
                    print("❌ Execution cancelled due to blockers")
                    sys.exit(1)

            if result.infrastructure_requirements:
                print(f"\n📦 INFRASTRUCTURE REQUIREMENTS:")
                for req in result.infrastructure_requirements:
                    print(f"   - {req}")

            print(f"\n📄 Full analysis saved to: {analysis_file}")

            # Generate enhanced run config with analysis results
            enhanced_config = plan_file.parent / f"{plan_file.stem}_enhanced.json"
            with open(plan_file) as f:
                plan_data = json.load(f)

            # Enhance with analysis results
            for phase_spec in plan_data.get("phases", []):
                phase_id = phase_spec.get("phase_id")
                phase_analysis = next((p for p in result.phases if p.phase_id == phase_id), None)

                if phase_analysis:
                    # Add analysis fields
                    phase_spec["analysis"] = {
                        "feasibility": phase_analysis.feasibility.value,
                        "confidence": phase_analysis.confidence,
                        "risk_level": phase_analysis.risk_level.value,
                        "decision_category": phase_analysis.decision_category.value,
                        "auto_apply": phase_analysis.auto_apply,
                    }

                    # Add scope if not already present
                    if "scope" not in phase_spec:
                        phase_spec["scope"] = {
                            "paths": phase_analysis.allowed_paths,
                            "read_only_context": phase_analysis.readonly_context,
                        }

                    # Add success criteria if not already present
                    if "success_criteria" not in phase_spec:
                        phase_spec["success_criteria"] = phase_analysis.success_criteria

                    # Add validation tests
                    if "validation_tests" not in phase_spec:
                        phase_spec["validation_tests"] = phase_analysis.validation_tests

            # Save enhanced config
            with open(enhanced_config, "w") as f:
                json.dump(plan_data, f, indent=2)

            print(f"📄 Enhanced config saved to: {enhanced_config}")

            # Use enhanced config for execution
            plan_file = enhanced_config

        except Exception as e:
            print(f"\n❌ Analysis failed: {e}")
            import traceback
            traceback.print_exc()

            response = input("\nAnalysis failed. Continue with execution anyway? [y/N]: ")
            if response.lower() != 'y':
                print("❌ Execution cancelled")
                sys.exit(1)

    # Step 2: Autonomous execution
    print("\n" + "="*80)
    print("STEP 2: AUTONOMOUS EXECUTION")
    print("="*80)

    print(f"\n🚀 Starting autonomous execution")
    print(f"   Run ID: {run_id}")
    print(f"   Plan: {plan_file}")
    print(f"   Max Iterations: {args.max_iterations}")

    # Build command
    cmd = [
        sys.executable,
        "-m", "autopack.autonomous_executor",
        "--run-id", run_id,
        "--config", str(plan_file),
        "--max-iterations", str(args.max_iterations),
    ]

    print(f"\nCommand: {' '.join(cmd)}\n")

    # Execute
    try:
        result = subprocess.run(
            cmd,
            cwd=workspace,
            env={
                **subprocess.os.environ,
                "PYTHONUTF8": "1",
                "PYTHONPATH": "src",
                "DATABASE_URL": subprocess.os.environ.get("DATABASE_URL", "sqlite:///autopack.db"),
            }
        )

        if result.returncode == 0:
            print("\n" + "="*80)
            print("✅ EXECUTION COMPLETE")
            print("="*80)
        else:
            print("\n" + "="*80)
            print("❌ EXECUTION FAILED")
            print("="*80)

        sys.exit(result.returncode)

    except KeyboardInterrupt:
        print("\n\n⚠️  Execution interrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"\n❌ Execution failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
