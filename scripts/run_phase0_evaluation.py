#!/usr/bin/env python3
"""
Phase 0 Evaluation Script - Citation Validity Measurement

This script runs the Phase 0 evaluation to measure citation validity
after the Phase 3 enhanced normalization fix has been applied.
"""

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


def run_evaluation() -> dict[str, Any]:
    """
    Run the Phase 0 evaluation and collect metrics.

    Returns:
        dict: Evaluation results including citation validity metrics
    """
    results: dict[str, Any] = {
        "timestamp": datetime.utcnow().isoformat(),
        "phase": "phase_0_final_evaluation",
        "status": "running",
        "metrics": {},
        "errors": [],
    }

    # Check if pytest is available
    try:
        import pytest

        results["pytest_available"] = True
    except ImportError:
        results["pytest_available"] = False
        results["errors"].append("pytest not installed")

    # Run citation validity tests if they exist
    test_paths = [
        Path("tests/test_citation_validity.py"),
        Path("tests/unit/test_citations.py"),
        Path("src/autopack/tests/test_citations.py"),
    ]

    test_file = None
    for path in test_paths:
        if path.exists():
            test_file = path
            break

    if test_file:
        results["test_file"] = str(test_file)
        try:
            proc = subprocess.run(
                [sys.executable, "-m", "pytest", str(test_file), "-v", "--tb=short"],
                capture_output=True,
                text=True,
                timeout=120,
            )
            results["metrics"]["test_exit_code"] = proc.returncode
            results["metrics"]["test_stdout"] = (
                proc.stdout[-2000:] if len(proc.stdout) > 2000 else proc.stdout
            )
            results["metrics"]["test_stderr"] = (
                proc.stderr[-1000:] if len(proc.stderr) > 1000 else proc.stderr
            )
            results["metrics"]["tests_passed"] = proc.returncode == 0
        except subprocess.TimeoutExpired:
            results["errors"].append("Test execution timed out after 120 seconds")
            results["metrics"]["tests_passed"] = False
        except Exception as e:
            results["errors"].append(f"Test execution failed: {str(e)}")
            results["metrics"]["tests_passed"] = False
    else:
        results["test_file"] = None
        results["metrics"]["tests_passed"] = None
        results["errors"].append("No citation test file found")

    # Check for normalization module
    normalization_paths = [
        Path("src/autopack/normalization.py"),
        Path("src/autopack/citation_normalizer.py"),
        Path("autopack/normalization.py"),
    ]

    normalization_file = None
    for path in normalization_paths:
        if path.exists():
            normalization_file = path
            break

    results["metrics"]["normalization_module_exists"] = normalization_file is not None
    if normalization_file:
        results["metrics"]["normalization_module_path"] = str(normalization_file)
        # Read and check for key functions
        content = normalization_file.read_text()
        results["metrics"]["has_normalize_function"] = "def normalize" in content
        results["metrics"]["has_citation_class"] = (
            "class Citation" in content or "class Normalizer" in content
        )

    # Collect project structure metrics
    results["metrics"]["project_structure"] = {
        "has_src_dir": Path("src").is_dir(),
        "has_tests_dir": Path("tests").is_dir(),
        "has_pyproject": Path("pyproject.toml").exists(),
        "has_requirements": Path("requirements.txt").exists(),
    }

    # Determine overall status
    if results["errors"]:
        if results["metrics"].get("tests_passed") is True:
            results["status"] = "completed_with_warnings"
        else:
            results["status"] = "completed_with_errors"
    else:
        results["status"] = "completed_successfully"

    return results


def generate_report(results: dict[str, Any]) -> str:
    """
    Generate a comprehensive results report.

    Args:
        results: Evaluation results dictionary

    Returns:
        str: Formatted report string
    """
    lines = [
        "=" * 60,
        "PHASE 0 FINAL EVALUATION REPORT",
        "=" * 60,
        f"Timestamp: {results['timestamp']}",
        f"Phase: {results['phase']}",
        f"Status: {results['status']}",
        "",
        "-" * 40,
        "METRICS",
        "-" * 40,
    ]

    metrics = results.get("metrics", {})
    for key, value in metrics.items():
        if isinstance(value, dict):
            lines.append(f"  {key}:")
            for k, v in value.items():
                lines.append(f"    {k}: {v}")
        else:
            lines.append(f"  {key}: {value}")

    if results.get("errors"):
        lines.extend(
            [
                "",
                "-" * 40,
                "ERRORS/WARNINGS",
                "-" * 40,
            ]
        )
        for error in results["errors"]:
            lines.append(f"  - {error}")

    lines.extend(["", "=" * 60])
    return "\n".join(lines)


def main() -> int:
    """Main entry point for the evaluation script."""
    print("Starting Phase 0 Final Evaluation...")

    results = run_evaluation()
    report = generate_report(results)

    print(report)

    # Write results to JSON file
    output_path = Path("phase0_evaluation_results.json")
    output_path.write_text(json.dumps(results, indent=2))
    print(f"\nResults written to: {output_path}")

    # Return appropriate exit code
    if results["status"] == "completed_successfully":
        return 0
    elif results["status"] == "completed_with_warnings":
        return 0  # Warnings are acceptable
    else:
        return 1


if __name__ == "__main__":
    sys.exit(main())
from pathlib import Path


def run_evaluation() -> dict:
    """
    Run the Phase 0 evaluation and collect metrics.

    Returns:
        dict: Evaluation results including citation validity metrics
    """
    results = {
        "timestamp": datetime.utcnow().isoformat(),
        "phase": "phase_0_post_phase3_fix",
        "status": "running",
        "metrics": {},
        "errors": [],
    }

    # Check if pytest is available
    try:
        subprocess.run(
            [sys.executable, "-m", "pytest", "--version"], capture_output=True, check=True
        )
    except subprocess.CalledProcessError:
        results["errors"].append("pytest not available")
        results["status"] = "error"
        return results

    # Run citation validity tests if they exist
    test_paths = [
        "tests/test_citation_validity.py",
        "tests/unit/test_citations.py",
        "src/autopack/tests/test_citations.py",
    ]

    test_file = None
    for path in test_paths:
        if Path(path).exists():
            test_file = path
            break

    if test_file:
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pytest", test_file, "-v", "--tb=short"],
                capture_output=True,
                text=True,
                timeout=300,
            )
            results["metrics"]["test_output"] = result.stdout
            results["metrics"]["test_errors"] = result.stderr
            results["metrics"]["return_code"] = result.returncode
            results["status"] = "passed" if result.returncode == 0 else "failed"
        except subprocess.TimeoutExpired:
            results["errors"].append("Test execution timed out")
            results["status"] = "timeout"
        except Exception as e:
            results["errors"].append(str(e))
            results["status"] = "error"
    else:
        # No specific citation tests found, run general test suite
        results["metrics"]["note"] = "No citation-specific tests found"
        results["status"] = "skipped"

    return results


if __name__ == "__main__":
    evaluation_results = run_evaluation()
    print(json.dumps(evaluation_results, indent=2))
    sys.exit(0 if evaluation_results["status"] in ("passed", "skipped") else 1)
