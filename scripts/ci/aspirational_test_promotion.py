#!/usr/bin/env python3
"""
Aspirational Test Promotion Tracker (Item 1.2 Follow-up).

This script helps manage the "aspirational → core" promotion cadence:
1. Lists all aspirational tests and their xfail status
2. Identifies xpass tests (passing but still marked xfail)
3. Suggests tests ready for promotion to core
4. Provides commands to promote tests

Usage:
    # List all aspirational tests
    python scripts/ci/aspirational_test_promotion.py --list

    # Find xpass tests (candidates for promotion)
    python scripts/ci/aspirational_test_promotion.py --find-xpass

    # Generate promotion report
    python scripts/ci/aspirational_test_promotion.py --report

See docs/CONTRIBUTING.md for full aspirational test ladder policy.
"""

import argparse
import ast
import re
import subprocess
import sys
from pathlib import Path
from typing import List, Dict, Tuple


class AspirationalTestTracker:
    """Track and report on aspirational test status."""

    def __init__(self, repo_root: Path):
        self.repo_root = repo_root
        self.tests_dir = repo_root / "tests"

    def find_aspirational_tests(self) -> List[Tuple[Path, str, bool]]:
        """
        Find all tests marked with pytest.mark.aspirational or pytest.mark.xfail.

        Returns:
            List of (file_path, test_name, has_xfail_marker) tuples
        """
        results = []

        for test_file in self.tests_dir.rglob("test_*.py"):
            try:
                content = test_file.read_text(encoding="utf-8")
                tree = ast.parse(content, filename=str(test_file))

                for node in ast.walk(tree):
                    if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
                        # Check for aspirational or xfail decorators
                        has_aspirational = False
                        has_xfail = False

                        for decorator in node.decorator_list:
                            decorator_str = ast.unparse(decorator)
                            if "aspirational" in decorator_str:
                                has_aspirational = True
                            if "xfail" in decorator_str:
                                has_xfail = True

                        if has_aspirational or has_xfail:
                            results.append((test_file, node.name, has_xfail))

            except Exception as e:
                print(f"Warning: Could not parse {test_file}: {e}", file=sys.stderr)

        return results

    def run_aspirational_tests(self) -> Dict[str, str]:
        """
        Run aspirational tests and capture results.

        Returns:
            Dict mapping test ID to status (passed, xfailed, xpassed, failed)
        """
        try:
            result = subprocess.run(
                ["pytest", "tests/", "-m", "aspirational", "-v", "--tb=no"],
                cwd=self.repo_root,
                capture_output=True,
                text=True,
                timeout=300
            )

            # Parse pytest output for test results
            status_map = {}
            for line in result.stdout.splitlines():
                # Match lines like: tests/test_file.py::test_name XPASS
                match = re.match(r"(tests/[^\s]+)::(test_\w+)\s+(PASSED|XFAIL|XPASS|FAILED)", line)
                if match:
                    test_id = f"{match.group(1)}::{match.group(2)}"
                    status = match.group(3)
                    status_map[test_id] = status

            return status_map

        except subprocess.TimeoutExpired:
            print("Error: Test run timed out", file=sys.stderr)
            return {}
        except Exception as e:
            print(f"Error running tests: {e}", file=sys.stderr)
            return {}

    def list_all_aspirational_tests(self):
        """List all aspirational tests with their markers."""
        tests = self.find_aspirational_tests()

        print("Aspirational Tests Inventory")
        print("=" * 80)
        print(f"Total: {len(tests)} tests\n")

        for file_path, test_name, has_xfail in sorted(tests):
            rel_path = file_path.relative_to(self.repo_root)
            marker = "xfail" if has_xfail else "aspirational"
            print(f"  [{marker}] {rel_path}::{test_name}")

    def find_promotion_candidates(self):
        """Find xpass tests (passing but still marked xfail) - ready for promotion."""
        print("Finding promotion candidates (xpass tests)...")
        print("=" * 80)

        test_results = self.run_aspirational_tests()

        if not test_results:
            print("Could not run aspirational tests. Run pytest manually to check status.")
            return

        xpass_tests = [test_id for test_id, status in test_results.items() if status == "XPASS"]

        if not xpass_tests:
            print("✓ No xpass tests found - all aspirational tests are properly marked.")
            return

        print(f"\n✓ Found {len(xpass_tests)} promotion candidates (xpass):\n")

        for test_id in sorted(xpass_tests):
            print(f"  - {test_id}")

        print("\nPromotion Process:")
        print("  1. Remove @pytest.mark.xfail decorator")
        print("  2. Remove @pytest.mark.aspirational decorator")
        print("  3. Test passes in core gate: pytest tests/ -m 'not research and not aspirational'")
        print("  4. Commit with message: 'test: promote <test_name> to core gate'")

    def generate_report(self):
        """Generate comprehensive promotion report."""
        print("Aspirational Test Promotion Report")
        print("=" * 80)
        print()

        tests = self.find_aspirational_tests()
        test_results = self.run_aspirational_tests()

        # Categorize tests
        xpass_tests = []
        xfail_tests = []
        passed_tests = []
        failed_tests = []

        for file_path, test_name, has_xfail in tests:
            rel_path = file_path.relative_to(self.repo_root)
            test_id = f"{rel_path.as_posix()}::{test_name}"

            status = test_results.get(test_id, "UNKNOWN")

            if status == "XPASS":
                xpass_tests.append(test_id)
            elif status == "XFAIL":
                xfail_tests.append(test_id)
            elif status == "PASSED":
                passed_tests.append(test_id)
            elif status == "FAILED":
                failed_tests.append(test_id)

        print(f"Total Aspirational Tests: {len(tests)}")
        print()
        print(f"✓ XPASS (Ready for Promotion):  {len(xpass_tests)}")
        print(f"⚠ XFAIL (Expected Failures):    {len(xfail_tests)}")
        print(f"✓ PASSED (No xfail marker):     {len(passed_tests)}")
        print(f"✗ FAILED (Needs Investigation): {len(failed_tests)}")
        print()

        if xpass_tests:
            print("HIGH PRIORITY: Promote these xpass tests to core:")
            for test_id in sorted(xpass_tests):
                print(f"  - {test_id}")
            print()

        if passed_tests:
            print("PASSED tests without xfail marker (already promotable):")
            for test_id in sorted(passed_tests):
                print(f"  - {test_id}")
            print()

        if failed_tests:
            print("FAILED tests (investigate before promoting):")
            for test_id in sorted(failed_tests):
                print(f"  - {test_id}")
            print()

        print("Promotion Cadence Recommendation:")
        print("  - Weekly review: Check xpass tests")
        print("  - Monthly quota: Promote 2-3 stable tests per month")
        print("  - Goal: Reduce aspirational backlog to <20 tests by Q2 2026")


def main():
    parser = argparse.ArgumentParser(
        description="Track and promote aspirational tests to core gate"
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List all aspirational tests"
    )
    parser.add_argument(
        "--find-xpass",
        action="store_true",
        help="Find xpass tests (promotion candidates)"
    )
    parser.add_argument(
        "--report",
        action="store_true",
        help="Generate comprehensive promotion report"
    )

    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parent.parent.parent
    tracker = AspirationalTestTracker(repo_root)

    if args.list:
        tracker.list_all_aspirational_tests()
    elif args.find_xpass:
        tracker.find_promotion_candidates()
    elif args.report:
        tracker.generate_report()
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
