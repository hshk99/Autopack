#!/usr/bin/env python3
"""
CVE dependency vulnerability scanner for CI/CD pipeline.

Uses pip-audit to scan Python dependencies for known CVE vulnerabilities.
Exits with non-zero status if vulnerabilities are found (blocks CI).

Part of IMP-S04: CVE Monitoring (Phase 2 Wave 2)
"""

import subprocess
import sys


def check_cves():
    """Run pip-audit to check for CVE vulnerabilities in dependencies."""
    print("Running CVE scan with pip-audit...")

    result = subprocess.run(
        ['pip-audit', '--format', 'json'],
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        print("=" * 70)
        print("CVE VULNERABILITIES FOUND!")
        print("=" * 70)
        print(result.stdout)
        if result.stderr:
            print("\nErrors:")
            print(result.stderr)
        print("=" * 70)
        print("Action required: Review vulnerabilities and update dependencies")
        sys.exit(1)

    print("No CVE vulnerabilities found")
    print(result.stdout)


if __name__ == '__main__':
    check_cves()
