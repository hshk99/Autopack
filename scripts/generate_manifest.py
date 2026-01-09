#!/usr/bin/env python3
"""
Generate Scope Manifest for Implementation Plan

Standalone CLI tool for BUILD-123v2 Manifest Generator.
Enhances minimal plans with deterministic scope generation.

Usage:
    # Enhance minimal plan
    python scripts/generate_manifest.py plan.json --output enhanced_plan.json

    # Validate plan only (no output)
    python scripts/generate_manifest.py plan.json --validate-only

    # Show statistics
    python scripts/generate_manifest.py plan.json --stats
"""

import argparse
import json
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from autopack.manifest_generator import ManifestGenerator, ManifestGenerationResult


def print_result_summary(result: ManifestGenerationResult):
    """Print human-readable summary of generation"""

    print("\n" + "=" * 80)
    print("MANIFEST GENERATION RESULT")
    print("=" * 80)

    if result.success:
        print("\n✅ Generation successful")
    else:
        print(f"\n❌ Generation failed: {result.error}")
        return

    # Confidence scores
    print("\nConfidence Scores:")
    for phase_id, confidence in result.confidence_scores.items():
        icon = "✅" if confidence >= 0.70 else "⚠️" if confidence >= 0.30 else "❌"
        print(f"  {icon} {phase_id}: {confidence:.1%}")

    # Warnings
    if result.warnings:
        print(f"\n⚠️  Warnings ({len(result.warnings)}):")
        for warning in result.warnings[:10]:  # Limit to 10
            print(f"  - {warning}")
        if len(result.warnings) > 10:
            print(f"  ... and {len(result.warnings) - 10} more")

    print("\n" + "=" * 80)


def print_statistics(generator: ManifestGenerator, plan_data: dict):
    """Print scope statistics"""

    stats = generator.get_scope_statistics(plan_data)

    print("\n" + "=" * 80)
    print("SCOPE STATISTICS")
    print("=" * 80)

    print(f"\nTotal Files: {stats['total_files']}")
    print(f"Total Directories: {stats['total_directories']}")
    print(f"Average Confidence: {stats['confidence_avg']:.1%}")

    print("\nCategories:")
    for category, count in sorted(stats['categories'].items(), key=lambda x: x[1], reverse=True):
        print(f"  - {category}: {count} phases")

    print("\n" + "=" * 80)


def main():
    parser = argparse.ArgumentParser(description="Generate scope manifest for implementation plan")
    parser.add_argument("plan_file", help="Path to implementation plan (JSON)")
    parser.add_argument("--output", "-o", help="Output file for enhanced plan (default: stdout)")
    parser.add_argument("--validate-only", action="store_true", help="Validate plan without output")
    parser.add_argument("--stats", action="store_true", help="Show scope statistics")
    parser.add_argument("--workspace", help="Project workspace directory (default: current dir)")
    parser.add_argument("--autopack-internal-mode", action="store_true", help="Allow src/autopack/ writes")
    parser.add_argument("--run-type", default="project_build", help="Run type (default: project_build)")
    parser.add_argument("--skip-validation", action="store_true", help="Skip preflight validation")
    parser.add_argument("--enable-plan-analyzer", action="store_true", help="Enable LLM-based feasibility analysis (BUILD-124, experimental)")

    args = parser.parse_args()

    plan_file = Path(args.plan_file)
    if not plan_file.exists():
        print(f"❌ Plan file not found: {plan_file}")
        sys.exit(1)

    # Load plan
    try:
        with open(plan_file) as f:
            plan_data = json.load(f)
    except Exception as e:
        print(f"❌ Failed to load plan file: {e}")
        sys.exit(1)

    # Workspace
    workspace = Path(args.workspace) if args.workspace else Path.cwd()

    # Create manifest generator
    generator = ManifestGenerator(
        workspace=workspace,
        autopack_internal_mode=args.autopack_internal_mode,
        run_type=args.run_type,
        enable_plan_analyzer=args.enable_plan_analyzer  # BUILD-124
    )

    print(f"🔍 Generating manifest for: {plan_data.get('run_id', 'unknown')}")
    print(f"📁 Workspace: {workspace}")

    # Generate manifest
    try:
        result = generator.generate_manifest(
            plan_data=plan_data,
            skip_validation=args.skip_validation
        )
    except Exception as e:
        print(f"\n❌ Generation failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    # Print summary
    print_result_summary(result)

    if not result.success:
        sys.exit(1)

    # Show statistics if requested
    if args.stats:
        print_statistics(generator, result.enhanced_plan)

    # Validate-only mode
    if args.validate_only:
        print("\n✅ Validation complete (no output file)")
        sys.exit(0)

    # Output enhanced plan
    if args.output:
        output_file = Path(args.output)
        try:
            with open(output_file, "w") as f:
                json.dump(result.enhanced_plan, f, indent=2)
            print(f"\n✅ Enhanced plan saved to: {output_file}")
        except Exception as e:
            print(f"\n❌ Failed to save output: {e}")
            sys.exit(1)
    else:
        # Print to stdout
        print("\n" + "=" * 80)
        print("ENHANCED PLAN")
        print("=" * 80)
        print(json.dumps(result.enhanced_plan, indent=2))

    sys.exit(0)


if __name__ == "__main__":
    main()
