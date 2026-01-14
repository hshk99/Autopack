#!/usr/bin/env python3
"""
Diagnostic script to analyze the 4 failing citations from Phase 2 evaluation.

This script re-runs the evaluation with detailed logging to understand:
1. What are the actual extraction_span values that failed?
2. Why did they fail (numeric vs. text matching)?
3. Are these legitimate failures or validator issues?
"""

import json
import logging
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from autopack.research.gatherers.github_gatherer import GitHubGatherer
from autopack.research.models.validators import CitationValidator, Finding

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def diagnose_failures() -> Dict[str, Any]:
    """
    Run evaluation with detailed failure diagnostics.

    Returns:
        dict: Diagnostic results with failure details
    """
    results = {"total_findings": 0, "valid_count": 0, "invalid_count": 0, "failures": []}

    # Check for required environment variables
    github_token = os.getenv("GITHUB_TOKEN")
    anthropic_key = os.getenv("ANTHROPIC_API_KEY")

    if not anthropic_key:
        logger.error("ANTHROPIC_API_KEY environment variable not set")
        return results

    try:
        # Initialize gatherer and validator
        gatherer = GitHubGatherer(github_token=github_token)
        validator = CitationValidator()

        # Test same repositories as Phase 2 evaluation
        test_topics = ["machine learning python", "web framework", "data visualization"]

        for topic in test_topics:
            logger.info(f"\n{'=' * 70}")
            logger.info(f"Topic: {topic}")
            logger.info(f"{'=' * 70}")

            # Discover 2 repos per topic
            repos = gatherer.discover_repositories(topic, max_repos=2)

            for repo in repos:
                repo_name = repo["full_name"]
                logger.info(f"\nRepository: {repo_name}")

                # Fetch README
                readme_content = gatherer.fetch_readme(repo_name)

                if not readme_content:
                    logger.warning("  No README content")
                    continue

                # Extract findings
                findings = gatherer.extract_findings(readme_content, topic, max_findings=3)

                if not findings:
                    logger.warning("  No findings extracted")
                    continue

                logger.info(f"  Extracted {len(findings)} findings")

                # Validate each finding
                for idx, finding in enumerate(findings, 1):
                    results["total_findings"] += 1

                    # Verify citation
                    verification = validator.verify(finding, readme_content, finding.source_hash)

                    if verification.valid:
                        results["valid_count"] += 1
                        logger.info(f"    ✅ Finding {idx}: VALID")
                    else:
                        results["invalid_count"] += 1
                        logger.warning(f"    ❌ Finding {idx}: INVALID - {verification.reason}")

                        # Collect detailed failure information
                        failure_info = {
                            "repository": repo_name,
                            "topic": topic,
                            "finding_index": idx,
                            "category": finding.category,
                            "reason": verification.reason,
                            "confidence": verification.confidence,
                            "content": finding.content[:200] + "..."
                            if len(finding.content) > 200
                            else finding.content,
                            "extraction_span": finding.extraction_span[:300] + "..."
                            if len(finding.extraction_span) > 300
                            else finding.extraction_span,
                            "extraction_span_length": len(finding.extraction_span),
                            "has_numbers_in_span": bool(
                                re.findall(r"\d+(?:\.\d+)?", finding.extraction_span)
                            ),
                            "readme_snippet": "",
                        }

                        # Try to find where the span should be in the README
                        if verification.reason == "extraction_span not found in source document":
                            # Show a snippet to help diagnose why it's not matching
                            normalized_span = validator._normalize_text(finding.extraction_span)
                            normalized_readme = validator._normalize_text(readme_content)

                            # Try to find the closest match
                            span_words = normalized_span.split()[:10]  # First 10 words
                            search_phrase = " ".join(span_words)

                            if search_phrase in normalized_readme:
                                pos = normalized_readme.index(search_phrase)
                                snippet = readme_content[max(0, pos - 100) : pos + 200]
                                failure_info["readme_snippet"] = snippet
                                failure_info["partial_match"] = True
                            else:
                                failure_info["partial_match"] = False

                        results["failures"].append(failure_info)

        # Calculate validity percentage
        if results["total_findings"] > 0:
            results["validity_percentage"] = (
                results["valid_count"] / results["total_findings"]
            ) * 100
        else:
            results["validity_percentage"] = 0.0

    except Exception as e:
        logger.error(f"Diagnostic failed: {e}", exc_info=True)

    return results


def generate_diagnostic_report(results: Dict[str, Any]) -> str:
    """Generate a detailed diagnostic report."""
    lines = [
        "=" * 70,
        "CITATION FAILURE DIAGNOSTIC REPORT",
        "=" * 70,
        f"Total Findings: {results['total_findings']}",
        f"Valid: {results['valid_count']}",
        f"Invalid: {results['invalid_count']}",
        f"Validity: {results.get('validity_percentage', 0):.1f}%",
        "",
        "=" * 70,
        "DETAILED FAILURE ANALYSIS",
        "=" * 70,
    ]

    for idx, failure in enumerate(results.get("failures", []), 1):
        lines.extend(
            [
                "",
                f"FAILURE #{idx}",
                "-" * 70,
                f"Repository:        {failure['repository']}",
                f"Topic:             {failure['topic']}",
                f"Category:          {failure['category']}",
                f"Reason:            {failure['reason']}",
                f"Confidence:        {failure['confidence']}",
                "",
                "Content (LLM interpretation):",
                f"  {failure['content']}",
                "",
                "Extraction Span (quote from source):",
                f"  Length: {failure['extraction_span_length']} chars",
                f"  Has numbers: {failure['has_numbers_in_span']}",
                f"  Text: {failure['extraction_span']}",
            ]
        )

        if "readme_snippet" in failure and failure["readme_snippet"]:
            lines.extend(
                [
                    "",
                    "README Snippet (closest match):",
                    f"  {failure['readme_snippet'][:300]}",
                ]
            )

        if failure["reason"] == "numeric claim does not match extraction_span":
            lines.extend(
                [
                    "",
                    "ANALYSIS: Numeric verification failure",
                    "  - Category is market_intelligence or competitive_analysis",
                    "  - extraction_span is missing numbers",
                    "  - This suggests LLM categorized incorrectly OR extracted non-numeric quote",
                ]
            )
        elif failure["reason"] == "extraction_span not found in source document":
            lines.extend(
                [
                    "",
                    "ANALYSIS: Text matching failure",
                    "  - extraction_span quote not found in normalized source",
                    "  - Could be: encoding issue, LLM hallucination, or normalization gap",
                ]
            )

    lines.extend(
        [
            "",
            "=" * 70,
            "RECOMMENDATIONS",
            "=" * 70,
        ]
    )

    # Analyze failure patterns
    numeric_failures = sum(1 for f in results.get("failures", []) if "numeric" in f["reason"])
    text_failures = sum(1 for f in results.get("failures", []) if "not found" in f["reason"])

    if numeric_failures >= 3:
        lines.extend(
            [
                "",
                f"PRIMARY ISSUE: Numeric verification ({numeric_failures} failures)",
                "  - LLM is categorizing findings as market_intelligence/competitive_analysis",
                "  - But extraction_span doesn't contain numbers",
                "  - OPTIONS:",
                "    A. Relax numeric requirement (allow empty numbers for these categories)",
                "    B. Improve LLM prompt to choose correct category",
                "    C. Remove numeric verification entirely",
            ]
        )

    if text_failures >= 1:
        lines.extend(
            [
                "",
                f"SECONDARY ISSUE: Text matching ({text_failures} failures)",
                "  - extraction_span quote not found in source",
                "  - Likely LLM hallucination or paraphrasing instead of exact quote",
                "  - OPTIONS:",
                "    A. Improve LLM prompt to emphasize EXACT quotes",
                "    B. Add fuzzy matching (risky - might allow bad citations)",
                "    C. Accept this as acceptable failure rate",
            ]
        )

    lines.append("=" * 70)
    return "\n".join(lines)


def main() -> int:
    """Main entry point."""
    print("Starting Citation Failure Diagnostics...")
    print("This will re-run evaluation with detailed failure logging")
    print()

    results = diagnose_failures()
    report = generate_diagnostic_report(results)

    print(report)

    # Write results to JSON
    output_dir = Path(".autonomous_runs/research-citation-fix")
    output_dir.mkdir(parents=True, exist_ok=True)

    json_path = output_dir / "failure_diagnostics.json"
    json_path.write_text(json.dumps(results, indent=2))
    print(f"\n\nDetailed results written to: {json_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
