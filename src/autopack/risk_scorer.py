"""Risk Scorer - Deterministic proactive risk assessment

Ported from chatbot_project as metadata provider for quality gate.
Complements learned rules (reactive) with proactive static analysis.

Key features:
- LOC delta scoring
- Critical path detection (migrations, auth, schema, infra)
- Test presence validation
- Code hygiene checks (TODO/FIXME/HACK)

Integration: Feeds quality_gate.py as metadata, NOT a standalone blocker.
"""

from pathlib import Path
from typing import Dict, List, Optional


class RiskScorer:
    """Deterministic risk scorer for code changes.

    Provides proactive risk assessment before apply, complementing
    reactive learned rules that only fire for seen patterns.
    """

    # Critical paths that warrant higher scrutiny
    CRITICAL_PATHS = [
        "database/migrations",
        "auth",
        "infra",
        "config/production",
        "deployment",
        ".github/workflows",
    ]

    # High-risk file extensions
    HIGH_RISK_EXTENSIONS = [
        ".sql",
        ".yaml",
        ".yml",
        ".env",
        ".production",
    ]

    # Code hygiene markers
    HYGIENE_MARKERS = [
        "TODO",
        "FIXME",
        "HACK",
        "XXX",
        "TEMP",
    ]

    def __init__(self, repo_root: Optional[Path] = None):
        """Initialize risk scorer.

        Args:
            repo_root: Repository root for path resolution
        """
        self.repo_root = repo_root or Path.cwd()

    def score_change(
        self,
        files_changed: List[str],
        loc_added: int,
        loc_removed: int,
        patch_content: Optional[str] = None,
    ) -> Dict:
        """Score a code change for risk level.

        Args:
            files_changed: List of file paths modified
            loc_added: Lines of code added
            loc_removed: Lines of code removed
            patch_content: Optional patch/diff content for hygiene checks

        Returns:
            Dict with:
                - risk_score: 0-100 (0=safe, 100=maximum risk)
                - risk_level: "low" | "medium" | "high" | "critical"
                - checks: Dict of individual check results
                - reasons: List of human-readable risk factors
        """
        checks = {}
        reasons = []
        score = 0

        # 1. LOC delta scoring (max 25 points)
        loc_delta = loc_added + loc_removed
        if loc_delta > 1000:
            checks["loc_delta"] = "critical"
            score += 25
            reasons.append(f"Very large change ({loc_delta} LOC)")
        elif loc_delta > 500:
            checks["loc_delta"] = "high"
            score += 20
            reasons.append(f"Large change ({loc_delta} LOC)")
        elif loc_delta > 200:
            checks["loc_delta"] = "medium"
            score += 10
            reasons.append(f"Moderate change ({loc_delta} LOC)")
        else:
            checks["loc_delta"] = "low"

        # 2. Large deletion detection (max 40 points) - TWO-TIER SYSTEM
        net_deletion = loc_removed - loc_added

        # Two-tier deletion thresholds
        NOTIFICATION_THRESHOLD = 100   # Send notification (don't block) at >100 lines
        BLOCKING_THRESHOLD = 200       # Require approval (block) at >200 lines

        # Initialize flags
        checks["large_deletion"] = False
        checks["deletion_notification_needed"] = False
        checks["deletion_approval_required"] = False
        checks["net_deletion"] = net_deletion

        if net_deletion > BLOCKING_THRESHOLD:
            # Tier 2: Block and require approval (200+ lines)
            checks["large_deletion"] = True
            checks["deletion_notification_needed"] = True
            checks["deletion_approval_required"] = True
            deletion_severity = 40
            reasons.append(f"CRITICAL DELETION: Net removal of {net_deletion} lines (requires approval, threshold: {BLOCKING_THRESHOLD})")
            score += deletion_severity
        elif net_deletion > NOTIFICATION_THRESHOLD:
            # Tier 1: Send notification only, don't block (100+ lines)
            checks["large_deletion"] = True
            checks["deletion_notification_needed"] = True
            checks["deletion_approval_required"] = False
            deletion_severity = 20
            reasons.append(f"LARGE DELETION: Net removal of {net_deletion} lines (notification sent, threshold: {NOTIFICATION_THRESHOLD})")
            score += deletion_severity

        # 3. Critical path detection (max 30 points)
        critical_paths_hit = []
        for file_path in files_changed:
            for critical_path in self.CRITICAL_PATHS:
                if critical_path in file_path:
                    critical_paths_hit.append(critical_path)

        if critical_paths_hit:
            checks["critical_paths"] = critical_paths_hit
            score += min(30, len(critical_paths_hit) * 15)
            reasons.append(f"Touches critical paths: {', '.join(set(critical_paths_hit))}")
        else:
            checks["critical_paths"] = []

        # 4. High-risk file extensions (max 15 points)
        high_risk_files = []
        for file_path in files_changed:
            for ext in self.HIGH_RISK_EXTENSIONS:
                if file_path.endswith(ext):
                    high_risk_files.append(file_path)

        if high_risk_files:
            checks["high_risk_files"] = high_risk_files
            score += min(15, len(high_risk_files) * 5)
            reasons.append(f"Modifies {len(high_risk_files)} high-risk config/schema file(s)")
        else:
            checks["high_risk_files"] = []

        # 5. Test presence (max 20 points penalty if missing)
        test_files = [f for f in files_changed if "test" in f.lower() or f.endswith("_test.py")]
        if not test_files and loc_delta > 50:
            checks["tests_present"] = False
            score += 20
            reasons.append("No test files modified in non-trivial change")
        else:
            checks["tests_present"] = True

        # 6. Code hygiene (max 10 points)
        if patch_content:
            hygiene_issues = []
            for marker in self.HYGIENE_MARKERS:
                if marker in patch_content:
                    hygiene_issues.append(marker)

            if hygiene_issues:
                checks["hygiene_issues"] = hygiene_issues
                score += min(10, len(hygiene_issues) * 3)
                reasons.append(f"Contains hygiene markers: {', '.join(hygiene_issues)}")
            else:
                checks["hygiene_issues"] = []
        else:
            checks["hygiene_issues"] = []

        # Determine risk level from score
        if score >= 70:
            risk_level = "critical"
        elif score >= 50:
            risk_level = "high"
        elif score >= 25:
            risk_level = "medium"
        else:
            risk_level = "low"

        return {
            "risk_score": min(100, score),
            "risk_level": risk_level,
            "checks": checks,
            "reasons": reasons if reasons else ["Low-risk routine change"],
            "metadata": {
                "files_changed_count": len(files_changed),
                "loc_added": loc_added,
                "loc_removed": loc_removed,
                "loc_delta": loc_delta,
            },
        }

    def format_report(self, score_result: Dict) -> str:
        """Format risk score result as human-readable report.

        Args:
            score_result: Result from score_change()

        Returns:
            Formatted string report
        """
        risk_level = score_result["risk_level"]
        risk_score = score_result["risk_score"]
        reasons = score_result["reasons"]

        # Risk level emoji
        emoji = {
            "low": "✅",
            "medium": "⚠️",
            "high": "🔴",
            "critical": "🚨",
        }.get(risk_level, "❓")

        report = [
            f"\n{'='*60}",
            f"RISK ASSESSMENT: {emoji} {risk_level.upper()} (score: {risk_score}/100)",
            f"{'='*60}",
        ]

        if reasons:
            report.append("\nRisk Factors:")
            for reason in reasons:
                report.append(f"  • {reason}")

        # Add check details
        checks = score_result["checks"]
        if checks.get("critical_paths"):
            report.append(f"\nCritical paths: {', '.join(checks['critical_paths'])}")
        if checks.get("high_risk_files"):
            report.append(f"High-risk files: {len(checks['high_risk_files'])} file(s)")
        if not checks.get("tests_present", True):
            report.append("⚠️  No test coverage detected")
        if checks.get("hygiene_issues"):
            report.append(f"Hygiene: Found {', '.join(checks['hygiene_issues'])}")

        report.append(f"{'='*60}\n")

        return "\n".join(report)


def integrate_with_quality_gate(quality_report: Dict, risk_result: Dict) -> Dict:
    """Integrate risk scorer results into quality gate report.

    Args:
        quality_report: Quality gate assessment dict
        risk_result: Risk scorer result dict

    Returns:
        Enhanced quality report with risk metadata
    """
    # Add risk assessment to quality report
    quality_report["risk_assessment"] = {
        "risk_score": risk_result["risk_score"],
        "risk_level": risk_result["risk_level"],
        "risk_reasons": risk_result["reasons"],
    }

    # If high/critical risk, add warning
    if risk_result["risk_level"] in ["high", "critical"]:
        if "warnings" not in quality_report:
            quality_report["warnings"] = []
        quality_report["warnings"].append(
            f"Risk scorer flagged as {risk_result['risk_level']} risk (score: {risk_result['risk_score']})"
        )

    return quality_report
