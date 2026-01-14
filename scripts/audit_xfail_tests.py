"""Audit xfail tests to identify which can be fixed or removed.

This script finds all xfail-marked tests in the codebase and provides
a summary of their locations and potential actions.
"""

import subprocess
import re
from pathlib import Path
from typing import List, Dict, Tuple


def find_xfail_tests() -> Tuple[List[Dict], List[Dict]]:
    """Find all xfail tests in codebase.

    Returns:
        Tuple of (module_level_xfails, function_level_xfails)
    """
    module_xfails = []
    function_xfails = []

    tests_dir = Path("tests")

    for py_file in tests_dir.rglob("test_*.py"):
        try:
            content = py_file.read_text(encoding="utf-8")
        except Exception as e:
            print(f"Warning: Could not read {py_file}: {e}")
            continue

        # Check for module-level xfail (both direct and in list)
        if re.search(r"pytestmark\s*=.*?pytest\.mark\.xfail", content, re.MULTILINE | re.DOTALL):
            # Count tests in this file
            test_funcs = len(re.findall(r"^def test_", content, re.MULTILINE))
            module_xfails.append(
                {
                    "file": str(py_file),
                    "line": 1,
                    "type": "module-level",
                    "estimated_tests": test_funcs,
                }
            )

        # Count function-level xfails by counting @pytest.mark.xfail decorators
        for match in re.finditer(r"@pytest\.mark\.xfail", content):
            line_no = content[: match.start()].count("\n") + 1
            function_xfails.append(
                {
                    "file": str(py_file),
                    "line": line_no,
                    "type": "function-level",
                }
            )

    return module_xfails, function_xfails


def main():
    """Main entry point."""
    print("Auditing xfail tests...\n")

    module_xfails, function_xfails = find_xfail_tests()

    # Estimate total based on file statistics
    total_module_estimated = sum(x["estimated_tests"] for x in module_xfails)
    total_function = len(function_xfails)

    print(f"MODULE-LEVEL XFAIL FILES: {len(module_xfails)}")
    print("-" * 80)
    for xfail in sorted(module_xfails, key=lambda x: x["file"]):
        print(f"  {xfail['file']}")
        print(f"    Estimated tests: {xfail['estimated_tests']}")

    print(f"\nFUNCTION-LEVEL XFAILS: {total_function}")
    print("-" * 80)
    if function_xfails:
        for xfail in sorted(function_xfails, key=lambda x: (x["file"], x["line"])):
            func_info = f" - {xfail.get('func_name', '?')}" if xfail.get("func_name") else ""
            print(f"  {xfail['file']}:{xfail['line']}{func_info}")

    print("\n" + "=" * 80)
    print("SUMMARY:")
    print(
        f"  Module-level xfail files: {len(module_xfails)} (estimated {total_module_estimated} tests)"
    )
    print(f"  Function-level xfails: {total_function} tests")
    print(f"  TOTAL ESTIMATED: {total_module_estimated + total_function} xfail tests")
    print("=" * 80)

    return len(module_xfails), total_function


if __name__ == "__main__":
    main()
