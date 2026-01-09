"""Security baseline exemption classifier for Phase C auto-merge.

This module analyzes baseline diff outputs and classifies whether changes
are safe for automatic merge without human review.

Safety Philosophy:
- Conservative by default (require human review when uncertain)
- Only auto-merge when ALL criteria are met
- Fail-safe on any ambiguity

Reference: docs/FUTURE_PLAN.md "Security Baseline Automation - Phase C"
"""

import json
import subprocess
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional


class ExemptionRule(str, Enum):
    """Known exemption rules for auto-merge."""

    TRIVY_DB_METADATA_ONLY = "trivy_db_metadata_only"
    CODEQL_HELP_TEXT_ONLY = "codeql_help_text_only"
    DEPENDENCY_BUMP_CLEAN_SCAN = "dependency_bump_clean_scan"


class ExemptionDecision(str, Enum):
    """Classification result for baseline changes."""

    AUTO_MERGE = "auto_merge"
    REQUIRE_REVIEW = "require_review"
    ERROR = "error"


@dataclass
class BaselineDiff:
    """Parsed baseline diff for classification."""

    trivy_fs_changes: dict = field(default_factory=dict)
    trivy_container_changes: dict = field(default_factory=dict)
    codeql_changes: dict = field(default_factory=dict)
    burndown_changes: dict = field(default_factory=dict)
    new_cve_ids: list[str] = field(default_factory=list)
    removed_cve_ids: list[str] = field(default_factory=list)
    severity_changes: list[dict] = field(default_factory=list)
    finding_count_before: int = 0
    finding_count_after: int = 0
    metadata_only_fields: list[str] = field(default_factory=list)

    @property
    def finding_count_delta(self) -> int:
        """Net change in finding count."""
        return self.finding_count_after - self.finding_count_before

    @property
    def has_new_cves(self) -> bool:
        """Whether any new CVE IDs were introduced."""
        return len(self.new_cve_ids) > 0

    @property
    def has_severity_escalations(self) -> bool:
        """Whether any severity increased (e.g., low→high)."""
        severity_order = ["unknown", "low", "medium", "high", "critical"]
        for change in self.severity_changes:
            old_idx = severity_order.index(change.get("old", "unknown").lower())
            new_idx = severity_order.index(change.get("new", "unknown").lower())
            if new_idx > old_idx:
                return True
        return False


@dataclass
class ClassificationResult:
    """Result of exemption classification."""

    decision: ExemptionDecision
    rationale: str
    rules_applied: list[str] = field(default_factory=list)
    confidence: float = 0.0  # 0.0-1.0, only used for logging
    dry_run: bool = False

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "decision": self.decision.value,
            "rationale": self.rationale,
            "rules_applied": self.rules_applied,
            "confidence": self.confidence,
            "dry_run": self.dry_run,
        }


class BaselineExemptionClassifier:
    """Classifier for baseline exemption decisions.

    Usage:
        classifier = BaselineExemptionClassifier()
        diff = classifier.parse_git_diff("security/baselines/")
        result = classifier.classify(diff)
        if result.decision == ExemptionDecision.AUTO_MERGE:
            # Safe to auto-merge
            ...
    """

    # Trivy metadata-only fields that are safe to change without review
    TRIVY_SAFE_METADATA_FIELDS = frozenset([
        "DataSource.ID",
        "DataSource.URL",
        "DataSource.Name",
        "Metadata.RepoDigests",
        "Metadata.RepoTags",
        "SchemaVersion",
        "ArtifactName",
        "CreatedAt",  # Scan timestamp
    ])

    # CodeQL help text fields that are safe to change without review
    CODEQL_SAFE_HELP_FIELDS = frozenset([
        "help.text",
        "help.markdown",
        "shortDescription.text",
        "fullDescription.text",
        "properties.problem.severity",  # description of severity, not actual severity
    ])

    def __init__(self, emergency_disable: bool = False, dry_run: bool = False):
        """Initialize classifier.

        Args:
            emergency_disable: If True, always require human review (Phase C disabled)
            dry_run: If True, mark results as dry-run (no actual auto-merge)
        """
        self.emergency_disable = emergency_disable
        self.dry_run = dry_run

    def parse_git_diff(self, baseline_path: str = "security/baselines/") -> BaselineDiff:
        """Parse git diff output for baseline changes.

        Args:
            baseline_path: Path to baseline directory

        Returns:
            Parsed BaselineDiff object
        """
        diff = BaselineDiff()

        try:
            # Get changed files
            result = subprocess.run(
                ["git", "diff", "--name-only", "origin/main", "--", baseline_path],
                capture_output=True,
                text=True,
                check=True,
            )
            changed_files = result.stdout.strip().split("\n") if result.stdout.strip() else []

            for filepath in changed_files:
                if not filepath:
                    continue

                # Get the actual diff for this file
                file_diff = subprocess.run(
                    ["git", "diff", "origin/main", "--", filepath],
                    capture_output=True,
                    text=True,
                    check=True,
                )

                if "trivy" in filepath.lower() and "filesystem" in filepath.lower():
                    diff.trivy_fs_changes = self._parse_trivy_diff(file_diff.stdout)
                elif "trivy" in filepath.lower() and "container" in filepath.lower():
                    diff.trivy_container_changes = self._parse_trivy_diff(file_diff.stdout)
                elif "codeql" in filepath.lower():
                    diff.codeql_changes = self._parse_codeql_diff(file_diff.stdout)

            # Aggregate findings
            diff = self._aggregate_findings(diff)

        except subprocess.CalledProcessError as e:
            # Return empty diff on git errors (will trigger require_review)
            print(f"[WARN] Git diff failed: {e}", file=sys.stderr)

        return diff

    def _parse_trivy_diff(self, diff_output: str) -> dict:
        """Parse Trivy baseline diff output."""
        changes = {
            "added_lines": [],
            "removed_lines": [],
            "metadata_only": True,
            "new_cves": [],
            "removed_cves": [],
        }

        for line in diff_output.split("\n"):
            if line.startswith("+") and not line.startswith("+++"):
                changes["added_lines"].append(line[1:].strip())
                # Check for CVE IDs in added lines
                if "CVE-" in line:
                    import re
                    cves = re.findall(r"CVE-\d{4}-\d+", line)
                    changes["new_cves"].extend(cves)
                # Check if line changes non-metadata fields
                if not any(safe in line for safe in self.TRIVY_SAFE_METADATA_FIELDS):
                    if '"VulnerabilityID"' in line or '"Severity"' in line or '"Title"' in line:
                        changes["metadata_only"] = False

            elif line.startswith("-") and not line.startswith("---"):
                changes["removed_lines"].append(line[1:].strip())
                # Check for CVE IDs in removed lines
                if "CVE-" in line:
                    import re
                    cves = re.findall(r"CVE-\d{4}-\d+", line)
                    changes["removed_cves"].extend(cves)

        return changes

    def _parse_codeql_diff(self, diff_output: str) -> dict:
        """Parse CodeQL baseline diff output."""
        changes = {
            "added_lines": [],
            "removed_lines": [],
            "help_text_only": True,
            "new_rules": [],
            "removed_rules": [],
        }

        for line in diff_output.split("\n"):
            if line.startswith("+") and not line.startswith("+++"):
                changes["added_lines"].append(line[1:].strip())
                # Check if line changes non-help fields
                if not any(safe in line for safe in self.CODEQL_SAFE_HELP_FIELDS):
                    if '"ruleId"' in line or '"level"' in line or '"location"' in line:
                        changes["help_text_only"] = False

            elif line.startswith("-") and not line.startswith("---"):
                changes["removed_lines"].append(line[1:].strip())

        return changes

    def _aggregate_findings(self, diff: BaselineDiff) -> BaselineDiff:
        """Aggregate findings across all change sources."""
        # Collect all new CVEs
        if diff.trivy_fs_changes:
            diff.new_cve_ids.extend(diff.trivy_fs_changes.get("new_cves", []))
            diff.removed_cve_ids.extend(diff.trivy_fs_changes.get("removed_cves", []))

        if diff.trivy_container_changes:
            diff.new_cve_ids.extend(diff.trivy_container_changes.get("new_cves", []))
            diff.removed_cve_ids.extend(diff.trivy_container_changes.get("removed_cves", []))

        # Deduplicate
        diff.new_cve_ids = list(set(diff.new_cve_ids))
        diff.removed_cve_ids = list(set(diff.removed_cve_ids))

        return diff

    def classify(self, diff: BaselineDiff) -> ClassificationResult:
        """Classify baseline diff for exemption decision.

        Args:
            diff: Parsed baseline diff

        Returns:
            Classification result with decision and rationale
        """
        # Emergency disable - always require review
        if self.emergency_disable:
            return ClassificationResult(
                decision=ExemptionDecision.REQUIRE_REVIEW,
                rationale="Phase C auto-merge disabled (emergency disable active)",
                rules_applied=[],
                confidence=1.0,
                dry_run=self.dry_run,
            )

        # Collect matching rules
        matching_rules: list[str] = []

        # Check Trivy DB metadata-only rule
        if self._check_trivy_metadata_only(diff):
            matching_rules.append(ExemptionRule.TRIVY_DB_METADATA_ONLY.value)

        # Check CodeQL help text-only rule
        if self._check_codeql_help_text_only(diff):
            matching_rules.append(ExemptionRule.CODEQL_HELP_TEXT_ONLY.value)

        # Check dependency bump with clean scan
        if self._check_dependency_bump_clean(diff):
            matching_rules.append(ExemptionRule.DEPENDENCY_BUMP_CLEAN_SCAN.value)

        # Decision logic
        if len(matching_rules) == 0:
            return ClassificationResult(
                decision=ExemptionDecision.REQUIRE_REVIEW,
                rationale="No exemption rules matched - requires human review",
                rules_applied=[],
                confidence=0.9,
                dry_run=self.dry_run,
            )

        if len(matching_rules) > 1:
            # Multiple rules matching = ambiguous = require review
            return ClassificationResult(
                decision=ExemptionDecision.REQUIRE_REVIEW,
                rationale=f"Multiple exemption rules matched ({', '.join(matching_rules)}) - ambiguous, requires human review",
                rules_applied=matching_rules,
                confidence=0.5,
                dry_run=self.dry_run,
            )

        # Exactly one rule matched - check safety constraints
        rule = matching_rules[0]

        # Final safety checks (must pass regardless of rule)
        if diff.has_new_cves:
            return ClassificationResult(
                decision=ExemptionDecision.REQUIRE_REVIEW,
                rationale=f"New CVE IDs detected ({', '.join(diff.new_cve_ids[:5])}) - requires human review",
                rules_applied=[rule],
                confidence=1.0,
                dry_run=self.dry_run,
            )

        if diff.has_severity_escalations:
            return ClassificationResult(
                decision=ExemptionDecision.REQUIRE_REVIEW,
                rationale="Severity escalation detected - requires human review",
                rules_applied=[rule],
                confidence=1.0,
                dry_run=self.dry_run,
            )

        if diff.finding_count_delta > 0:
            return ClassificationResult(
                decision=ExemptionDecision.REQUIRE_REVIEW,
                rationale=f"Finding count increased (+{diff.finding_count_delta}) - requires human review",
                rules_applied=[rule],
                confidence=1.0,
                dry_run=self.dry_run,
            )

        # All safety checks passed
        return ClassificationResult(
            decision=ExemptionDecision.AUTO_MERGE,
            rationale=f"Safe for auto-merge via rule: {rule}",
            rules_applied=[rule],
            confidence=0.95,
            dry_run=self.dry_run,
        )

    def _check_trivy_metadata_only(self, diff: BaselineDiff) -> bool:
        """Check if Trivy changes are metadata-only."""
        fs_changes = diff.trivy_fs_changes
        container_changes = diff.trivy_container_changes

        # If both are empty, not a Trivy-only change
        if not fs_changes and not container_changes:
            return False

        # Must have actual changes in at least one Trivy baseline
        has_trivy_changes = False
        if fs_changes and (fs_changes.get("added_lines") or fs_changes.get("removed_lines")):
            has_trivy_changes = True
        if container_changes and (container_changes.get("added_lines") or container_changes.get("removed_lines")):
            has_trivy_changes = True

        if not has_trivy_changes:
            return False

        # Check filesystem scan - must be metadata-only if present
        if fs_changes and not fs_changes.get("metadata_only", True):
            return False

        # Check container scan - must be metadata-only if present
        if container_changes and not container_changes.get("metadata_only", True):
            return False

        # No CodeQL changes should be present for this rule
        if diff.codeql_changes:
            codeql_added = diff.codeql_changes.get("added_lines", [])
            codeql_removed = diff.codeql_changes.get("removed_lines", [])
            if codeql_added or codeql_removed:
                return False

        return True

    def _check_codeql_help_text_only(self, diff: BaselineDiff) -> bool:
        """Check if CodeQL changes are help text-only."""
        codeql_changes = diff.codeql_changes

        # If empty, not a CodeQL-only change
        if not codeql_changes:
            return False

        # Must have actual changes
        if not codeql_changes.get("added_lines") and not codeql_changes.get("removed_lines"):
            return False

        # Check if help text only
        if not codeql_changes.get("help_text_only", True):
            return False

        # No Trivy changes should be present for this rule
        if diff.trivy_fs_changes:
            trivy_fs_added = diff.trivy_fs_changes.get("added_lines", [])
            trivy_fs_removed = diff.trivy_fs_changes.get("removed_lines", [])
            if trivy_fs_added or trivy_fs_removed:
                return False
        if diff.trivy_container_changes:
            trivy_container_added = diff.trivy_container_changes.get("added_lines", [])
            trivy_container_removed = diff.trivy_container_changes.get("removed_lines", [])
            if trivy_container_added or trivy_container_removed:
                return False

        return True

    def _check_dependency_bump_clean(self, diff: BaselineDiff) -> bool:
        """Check if changes are dependency bump with clean scan.

        This rule applies when:
        - Changes are NOT purely metadata-only (that's the trivy rule)
        - Changes are NOT purely help-text-only (that's the codeql rule)
        - But zero NEW findings introduced
        - And zero severity escalations
        - Must have actual changes (not just an empty diff)

        This is the "catchall" rule for any baseline changes that aren't
        purely cosmetic, but also don't introduce new security issues.
        """
        # Must have actual baseline changes to qualify
        has_changes = False
        trivy_fs_changed = False
        trivy_container_changed = False
        codeql_changed = False

        if diff.trivy_fs_changes:
            trivy_fs_added = diff.trivy_fs_changes.get("added_lines", [])
            trivy_fs_removed = diff.trivy_fs_changes.get("removed_lines", [])
            if trivy_fs_added or trivy_fs_removed:
                has_changes = True
                trivy_fs_changed = True

        if diff.trivy_container_changes:
            trivy_container_added = diff.trivy_container_changes.get("added_lines", [])
            trivy_container_removed = diff.trivy_container_changes.get("removed_lines", [])
            if trivy_container_added or trivy_container_removed:
                has_changes = True
                trivy_container_changed = True

        if diff.codeql_changes:
            codeql_added = diff.codeql_changes.get("added_lines", [])
            codeql_removed = diff.codeql_changes.get("removed_lines", [])
            if codeql_added or codeql_removed:
                has_changes = True
                codeql_changed = True

        if not has_changes:
            return False

        # This rule should NOT match if it would also match trivy_metadata_only
        # Check: is this trivy-only AND metadata-only?
        trivy_only = (trivy_fs_changed or trivy_container_changed) and not codeql_changed
        all_trivy_metadata_only = True
        if diff.trivy_fs_changes and trivy_fs_changed:
            if not diff.trivy_fs_changes.get("metadata_only", True):
                all_trivy_metadata_only = False
        if diff.trivy_container_changes and trivy_container_changed:
            if not diff.trivy_container_changes.get("metadata_only", True):
                all_trivy_metadata_only = False

        # If trivy-only AND all metadata-only, let the trivy rule handle it
        if trivy_only and all_trivy_metadata_only:
            return False

        # This rule should NOT match if it would also match codeql_help_text_only
        # Check: is this codeql-only AND help-text-only?
        codeql_only = codeql_changed and not trivy_fs_changed and not trivy_container_changed
        codeql_help_only = diff.codeql_changes.get("help_text_only", True) if diff.codeql_changes else True

        # If codeql-only AND help-text-only, let the codeql rule handle it
        if codeql_only and codeql_help_only:
            return False

        # Must have no new findings
        if diff.has_new_cves:
            return False

        # Must have no severity escalations
        if diff.has_severity_escalations:
            return False

        # Finding count must decrease or stay same
        if diff.finding_count_delta > 0:
            return False

        return True


def main():
    """CLI entry point for exemption classifier."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Classify security baseline changes for Phase C auto-merge"
    )
    parser.add_argument(
        "--baseline-path",
        default="security/baselines/",
        help="Path to baseline directory",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run in dry-run mode (report decision, don't auto-merge)",
    )
    parser.add_argument(
        "--emergency-disable",
        action="store_true",
        help="Force require-review for all changes (emergency disable)",
    )
    parser.add_argument(
        "--output-json",
        type=str,
        help="Write result to JSON file",
    )

    args = parser.parse_args()

    # Check for emergency disable env var
    import os
    emergency_disable = args.emergency_disable or os.getenv("DISABLE_PHASE_C_AUTOMERGE") == "1"

    classifier = BaselineExemptionClassifier(
        emergency_disable=emergency_disable,
        dry_run=args.dry_run,
    )

    print(f"[Phase C] Parsing baseline diff from {args.baseline_path}...")
    diff = classifier.parse_git_diff(args.baseline_path)

    print(f"[Phase C] Classifying changes...")
    print(f"  - New CVE IDs: {len(diff.new_cve_ids)}")
    print(f"  - Finding count delta: {diff.finding_count_delta:+d}")
    print(f"  - Severity escalations: {diff.has_severity_escalations}")

    result = classifier.classify(diff)

    print(f"\n[Phase C] Classification Result:")
    print(f"  Decision: {result.decision.value}")
    print(f"  Rationale: {result.rationale}")
    print(f"  Rules applied: {result.rules_applied}")
    print(f"  Dry-run: {result.dry_run}")

    if args.output_json:
        with open(args.output_json, "w") as f:
            json.dump(result.to_dict(), f, indent=2)
        print(f"\n[Phase C] Result written to {args.output_json}")

    # Exit code: 0 = auto-merge, 1 = require review, 2 = error
    if result.decision == ExemptionDecision.AUTO_MERGE:
        sys.exit(0)
    elif result.decision == ExemptionDecision.REQUIRE_REVIEW:
        sys.exit(1)
    else:
        sys.exit(2)


if __name__ == "__main__":
    main()
