#!/usr/bin/env python3
"""
Generate or verify security burndown counts in SECURITY_BURNDOWN.md

This script:
1. Reads baseline JSON files (CodeQL, Trivy filesystem, Trivy container)
2. Computes counts by severity/category
3. Rewrites the marker-delimited section in docs/SECURITY_BURNDOWN.md

Usage:
    python scripts/security/generate_security_burndown_counts.py        # Update burndown section
    python scripts/security/generate_security_burndown_counts.py --check  # Exit non-zero if drift
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Dict, List


def load_findings(path: Path) -> List[dict]:
    """Load normalized findings from a baseline JSON file."""
    if not path.exists():
        return []
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def summarize_counts(findings_by_source: Dict[str, List[dict]]) -> dict:
    """
    Compute counts by source.

    Returns:
        {
            "codeql": {"total": 140},
            "trivy-fs": {"total": 0},
            "trivy-image": {"total": 0},
            "timestamp": "2026-01-05"
        }
    """
    summary = {}

    for source, findings in findings_by_source.items():
        summary[source] = {"total": len(findings)}

    return summary


def _get_last_updated_from_git(repo_root: Path) -> str:
    """
    Return a deterministic "last updated" date for the baseline counts.

    IMPORTANT: Do not use wall-clock time; that would cause CI drift every day.
    We instead use the last commit date that touched `security/baselines/`.
    """
    try:
        res = subprocess.run(
            ["git", "-C", str(repo_root), "log", "-1", "--format=%cs", "--", "security/baselines"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
        date_str = (res.stdout or "").strip()
        return date_str or "unknown"
    except Exception:
        return "unknown"


def render_markdown(summary: dict, *, last_updated: str) -> str:
    """
    Render markdown table from summary counts.

    Returns the content between (but not including) the AUTO_COUNTS markers.
    """
    codeql_total = summary.get("codeql", {}).get("total", 0)
    trivy_fs_total = summary.get("trivy-fs", {}).get("total", 0)
    trivy_image_total = summary.get("trivy-image", {}).get("total", 0)

    total_high = codeql_total + trivy_fs_total + trivy_image_total
    timestamp = last_updated or "unknown"

    lines = [
        "",
        "| Category | Critical | High | Medium | Low | Total |",
        "|----------|----------|------|--------|-----|-------|",
        f"| **Trivy (filesystem)** | 0 | {trivy_fs_total} | - | - | {trivy_fs_total} |",
        f"| **Trivy (container)** | 0 | {trivy_image_total} | - | - | {trivy_image_total} |",
        f"| **CodeQL** | 0 | {codeql_total} | - | - | {codeql_total} |",
        f"| **Total** | **0** | **{total_high}** | **-** | **-** | **{total_high}** |",
        "",
        f"_Last Updated: {timestamp} (auto-generated from security/baselines/)_",
        "",
    ]

    return "\n".join(lines)


def replace_block(md_content: str, new_block: str) -> str:
    """
    Replace content between AUTO_COUNTS_START and AUTO_COUNTS_END markers.

    Raises ValueError if markers are missing.
    """
    start_marker = "<!-- AUTO_COUNTS_START -->"
    end_marker = "<!-- AUTO_COUNTS_END -->"

    if start_marker not in md_content or end_marker not in md_content:
        raise ValueError(
            f"Missing markers in SECURITY_BURNDOWN.md. Expected:\n"
            f"  {start_marker}\n"
            f"  {end_marker}"
        )

    parts = md_content.split(start_marker, 1)
    before = parts[0]
    rest = parts[1]

    after = rest.split(end_marker, 1)[1]

    return f"{before}{start_marker}{new_block}{end_marker}{after}"


def main():
    parser = argparse.ArgumentParser(description="Generate security burndown counts")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check if burndown section is up-to-date (exit non-zero if drift)",
    )
    args = parser.parse_args()

    # Paths
    repo_root = Path(__file__).parent.parent.parent
    baselines_dir = repo_root / "security" / "baselines"
    burndown_path = repo_root / "docs" / "SECURITY_BURNDOWN.md"

    # Load baseline findings
    findings_by_source = {
        "codeql": load_findings(baselines_dir / "codeql.python.json"),
        "trivy-fs": load_findings(baselines_dir / "trivy-fs.high.json"),
        "trivy-image": load_findings(baselines_dir / "trivy-image.high.json"),
    }

    # Compute summary
    summary = summarize_counts(findings_by_source)

    # Render new block
    last_updated = _get_last_updated_from_git(repo_root)
    new_block = render_markdown(summary, last_updated=last_updated)

    # Read current burndown
    if not burndown_path.exists():
        print(f"ERROR: {burndown_path} not found", file=sys.stderr)
        sys.exit(1)

    current_content = burndown_path.read_text(encoding="utf-8")

    try:
        updated_content = replace_block(current_content, new_block)
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    if args.check:
        # Check mode: exit non-zero if drift
        if updated_content != current_content:
            print("ERROR: SECURITY_BURNDOWN.md counts are out of sync with baselines.", file=sys.stderr)
            print("Run: python scripts/security/generate_security_burndown_counts.py", file=sys.stderr)
            sys.exit(1)
        else:
            print("✓ SECURITY_BURNDOWN.md counts are up-to-date")
            sys.exit(0)
    else:
        # Update mode: write new content
        burndown_path.write_text(updated_content, encoding="utf-8")
        print(f"✓ Updated {burndown_path}")
        print(f"  CodeQL: {summary['codeql']['total']} findings")
        print(f"  Trivy FS: {summary['trivy-fs']['total']} findings")
        print(f"  Trivy Image: {summary['trivy-image']['total']} findings")
        sys.exit(0)


if __name__ == "__main__":
    main()
