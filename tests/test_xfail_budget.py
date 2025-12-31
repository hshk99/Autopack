"""Test to guard against untracked growth of xfail markers.

This test ensures that the number of xfail-marked tests doesn't increase
without explicit documentation and review. Any increase in xfail count
requires updating the EXPECTED_XFAIL_COUNT constant and documenting the
reason in the commit message.

Philosophy:
- xfail markers should be explicitly tracked and justified
- Growing xfail count indicates growing technical debt
- Each xfail should have a clear reason and tracking identifier
- Unexpected xpass should be investigated (test might be fixed)

Current xfails (as of 2025-12-31 BUILD-146 Phase A P15):
- 6 module-level xfail files (~110 tests): extended test suites + high-signal aspirational
  * test_context_budgeter_extended.py
  * test_error_recovery_extended.py
  * test_governance_requests_extended.py
  * test_token_estimator_calibration.py
  * test_memory_service_extended.py
  * test_build_history_integrator.py
- 5 function-level xfails:
  * 3 parallel_orchestrator tests - aspirational WorkspaceManager integration
  * 1 dashboard integration test - DB session isolation issue
  * 1 telemetry_unblock_fixes T2 test - retry logic not yet implemented

Total: 115 xfailed tests (down from 121 after P15 XPASS graduation)

Changes in P15:
- Graduated 67 tests that were XPASS (removed stale xfail markers)
- Removed module-level xfail from: test_telemetry_utils.py, test_deep_retrieval_extended.py, test_telemetry_unblock_fixes.py
- Added 1 function-level xfail for T2 retry logic test
- Net reduction: 121 → 115 xfailed tests
"""
import pytest
import subprocess
import sys

# Expected xfail count as of 2025-12-31 BUILD-146 Phase A P15
# Update this number when adding new xfails, with documentation in commit message
# Current breakdown:
# - 6 module-level xfail files (~110 tests): extended test suites + high-signal aspirational
# - 5 function-level xfails: 3 parallel_orchestrator + 1 dashboard + 1 telemetry T2
EXPECTED_XFAIL_COUNT = 115

# Tolerance for minor variations in xfail count (e.g., parameterized tests)
TOLERANCE = 5


def test_xfail_budget_not_exceeded():
    """Verify that xfail count hasn't grown without explicit approval.

    This test counts xfail markers in the codebase directly rather than
    running pytest, since subprocess execution can be unreliable in CI.
    """
    import pathlib
    import re

    # Count files with module-level pytestmark xfail
    tests_dir = pathlib.Path("tests")
    module_xfail_files = []
    function_xfail_count = 0

    for py_file in tests_dir.rglob("test_*.py"):
        content = py_file.read_text(encoding="utf-8")

        # Check for module-level xfail
        if re.search(r"^pytestmark\s*=\s*pytest\.mark\.xfail", content, re.MULTILINE):
            module_xfail_files.append(str(py_file))

        # Count function-level xfails
        function_xfail_count += len(re.findall(r"@pytest\.mark\.xfail", content))

    # Estimate total xfails
    # Module-level xfails mark all tests in file - estimate based on actual average
    # As of P15: 110 module xfails / 6 files = ~18.3 tests per file
    estimated_tests_per_module = 18  # Average for extended test suites (updated in P15)
    estimated_module_xfails = len(module_xfail_files) * estimated_tests_per_module

    total_estimated_xfails = estimated_module_xfails + function_xfail_count

    # Check if count is within acceptable range
    max_allowed = EXPECTED_XFAIL_COUNT + TOLERANCE

    if total_estimated_xfails > max_allowed:
        pytest.fail(
            f"XFAIL count ({total_estimated_xfails}) exceeds budget ({EXPECTED_XFAIL_COUNT} + {TOLERANCE} tolerance).\n"
            f"Module-level xfails: {len(module_xfail_files)} files (est. {estimated_module_xfails} tests)\n"
            f"Function-level xfails: {function_xfail_count} tests\n"
            f"This indicates new tests are being marked as xfail without proper tracking.\n"
            f"To fix:\n"
            f"1. Review newly added xfails and ensure they have clear reasons\n"
            f"2. Update EXPECTED_XFAIL_COUNT in tests/test_xfail_budget.py\n"
            f"3. Document the new xfails in your commit message\n"
            f"4. Consider if the xfail is truly necessary or if the test should be fixed"
        )

    # Log the current count for visibility
    print(f"✓ XFAIL budget check passed: {total_estimated_xfails} estimated xfails (max allowed: {max_allowed})")
    print(f"  - {len(module_xfail_files)} module-level xfail files (est. {estimated_module_xfails} tests)")
    print(f"  - {function_xfail_count} function-level xfails")


def test_xfail_markers_have_reasons():
    """Verify that all xfail markers include a reason string.

    xfail markers without reasons make it hard to track why tests are failing
    and when they should be fixed.
    """
    # This is a static check - would require AST parsing to implement fully
    # For now, just document the requirement
    pytest.skip("Static analysis not implemented - manual review required")
