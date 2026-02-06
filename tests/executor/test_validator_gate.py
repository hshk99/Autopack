"""Tests for validator gate wiring (IMP-RES-005)

Tests the validator gate infrastructure and phase runner integration.
"""

import pytest

from autopack.executor.phase_spec_validator_gate import (
    PhaseContextValidator,
    PhaseSpecificationValidator,
)
from autopack.executor.validator_gate import (
    GateExecutionResult,
    GateResult,
    GateType,
    ValidatorGate,
    ValidatorGatePipeline,
    create_default_validator_gate_pipeline,
)


class TestGateType:
    """Tests for GateType enum."""

    def test_gate_type_values(self):
        """Test gate type enum values."""
        assert GateType.HARD.value == "hard"
        assert GateType.SOFT.value == "soft"


class TestGateResult:
    """Tests for GateResult dataclass."""

    def test_gate_result_initialization(self):
        """Test creating a gate result."""
        result = GateResult(passed=True, gate_name="TestGate", gate_type=GateType.HARD)
        assert result.passed is True
        assert result.gate_name == "TestGate"
        assert result.gate_type == GateType.HARD
        assert result.errors == []
        assert result.warnings == []

    def test_add_error(self):
        """Test adding errors to gate result."""
        result = GateResult(passed=True, gate_name="TestGate", gate_type=GateType.HARD)
        result.add_error("Test error")
        assert result.passed is False
        assert "Test error" in result.errors

    def test_add_warning(self):
        """Test adding warnings to gate result."""
        result = GateResult(passed=True, gate_name="TestGate", gate_type=GateType.SOFT)
        result.add_warning("Test warning")
        assert "Test warning" in result.warnings

    def test_is_blocking_hard_gate_failed(self):
        """Test is_blocking for hard gate that failed."""
        result = GateResult(passed=False, gate_name="TestGate", gate_type=GateType.HARD)
        assert result.is_blocking() is True

    def test_is_blocking_hard_gate_passed(self):
        """Test is_blocking for hard gate that passed."""
        result = GateResult(passed=True, gate_name="TestGate", gate_type=GateType.HARD)
        assert result.is_blocking() is False

    def test_is_blocking_soft_gate_failed(self):
        """Test is_blocking for soft gate that failed."""
        result = GateResult(passed=False, gate_name="TestGate", gate_type=GateType.SOFT)
        assert result.is_blocking() is False


class SimpleTestGate(ValidatorGate):
    """Simple test validator gate."""

    def __init__(self, name="TestGate", should_pass=True, gate_type=GateType.HARD):
        """Initialize simple test gate."""
        super().__init__(name, gate_type)
        self.should_pass = should_pass

    def validate(self, context):
        """Validate context."""
        result = GateResult(
            passed=self.should_pass, gate_name=self.name, gate_type=self.gate_type
        )
        if not self.should_pass:
            result.add_error("Test failure")
        return result


class TestValidatorGatePipeline:
    """Tests for ValidatorGatePipeline."""

    def test_pipeline_initialization(self):
        """Test creating a validator gate pipeline."""
        pipeline = ValidatorGatePipeline()
        assert pipeline.gates == []
        assert pipeline._results == []

    def test_register_gate(self):
        """Test registering a gate in the pipeline."""
        pipeline = ValidatorGatePipeline()
        gate = SimpleTestGate()
        pipeline.register_gate(gate)
        assert len(pipeline.gates) == 1
        assert pipeline.gates[0] is gate

    def test_register_invalid_gate(self):
        """Test registering invalid gate raises error."""
        pipeline = ValidatorGatePipeline()
        with pytest.raises(TypeError):
            pipeline.register_gate("not a gate")

    def test_execute_all_pass(self):
        """Test executing pipeline where all gates pass."""
        pipeline = ValidatorGatePipeline()
        pipeline.register_gate(SimpleTestGate("Gate1", should_pass=True))
        pipeline.register_gate(SimpleTestGate("Gate2", should_pass=True))

        result = pipeline.execute({})

        assert result.can_proceed is True
        assert result.all_passed is True
        assert result.total_gates == 2
        assert result.passed_gates == 2
        assert result.failed_gates == 0
        assert len(result.blocking_failures) == 0

    def test_execute_hard_gate_fails(self):
        """Test executing pipeline where hard gate fails."""
        pipeline = ValidatorGatePipeline()
        pipeline.register_gate(SimpleTestGate("Gate1", should_pass=True))
        pipeline.register_gate(SimpleTestGate("Gate2", should_pass=False, gate_type=GateType.HARD))

        result = pipeline.execute({})

        assert result.can_proceed is False
        assert result.all_passed is False
        assert result.total_gates == 2
        assert result.passed_gates == 1
        assert result.failed_gates == 1
        assert len(result.blocking_failures) == 1

    def test_execute_soft_gate_fails(self):
        """Test executing pipeline where soft gate fails."""
        pipeline = ValidatorGatePipeline()
        pipeline.register_gate(SimpleTestGate("Gate1", should_pass=True))
        pipeline.register_gate(SimpleTestGate("Gate2", should_pass=False, gate_type=GateType.SOFT))

        result = pipeline.execute({})

        assert result.can_proceed is True
        assert result.all_passed is False
        assert result.total_gates == 2
        assert result.passed_gates == 1
        assert result.failed_gates == 1
        assert len(result.blocking_failures) == 0

    def test_get_results(self):
        """Test getting results from last execution."""
        pipeline = ValidatorGatePipeline()
        pipeline.register_gate(SimpleTestGate("Gate1", should_pass=True))
        pipeline.execute({})

        results = pipeline.get_results()
        assert len(results) == 1
        assert results[0].gate_name == "Gate1"


class TestGateExecutionResult:
    """Tests for GateExecutionResult."""

    def test_get_summary_all_passed(self):
        """Test summary when all gates passed."""
        result = GateExecutionResult(
            can_proceed=True,
            all_passed=True,
            total_gates=2,
            passed_gates=2,
            failed_gates=0,
            blocking_failures=[],
            results=[],
        )
        summary = result.get_summary()
        assert "PASS" in summary
        assert "2/2" in summary
        assert "CAN" in summary

    def test_get_summary_failed(self):
        """Test summary when gates failed."""
        result = GateExecutionResult(
            can_proceed=False,
            all_passed=False,
            total_gates=2,
            passed_gates=1,
            failed_gates=1,
            blocking_failures=[],
            results=[],
        )
        summary = result.get_summary()
        assert "FAIL" in summary
        assert "1/2" in summary
        assert "CANNOT" in summary

    def test_get_blocking_failure_messages(self):
        """Test getting blocking failure messages."""
        failure = GateResult(passed=False, gate_name="FailGate", gate_type=GateType.HARD)
        failure.add_error("Error 1")
        failure.add_error("Error 2")

        result = GateExecutionResult(
            can_proceed=False,
            all_passed=False,
            total_gates=1,
            passed_gates=0,
            failed_gates=1,
            blocking_failures=[failure],
            results=[failure],
        )
        messages = result.get_blocking_failure_messages()
        assert len(messages) == 3  # 1 message line + 2 errors
        assert "[FailGate]" in messages[0]


class TestPhaseSpecificationValidator:
    """Tests for PhaseSpecificationValidator gate."""

    def test_valid_phase_spec(self):
        """Test validating a valid phase specification."""
        validator = PhaseSpecificationValidator()
        context = {
            "phase": {
                "phase_id": "test-phase",
                "phase_name": "Test Phase",
                "phase_type": "build",
            },
            "phase_id": "test-phase",
        }
        result = validator.validate(context)
        assert result.passed is True

    def test_missing_phase_in_context(self):
        """Test validation when phase is missing from context."""
        validator = PhaseSpecificationValidator()
        context = {"phase_id": "test-phase"}
        result = validator.validate(context)
        assert result.passed is False
        assert any("missing" in err.lower() for err in result.errors)

    def test_missing_required_field(self):
        """Test validation when required field is missing."""
        validator = PhaseSpecificationValidator()
        context = {
            "phase": {
                "phase_id": "test-phase",
                # missing phase_name and phase_type
            },
            "phase_id": "test-phase",
        }
        result = validator.validate(context)
        assert result.passed is False
        assert "required fields" in result.message.lower()

    def test_invalid_phase_type(self):
        """Test validation with invalid phase type."""
        validator = PhaseSpecificationValidator()
        context = {
            "phase": {
                "phase_id": "test-phase",
                "phase_name": "Test Phase",
                "phase_type": "invalid_type",
            },
            "phase_id": "test-phase",
        }
        result = validator.validate(context)
        # Should pass but with warnings
        assert result.passed is True
        assert len(result.warnings) > 0


class TestPhaseContextValidator:
    """Tests for PhaseContextValidator gate."""

    def test_valid_context(self):
        """Test validating a valid execution context."""
        validator = PhaseContextValidator()
        context = {
            "phase": {"phase_id": "test-phase"},
            "phase_id": "test-phase",
            "attempt_index": 0,
            "escalation_level": 1,
            "allowed_paths": ["src/"],
        }
        result = validator.validate(context)
        assert result.passed is True

    def test_missing_required_context_field(self):
        """Test validation when required context field is missing."""
        validator = PhaseContextValidator()
        context = {"phase_id": "test-phase"}  # missing "phase"
        result = validator.validate(context)
        assert result.passed is False

    def test_invalid_attempt_index(self):
        """Test validation with invalid attempt index."""
        validator = PhaseContextValidator()
        context = {
            "phase": {"phase_id": "test-phase"},
            "phase_id": "test-phase",
            "attempt_index": -1,  # negative
        }
        result = validator.validate(context)
        assert result.passed is False


class TestDefaultValidatorGatePipeline:
    """Tests for the default validator gate pipeline."""

    def test_create_default_pipeline(self):
        """Test creating default validator gate pipeline."""
        pipeline = create_default_validator_gate_pipeline()
        assert len(pipeline.gates) == 2
        assert pipeline.gates[0].name == "PhaseSpecification"
        assert pipeline.gates[1].name == "PhaseContext"

    def test_default_pipeline_with_valid_context(self):
        """Test executing default pipeline with valid context."""
        pipeline = create_default_validator_gate_pipeline()
        context = {
            "phase": {
                "phase_id": "test-phase",
                "phase_name": "Test Phase",
                "phase_type": "build",
            },
            "phase_id": "test-phase",
            "attempt_index": 0,
        }
        result = pipeline.execute(context)
        assert result.can_proceed is True
        assert result.all_passed is True

    def test_default_pipeline_with_invalid_context(self):
        """Test executing default pipeline with invalid context."""
        pipeline = create_default_validator_gate_pipeline()
        context = {}  # Empty context
        result = pipeline.execute(context)
        assert result.can_proceed is False
