"""Dual Auditor with Issue-Based Merging

Per GPT recommendation: Auditors are sensors, not judges.
Conflict resolution via merged issue sets with severity escalation.

Usage:
    dual_auditor = DualAuditor(openai_auditor, claude_auditor)

    merged_result = dual_auditor.review_patch(
        patch_content=patch,
        phase_spec=phase_spec,
        high_risk_category=True  # Enable dual audit for this category
    )

    # merged_result contains union of issues from both auditors
    # with effective_severity = max(severity_from_each)
"""

from typing import List, Dict, Optional
from dataclasses import dataclass

from .llm_client import AuditorResult


@dataclass
class MergedIssue:
    """Single issue from merged auditor results

    Per GPT: effective_severity = max(severity from each auditor)
    """

    issue_key: str  # Unique identifier for deduplication
    category: str
    description: str
    location: str
    effective_severity: str  # "minor" or "major"
    sources: List[str]  # Which auditors flagged this ["openai", "claude"]
    openai_severity: Optional[str] = None
    claude_severity: Optional[str] = None
    suggestions: List[str] = None

    def __post_init__(self):
        if self.suggestions is None:
            self.suggestions = []


class DualAuditor:
    """Dual auditor with issue-based conflict resolution

    Per GPT recommendation:
    - Auditors return issues[], not boolean approve/reject
    - Merge issue sets with union
    - Escalate severity: any "major" → effective_severity="major"
    - Gate decision based on merged issue profile

    High-risk categories that trigger dual audit:
    - external_feature_reuse
    - security_auth_change
    - schema_contract_change (optional)
    """

    def __init__(
        self,
        primary_auditor,  # OpenAI auditor
        secondary_auditor,  # Claude auditor
        high_risk_categories: Optional[List[str]] = None,
    ):
        """Initialize dual auditor

        Args:
            primary_auditor: Primary auditor client (OpenAI)
            secondary_auditor: Secondary auditor client (Claude)
            high_risk_categories: Categories that trigger dual audit
        """
        self.primary = primary_auditor
        self.secondary = secondary_auditor
        self.high_risk_categories = high_risk_categories or [
            "external_feature_reuse",
            "security_auth_change",
        ]

        # Track disagreement metrics
        self.disagreement_count = 0
        self.total_dual_audits = 0

    def should_use_dual_audit(self, phase_spec: Dict) -> bool:
        """Determine if this phase requires dual audit

        Args:
            phase_spec: Phase specification with task_category

        Returns:
            True if dual audit should be used
        """
        task_category = phase_spec.get("task_category", "")
        return task_category in self.high_risk_categories

    def review_patch(
        self,
        patch_content: str,
        phase_spec: Dict,
        max_tokens: Optional[int] = None,
        model: Optional[str] = None,
        project_rules: Optional[List] = None,
        run_hints: Optional[List] = None,
        force_dual: bool = False,
    ) -> AuditorResult:
        """Review patch with single or dual audit based on risk

        Args:
            patch_content: Git diff/patch to review
            phase_spec: Phase specification
            max_tokens: Token budget
            model: Model to use (for primary auditor)
            project_rules: Learned rules (Stage 0B)
            run_hints: Run hints (Stage 0A)
            force_dual: Force dual audit even if not high-risk

        Returns:
            AuditorResult with merged issues if dual audit used
        """
        use_dual = force_dual or self.should_use_dual_audit(phase_spec)

        # Debug logging
        print("[DualAuditor] review_patch called with:")
        print(f"[DualAuditor]   phase_spec: {phase_spec.get('phase_id', 'unknown')}")
        print(f"[DualAuditor]   max_tokens: {max_tokens}")
        print(f"[DualAuditor]   model: {model}")
        print(f"[DualAuditor]   use_dual: {use_dual}")
        print(f"[DualAuditor]   patch_content length: {len(patch_content)}")

        if not use_dual:
            # Single audit (standard path)
            print("[DualAuditor] Using single audit (primary only)")
            return self.primary.review_patch(
                patch_content=patch_content,
                phase_spec=phase_spec,
                max_tokens=max_tokens,
                model=model,
                project_rules=project_rules,
                run_hints=run_hints,
            )

        # Dual audit for high-risk category
        print(f"[DualAuditor] 🔍 High-risk category detected: {phase_spec.get('task_category')}")
        print("[DualAuditor] Running dual audit (OpenAI + Claude)")

        # Run both auditors in parallel (conceptually; sequential for now)
        primary_result = self.primary.review_patch(
            patch_content=patch_content,
            phase_spec=phase_spec,
            max_tokens=max_tokens,
            model=model,
            project_rules=project_rules,
            run_hints=run_hints,
        )

        secondary_result = self.secondary.review_patch(
            patch_content=patch_content,
            phase_spec=phase_spec,
            max_tokens=max_tokens // 2 if max_tokens else None,  # Half budget for secondary
            model="claude-sonnet-3-5",  # Claude model
            project_rules=project_rules,
            run_hints=run_hints,
        )

        # Merge results
        merged_result = self._merge_auditor_results(primary_result, secondary_result, phase_spec)

        # Track metrics
        self.total_dual_audits += 1
        if primary_result.approved != secondary_result.approved:
            self.disagreement_count += 1

        disagreement_rate = (self.disagreement_count / self.total_dual_audits) * 100
        print(
            f"[DualAuditor] Disagreement rate: {disagreement_rate:.1f}% ({self.disagreement_count}/{self.total_dual_audits})"
        )

        return merged_result

    def _merge_auditor_results(
        self, primary: AuditorResult, secondary: AuditorResult, phase_spec: Dict
    ) -> AuditorResult:
        """Merge two auditor results using issue-based conflict resolution

        Per GPT recommendation:
        1. Union of issue sets
        2. Deduplicate by logical issue (not exact match)
        3. Escalate severity: any "major" → effective_severity="major"
        4. Gate decision based on merged profile (any major → fail)

        Args:
            primary: OpenAI auditor result
            secondary: Claude auditor result
            phase_spec: Phase specification

        Returns:
            Merged AuditorResult
        """
        print("\n[DualAuditor] Merging audit results:")
        print(
            f"[DualAuditor]    OpenAI: {len(primary.issues_found)} issues, approved={primary.approved}"
        )
        print(
            f"[DualAuditor]    Claude: {len(secondary.issues_found)} issues, approved={secondary.approved}"
        )

        # Build merged issue set
        merged_issues = self._build_merged_issue_set(primary.issues_found, secondary.issues_found)

        print(f"[DualAuditor]    Merged: {len(merged_issues)} unique issues")

        # Apply gating decision (per GPT: any major → fail)
        has_major_issues = any(issue.effective_severity == "major" for issue in merged_issues)

        approved = not has_major_issues

        # Combine messages
        combined_messages = []
        combined_messages.extend(primary.auditor_messages or [])
        combined_messages.append("--- Secondary Auditor (Claude) ---")
        combined_messages.extend(secondary.auditor_messages or [])

        # Convert MergedIssue back to dict format
        merged_issues_dict = [
            {
                "severity": issue.effective_severity,
                "category": issue.category,
                "description": issue.description,
                "location": issue.location,
                "sources": issue.sources,  # Metadata: which auditors flagged this
                "openai_severity": issue.openai_severity,
                "claude_severity": issue.claude_severity,
                "suggestion": "; ".join(issue.suggestions) if issue.suggestions else None,
            }
            for issue in merged_issues
        ]

        print(f"[DualAuditor] Final decision: {'APPROVED' if approved else 'REJECTED'}")
        if not approved:
            major_issues = [i for i in merged_issues if i.effective_severity == "major"]
            print(f"[DualAuditor]    Major issues: {len(major_issues)}")
            for issue in major_issues[:3]:  # Show first 3
                print(
                    f"[DualAuditor]       - {issue.description} (sources: {', '.join(issue.sources)})"
                )

        return AuditorResult(
            approved=approved,
            issues_found=merged_issues_dict,
            auditor_messages=combined_messages,
            tokens_used=primary.tokens_used + secondary.tokens_used,
            model_used=f"{primary.model_used}+{secondary.model_used}",
        )

    def _build_merged_issue_set(
        self, primary_issues: List[Dict], secondary_issues: List[Dict]
    ) -> List[MergedIssue]:
        """Build merged issue set with deduplication and severity escalation

        Args:
            primary_issues: Issues from OpenAI auditor
            secondary_issues: Issues from Claude auditor

        Returns:
            List of MergedIssue with effective_severity
        """
        # Index issues by fuzzy key for deduplication
        issue_map = {}

        # Add primary issues
        for issue in primary_issues:
            key = self._normalize_issue_key(issue)
            if key not in issue_map:
                issue_map[key] = MergedIssue(
                    issue_key=key,
                    category=issue.get("category", "unknown"),
                    description=issue.get("description", ""),
                    location=issue.get("location", "unknown"),
                    effective_severity=issue.get("severity", "minor"),
                    sources=["openai"],
                    openai_severity=issue.get("severity", "minor"),
                    suggestions=[issue.get("suggestion", "")] if issue.get("suggestion") else [],
                )
            else:
                # Duplicate from primary (shouldn't happen but handle gracefully)
                pass

        # Add secondary issues (merge or escalate)
        for issue in secondary_issues:
            key = self._normalize_issue_key(issue)
            if key in issue_map:
                # Same issue flagged by both → escalate severity
                existing = issue_map[key]
                existing.sources.append("claude")
                existing.claude_severity = issue.get("severity", "minor")

                # Escalate to major if either is major
                if issue.get("severity") == "major" or existing.effective_severity == "major":
                    existing.effective_severity = "major"

                # Add suggestion if present
                if issue.get("suggestion"):
                    existing.suggestions.append(issue.get("suggestion"))
            else:
                # New issue only seen by Claude
                issue_map[key] = MergedIssue(
                    issue_key=key,
                    category=issue.get("category", "unknown"),
                    description=issue.get("description", ""),
                    location=issue.get("location", "unknown"),
                    effective_severity=issue.get("severity", "minor"),
                    sources=["claude"],
                    claude_severity=issue.get("severity", "minor"),
                    suggestions=[issue.get("suggestion", "")] if issue.get("suggestion") else [],
                )

        return list(issue_map.values())

    def _normalize_issue_key(self, issue: Dict) -> str:
        """Generate normalized key for issue deduplication

        Uses category + location for fuzzy matching.
        Issues with same category+location are considered same logical issue.

        Args:
            issue: Issue dict

        Returns:
            Normalized key string
        """
        category = issue.get("category", "unknown").lower()
        location = issue.get("location", "unknown").lower()

        # Normalize location (strip line numbers, etc.)
        # Simple approach: just use file path part
        if ":" in location:
            location = location.split(":")[0]

        return f"{category}@{location}"

    def get_disagreement_rate(self) -> float:
        """Get disagreement rate between auditors

        Returns:
            Percentage of dual audits where auditors disagreed on approval
        """
        if self.total_dual_audits == 0:
            return 0.0
        return (self.disagreement_count / self.total_dual_audits) * 100


# DEPRECATED: Stub Claude auditor for testing
# ⚠️  WARNING: This stub returns empty results and should NOT be used in production.
#
# For real Claude-based auditing, use AnthropicAuditorClient instead:
#
#   from autopack.anthropic_clients import AnthropicAuditorClient
#   auditor = AnthropicAuditorClient(api_key=os.getenv("ANTHROPIC_API_KEY"))
#
# This stub is retained for backward compatibility only and will be removed
# in a future release.
class StubClaudeAuditor:
    """DEPRECATED: Stub Claude auditor for testing dual auditor logic.

    ⚠️  This is a stub that returns empty results. Use AnthropicAuditorClient
    from autopack.anthropic_clients for real Claude-based auditing.
    """

    def review_patch(
        self,
        patch_content: str,
        phase_spec: Dict,
        max_tokens: Optional[int] = None,
        model: Optional[str] = None,
        project_rules: Optional[List] = None,
        run_hints: Optional[List] = None,
    ) -> AuditorResult:
        """Stub review (returns empty issues for now)"""
        import warnings

        warnings.warn(
            "StubClaudeAuditor is deprecated. Use AnthropicAuditorClient from "
            "autopack.anthropic_clients for real Claude-based auditing.",
            DeprecationWarning,
            stacklevel=2,
        )
        # Always append "-stub" to make it clear this is not a real audit
        model_name = (model or "claude-sonnet-3-5") + "-stub"
        return AuditorResult(
            approved=True,
            issues_found=[],
            auditor_messages=[
                "⚠️  Claude audit stub called (no real auditing performed).",
                "Use AnthropicAuditorClient for production auditing.",
            ],
            tokens_used=0,  # Stub - no actual API call
            model_used=model_name,
        )
