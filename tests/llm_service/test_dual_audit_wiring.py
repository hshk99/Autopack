"""Tests for dual-audit system wiring (IMP-T02).

These tests verify:
- Audit trail is created for all LLM calls (primary, secondary, judge)
- Tool use is properly logged with role suffixes
- Token usage is tracked for each auditor
- Errors are captured in audit trail
- Disagreement detection works correctly
- Judge escalation is triggered when needed
"""

import pytest
from unittest.mock import MagicMock, patch

from autopack.llm_service import LlmService
from autopack.llm_client import AuditorResult


@pytest.mark.aspirational
class TestDualAuditTrailCreation:
    """Tests for audit trail creation in dual-audit mode."""

    def test_dual_audit_creates_audit_trail_for_primary(self):
        """Dual audit creates LlmUsageEvent for primary auditor."""
        # Create mock service with dual audit enabled
        with patch.object(LlmService, "__init__", lambda self, *args, **kwargs: None):
            service = LlmService.__new__(LlmService)
            service.db = MagicMock()

            # Mock model router to enable dual audit
            service.model_router = MagicMock()
            service.model_router.config = {
                "llm_routing_policies": {
                    "security_auth_change": {
                        "dual_audit": True,
                        "secondary_auditor": "claude-sonnet-4-5",
                    }
                }
            }
            service.model_router.select_model_with_escalation = MagicMock(
                return_value=("claude-opus-4-5", "high", {})
            )

            # Mock auditor clients
            primary_result = AuditorResult(
                approved=True,
                issues_found=[],
                auditor_messages=["Primary review complete"],
                tokens_used=1000,
                prompt_tokens=600,
                completion_tokens=400,
                model_used="claude-opus-4-5",
            )

            secondary_result = AuditorResult(
                approved=True,
                issues_found=[],
                auditor_messages=["Secondary review complete"],
                tokens_used=800,
                prompt_tokens=500,
                completion_tokens=300,
                model_used="claude-sonnet-4-5",
            )

            mock_primary_client = MagicMock()
            mock_primary_client.review_patch = MagicMock(return_value=primary_result)

            mock_secondary_client = MagicMock()
            mock_secondary_client.review_patch = MagicMock(return_value=secondary_result)

            service._resolve_client_and_model = MagicMock(
                side_effect=[
                    (mock_primary_client, "claude-opus-4-5"),
                    (mock_secondary_client, "claude-sonnet-4-5"),
                ]
            )
            service._model_to_provider = MagicMock(return_value="anthropic")
            service._record_usage = MagicMock()
            service.quality_gate = MagicMock()
            service.quality_gate.assess_phase = MagicMock(return_value={})

            # Execute dual audit
            phase_spec = {"task_category": "security_auth_change", "phase_id": "phase-1"}
            _result = service.execute_auditor_review(
                patch_content="diff content",
                phase_spec=phase_spec,
                run_id="test-run",
                phase_id="phase-1",
            )

            # Verify primary auditor usage was recorded with role suffix
            assert service._record_usage.called
            primary_call = service._record_usage.call_args_list[0]
            assert primary_call[1]["role"] == "auditor:primary"
            assert primary_call[1]["prompt_tokens"] == 600
            assert primary_call[1]["completion_tokens"] == 400
            assert primary_call[1]["run_id"] == "test-run"
            assert primary_call[1]["phase_id"] == "phase-1"

    def test_dual_audit_creates_audit_trail_for_secondary(self):
        """Dual audit creates LlmUsageEvent for secondary auditor."""
        with patch.object(LlmService, "__init__", lambda self, *args, **kwargs: None):
            service = LlmService.__new__(LlmService)
            service.db = MagicMock()

            # Mock model router to enable dual audit
            service.model_router = MagicMock()
            service.model_router.config = {
                "llm_routing_policies": {
                    "security_auth_change": {
                        "dual_audit": True,
                        "secondary_auditor": "claude-sonnet-4-5",
                    }
                }
            }
            service.model_router.select_model_with_escalation = MagicMock(
                return_value=("claude-opus-4-5", "high", {})
            )

            # Mock auditor results
            primary_result = AuditorResult(
                approved=True,
                issues_found=[],
                auditor_messages=[],
                tokens_used=1000,
                prompt_tokens=600,
                completion_tokens=400,
                model_used="claude-opus-4-5",
            )

            secondary_result = AuditorResult(
                approved=True,
                issues_found=[],
                auditor_messages=[],
                tokens_used=800,
                prompt_tokens=500,
                completion_tokens=300,
                model_used="claude-sonnet-4-5",
            )

            service._resolve_client_and_model = MagicMock(
                side_effect=[
                    (
                        MagicMock(review_patch=MagicMock(return_value=primary_result)),
                        "claude-opus-4-5",
                    ),
                    (
                        MagicMock(review_patch=MagicMock(return_value=secondary_result)),
                        "claude-sonnet-4-5",
                    ),
                ]
            )
            service._model_to_provider = MagicMock(return_value="anthropic")
            service._record_usage = MagicMock()
            service.quality_gate = MagicMock()
            service.quality_gate.assess_phase = MagicMock(return_value={})

            # Execute dual audit
            phase_spec = {"task_category": "security_auth_change", "phase_id": "phase-1"}
            _result = service.execute_auditor_review(
                patch_content="diff content",
                phase_spec=phase_spec,
                run_id="test-run",
                phase_id="phase-1",
            )

            # Verify secondary auditor usage was recorded with role suffix
            assert service._record_usage.call_count == 2
            secondary_call = service._record_usage.call_args_list[1]
            assert secondary_call[1]["role"] == "auditor:secondary"
            assert secondary_call[1]["prompt_tokens"] == 500
            assert secondary_call[1]["completion_tokens"] == 300
            assert secondary_call[1]["run_id"] == "test-run"
            assert secondary_call[1]["phase_id"] == "phase-1"

    def test_dual_audit_creates_audit_trail_for_judge(self):
        """Judge auditor creates LlmUsageEvent with auditor:judge role."""
        with patch.object(LlmService, "__init__", lambda self, *args, **kwargs: None):
            service = LlmService.__new__(LlmService)
            service.db = MagicMock()

            # Mock model router to enable dual audit
            service.model_router = MagicMock()
            service.model_router.config = {
                "llm_routing_policies": {
                    "security_auth_change": {
                        "dual_audit": True,
                        "secondary_auditor": "claude-sonnet-4-5",
                    }
                },
                "dual_audit_judge": {"model": "claude-opus-4-5"},
            }
            service.model_router.select_model_with_escalation = MagicMock(
                return_value=("claude-opus-4-5", "high", {})
            )

            # Mock disagreement: primary approves, secondary rejects
            primary_result = AuditorResult(
                approved=True,
                issues_found=[],
                auditor_messages=[],
                tokens_used=1000,
                prompt_tokens=600,
                completion_tokens=400,
                model_used="claude-opus-4-5",
            )

            secondary_result = AuditorResult(
                approved=False,
                issues_found=[{"severity": "major", "category": "security"}],
                auditor_messages=[],
                tokens_used=800,
                prompt_tokens=500,
                completion_tokens=300,
                model_used="claude-sonnet-4-5",
            )

            judge_result = AuditorResult(
                approved=False,
                issues_found=[{"severity": "major", "category": "security"}],
                auditor_messages=["Judge review"],
                tokens_used=1200,
                prompt_tokens=700,
                completion_tokens=500,
                model_used="claude-opus-4-5",
            )

            service._resolve_client_and_model = MagicMock(
                side_effect=[
                    (
                        MagicMock(review_patch=MagicMock(return_value=primary_result)),
                        "claude-opus-4-5",
                    ),
                    (
                        MagicMock(review_patch=MagicMock(return_value=secondary_result)),
                        "claude-sonnet-4-5",
                    ),
                    (
                        MagicMock(review_patch=MagicMock(return_value=judge_result)),
                        "claude-opus-4-5",
                    ),
                ]
            )
            service._model_to_provider = MagicMock(return_value="anthropic")
            service._record_usage = MagicMock()
            service.quality_gate = MagicMock()
            service.quality_gate.assess_phase = MagicMock(return_value={})

            # Execute dual audit (should trigger judge)
            phase_spec = {"task_category": "security_auth_change", "phase_id": "phase-1"}
            _result = service.execute_auditor_review(
                patch_content="diff content",
                phase_spec=phase_spec,
                run_id="test-run",
                phase_id="phase-1",
            )

            # Verify judge usage was recorded
            assert service._record_usage.call_count == 3
            judge_call = service._record_usage.call_args_list[2]
            assert judge_call[1]["role"] == "auditor:judge"
            assert judge_call[1]["prompt_tokens"] == 700
            assert judge_call[1]["completion_tokens"] == 500
            assert judge_call[1]["run_id"] == "test-run"
            assert judge_call[1]["phase_id"] == "phase-1"


@pytest.mark.aspirational
class TestTokenUsageTracking:
    """Tests for token usage tracking in dual-audit mode."""

    def test_token_usage_tracked_for_all_auditors(self):
        """Token usage is tracked separately for primary, secondary, and judge."""
        with patch.object(LlmService, "__init__", lambda self, *args, **kwargs: None):
            service = LlmService.__new__(LlmService)
            service.db = MagicMock()

            # Mock model router to enable dual audit
            service.model_router = MagicMock()
            service.model_router.config = {
                "llm_routing_policies": {
                    "security_auth_change": {
                        "dual_audit": True,
                        "secondary_auditor": "claude-sonnet-4-5",
                    }
                },
                "dual_audit_judge": {"model": "claude-opus-4-5"},
            }
            service.model_router.select_model_with_escalation = MagicMock(
                return_value=("claude-opus-4-5", "high", {})
            )

            # Mock disagreement to trigger judge
            primary_result = AuditorResult(
                approved=True,
                issues_found=[],
                auditor_messages=[],
                tokens_used=1000,
                prompt_tokens=600,
                completion_tokens=400,
                model_used="claude-opus-4-5",
            )

            secondary_result = AuditorResult(
                approved=False,
                issues_found=[{"severity": "major", "category": "security"}],
                auditor_messages=[],
                tokens_used=800,
                prompt_tokens=500,
                completion_tokens=300,
                model_used="claude-sonnet-4-5",
            )

            judge_result = AuditorResult(
                approved=False,
                issues_found=[{"severity": "major", "category": "security"}],
                auditor_messages=[],
                tokens_used=1200,
                prompt_tokens=700,
                completion_tokens=500,
                model_used="claude-opus-4-5",
            )

            service._resolve_client_and_model = MagicMock(
                side_effect=[
                    (
                        MagicMock(review_patch=MagicMock(return_value=primary_result)),
                        "claude-opus-4-5",
                    ),
                    (
                        MagicMock(review_patch=MagicMock(return_value=secondary_result)),
                        "claude-sonnet-4-5",
                    ),
                    (
                        MagicMock(review_patch=MagicMock(return_value=judge_result)),
                        "claude-opus-4-5",
                    ),
                ]
            )
            service._model_to_provider = MagicMock(return_value="anthropic")
            service._record_usage = MagicMock()
            service.quality_gate = MagicMock()
            service.quality_gate.assess_phase = MagicMock(return_value={})

            # Execute dual audit
            phase_spec = {"task_category": "security_auth_change", "phase_id": "phase-1"}
            _result = service.execute_auditor_review(
                patch_content="diff content",
                phase_spec=phase_spec,
                run_id="test-run",
                phase_id="phase-1",
            )

            # Verify all three auditors recorded usage
            assert service._record_usage.call_count == 3

            # Check token counts are preserved
            primary_call = service._record_usage.call_args_list[0][1]
            assert primary_call["prompt_tokens"] == 600
            assert primary_call["completion_tokens"] == 400

            secondary_call = service._record_usage.call_args_list[1][1]
            assert secondary_call["prompt_tokens"] == 500
            assert secondary_call["completion_tokens"] == 300

            judge_call = service._record_usage.call_args_list[2][1]
            assert judge_call["prompt_tokens"] == 700
            assert judge_call["completion_tokens"] == 500

    def test_total_only_token_accounting_for_dual_audit(self):
        """Dual audit handles total-only token accounting when splits unavailable."""
        with patch.object(LlmService, "__init__", lambda self, *args, **kwargs: None):
            service = LlmService.__new__(LlmService)
            service.db = MagicMock()

            # Mock model router to enable dual audit
            service.model_router = MagicMock()
            service.model_router.config = {
                "llm_routing_policies": {
                    "security_auth_change": {
                        "dual_audit": True,
                        "secondary_auditor": "claude-sonnet-4-5",
                    }
                }
            }
            service.model_router.select_model_with_escalation = MagicMock(
                return_value=("claude-opus-4-5", "high", {})
            )

            # Mock results without token splits (only total)
            primary_result = AuditorResult(
                approved=True,
                issues_found=[],
                auditor_messages=[],
                tokens_used=1000,
                prompt_tokens=None,  # No split available
                completion_tokens=None,
                model_used="claude-opus-4-5",
            )

            secondary_result = AuditorResult(
                approved=True,
                issues_found=[],
                auditor_messages=[],
                tokens_used=800,
                prompt_tokens=None,  # No split available
                completion_tokens=None,
                model_used="claude-sonnet-4-5",
            )

            service._resolve_client_and_model = MagicMock(
                side_effect=[
                    (
                        MagicMock(review_patch=MagicMock(return_value=primary_result)),
                        "claude-opus-4-5",
                    ),
                    (
                        MagicMock(review_patch=MagicMock(return_value=secondary_result)),
                        "claude-sonnet-4-5",
                    ),
                ]
            )
            service._model_to_provider = MagicMock(return_value="anthropic")
            service._record_usage_total_only = MagicMock()
            service.quality_gate = MagicMock()
            service.quality_gate.assess_phase = MagicMock(return_value={})

            # Execute dual audit
            phase_spec = {"task_category": "security_auth_change", "phase_id": "phase-1"}
            _result = service.execute_auditor_review(
                patch_content="diff content",
                phase_spec=phase_spec,
                run_id="test-run",
                phase_id="phase-1",
            )

            # Verify total-only recording was used
            assert service._record_usage_total_only.call_count == 2

            primary_call = service._record_usage_total_only.call_args_list[0][1]
            assert primary_call["role"] == "auditor:primary"
            assert primary_call["total_tokens"] == 1000

            secondary_call = service._record_usage_total_only.call_args_list[1][1]
            assert secondary_call["role"] == "auditor:secondary"
            assert secondary_call["total_tokens"] == 800


@pytest.mark.aspirational
class TestErrorCapture:
    """Tests for error capture in dual-audit trail."""

    def test_audit_trail_captures_primary_auditor_failure(self):
        """Audit trail captures errors when primary auditor fails."""
        with patch.object(LlmService, "__init__", lambda self, *args, **kwargs: None):
            service = LlmService.__new__(LlmService)
            service.db = MagicMock()

            # Mock model router to enable dual audit
            service.model_router = MagicMock()
            service.model_router.config = {
                "llm_routing_policies": {
                    "security_auth_change": {
                        "dual_audit": True,
                        "secondary_auditor": "claude-sonnet-4-5",
                    }
                }
            }
            service.model_router.select_model_with_escalation = MagicMock(
                return_value=("claude-opus-4-5", "high", {})
            )

            # Mock primary auditor failure
            mock_primary_client = MagicMock()
            mock_primary_client.review_patch = MagicMock(side_effect=Exception("API error"))

            service._resolve_client_and_model = MagicMock(
                return_value=(mock_primary_client, "claude-opus-4-5")
            )
            service._model_to_provider = MagicMock(return_value="anthropic")
            service._record_usage = MagicMock()

            # Execute dual audit (should raise exception)
            phase_spec = {"task_category": "security_auth_change", "phase_id": "phase-1"}

            with pytest.raises(Exception, match="API error"):
                service.execute_auditor_review(
                    patch_content="diff content",
                    phase_spec=phase_spec,
                    run_id="test-run",
                    phase_id="phase-1",
                )

            # Verify no usage was recorded (call failed)
            assert not service._record_usage.called

    def test_audit_trail_captures_secondary_auditor_failure(self):
        """Secondary auditor failure propagates exception, no partial usage recorded."""
        with patch.object(LlmService, "__init__", lambda self, *args, **kwargs: None):
            service = LlmService.__new__(LlmService)
            service.db = MagicMock()

            # Mock model router to enable dual audit
            service.model_router = MagicMock()
            service.model_router.config = {
                "llm_routing_policies": {
                    "security_auth_change": {
                        "dual_audit": True,
                        "secondary_auditor": "claude-sonnet-4-5",
                    }
                }
            }
            service.model_router.select_model_with_escalation = MagicMock(
                return_value=("claude-opus-4-5", "high", {})
            )

            # Primary succeeds, secondary fails
            primary_result = AuditorResult(
                approved=True,
                issues_found=[],
                auditor_messages=[],
                tokens_used=1000,
                prompt_tokens=600,
                completion_tokens=400,
                model_used="claude-opus-4-5",
            )

            mock_primary_client = MagicMock()
            mock_primary_client.review_patch = MagicMock(return_value=primary_result)

            mock_secondary_client = MagicMock()
            mock_secondary_client.review_patch = MagicMock(
                side_effect=Exception("Secondary failed")
            )

            service._resolve_client_and_model = MagicMock(
                side_effect=[
                    (mock_primary_client, "claude-opus-4-5"),
                    (mock_secondary_client, "claude-sonnet-4-5"),
                ]
            )
            service._model_to_provider = MagicMock(return_value="anthropic")
            service._record_usage = MagicMock()

            # Execute dual audit (should raise exception)
            phase_spec = {"task_category": "security_auth_change", "phase_id": "phase-1"}

            with pytest.raises(Exception, match="Secondary failed"):
                service.execute_auditor_review(
                    patch_content="diff content",
                    phase_spec=phase_spec,
                    run_id="test-run",
                    phase_id="phase-1",
                )

            # Verify no usage recorded when secondary fails (usage recorded after both complete)
            # Per _run_dual_audit implementation, usage is recorded after both auditors complete
            assert service._record_usage.call_count == 0


@pytest.mark.aspirational
class TestDisagreementDetection:
    """Tests for disagreement detection in dual-audit system."""

    def test_approval_mismatch_detected(self):
        """Disagreement detected when primary approves but secondary rejects."""
        with patch.object(LlmService, "__init__", lambda self, *args, **kwargs: None):
            service = LlmService.__new__(LlmService)

            # Create results with approval mismatch
            primary = AuditorResult(
                approved=True,
                issues_found=[],
                auditor_messages=[],
                tokens_used=1000,
                model_used="claude-opus-4-5",
            )

            secondary = AuditorResult(
                approved=False,
                issues_found=[{"severity": "major", "category": "security"}],
                auditor_messages=[],
                tokens_used=800,
                model_used="claude-sonnet-4-5",
            )

            # Detect disagreement
            disagreement = service._detect_dual_audit_disagreement(primary, secondary)

            # Verify disagreement was detected
            assert disagreement["has_disagreement"] is True
            assert disagreement["type"] == "approval_mismatch"
            assert disagreement["details"]["primary_approved"] is True
            assert disagreement["details"]["secondary_approved"] is False

    def test_severity_mismatch_detected(self):
        """Disagreement detected when auditors find different severity levels."""
        with patch.object(LlmService, "__init__", lambda self, *args, **kwargs: None):
            service = LlmService.__new__(LlmService)

            # Both reject, but different severity
            primary = AuditorResult(
                approved=False,
                issues_found=[
                    {"severity": "minor", "category": "style"},
                ],
                auditor_messages=[],
                tokens_used=1000,
                model_used="claude-opus-4-5",
            )

            secondary = AuditorResult(
                approved=False,
                issues_found=[
                    {"severity": "major", "category": "security"},
                    {"severity": "major", "category": "correctness"},
                    {"severity": "major", "category": "performance"},
                ],
                auditor_messages=[],
                tokens_used=800,
                model_used="claude-sonnet-4-5",
            )

            # Detect disagreement
            disagreement = service._detect_dual_audit_disagreement(primary, secondary)

            # Verify severity mismatch detected
            assert disagreement["has_disagreement"] is True
            assert disagreement["type"] == "severity_mismatch"
            assert disagreement["details"]["primary_major_issues"] == 0
            assert disagreement["details"]["secondary_major_issues"] == 3

    def test_category_miss_detected(self):
        """Disagreement detected when one auditor misses issue categories."""
        with patch.object(LlmService, "__init__", lambda self, *args, **kwargs: None):
            service = LlmService.__new__(LlmService)

            # Primary misses security issue
            primary = AuditorResult(
                approved=False,
                issues_found=[
                    {"severity": "minor", "category": "style"},
                ],
                auditor_messages=[],
                tokens_used=1000,
                model_used="claude-opus-4-5",
            )

            secondary = AuditorResult(
                approved=False,
                issues_found=[
                    {"severity": "major", "category": "security"},
                    {"severity": "minor", "category": "style"},
                ],
                auditor_messages=[],
                tokens_used=800,
                model_used="claude-sonnet-4-5",
            )

            # Detect disagreement
            disagreement = service._detect_dual_audit_disagreement(primary, secondary)

            # Verify category miss detected
            assert disagreement["has_disagreement"] is True
            assert disagreement["type"] == "category_miss"
            assert "security" in disagreement["details"]["major_categories_missed"]


@pytest.mark.aspirational
class TestJudgeEscalation:
    """Tests for judge escalation when auditors disagree."""

    def test_judge_invoked_on_disagreement(self):
        """Judge is invoked when primary and secondary auditors disagree."""
        with patch.object(LlmService, "__init__", lambda self, *args, **kwargs: None):
            service = LlmService.__new__(LlmService)
            service.db = MagicMock()

            # Mock model router to enable dual audit
            service.model_router = MagicMock()
            service.model_router.config = {
                "llm_routing_policies": {
                    "security_auth_change": {
                        "dual_audit": True,
                        "secondary_auditor": "claude-sonnet-4-5",
                    }
                },
                "dual_audit_judge": {"model": "claude-opus-4-5"},
            }
            service.model_router.select_model_with_escalation = MagicMock(
                return_value=("claude-opus-4-5", "high", {})
            )

            # Mock disagreement
            primary_result = AuditorResult(
                approved=True,
                issues_found=[],
                auditor_messages=[],
                tokens_used=1000,
                prompt_tokens=600,
                completion_tokens=400,
                model_used="claude-opus-4-5",
            )

            secondary_result = AuditorResult(
                approved=False,
                issues_found=[{"severity": "major", "category": "security"}],
                auditor_messages=[],
                tokens_used=800,
                prompt_tokens=500,
                completion_tokens=300,
                model_used="claude-sonnet-4-5",
            )

            judge_result = AuditorResult(
                approved=False,
                issues_found=[{"severity": "major", "category": "security"}],
                auditor_messages=["Judge agrees with secondary"],
                tokens_used=1200,
                prompt_tokens=700,
                completion_tokens=500,
                model_used="claude-opus-4-5",
            )

            call_count = 0

            def mock_resolve_side_effect(*args, **kwargs):
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    return (
                        MagicMock(review_patch=MagicMock(return_value=primary_result)),
                        "claude-opus-4-5",
                    )
                elif call_count == 2:
                    return (
                        MagicMock(review_patch=MagicMock(return_value=secondary_result)),
                        "claude-sonnet-4-5",
                    )
                else:
                    return (
                        MagicMock(review_patch=MagicMock(return_value=judge_result)),
                        "claude-opus-4-5",
                    )

            service._resolve_client_and_model = MagicMock(side_effect=mock_resolve_side_effect)
            service._model_to_provider = MagicMock(return_value="anthropic")
            service._record_usage = MagicMock()
            service.quality_gate = MagicMock()
            service.quality_gate.assess_phase = MagicMock(return_value={})

            # Execute dual audit
            phase_spec = {"task_category": "security_auth_change", "phase_id": "phase-1"}
            result = service.execute_auditor_review(
                patch_content="diff content",
                phase_spec=phase_spec,
                run_id="test-run",
                phase_id="phase-1",
            )

            # Verify judge was invoked (3 calls: primary, secondary, judge)
            assert service._resolve_client_and_model.call_count == 3
            assert service._record_usage.call_count == 3

            # Verify judge's decision was used
            assert result.approved is False  # Judge rejected

    def test_no_judge_invoked_on_agreement(self):
        """Judge is NOT invoked when primary and secondary auditors agree."""
        with patch.object(LlmService, "__init__", lambda self, *args, **kwargs: None):
            service = LlmService.__new__(LlmService)
            service.db = MagicMock()

            # Mock model router to enable dual audit
            service.model_router = MagicMock()
            service.model_router.config = {
                "llm_routing_policies": {
                    "security_auth_change": {
                        "dual_audit": True,
                        "secondary_auditor": "claude-sonnet-4-5",
                    }
                },
                "dual_audit_judge": {"model": "claude-opus-4-5"},
            }
            service.model_router.select_model_with_escalation = MagicMock(
                return_value=("claude-opus-4-5", "high", {})
            )

            # Both auditors agree
            primary_result = AuditorResult(
                approved=True,
                issues_found=[],
                auditor_messages=[],
                tokens_used=1000,
                prompt_tokens=600,
                completion_tokens=400,
                model_used="claude-opus-4-5",
            )

            secondary_result = AuditorResult(
                approved=True,
                issues_found=[],
                auditor_messages=[],
                tokens_used=800,
                prompt_tokens=500,
                completion_tokens=300,
                model_used="claude-sonnet-4-5",
            )

            service._resolve_client_and_model = MagicMock(
                side_effect=[
                    (
                        MagicMock(review_patch=MagicMock(return_value=primary_result)),
                        "claude-opus-4-5",
                    ),
                    (
                        MagicMock(review_patch=MagicMock(return_value=secondary_result)),
                        "claude-sonnet-4-5",
                    ),
                ]
            )
            service._model_to_provider = MagicMock(return_value="anthropic")
            service._record_usage = MagicMock()
            service.quality_gate = MagicMock()
            service.quality_gate.assess_phase = MagicMock(return_value={})

            # Execute dual audit
            phase_spec = {"task_category": "security_auth_change", "phase_id": "phase-1"}
            _result = service.execute_auditor_review(
                patch_content="diff content",
                phase_spec=phase_spec,
                run_id="test-run",
                phase_id="phase-1",
            )

            # Verify judge was NOT invoked (only 2 calls: primary, secondary)
            assert service._resolve_client_and_model.call_count == 2
            assert service._record_usage.call_count == 2


@pytest.mark.aspirational
class TestDualAuditConfiguration:
    """Tests for dual-audit configuration and enablement."""

    def test_dual_audit_enabled_for_configured_category(self):
        """Dual audit is enabled for categories with dual_audit: true."""
        with patch.object(LlmService, "__init__", lambda self, *args, **kwargs: None):
            service = LlmService.__new__(LlmService)
            service.model_router = MagicMock()
            service.model_router.config = {
                "llm_routing_policies": {
                    "security_auth_change": {
                        "dual_audit": True,
                    }
                }
            }

            # Check dual audit is enabled
            assert service._should_use_dual_audit("security_auth_change") is True

    def test_dual_audit_disabled_for_non_configured_category(self):
        """Dual audit is disabled for categories without dual_audit: true."""
        with patch.object(LlmService, "__init__", lambda self, *args, **kwargs: None):
            service = LlmService.__new__(LlmService)
            service.model_router = MagicMock()
            service.model_router.config = {
                "llm_routing_policies": {
                    "general": {
                        "dual_audit": False,
                    }
                }
            }

            # Check dual audit is disabled
            assert service._should_use_dual_audit("general") is False

    def test_secondary_auditor_model_from_config(self):
        """Secondary auditor model is read from config."""
        with patch.object(LlmService, "__init__", lambda self, *args, **kwargs: None):
            service = LlmService.__new__(LlmService)
            service.model_router = MagicMock()
            service.model_router.config = {
                "llm_routing_policies": {
                    "security_auth_change": {
                        "dual_audit": True,
                        "secondary_auditor": "custom-model",
                    }
                }
            }

            # Check secondary auditor model
            assert service._get_secondary_auditor_model("security_auth_change") == "custom-model"

    def test_secondary_auditor_defaults_to_claude_sonnet(self):
        """Secondary auditor defaults to claude-sonnet-4-5 if not configured."""
        with patch.object(LlmService, "__init__", lambda self, *args, **kwargs: None):
            service = LlmService.__new__(LlmService)
            service.model_router = MagicMock()
            service.model_router.config = {
                "llm_routing_policies": {
                    "security_auth_change": {
                        "dual_audit": True,
                    }
                }
            }

            # Check secondary auditor defaults
            assert (
                service._get_secondary_auditor_model("security_auth_change") == "claude-sonnet-4-5"
            )
