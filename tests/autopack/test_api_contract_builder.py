"""
P0.2 Reliability Test: Builder result API contract validation.

Validates that executor payloads match FastAPI endpoint schemas.
Prevents runtime 422 errors due to schema drift.
"""

from pathlib import Path
from types import SimpleNamespace

import pytest

from autopack.builder_schemas import (
    BuilderProbeResult,
    BuilderResult,
    BuilderSuggestedIssue,
)


class TestBuilderResultContract:
    """Test that builder_result payloads match Pydantic schemas."""

    def test_minimal_builder_result_schema(self):
        """Minimal valid BuilderResult should validate."""
        payload = {"phase_id": "test-phase", "run_id": "test-run", "status": "success"}

        # Should validate without errors
        result = BuilderResult(**payload)
        assert result.phase_id == "test-phase"
        assert result.run_id == "test-run"
        assert result.status == "success"

    def test_full_builder_result_schema(self):
        """Full BuilderResult with all fields should validate."""
        payload = {
            "phase_id": "test-phase",
            "run_id": "test-run",
            "run_type": "project_build",
            "allowed_paths": ["src/", "tests/"],
            "patch_content": "diff --git a/foo.py b/foo.py\n...",
            "files_changed": ["foo.py", "bar.py"],
            "lines_added": 10,
            "lines_removed": 5,
            "builder_attempts": 2,
            "tokens_used": 1500,
            "duration_minutes": 2.5,
            "probe_results": [
                {
                    "probe_type": "pytest",
                    "exit_code": 0,
                    "stdout": "All tests passed",
                    "stderr": "",
                    "duration_seconds": 5.2,
                }
            ],
            "suggested_issues": [
                {
                    "issue_key": "test-coverage-low",
                    "severity": "medium",
                    "source": "builder",
                    "category": "quality",
                    "evidence_refs": ["tests/test_foo.py"],
                    "description": "Test coverage below 80%",
                }
            ],
            "status": "success",
            "notes": "Build completed successfully",
        }

        result = BuilderResult(**payload)
        assert result.phase_id == "test-phase"
        assert result.tokens_used == 1500
        assert len(result.probe_results) == 1
        assert len(result.suggested_issues) == 1

    @pytest.mark.legacy_contract
    def test_legacy_payload_rejected_by_strict_schema(self):
        """
        Test that legacy payload format is REJECTED by the strict schema.

        P1.3 COMPLETE: BuilderResult now has extra="forbid" which rejects legacy payloads
        that use non-canonical field names (output, files_modified, metadata wrapper).
        This is the intended behavior - protocol drift is caught at validation time.

        This test is OPTIONAL and excluded from default CI runs.
        Run it explicitly via: pytest -m legacy_contract
        """
        from pydantic import ValidationError

        # Legacy payload format that older executors might send
        legacy_payload = {
            "phase_id": "test-phase",
            "run_id": "test-run",
            "status": "SUCCESS",  # Wrong: schema expects lowercase "success"
            "success": True,  # Extra field not in schema
            "output": "diff --git ...",  # Wrong: schema expects "patch_content"
            "files_modified": ["foo.py"],  # Wrong: schema expects "files_changed"
            "metadata": {  # Wrong: fields should be top-level
                "run_type": "project_build",
                "tokens_used": 1500,
            },
        }

        # Strict schema should REJECT legacy payloads (extra="forbid")
        with pytest.raises(ValidationError) as exc_info:
            BuilderResult(**legacy_payload)

        # Verify the rejection identifies the extra fields
        error_str = str(exc_info.value)
        assert "Extra inputs are not permitted" in error_str
        # Should catch at least some of the legacy fields
        assert any(
            field in error_str for field in ["success", "output", "files_modified", "metadata"]
        ), f"Expected legacy field rejection, got: {error_str}"

    @pytest.mark.legacy_contract
    def test_builder_result_poster_produces_schema_compliant_payload(self, tmp_path, monkeypatch):
        """
        Contract: BuilderResultPoster produces schema-compliant payloads.

        P1.2 COMPLETE: BuilderResultPoster.post_result() now emits canonical payload
        with proper field names (patch_content, files_changed, status="success").
        This test verifies the contract is maintained.
        """
        from unittest.mock import MagicMock

        from autopack.api.builder_result_poster import BuilderResultPoster

        # Create a mock executor with required attributes
        mock_executor = MagicMock()
        mock_executor.run_id = "test-run"
        mock_executor.run_type = "project_build"
        mock_executor.workspace = Path(tmp_path)
        mock_executor._run_http_500_count = 0
        mock_executor.MAX_HTTP_500_PER_RUN = 10

        # Capture the payload sent to api_client
        captured = {}

        def capture_submit(run_id, phase_id, payload, timeout=None):
            captured["run_id"] = run_id
            captured["phase_id"] = phase_id
            captured["payload"] = payload

        mock_executor.api_client = MagicMock()
        mock_executor.api_client.submit_builder_result = capture_submit

        # Create poster with mock executor
        poster = BuilderResultPoster(mock_executor)

        # Minimal llm_client.BuilderResult-like object
        llm_result = SimpleNamespace(
            patch_content="diff --git a/foo.py b/foo.py\n--- a/foo.py\n+++ b/foo.py\n@@ -1 +1 @@\n-old\n+new\n",
            success=True,
            tokens_used=1500,
            builder_messages=["Build completed"],
            error=None,
        )

        poster.post_result("test-phase", llm_result, allowed_paths=["src/"])

        # Contract: the payload produced by BuilderResultPoster must parse as BuilderResult
        # AND preserve critical fields at top level (no metadata burying, no silent data loss).
        payload = captured["payload"]
        parsed = BuilderResult(**payload)

        assert parsed.phase_id == "test-phase"
        assert parsed.run_id == "test-run"
        assert parsed.status == "success"  # Must be lowercase canonical value
        assert parsed.patch_content is not None and parsed.patch_content.strip()
        assert parsed.files_changed, "files_changed must be populated when patch modifies files"
        assert parsed.tokens_used == 1500

    def test_probe_result_schema(self):
        """BuilderProbeResult schema should validate correctly."""
        payload = {
            "probe_type": "pytest",
            "exit_code": 0,
            "stdout": "All tests passed",
            "stderr": "",
            "duration_seconds": 5.2,
        }

        probe = BuilderProbeResult(**payload)
        assert probe.probe_type == "pytest"
        assert probe.exit_code == 0

    def test_suggested_issue_schema(self):
        """BuilderSuggestedIssue schema should validate correctly."""
        payload = {
            "issue_key": "test-coverage-low",
            "severity": "medium",
            "source": "builder",
            "category": "quality",
            "evidence_refs": ["tests/test_foo.py"],
            "description": "Test coverage below 80%",
        }

        issue = BuilderSuggestedIssue(**payload)
        assert issue.issue_key == "test-coverage-low"
        assert issue.severity == "medium"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
