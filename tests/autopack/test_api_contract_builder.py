"""
P0.2 Reliability Test: Builder result API contract validation.

Validates that executor payloads match FastAPI endpoint schemas.
Prevents runtime 422 errors due to schema drift.
"""
from pathlib import Path
from types import SimpleNamespace

import pytest

from autopack.builder_schemas import BuilderResult, BuilderProbeResult, BuilderSuggestedIssue
from autopack.autonomous_executor import AutonomousExecutor


class TestBuilderResultContract:
    """Test that builder_result payloads match Pydantic schemas."""

    def test_minimal_builder_result_schema(self):
        """Minimal valid BuilderResult should validate."""
        payload = {
            "phase_id": "test-phase",
            "run_id": "test-run",
            "status": "success"
        }

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
                    "duration_seconds": 5.2
                }
            ],
            "suggested_issues": [
                {
                    "issue_key": "test-coverage-low",
                    "severity": "medium",
                    "source": "builder",
                    "category": "quality",
                    "evidence_refs": ["tests/test_foo.py"],
                    "description": "Test coverage below 80%"
                }
            ],
            "status": "success",
            "notes": "Build completed successfully"
        }

        result = BuilderResult(**payload)
        assert result.phase_id == "test-phase"
        assert result.tokens_used == 1500
        assert len(result.probe_results) == 1
        assert len(result.suggested_issues) == 1

    @pytest.mark.legacy_contract
    def test_executor_legacy_payload_data_loss__legacy_optional(self):
        """
        Test that ACTUAL executor payload (autonomous_executor.py:7977-7996) causes data loss.

        CONFIRMED DRIFT: Executor sends legacy format that validates but loses data.
        This test is OPTIONAL and excluded from default CI runs.
        Run it explicitly via: pytest -m legacy_contract
        Remove it after the P1 payload migration is complete.
        """
        # This is what autonomous_executor.py CURRENTLY sends (simplified)
        executor_payload = {
            "phase_id": "test-phase",
            "run_id": "test-run",
            "status": "SUCCESS",  # Wrong: schema expects "success"
            "success": True,  # Extra field not in schema
            "output": "diff --git ...",  # Wrong: schema expects "patch_content"
            "files_modified": ["foo.py"],  # Wrong: schema expects "files_changed"
            "metadata": {  # Wrong: fields should be top-level
                "run_type": "project_build",
                "lines_added": 10,
                "lines_removed": 5,
                "builder_attempts": 1,
                "tokens_used": 1500,
                "duration_minutes": 0.0,
                "probe_results": [],
                "suggested_issues": [],
                "notes": "Build completed",
                "allowed_paths": ["src/"]
            }
        }

        # Pydantic allows extra fields by default, so validation succeeds but data is lost
        result = BuilderResult(**executor_payload)

        # Verify data loss occurs
        assert result.patch_content is None, "Data lost: executor sends 'output' not 'patch_content'"
        assert result.files_changed == [], "Data lost: executor sends 'files_modified' not 'files_changed'"
        assert result.tokens_used == 0, "Data lost: executor packs 'tokens_used' in 'metadata' not top-level"

    @pytest.mark.xfail(
        strict=True,
        reason=(
            "Deferred until P1: executor _post_builder_result still sends legacy payload "
            "(output/files_modified/metadata/status=SUCCESS). Remove xfail once executor posts "
            "schema-compliant BuilderResult payload."
        ),
    )
    def test_builder_result_correct_payload_preserves_fields__contract_deferred(self, tmp_path, monkeypatch):
        """
        Permanent contract: schema-compliant payload must preserve critical fields.

        This is the intended BuilderResult contract at the Executor ↔ FastAPI boundary.
        """
        # Create an executor instance WITHOUT running __init__ (avoids API key checks + DB init).
        executor = AutonomousExecutor.__new__(AutonomousExecutor)
        executor.run_id = "test-run"
        executor.api_url = "http://example.invalid"
        executor.api_key = None
        executor.run_type = "project_build"
        executor.workspace = Path(tmp_path)
        executor._run_http_500_count = 0
        executor.MAX_HTTP_500_PER_RUN = 10

        captured = {}

        class _FakeResponse:
            status_code = 200

            def raise_for_status(self):
                return None

            def json(self):
                return {}

        def _fake_post(url, headers=None, json=None, timeout=None):
            captured["url"] = url
            captured["payload"] = json
            return _FakeResponse()

        # Patch the requests module used inside autopack.autonomous_executor
        import autopack.autonomous_executor as ae
        monkeypatch.setattr(ae.requests, "post", _fake_post)

        # Minimal llm_client.BuilderResult-like object (only the fields _post_builder_result uses)
        llm_result = SimpleNamespace(
            patch_content="diff --git a/foo.py b/foo.py\n--- a/foo.py\n+++ b/foo.py\n",
            success=True,
            tokens_used=1500,
            builder_messages=["Build completed"],
            error=None,
        )

        executor._post_builder_result("test-phase", llm_result, allowed_paths=["src/"])

        # Contract: the payload produced by _post_builder_result must parse as BuilderResult
        # AND preserve critical fields at top level (no metadata burying, no silent data loss).
        parsed = BuilderResult(**captured["payload"])
        assert parsed.phase_id == "test-phase"
        assert parsed.run_id == "test-run"
        assert parsed.status == "success"
        assert parsed.patch_content is not None and parsed.patch_content.strip()
        assert parsed.files_changed, "files_changed must be top-level and non-empty when patch modifies files"
        assert parsed.tokens_used == 1500

    def test_probe_result_schema(self):
        """BuilderProbeResult schema should validate correctly."""
        payload = {
            "probe_type": "pytest",
            "exit_code": 0,
            "stdout": "All tests passed",
            "stderr": "",
            "duration_seconds": 5.2
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
            "description": "Test coverage below 80%"
        }

        issue = BuilderSuggestedIssue(**payload)
        assert issue.issue_key == "test-coverage-low"
        assert issue.severity == "medium"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
