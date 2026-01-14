#!/usr/bin/env python3
"""
Phase 1 Evaluation Script - Citation Validity Measurement

This script runs the Phase 1 evaluation to measure citation validity
after the Phase 1 fix (relaxed numeric verification in extraction_span).

Tests citation validity on 3-5 sample repositories to measure improvement
from the 59.3% baseline.
"""

import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from autopack.research.gatherers.github_gatherer import GitHubGatherer
from autopack.research.evaluation.citation_validator import CitationValidityEvaluator
from autopack.research.models.validators import Finding

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def run_evaluation() -> Dict[str, Any]:
    """
    Run the Phase 1 evaluation and collect citation validity metrics.

    Returns:
        dict: Evaluation results including citation validity metrics
    """
    results: Dict[str, Any] = {
        "timestamp": datetime.utcnow().isoformat(),
        "phase": "phase_1_evaluation",
        "description": "Citation validity after Phase 1 fix (relaxed numeric verification)",
        "status": "running",
        "baseline": 59.3,  # Original baseline from research
        "target": 80.0,  # Target validity percentage
        "metrics": {},
        "repositories_tested": [],
        "errors": [],
    }

    # Check for required environment variables
    github_token = os.getenv("GITHUB_TOKEN")
    anthropic_key = os.getenv("ANTHROPIC_API_KEY")

    if not github_token:
        results["errors"].append("GITHUB_TOKEN environment variable not set")
        logger.warning("GITHUB_TOKEN not set - may hit rate limits")

    if not anthropic_key:
        results["errors"].append("ANTHROPIC_API_KEY environment variable not set")
        results["status"] = "error"
        return results

    try:
        # Initialize gatherer and evaluator
        gatherer = GitHubGatherer(github_token=github_token)
        evaluator = CitationValidityEvaluator()

        # Test topics for diverse coverage
        test_topics = ["machine learning python", "web framework", "data visualization"]

        all_findings: List[Finding] = []
        source_content_map: Dict[str, str] = {}

        # Gather findings from repositories
        for topic in test_topics:
            logger.info(f"Discovering repositories for topic: {topic}")

            # Discover 2 repos per topic = 6 total
            repos = gatherer.discover_repositories(topic, max_repos=2)

            for repo in repos:
                repo_name = repo["full_name"]
                logger.info(f"Processing repository: {repo_name}")

                # Fetch README
                readme_content = gatherer.fetch_readme(repo_name)

                if not readme_content:
                    logger.warning(f"No README content for {repo_name}")
                    continue

                # Extract findings (max 3 per repo to keep evaluation quick)
                findings = gatherer.extract_findings(readme_content, topic, max_findings=3)

                if findings:
                    # Store source content for validation
                    for finding in findings:
                        source_key = finding.source_hash
                        source_content_map[source_key] = readme_content

                    all_findings.extend(findings)

                    results["repositories_tested"].append(
                        {
                            "repo_name": repo_name,
                            "topic": topic,
                            "findings_extracted": len(findings),
                            "readme_length": len(readme_content),
                        }
                    )

                    logger.info(f"Extracted {len(findings)} findings from {repo_name}")

        # Evaluate citation validity
        if all_findings:
            logger.info(f"Evaluating {len(all_findings)} total findings")

            evaluation_results = evaluator.evaluate_summary(all_findings, source_content_map)

            results["metrics"] = {
                "total_findings": evaluation_results["total_findings"],
                "valid_citations": evaluation_results["valid_citations"],
                "invalid_citations": evaluation_results["invalid_citations"],
                "validity_percentage": evaluation_results["validity_percentage"],
                "failure_breakdown": evaluation_results["failure_breakdown"],
                "repositories_tested": len(results["repositories_tested"]),
                "topics_tested": len(test_topics),
            }

            # Calculate improvement over baseline
            improvement = evaluation_results["validity_percentage"] - results["baseline"]
            results["metrics"]["improvement_over_baseline"] = round(improvement, 2)
            results["metrics"]["target_met"] = (
                evaluation_results["validity_percentage"] >= results["target"]
            )

            # Determine status
            if evaluation_results["validity_percentage"] >= results["target"]:
                results["status"] = "success_target_met"
            else:
                results["status"] = "completed_target_not_met"

            logger.info(f"Citation validity: {evaluation_results['validity_percentage']:.1f}%")
            logger.info(f"Improvement: {improvement:+.1f}% from baseline")

        else:
            results["errors"].append("No findings extracted from any repository")
            results["status"] = "error"

    except Exception as e:
        logger.error(f"Evaluation failed: {e}", exc_info=True)
        results["errors"].append(f"Evaluation exception: {str(e)}")
        results["status"] = "error"

    return results


def generate_report(results: Dict[str, Any]) -> str:
    """
    Generate a comprehensive results report.

    Args:
        results: Evaluation results dictionary

    Returns:
        str: Formatted report string
    """
    lines = [
        "=" * 70,
        "PHASE 1 EVALUATION REPORT - CITATION VALIDITY",
        "=" * 70,
        f"Timestamp: {results['timestamp']}",
        f"Phase: {results['phase']}",
        f"Description: {results['description']}",
        f"Status: {results['status']}",
        "",
        "-" * 70,
        "OBJECTIVES",
        "-" * 70,
        f"  Baseline (before Phase 1 fix):  {results['baseline']}%",
        f"  Target (≥80% validity):         {results['target']}%",
        "",
    ]

    metrics = results.get("metrics", {})
    if metrics:
        validity = metrics.get("validity_percentage", 0)
        improvement = metrics.get("improvement_over_baseline", 0)
        target_met = metrics.get("target_met", False)

        lines.extend(
            [
                "-" * 70,
                "RESULTS",
                "-" * 70,
                f"  Total Findings Tested:          {metrics.get('total_findings', 0)}",
                f"  Valid Citations:                {metrics.get('valid_citations', 0)}",
                f"  Invalid Citations:              {metrics.get('invalid_citations', 0)}",
                f"  Citation Validity:              {validity:.1f}%",
                f"  Improvement over Baseline:      {improvement:+.1f}%",
                f"  Target Met (≥80%):              {'✅ YES' if target_met else '❌ NO'}",
                "",
                f"  Repositories Tested:            {metrics.get('repositories_tested', 0)}",
                f"  Topics Tested:                  {metrics.get('topics_tested', 0)}",
                "",
            ]
        )

        # Failure breakdown
        failure_breakdown = metrics.get("failure_breakdown", {})
        if failure_breakdown:
            lines.extend(
                [
                    "-" * 70,
                    "FAILURE BREAKDOWN",
                    "-" * 70,
                ]
            )
            for reason, count in sorted(
                failure_breakdown.items(), key=lambda x: x[1], reverse=True
            ):
                lines.append(f"  {reason}: {count}")
            lines.append("")

    # Repository details
    repos_tested = results.get("repositories_tested", [])
    if repos_tested:
        lines.extend(
            [
                "-" * 70,
                "REPOSITORIES TESTED",
                "-" * 70,
            ]
        )
        for repo in repos_tested:
            lines.append(f"  {repo['repo_name']}")
            lines.append(f"    Topic: {repo['topic']}")
            lines.append(f"    Findings: {repo['findings_extracted']}")
            lines.append(f"    README Length: {repo['readme_length']:,} chars")
            lines.append("")

    # Errors
    if results.get("errors"):
        lines.extend(
            [
                "-" * 70,
                "ERRORS/WARNINGS",
                "-" * 70,
            ]
        )
        for error in results["errors"]:
            lines.append(f"  ⚠️  {error}")
        lines.append("")

    # Next steps
    lines.extend(
        [
            "-" * 70,
            "NEXT STEPS",
            "-" * 70,
        ]
    )

    if results["status"] == "success_target_met":
        lines.append("  ✅ Phase 1 fix achieved ≥80% citation validity")
        lines.append("  ✅ No further phases needed")
        lines.append("  📝 Update RESEARCH_CITATION_FIX_PLAN.md with results")
    elif results["status"] == "completed_target_not_met":
        lines.append("  ⚠️  Phase 1 fix did not achieve ≥80% target")
        lines.append("  📋 Proceed to Phase 2: Enhanced normalization")
        lines.append("  🔧 Integrate text_normalization into validators.py")
    else:
        lines.append("  ❌ Evaluation encountered errors")
        lines.append("  🔍 Review error messages above")

    lines.extend(["", "=" * 70])
    return "\n".join(lines)


def main() -> int:
    """Main entry point for the evaluation script."""
    print("Starting Phase 1 Citation Validity Evaluation...")
    print("This will test citation validity on 3-5 sample repositories")
    print()

    results = run_evaluation()
    report = generate_report(results)

    print(report)

    # Write results to JSON file
    output_dir = Path(".autonomous_runs/research-citation-fix")
    output_dir.mkdir(parents=True, exist_ok=True)

    output_path = output_dir / "phase1_evaluation_results.json"
    output_path.write_text(json.dumps(results, indent=2))
    print(f"\nResults written to: {output_path}")

    # Return appropriate exit code
    if results["status"] in ("success_target_met", "completed_target_not_met"):
        return 0
    else:
        return 1


if __name__ == "__main__":
    sys.exit(main())
