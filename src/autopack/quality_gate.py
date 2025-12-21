"""Thin Quality Gate for High-Risk Categories

Following GPT's recommendation: Lightweight quality enforcement only for
high-risk categories (security, schema changes, external APIs), not a full
TRUST-5 framework.

Philosophy:
- High-risk categories: Require CI success + no major security issues
- Everything else: Attach quality labels (ok|needs_review), don't block
- No global 85% coverage enforcement (too rigid)
- Reuse existing Auditor + CI instead of building parallel system
- Integrates risk scorer for proactive risk assessment
"""

from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass, field

from .risk_scorer import RiskScorer


@dataclass
class QualityReport:
    """Quality assessment for a phase"""
    phase_id: str
    category: str

    # Quality dimensions
    ci_passed: bool
    has_major_auditor_issues: bool
    coverage_regressed: bool

    # Quality label
    quality_level: str  # "ok" | "needs_review" | "blocked"

    # Details
    issues: List[str]
    warnings: List[str]

    # Risk assessment (from risk scorer)
    risk_assessment: Optional[Dict] = None

    def is_blocked(self) -> bool:
        """Check if phase should be blocked"""
        return self.quality_level == "blocked"

    def needs_review(self) -> bool:
        """Check if phase needs human review"""
        return self.quality_level in ["needs_review", "blocked"]


class QualityGate:
    """
    Thin quality gate for high-risk categories only.

    High-risk categories (strict):
    - external_feature_reuse: Using external libraries/APIs
    - security_auth_change: Security or auth code changes
    - schema_contract_change: Database or API schema changes

    All other categories (lenient):
    - Attach quality labels but don't block
    - Warn on issues but allow progress
    """

    # High-risk categories that require strict quality checks
    HIGH_RISK_CATEGORIES = [
        "external_feature_reuse",
        "security_auth_change",
        "schema_contract_change",
    ]

    def __init__(self, repo_root: Path, config: Optional[Dict] = None):
        """
        Initialize quality gate.

        Args:
            repo_root: Repository root directory
            config: Optional config with test_strictness setting
        """
        self.root = repo_root
        self.config = config or {}

        # Get strictness level from config (lenient|normal|strict)
        self.strictness = self.config.get("quality", {}).get("test_strictness", "normal")

        # Initialize risk scorer
        self.risk_scorer = RiskScorer(repo_root=repo_root)

    def assess_phase(
        self,
        phase_id: str,
        phase_spec: Dict,
        auditor_result: Optional[Dict] = None,
        ci_result: Optional[Dict] = None,
        coverage_delta: Optional[float] = None,
        patch_content: Optional[str] = None,
        files_changed: Optional[List[str]] = None,
    ) -> QualityReport:
        """
        Assess quality for a phase.

        Args:
            phase_id: Phase identifier
            phase_spec: Phase specification with task_category
            auditor_result: Auditor review result (issues, approval)
            ci_result: CI test result (passed, failed, skipped)
            coverage_delta: Coverage change (+5%, -2%, etc.)
            patch_content: Optional patch/diff content for risk scoring
            files_changed: Optional list of changed files for risk scoring

        Returns:
            QualityReport with quality level and details
        """
        task_category = phase_spec.get("task_category", "general")
        is_high_risk = task_category in self.HIGH_RISK_CATEGORIES

        issues = []
        warnings = []

        # Run risk assessment if patch info available
        risk_result = None
        if files_changed is not None:
            # Extract LOC from patch if available
            loc_added, loc_removed = self._extract_loc_from_patch(patch_content)

            risk_result = self.risk_scorer.score_change(
                files_changed=files_changed,
                loc_added=loc_added,
                loc_removed=loc_removed,
                patch_content=patch_content,
            )

            # Add risk warnings for high/critical risk
            if risk_result["risk_level"] in ["high", "critical"]:
                for reason in risk_result["reasons"]:
                    warnings.append(f"Risk: {reason}")

        # Check CI status
        ci_passed = True
        if ci_result:
            status = ci_result.get("status")
            if status is None:
                status = "passed" if ci_result.get("passed", True) else "failed"

            message = ci_result.get("message") or ci_result.get("error") or "Unknown error"

            if status == "skipped":
                ci_passed = True
                warnings.append(f"CI skipped: {message}")
            else:
                ci_passed = status == "passed"
                if not ci_passed:
                    issues.append(f"CI tests failed: {message}")

        # Check Auditor issues
        has_major_issues = False
        if auditor_result:
            auditor_issues = auditor_result.get("issues_found", [])
            major_issues = [i for i in auditor_issues if i.get("severity") == "major"]

            if major_issues:
                has_major_issues = True

                # For high-risk categories, major issues are blocking
                if is_high_risk:
                    for issue in major_issues:
                        issues.append(f"Major issue: {issue.get('description', 'Unknown')}")
                else:
                    # For normal categories, major issues are warnings
                    for issue in major_issues:
                        warnings.append(f"Major issue (non-blocking): {issue.get('description', 'Unknown')}")

        # Check coverage regression
        coverage_regressed = False
        if coverage_delta is not None and coverage_delta < -2.0:
            coverage_regressed = True

            # For strict mode, coverage regression is an issue
            if self.strictness == "strict":
                issues.append(f"Coverage regressed by {abs(coverage_delta):.1f}%")
            else:
                warnings.append(f"Coverage regressed by {abs(coverage_delta):.1f}% (allowed in {self.strictness} mode)")

        # Determine quality level
        quality_level = self._determine_quality_level(
            is_high_risk=is_high_risk,
            ci_passed=ci_passed,
            has_major_issues=has_major_issues,
            coverage_regressed=coverage_regressed,
            risk_result=risk_result,
        )

        return QualityReport(
            phase_id=phase_id,
            category=task_category,
            ci_passed=ci_passed,
            has_major_auditor_issues=has_major_issues,
            coverage_regressed=coverage_regressed,
            quality_level=quality_level,
            issues=issues,
            warnings=warnings,
            risk_assessment=risk_result,
        )

    def _extract_loc_from_patch(self, patch_content: Optional[str]) -> tuple[int, int]:
        """Extract lines added/removed from patch content.

        Args:
            patch_content: Git diff/patch content

        Returns:
            Tuple of (lines_added, lines_removed)
        """
        if not patch_content:
            return 0, 0

        lines_added = 0
        lines_removed = 0

        for line in patch_content.split("\n"):
            if line.startswith("+") and not line.startswith("+++"):
                lines_added += 1
            elif line.startswith("-") and not line.startswith("---"):
                lines_removed += 1

        return lines_added, lines_removed

    def _determine_quality_level(
        self,
        is_high_risk: bool,
        ci_passed: bool,
        has_major_issues: bool,
        coverage_regressed: bool,
        risk_result: Optional[Dict] = None,
    ) -> str:
        """
        Determine quality level based on checks.

        Returns:
            "ok" | "needs_review" | "blocked"
        """
        # NEW: Check for large deletions that require approval
        if risk_result:
            checks = risk_result.get("checks", {})

            # Block if deletion threshold exceeded
            if checks.get("deletion_threshold_exceeded"):
                return "blocked"  # Requires human approval

            # Block if risk level is critical
            if risk_result.get("risk_level") == "critical":
                return "blocked"  # Too risky to proceed automatically

        if is_high_risk:
            # High-risk categories: Strict enforcement
            if not ci_passed:
                return "blocked"  # CI must pass

            if has_major_issues:
                return "blocked"  # No major security/contract issues

            if self.strictness == "strict" and coverage_regressed:
                return "needs_review"  # Coverage regression needs review

            return "ok"
        else:
            # Normal categories: Lenient enforcement
            if not ci_passed:
                return "needs_review"  # CI failure needs review but doesn't block

            if has_major_issues:
                return "needs_review"  # Major issues need review but don't block

            return "ok"

    def format_report(self, report: QualityReport) -> str:
        """
        Format quality report for display.

        Args:
            report: Quality report to format

        Returns:
            Formatted string for console output
        """
        lines = []

        lines.append(f"[Quality Gate] Phase {report.phase_id}")
        lines.append(f"Category: {report.category}")
        lines.append(f"Quality Level: {report.quality_level.upper()}")

        # Add risk assessment if available
        if report.risk_assessment:
            risk_level = report.risk_assessment["risk_level"]
            risk_score = report.risk_assessment["risk_score"]
            risk_emoji = {
                "low": "✅",
                "medium": "⚠️",
                "high": "🔴",
                "critical": "🚨",
            }.get(risk_level, "❓")
            lines.append(f"Risk Level: {risk_emoji} {risk_level.upper()} (score: {risk_score}/100)")

        if report.issues:
            lines.append("\nIssues (blocking):")
            for issue in report.issues:
                lines.append(f"  ✗ {issue}")

        if report.warnings:
            lines.append("\nWarnings (non-blocking):")
            for warning in report.warnings:
                lines.append(f"  ⚠ {warning}")

        if report.quality_level == "ok" and not report.warnings:
            lines.append("\n✓ All quality checks passed")

        return "\n".join(lines)


def integrate_with_auditor(auditor_result: Dict, quality_report: QualityReport) -> Dict:
    """
    Integrate quality gate results with existing auditor result.

    Args:
        auditor_result: Original auditor result
        quality_report: Quality gate assessment

    Returns:
        Enhanced auditor result with quality gate info
    """
    # Add quality gate assessment to auditor result
    auditor_result["quality_gate"] = {
        "quality_level": quality_report.quality_level,
        "is_blocked": quality_report.is_blocked(),
        "issues": quality_report.issues,
        "warnings": quality_report.warnings,
    }

    # Add risk assessment if available
    if quality_report.risk_assessment:
        auditor_result["risk_assessment"] = {
            "risk_score": quality_report.risk_assessment["risk_score"],
            "risk_level": quality_report.risk_assessment["risk_level"],
            "risk_reasons": quality_report.risk_assessment["reasons"],
        }

    # If quality gate blocks, override auditor approval
    if quality_report.is_blocked():
        auditor_result["approved"] = False

        # Add blocking issues to auditor issues
        for issue in quality_report.issues:
            auditor_result.setdefault("issues_found", []).append({
                "severity": "major",
                "category": "quality_gate",
                "description": issue,
                "location": "quality_gate"
            })

    return auditor_result
