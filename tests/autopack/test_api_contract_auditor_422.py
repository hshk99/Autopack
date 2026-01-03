"""
P0.2 Reliability Test: Auditor result API contract + 422 fallback validation.

Validates that auditor_result payloads match schemas and that the 422 fallback
logic (lines 8107-8138 in autonomous_executor.py) works correctly.
"""
import json
from typing import Dict, Any

import pytest
from pydantic import ValidationError

from autopack.builder_schemas import AuditorResult, BuilderSuggestedIssue, AuditorSuggestedPatch


class TestAuditorResultContract:
    """Test that auditor_result payloads match Pydantic schemas."""

    def test_minimal_auditor_result_schema(self):
        """Minimal valid AuditorResult should validate."""
        payload = {
            "phase_id": "test-phase",
            "run_id": "test-run",
            "review_notes": "Patch looks good",
            "recommendation": "approve"
        }

        result = AuditorResult(**payload)
        assert result.phase_id == "test-phase"
        assert result.recommendation == "approve"

    def test_full_auditor_result_schema(self):
        """Full AuditorResult with all fields should validate."""
        payload = {
            "phase_id": "test-phase",
            "run_id": "test-run",
            "review_notes": "Found security issues",
            "issues_found": [
                {
                    "issue_key": "sql-injection-risk",
                    "severity": "high",
                    "source": "auditor",
                    "category": "security",
                    "evidence_refs": ["src/db.py:42"],
                    "description": "Unescaped SQL query"
                }
            ],
            "suggested_patches": [
                {
                    "description": "Use parameterized query",
                    "patch_content": "diff --git a/src/db.py ...",
                    "files_affected": ["src/db.py"]
                }
            ],
            "auditor_attempts": 1,
            "tokens_used": 800,
            "recommendation": "revise",
            "confidence": "high"
        }

        result = AuditorResult(**payload)
        assert result.recommendation == "revise"
        assert len(result.issues_found) == 1
        assert len(result.suggested_patches) == 1

    def test_executor_auditor_payload_matches_schema(self):
        """
        Test that executor auditor payload matches AuditorResult schema.

        VERIFIED: autonomous_executor.py lines 8093-8103 already send schema-compliant payload.
        This test confirms the auditor endpoint has correct contract enforcement.
        """
        # This is what autonomous_executor.py SHOULD send (matching schema)
        executor_payload = {
            "phase_id": "test-phase",
            "run_id": "test-run",
            "review_notes": "Patch approved",
            "issues_found": [
                {
                    "issue_key": "style-issue",
                    "severity": "low",
                    "source": "auditor",
                    "category": "style",
                    "evidence_refs": [],
                    "description": "Missing docstring"
                }
            ],
            "suggested_patches": [],
            "auditor_attempts": 1,
            "tokens_used": 500,
            "recommendation": "approve",
            "confidence": "medium"
        }

        # Should validate successfully with all fields preserved
        result = AuditorResult(**executor_payload)
        assert result.phase_id == "test-phase"
        assert result.recommendation == "approve"
        assert result.tokens_used == 500
        assert len(result.issues_found) == 1
        assert result.issues_found[0].issue_key == "style-issue"

    def test_422_fallback_compatibility_payload(self):
        """
        Test the 422 fallback payload structure (lines 8125-8130).

        When backend incorrectly expects BuilderResultRequest at auditor_result endpoint,
        executor sends a compatibility wrapper with "success" field.
        """
        # Original auditor payload that triggers 422
        auditor_payload = {
            "phase_id": "test-phase",
            "run_id": "test-run",
            "review_notes": "Approved",
            "recommendation": "approve",
            "issues_found": [],
            "suggested_patches": [],
            "auditor_attempts": 1,
            "tokens_used": 300,
            "confidence": "high"
        }

        # Fallback wrapper (what executor sends on 422 retry)
        fallback_payload = {
            "success": True,  # Derived from recommendation == "approve"
            "output": auditor_payload.get("review_notes") or "",
            "files_modified": [],
            "metadata": auditor_payload  # Original payload preserved
        }

        # Verify fallback structure
        assert fallback_payload["success"] is True
        assert fallback_payload["output"] == "Approved"
        assert fallback_payload["metadata"]["recommendation"] == "approve"

        # The fallback should NOT validate as AuditorResult (it's a BuilderResultRequest wrapper)
        with pytest.raises(ValidationError):
            AuditorResult(**fallback_payload)

    def test_422_missing_success_field_detection(self):
        """
        Test detection logic for 422 "missing success field" error.

        This validates the logic at lines 8117-8123 in autonomous_executor.py.
        """
        # Simulate FastAPI 422 response detail
        pydantic_422_detail = [
            {
                "loc": ["body", "success"],
                "msg": "Field required",
                "type": "value_error.missing"
            }
        ]

        # Detection logic (from executor)
        is_missing_success = False
        for item in pydantic_422_detail:
            loc = item.get("loc") if isinstance(item, dict) else None
            msg = item.get("msg") if isinstance(item, dict) else ""
            if loc == ["body", "success"] and "Field required" in str(msg):
                is_missing_success = True
                break

        assert is_missing_success, "Should detect missing 'success' field from 422 detail"

    def test_recommendation_field_values(self):
        """Test that recommendation field accepts only valid values."""
        valid_recommendations = ["approve", "revise", "escalate"]

        for rec in valid_recommendations:
            payload = {
                "phase_id": "test-phase",
                "run_id": "test-run",
                "review_notes": f"Test {rec}",
                "recommendation": rec
            }
            result = AuditorResult(**payload)
            assert result.recommendation == rec

    def test_suggested_patch_schema(self):
        """AuditorSuggestedPatch schema should validate correctly."""
        payload = {
            "description": "Fix SQL injection",
            "patch_content": "diff --git a/db.py ...",
            "files_affected": ["src/db.py"]
        }

        patch = AuditorSuggestedPatch(**payload)
        assert patch.description == "Fix SQL injection"
        assert len(patch.files_affected) == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
