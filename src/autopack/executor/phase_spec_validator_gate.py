"""Phase Specification Validator Gate

Concrete implementation of ValidatorGate for validating phase specifications.
This gate ensures that phase specifications are valid before execution proceeds.

IMP-RES-005: Wire validators as pipeline gates
- Validates required phase fields
- Validates phase configuration
- Enforces phase specification contracts
"""

import logging
from typing import Any, Dict

from autopack.executor.validator_gate import GateResult, GateType, ValidatorGate

logger = logging.getLogger(__name__)

# Required fields in a phase specification
REQUIRED_PHASE_FIELDS = ["phase_id", "phase_name", "phase_type"]


class PhaseSpecificationValidator(ValidatorGate):
    """Validates phase specification structure and required fields.

    This gate ensures that all phases meet the minimum specification requirements
    before execution begins.
    """

    def __init__(self):
        """Initialize phase specification validator gate."""
        super().__init__(name="PhaseSpecification", gate_type=GateType.HARD)

    def validate(self, context: Dict[str, Any]) -> GateResult:
        """Validate phase specification.

        Args:
            context: Phase execution context containing phase specification

        Returns:
            GateResult indicating whether phase spec is valid
        """
        phase = context.get("phase")
        phase_id = context.get("phase_id", "unknown")

        result = GateResult(
            passed=True, gate_name=self.name, gate_type=self.gate_type, message="Phase specification valid"
        )

        if not phase:
            result.add_error("Phase specification is missing from context")
            result.message = "Phase specification not found"
            return result

        if not isinstance(phase, dict):
            result.add_error(f"Phase specification must be a dict, got {type(phase).__name__}")
            result.message = "Invalid phase specification type"
            return result

        # Validate required fields
        missing_fields = [field for field in REQUIRED_PHASE_FIELDS if field not in phase]
        if missing_fields:
            result.add_error(f"Phase specification missing required fields: {missing_fields}")
            result.message = f"Missing required fields: {missing_fields}"
            return result

        # Validate phase_id consistency
        spec_phase_id = phase.get("phase_id")
        if spec_phase_id != phase_id:
            logger.warning(
                f"Phase ID mismatch: context={phase_id}, spec={spec_phase_id}. "
                "Using spec phase_id for validation."
            )

        # Validate phase_type is a known type
        valid_phase_types = ["research", "plan", "build", "deploy", "monetize"]
        phase_type = phase.get("phase_type", "").lower()
        if phase_type not in valid_phase_types:
            result.add_warning(
                f"Phase type '{phase_type}' not in standard types: {valid_phase_types}. "
                "This may indicate a custom phase type."
            )

        # Validate optional scope field if present
        if "scope" in phase:
            scope = phase.get("scope")
            if not isinstance(scope, dict):
                result.add_warning(f"Scope should be a dict, got {type(scope).__name__}")

        result.message = f"Phase specification '{spec_phase_id}' is valid"
        return result


class PhaseContextValidator(ValidatorGate):
    """Validates phase execution context.

    Ensures that the execution context has all required information
    for phase execution to proceed.
    """

    def __init__(self):
        """Initialize phase context validator gate."""
        super().__init__(name="PhaseContext", gate_type=GateType.HARD)

    def validate(self, context: Dict[str, Any]) -> GateResult:
        """Validate phase execution context.

        Args:
            context: Phase execution context

        Returns:
            GateResult indicating whether context is valid
        """
        result = GateResult(
            passed=True, gate_name=self.name, gate_type=self.gate_type, message="Phase context valid"
        )

        # Check required context fields
        required_context_fields = ["phase", "phase_id"]
        missing_context = [field for field in required_context_fields if field not in context]

        if missing_context:
            result.add_error(f"Execution context missing required fields: {missing_context}")
            result.message = f"Invalid execution context"
            return result

        # Validate attempt index if present
        if "attempt_index" in context:
            attempt_index = context.get("attempt_index")
            if not isinstance(attempt_index, int) or attempt_index < 0:
                result.add_error(f"attempt_index must be non-negative integer, got {attempt_index}")

        # Validate escalation level if present
        if "escalation_level" in context:
            escalation_level = context.get("escalation_level")
            if not isinstance(escalation_level, int) or escalation_level < 0:
                result.add_warning(f"escalation_level should be non-negative integer")

        # Validate allowed_paths if present
        if "allowed_paths" in context:
            allowed_paths = context.get("allowed_paths")
            if not isinstance(allowed_paths, list):
                result.add_warning(f"allowed_paths should be a list")

        result.message = "Phase execution context is valid"
        return result
