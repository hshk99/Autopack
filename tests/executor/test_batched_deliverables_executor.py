"""Contract tests for BatchedDeliverablesExecutor.

Extracted from autonomous_executor.py as part of PR-EXE-14.
Tests the batched deliverables execution strategy.
"""

from unittest.mock import Mock, patch

import pytest

from autopack.executor.batched_deliverables_executor import (
    BatchedDeliverablesExecutor, BatchedExecutionContext,
    BatchedExecutionResult)
from autopack.llm_client import AuditorResult, BuilderResult


@pytest.fixture
def mock_executor():
    """Create a mock autonomous executor."""
    executor = Mock()
    executor.workspace = "/test/workspace"
    executor.run_id = "test-run"
    executor.run_type = "project_build"
    executor.builder_output_config = {}
    executor.memory_service = None
    executor.quality_gate = Mock()

    # Mock helper methods
    executor._load_repository_context = Mock(return_value={"existing_files": {}})
    executor._get_learning_context_for_phase = Mock(
        return_value={"project_rules": [], "run_hints": []}
    )
    executor._get_project_slug = Mock(return_value="test-project")
    executor._build_deliverables_contract = Mock(return_value="contract")
    executor._post_builder_result = Mock()
    executor._update_phase_status = Mock()
    executor._run_ci_checks = Mock(return_value={"status": "PASS"})
    executor._build_run_context = Mock(return_value={})
    executor._post_auditor_result = Mock()
    executor._record_phase_error = Mock()
    executor._record_learning_hint = Mock()

    # Mock LLM service
    executor.llm_service = Mock()
    executor.llm_service.execute_builder_phase = Mock(
        return_value=BuilderResult(
            success=True,
            patch_content="test patch",
            builder_messages=[],
            tokens_used=100,
            model_used="test-model",
            error=None,
        )
    )
    executor.llm_service.execute_auditor_review = Mock(
        return_value=AuditorResult(
            approved=True,
            issues_found=[],
            auditor_messages=[],
            tokens_used=50,
            model_used="test-model",
            error=None,
        )
    )
    executor.llm_service.generate_deliverables_manifest = Mock(return_value=(True, [], None, None))

    # Mock quality gate
    quality_report = Mock()
    quality_report.is_blocked = Mock(return_value=False)
    quality_report.quality_level = "ACCEPTABLE"
    quality_report.issues = []
    executor.quality_gate.assess_phase = Mock(return_value=quality_report)

    return executor


@pytest.fixture
def batched_executor(mock_executor):
    """Create a BatchedDeliverablesExecutor instance."""
    return BatchedDeliverablesExecutor(mock_executor)


@pytest.fixture
def sample_context():
    """Create a sample execution context."""
    return BatchedExecutionContext(
        phase={"phase_id": "test-phase", "description": "Test phase", "scope": {}},
        attempt_index=0,
        allowed_paths=None,
        batches=[["file1.py"], ["file2.py"]],
        batching_label="test",
        manifest_allowed_roots=("src/",),
        apply_allowed_roots=("src/",),
    )


class TestBatchedDeliverablesExecutor:
    """Test BatchedDeliverablesExecutor functionality."""

    def test_executor_initialization(self, mock_executor):
        """Test that executor initializes correctly."""
        executor = BatchedDeliverablesExecutor(mock_executor)
        assert executor.executor == mock_executor

    def test_context_dataclass_creation(self):
        """Test that BatchedExecutionContext can be created."""
        context = BatchedExecutionContext(
            phase={"phase_id": "test"},
            attempt_index=0,
            allowed_paths=None,
            batches=[["file.py"]],
            batching_label="test",
            manifest_allowed_roots=("src/",),
            apply_allowed_roots=("src/",),
        )
        assert context.phase["phase_id"] == "test"
        assert context.batches == [["file.py"]]

    def test_result_dataclass_creation(self):
        """Test that BatchedExecutionResult can be created."""
        result = BatchedExecutionResult(
            success=True,
            status="COMPLETE",
            combined_patch="patch",
            total_tokens=100,
        )
        assert result.success is True
        assert result.status == "COMPLETE"

    @patch("autopack.executor.batched_deliverables_executor.validate_deliverables")
    @patch(
        "autopack.executor.batched_deliverables_executor.validate_new_file_diffs_have_complete_structure"
    )
    @patch("autopack.executor.batched_deliverables_executor.GovernedApplyPath")
    def test_execute_batched_phase_success(
        self,
        mock_governed_apply,
        mock_struct_validate,
        mock_deliverables_validate,
        batched_executor,
        sample_context,
    ):
        """Test successful batched phase execution."""
        # Setup mocks
        mock_deliverables_validate.return_value = (True, [], {})
        mock_struct_validate.return_value = (True, [], {})

        governed_apply_instance = Mock()
        governed_apply_instance.apply_patch = Mock(return_value=(True, None))
        mock_governed_apply.return_value = governed_apply_instance

        # Execute
        result = batched_executor.execute_batched_phase(sample_context)

        # Assertions
        assert result.success is True
        assert result.status == "COMPLETE"
        assert result.total_tokens > 0
        batched_executor.executor._update_phase_status.assert_called_with("test-phase", "COMPLETE")

    @patch("autopack.executor.batched_deliverables_executor.validate_deliverables")
    def test_execute_batched_phase_validation_failure(
        self,
        mock_deliverables_validate,
        batched_executor,
        sample_context,
    ):
        """Test batched phase execution with validation failure."""
        # Setup mocks
        mock_deliverables_validate.return_value = (False, ["error1"], {"detail": "bad"})

        # Execute
        result = batched_executor.execute_batched_phase(sample_context)

        # Assertions
        assert result.success is False
        assert result.status == "DELIVERABLES_VALIDATION_FAILED"

    def test_execute_batched_phase_builder_failure(self, batched_executor, sample_context):
        """Test batched phase execution with Builder failure."""
        # Setup Builder to fail
        batched_executor.executor.llm_service.execute_builder_phase.return_value = BuilderResult(
            success=False,
            patch_content="",
            builder_messages=[],
            tokens_used=0,
            model_used=None,
            error="Builder error",
        )

        # Execute
        result = batched_executor.execute_batched_phase(sample_context)

        # Assertions
        assert result.success is False
        assert result.status == "FAILED"
        batched_executor.executor._update_phase_status.assert_called_with("test-phase", "FAILED")

    def test_execute_batched_phase_quality_gate_block(self, batched_executor, sample_context):
        """Test batched phase execution blocked by quality gate."""
        # Setup quality gate to block
        quality_report = Mock()
        quality_report.is_blocked = Mock(return_value=True)
        quality_report.quality_level = "UNACCEPTABLE"
        quality_report.issues = ["issue1"]
        batched_executor.executor.quality_gate.assess_phase.return_value = quality_report

        # Setup other mocks for success path
        with patch(
            "autopack.executor.batched_deliverables_executor.validate_deliverables"
        ) as mock_val:
            mock_val.return_value = (True, [], {})
            with patch(
                "autopack.executor.batched_deliverables_executor.validate_new_file_diffs_have_complete_structure"
            ) as mock_struct:
                mock_struct.return_value = (True, [], {})
                with patch(
                    "autopack.executor.batched_deliverables_executor.GovernedApplyPath"
                ) as mock_gov:
                    gov_instance = Mock()
                    gov_instance.apply_patch = Mock(return_value=(True, None))
                    mock_gov.return_value = gov_instance

                    # Execute
                    result = batched_executor.execute_batched_phase(sample_context)

        # Assertions
        assert result.success is False
        assert result.status == "BLOCKED"
        batched_executor.executor._update_phase_status.assert_called_with("test-phase", "BLOCKED")

    def test_execute_batched_phase_multiple_batches(self, batched_executor):
        """Test execution with multiple batches."""
        context = BatchedExecutionContext(
            phase={"phase_id": "multi-batch", "description": "Multi batch", "scope": {}},
            attempt_index=0,
            allowed_paths=None,
            batches=[["file1.py"], ["file2.py"], ["file3.py"]],
            batching_label="test",
            manifest_allowed_roots=("src/",),
            apply_allowed_roots=("src/",),
        )

        with patch(
            "autopack.executor.batched_deliverables_executor.validate_deliverables"
        ) as mock_val:
            mock_val.return_value = (True, [], {})
            with patch(
                "autopack.executor.batched_deliverables_executor.validate_new_file_diffs_have_complete_structure"
            ) as mock_struct:
                mock_struct.return_value = (True, [], {})
                with patch(
                    "autopack.executor.batched_deliverables_executor.GovernedApplyPath"
                ) as mock_gov:
                    gov_instance = Mock()
                    gov_instance.apply_patch = Mock(return_value=(True, None))
                    mock_gov.return_value = gov_instance

                    # Execute
                    result = batched_executor.execute_batched_phase(context)

        # Assertions
        assert result.success is True
        assert batched_executor.executor.llm_service.execute_builder_phase.call_count == 3

    @patch("autopack.executor.batched_deliverables_executor.subprocess.run")
    def test_execute_batched_phase_retry_skip(self, mock_subprocess, batched_executor):
        """Test retry optimization that skips already-complete batches."""
        context = BatchedExecutionContext(
            phase={"phase_id": "retry-test", "description": "Retry test", "scope": {}},
            attempt_index=1,  # Retry attempt
            allowed_paths=None,
            batches=[["existing_file.py"]],
            batching_label="test",
            manifest_allowed_roots=("src/",),
            apply_allowed_roots=("src/",),
        )

        # Mock file existence check
        with patch("autopack.executor.batched_deliverables_executor.Path") as mock_path:
            mock_file = Mock()
            mock_file.exists = Mock(return_value=True)
            mock_file.is_file = Mock(return_value=True)
            mock_file.stat = Mock(return_value=Mock(st_size=100))
            mock_path.return_value.__truediv__ = Mock(return_value=mock_file)

            mock_subprocess.return_value = Mock(returncode=0, stdout="diff content")

            with patch(
                "autopack.executor.batched_deliverables_executor.validate_deliverables"
            ) as mock_val:
                mock_val.return_value = (True, [], {})
                with patch(
                    "autopack.executor.batched_deliverables_executor.validate_new_file_diffs_have_complete_structure"
                ) as mock_struct:
                    mock_struct.return_value = (True, [], {})
                    with patch(
                        "autopack.executor.batched_deliverables_executor.GovernedApplyPath"
                    ) as mock_gov:
                        gov_instance = Mock()
                        gov_instance.apply_patch = Mock(return_value=(True, None))
                        mock_gov.return_value = gov_instance

                        # Execute
                        _result = batched_executor.execute_batched_phase(context)

            # Builder should not be called for skipped batch (batch was skipped due to retry optimization)
            assert batched_executor.executor.llm_service.execute_builder_phase.call_count == 0
