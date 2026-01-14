"""Analysis script for learned rules system

Per FINAL_LEARNED_RULES_DECISION.md - Stage 0B:
Provides insights into rule promotion patterns, effectiveness, and trends.

Usage:
    python scripts/analyze_learned_rules.py --project-id Autopack
    python scripts/analyze_learned_rules.py --run-id auto-build-123
    python scripts/analyze_learned_rules.py --all-projects
"""

import argparse
import json
from pathlib import Path
from typing import Dict, List, Optional
from collections import defaultdict
from datetime import datetime

import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.autopack.learned_rules import (
    load_project_learned_rules,
    load_run_rule_hints,
)


def analyze_project_rules(project_id: str) -> Dict:
    """Analyze learned rules for a project

    Returns:
        Dict with analysis results
    """
    print(f"\n{'=' * 60}")
    print(f"📚 Project Learned Rules Analysis: {project_id}")
    print(f"{'=' * 60}\n")

    rules = load_project_learned_rules(project_id)

    if not rules:
        print(f"⚠️  No learned rules found for project '{project_id}'")
        return {"project_id": project_id, "total_rules": 0, "rules": []}

    # Overall stats
    print(f"Total Rules: {len(rules)}")
    print(f"Active Rules: {sum(1 for r in rules if r.status == 'active')}")
    print(f"Deprecated Rules: {sum(1 for r in rules if r.status == 'deprecated')}")

    # Group by task_category
    by_category = defaultdict(list)
    for rule in rules:
        by_category[rule.task_category].append(rule)

    print("\n📊 Rules by Task Category:")
    for category, category_rules in sorted(by_category.items()):
        print(f"  {category}: {len(category_rules)} rules")

    # Find most promoted rules (highest confidence)
    print("\n🏆 Top Promoted Rules (highest confidence):")
    sorted_by_promotion = sorted(rules, key=lambda r: r.promotion_count, reverse=True)
    for i, rule in enumerate(sorted_by_promotion[:10], 1):
        print(f"  {i}. {rule.rule_id}")
        print(f"     Promoted: {rule.promotion_count} times")
        print(f"     Constraint: {rule.constraint[:80]}...")
        print(f"     First seen: {rule.first_seen[:10]}")
        print(f"     Last seen: {rule.last_seen[:10]}")
        print()

    # Pattern analysis
    print("\n🔍 Pattern Analysis:")
    patterns = defaultdict(int)
    for rule in rules:
        # Extract pattern from rule_id (e.g., "feature_scaffolding.missing_type_hints" -> "missing_type_hints")
        pattern = rule.rule_id.split(".", 1)[-1] if "." in rule.rule_id else rule.rule_id
        patterns[pattern] += 1

    print("  Most common patterns:")
    for pattern, count in sorted(patterns.items(), key=lambda x: x[1], reverse=True)[:10]:
        print(f"    - {pattern}: {count} rules")

    # Scope analysis
    print("\n📂 Scope Analysis:")
    global_rules = sum(1 for r in rules if r.scope_pattern is None)
    scoped_rules = sum(1 for r in rules if r.scope_pattern is not None)
    print(f"  Global rules (no scope): {global_rules}")
    print(f"  Scoped rules (specific patterns): {scoped_rules}")

    if scoped_rules > 0:
        print("\n  Common scope patterns:")
        scope_patterns = defaultdict(int)
        for rule in rules:
            if rule.scope_pattern:
                scope_patterns[rule.scope_pattern] += 1
        for pattern, count in sorted(scope_patterns.items(), key=lambda x: x[1], reverse=True)[:10]:
            print(f"    - {pattern}: {count} rules")

    return {
        "project_id": project_id,
        "total_rules": len(rules),
        "active_rules": sum(1 for r in rules if r.status == "active"),
        "by_category": {cat: len(r_list) for cat, r_list in by_category.items()},
        "top_promoted": [
            {"rule_id": r.rule_id, "promotion_count": r.promotion_count, "constraint": r.constraint}
            for r in sorted_by_promotion[:10]
        ],
    }


def analyze_run_hints(run_id: str) -> Dict:
    """Analyze hints from a specific run

    Returns:
        Dict with analysis results
    """
    print(f"\n{'=' * 60}")
    print(f"💡 Run Hints Analysis: {run_id}")
    print(f"{'=' * 60}\n")

    hints = load_run_rule_hints(run_id)

    if not hints:
        print(f"⚠️  No hints found for run '{run_id}'")
        return {"run_id": run_id, "total_hints": 0, "hints": []}

    # Overall stats
    print(f"Total Hints: {len(hints)}")

    # Group by phase
    by_phase = defaultdict(list)
    for hint in hints:
        by_phase[hint.phase_id].append(hint)

    print(f"Phases with hints: {len(by_phase)}")

    # Group by task_category
    by_category = defaultdict(list)
    for hint in hints:
        if hint.task_category:
            by_category[hint.task_category].append(hint)

    print("\n📊 Hints by Task Category:")
    for category, category_hints in sorted(by_category.items()):
        print(f"  {category}: {len(category_hints)} hints")

    # Pattern frequency (for promotion prediction)
    print("\n🔮 Pattern Frequency (promotion candidates):")
    pattern_counts = defaultdict(int)
    for hint in hints:
        if hint.source_issue_keys:
            # Extract pattern from first issue key
            issue_key = hint.source_issue_keys[0]
            # Simple pattern extraction (first 2-3 words)
            parts = issue_key.split("_")
            pattern_parts = []
            for part in parts[:3]:
                if part.isdigit() or "." in part:
                    break
                pattern_parts.append(part)
            pattern = "_".join(pattern_parts) if pattern_parts else issue_key
            pattern_counts[pattern] += 1

    promoted_count = sum(1 for count in pattern_counts.values() if count >= 2)
    print(f"  Patterns that will be promoted (2+ occurrences): {promoted_count}")
    print(f"  Total unique patterns: {len(pattern_counts)}")

    for pattern, count in sorted(pattern_counts.items(), key=lambda x: x[1], reverse=True):
        status = "✅ WILL PROMOTE" if count >= 2 else "  "
        print(f"    {status} {pattern}: {count} occurrences")

    # Hint details
    print("\n📝 Hint Details:")
    for hint in hints:
        print(f"\n  Phase {hint.phase_id} ({hint.task_category or 'unknown'}):")
        print(f"    {hint.hint_text}")
        print(f"    Files: {', '.join(hint.scope_paths[:3])}")
        if len(hint.scope_paths) > 3:
            print(f"          ... and {len(hint.scope_paths) - 3} more")

    return {
        "run_id": run_id,
        "total_hints": len(hints),
        "by_category": {cat: len(h_list) for cat, h_list in by_category.items()},
        "promotion_candidates": promoted_count,
        "total_patterns": len(pattern_counts),
    }


def analyze_all_projects() -> Dict:
    """Analyze all projects in .autonomous_runs

    Returns:
        Dict with cross-project analysis
    """
    print(f"\n{'=' * 60}")
    print("🌍 All Projects Analysis")
    print(f"{'=' * 60}\n")

    runs_dir = Path(".autonomous_runs")
    if not runs_dir.exists():
        print("⚠️  No .autonomous_runs directory found")
        return {"projects": []}

    # Find all project directories
    projects = []
    for project_dir in runs_dir.iterdir():
        if project_dir.is_dir() and project_dir.name != "runs":
            rules_file = project_dir / "project_learned_rules.json"
            if rules_file.exists():
                projects.append(project_dir.name)

    if not projects:
        print("⚠️  No projects with learned rules found")
        return {"projects": []}

    print(f"Found {len(projects)} project(s) with learned rules:\n")

    all_results = []
    for project_id in sorted(projects):
        result = analyze_project_rules(project_id)
        all_results.append(result)

    # Cross-project summary
    print(f"\n{'=' * 60}")
    print("📈 Cross-Project Summary")
    print(f"{'=' * 60}\n")

    total_rules = sum(r["total_rules"] for r in all_results)
    print(f"Total rules across all projects: {total_rules}")

    # Most common patterns across projects
    all_patterns = defaultdict(int)
    for result in all_results:
        rules = load_project_learned_rules(result["project_id"])
        for rule in rules:
            pattern = rule.rule_id.split(".", 1)[-1] if "." in rule.rule_id else rule.rule_id
            all_patterns[pattern] += 1

    print("\nMost common patterns across all projects:")
    for pattern, count in sorted(all_patterns.items(), key=lambda x: x[1], reverse=True)[:15]:
        print(f"  {pattern}: {count} projects")

    return {
        "projects": all_results,
        "total_projects": len(projects),
        "total_rules": total_rules,
        "common_patterns": dict(
            sorted(all_patterns.items(), key=lambda x: x[1], reverse=True)[:15]
        ),
    }


def analyze_run_series(project_id: str) -> Dict:
    """Analyze how rules evolved across multiple runs for a project

    Returns:
        Dict with time-series analysis
    """
    print(f"\n{'=' * 60}")
    print(f"📊 Run Series Analysis: {project_id}")
    print(f"{'=' * 60}\n")

    runs_dir = Path(".autonomous_runs") / "runs"
    if not runs_dir.exists():
        print("⚠️  No runs directory found")
        return {"project_id": project_id, "runs": []}

    # Find all runs
    runs = []
    for run_dir in runs_dir.iterdir():
        if run_dir.is_dir():
            hints_file = run_dir / "run_rule_hints.json"
            if hints_file.exists():
                # Load hints to check project context
                try:
                    hints = load_run_rule_hints(run_dir.name)
                    if hints:
                        # Get creation time from first hint
                        runs.append(
                            {
                                "run_id": run_dir.name,
                                "hint_count": len(hints),
                                "created_at": hints[0].created_at,
                            }
                        )
                except:
                    pass

    if not runs:
        print("⚠️  No runs found")
        return {"project_id": project_id, "runs": []}

    # Sort by creation time
    runs.sort(key=lambda r: r["created_at"])

    print(f"Found {len(runs)} run(s):\n")

    for i, run in enumerate(runs, 1):
        print(f"{i}. Run: {run['run_id']}")
        print(f"   Date: {run['created_at'][:10]}")
        print(f"   Hints: {run['hint_count']}")
        print()

    return {"project_id": project_id, "total_runs": len(runs), "runs": runs}


def main():
    parser = argparse.ArgumentParser(description="Analyze learned rules across runs and projects")
    parser.add_argument("--project-id", help="Analyze rules for specific project")
    parser.add_argument("--run-id", help="Analyze hints for specific run")
    parser.add_argument("--all-projects", action="store_true", help="Analyze all projects")
    parser.add_argument("--run-series", help="Analyze run series for project")
    parser.add_argument("--output-json", help="Save analysis results to JSON file")

    args = parser.parse_args()

    # Default to all-projects if no specific target
    if not any([args.project_id, args.run_id, args.all_projects, args.run_series]):
        args.all_projects = True

    results = {}

    if args.all_projects:
        results["all_projects"] = analyze_all_projects()

    if args.project_id:
        results["project"] = analyze_project_rules(args.project_id)

    if args.run_id:
        results["run"] = analyze_run_hints(args.run_id)

    if args.run_series:
        results["run_series"] = analyze_run_series(args.run_series)

    # Save to JSON if requested
    if args.output_json:
        output_path = Path(args.output_json)
        with open(output_path, "w") as f:
            json.dump(results, f, indent=2)
        print(f"\n💾 Analysis saved to: {output_path}")

    print(f"\n{'=' * 60}")
    print("✅ Analysis Complete")
    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    main()
