#!/usr/bin/env python3
"""
SARIF Normalization for Deterministic Baseline Comparison

Purpose: Convert SARIF files to stable, sorted JSON keys for diff gate enforcement.

Design Goals:
- Deterministic output (same input -> same output across runs)
- Platform-agnostic (normalize Windows vs Linux paths)
- Stable across minor code shifts (where feasible)

Usage:
    python scripts/security/normalize_sarif.py trivy-results.sarif > normalized.json
    python scripts/security/normalize_sarif.py --tool trivy trivy-fs.sarif trivy-container.sarif > combined.json
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List


def normalize_path(path: str) -> str:
    """
    Normalize file paths to be platform-agnostic.

    - Replace backslashes with forward slashes
    - Remove leading './' or '.\'
    - Ensure consistent representation
    """
    normalized = path.replace("\\", "/")
    if normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized


def extract_finding_key(result: Dict[str, Any], tool_name: str) -> Dict[str, Any]:
    """
    Extract a stable, deterministic key from a SARIF result object.

    Key Components (where available):
    - tool: Scanner name (trivy, codeql, etc.)
    - ruleId: Security rule or CVE identifier
    - fingerprint: Stable SARIF fingerprint (preferred for CodeQL shift-tolerance)
    - artifactUri: Normalized file path
    - message: Finding description (hashed to avoid verbosity)
    - location: Start line/column (only if no fingerprint exists)

    Shift-Tolerance Strategy:
    - Prefer partialFingerprints/fingerprints from SARIF for stability across code motion
    - For CodeQL: exclude line/column unless no fingerprint exists (prevents baseline drift)
    - For Trivy/others: include line/column for precision (CVEs are file-specific)
    """
    rule_id = result.get("ruleId", "unknown")
    message_text = ""

    # Extract message text
    if "message" in result:
        if isinstance(result["message"], dict):
            message_text = result["message"].get("text", "")
        else:
            message_text = str(result["message"])

    # Extract stable fingerprint if available (preferred for CodeQL)
    fingerprint = None
    if "partialFingerprints" in result:
        # CodeQL provides primaryLocationLineHash or other stable fingerprints
        partial = result["partialFingerprints"]
        fingerprint = partial.get("primaryLocationLineHash") or partial.get("primaryLocationStartColumnFingerprint")
    elif "fingerprints" in result:
        # Fallback to top-level fingerprints
        fps = result["fingerprints"]
        fingerprint = next((v for v in fps.values() if v), None)

    # Extract artifact location
    artifact_uri = "unknown"
    start_line = None
    start_column = None

    if "locations" in result and len(result["locations"]) > 0:
        location = result["locations"][0]
        if "physicalLocation" in location:
            phys_loc = location["physicalLocation"]

            # Artifact URI
            if "artifactLocation" in phys_loc:
                artifact_uri = normalize_path(
                    phys_loc["artifactLocation"].get("uri", "unknown")
                )

            # Region (line/column) - extract but conditionally include below
            if "region" in phys_loc:
                region = phys_loc["region"]
                start_line = region.get("startLine")
                start_column = region.get("startColumn")

    # Hash message to create stable, compact key (avoid long text bloat)
    message_hash = hashlib.sha256(message_text.encode("utf-8")).hexdigest()[:16]

    # Build finding key
    key: Dict[str, Any] = {
        "tool": tool_name,
        "ruleId": rule_id,
        "artifactUri": artifact_uri,
        "messageHash": message_hash,
    }

    # Shift-tolerance: prefer fingerprint over line/column for CodeQL
    if fingerprint:
        key["fingerprint"] = fingerprint
    elif tool_name == "codeql":
        # CodeQL without fingerprint: still exclude line/column for shift-tolerance
        # (ruleId + artifactUri + messageHash is sufficient for most cases)
        pass
    else:
        # Non-CodeQL tools (Trivy): include line/column for precision
        if start_line is not None:
            key["startLine"] = start_line
        if start_column is not None:
            key["startColumn"] = start_column

    return key


def normalize_sarif_file(sarif_path: Path, tool_name: str = None) -> List[Dict[str, Any]]:
    """
    Parse a SARIF file and extract normalized finding keys.

    Args:
        sarif_path: Path to SARIF file
        tool_name: Override tool name (auto-detect if None)

    Returns:
        List of normalized finding dictionaries (sorted for determinism)
    """
    with open(sarif_path, "r", encoding="utf-8") as f:
        sarif_data = json.load(f)

    findings = []

    # SARIF structure: runs[] -> tool + results[]
    for run in sarif_data.get("runs", []):
        # Auto-detect tool name if not provided
        detected_tool = tool_name
        if not detected_tool:
            tool_info = run.get("tool", {}).get("driver", {})
            detected_tool = tool_info.get("name", "unknown").lower()

        # Extract results
        results = run.get("results", [])
        for result in results:
            finding_key = extract_finding_key(result, detected_tool)
            findings.append(finding_key)

    # Sort for deterministic output (by JSON representation)
    findings.sort(key=lambda x: json.dumps(x, sort_keys=True))

    return findings


def main():
    parser = argparse.ArgumentParser(
        description="Normalize SARIF files to deterministic JSON finding keys"
    )
    parser.add_argument(
        "sarif_files",
        nargs="+",
        type=Path,
        help="One or more SARIF files to normalize",
    )
    parser.add_argument(
        "--tool",
        help="Override tool name (default: auto-detect from SARIF)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Output file path (default: stdout)",
    )

    args = parser.parse_args()

    all_findings = []
    for sarif_file in args.sarif_files:
        if not sarif_file.exists():
            print(f"Error: SARIF file not found: {sarif_file}", file=sys.stderr)
            sys.exit(1)

        findings = normalize_sarif_file(sarif_file, args.tool)
        all_findings.extend(findings)

    # Deduplicate (in case multiple SARIF files have overlapping findings)
    unique_findings = []
    seen = set()
    for finding in all_findings:
        finding_json = json.dumps(finding, sort_keys=True)
        if finding_json not in seen:
            seen.add(finding_json)
            unique_findings.append(finding)

    # Sort final output for determinism
    unique_findings.sort(key=lambda x: json.dumps(x, sort_keys=True))

    # Output
    output_json = json.dumps(unique_findings, indent=2, sort_keys=True)

    if args.output:
        args.output.write_text(output_json, encoding="utf-8")
        print(f"Normalized {len(unique_findings)} findings to {args.output}", file=sys.stderr)
    else:
        print(output_json)

    return 0


if __name__ == "__main__":
    sys.exit(main())
