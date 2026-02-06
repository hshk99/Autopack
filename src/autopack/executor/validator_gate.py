"""Validator Gate Wiring Module

Wires validators into the execution pipeline as gates to enforce validation checks
before phase execution. This module provides the infrastructure for treating validators
as blocking gates in the pipeline, following the pattern established by parallelism_gate.py.

IMP-RES-005: Wire validators as pipeline gates
- Validators enforce constraints before phase execution
- Gates can be soft (warnings only) or hard (blocking)
- Extensible architecture for adding new validators
"""

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any, Dict, List, Optional

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    pass


class GateType(Enum):
    """Gate enforcement type."""

    HARD = "hard"
    SOFT = "soft"


@dataclass
class GateResult:
    """Result of gate validation check."""

    passed: bool
    gate_name: str
    gate_type: GateType
    message: str = ""
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def add_error(self, error: str) -> None:
        """Add an error to the gate result."""
        self.errors.append(error)
        self.passed = False

    def add_warning(self, warning: str) -> None:
        """Add a warning to the gate result."""
        self.warnings.append(warning)

    def is_blocking(self) -> bool:
        """Check if this gate result is blocking."""
        return self.gate_type == GateType.HARD and not self.passed


class ValidatorGate:
    """Base class for validator gates."""

    def __init__(self, name: str, gate_type: GateType = GateType.HARD):
        """Initialize validator gate."""
        self.name = name
        self.gate_type = gate_type

    def validate(self, context: Dict[str, Any]) -> GateResult:
        """Validate the given context."""
        raise NotImplementedError("Subclasses must implement validate()")


class ValidatorGatePipeline:
    """Pipeline of validator gates for phase execution."""

    def __init__(self):
        """Initialize validator gate pipeline."""
        self.gates: List[ValidatorGate] = []
        self._results: List[GateResult] = []

    def register_gate(self, gate: ValidatorGate) -> None:
        """Register a validator gate in the pipeline."""
        if not isinstance(gate, ValidatorGate):
            raise TypeError(f"Expected ValidatorGate, got {type(gate).__name__}")
        self.gates.append(gate)
        logger.debug(f"Registered validator gate: {gate.name}")

    def execute(self, context: Dict[str, Any]) -> "GateExecutionResult":
        """Execute all registered validator gates."""
        self._results = []
        blocking_failures = []

        logger.info(f"[ValidatorGatePipeline] Executing {len(self.gates)} validator gates")

        for gate in self.gates:
            logger.debug(f"[ValidatorGatePipeline] Executing gate: {gate.name}")

            try:
                result = gate.validate(context)
                self._results.append(result)

                if result.passed:
                    logger.info(
                        f"[ValidatorGatePipeline] Gate '{gate.name}' PASSED ({result.gate_type.value})"
                    )
                else:
                    if result.is_blocking():
                        logger.error(
                            f"[ValidatorGatePipeline] Gate '{gate.name}' FAILED (blocking). "
                            f"Errors: {result.errors}"
                        )
                        blocking_failures.append(result)
                    else:
                        logger.warning(
                            f"[ValidatorGatePipeline] Gate '{gate.name}' FAILED (soft). "
                            f"Warnings: {result.warnings}"
                        )

                if result.warnings:
                    for warning in result.warnings:
                        logger.warning(f"[{gate.name}] {warning}")

            except Exception as e:
                logger.exception(f"[ValidatorGatePipeline] Exception in gate '{gate.name}': {e}")
                error_result = GateResult(
                    passed=False,
                    gate_name=gate.name,
                    gate_type=GateType.HARD,
                    message=f"Gate execution failed with exception: {str(e)}",
                    errors=[str(e)],
                )
                self._results.append(error_result)
                blocking_failures.append(error_result)

        can_proceed = len(blocking_failures) == 0
        all_passed = all(result.passed for result in self._results)

        return GateExecutionResult(
            can_proceed=can_proceed,
            all_passed=all_passed,
            total_gates=len(self.gates),
            passed_gates=sum(1 for r in self._results if r.passed),
            failed_gates=sum(1 for r in self._results if not r.passed),
            blocking_failures=blocking_failures,
            results=self._results,
        )

    def get_results(self) -> List[GateResult]:
        """Get results from the last execution."""
        return self._results


@dataclass
class GateExecutionResult:
    """Result of executing the entire validator gate pipeline."""

    can_proceed: bool
    all_passed: bool
    total_gates: int
    passed_gates: int
    failed_gates: int
    blocking_failures: List[GateResult]
    results: List[GateResult]

    def get_summary(self) -> str:
        """Get a summary of gate execution results."""
        status = "PASS" if self.all_passed else "FAIL"
        return (
            f"Gate Pipeline {status}: {self.passed_gates}/{self.total_gates} gates passed. "
            f"Execution {'CAN' if self.can_proceed else 'CANNOT'} proceed."
        )

    def get_blocking_failure_messages(self) -> List[str]:
        """Get error messages from all blocking gate failures."""
        messages = []
        for result in self.blocking_failures:
            messages.append(f"[{result.gate_name}] {result.message}")
            messages.extend(result.errors)
        return messages


def create_default_validator_gate_pipeline() -> ValidatorGatePipeline:
    """Create a default validator gate pipeline with standard gates."""
    from autopack.executor.phase_spec_validator_gate import (
        PhaseContextValidator,
        PhaseSpecificationValidator,
    )

    pipeline = ValidatorGatePipeline()

    # Register standard validator gates
    pipeline.register_gate(PhaseSpecificationValidator())
    pipeline.register_gate(PhaseContextValidator())

    return pipeline
