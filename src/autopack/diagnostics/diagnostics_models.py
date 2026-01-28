"""Shared Data Models for Diagnostics Subsystem

This module contains shared data models used across the diagnostics components
to avoid circular imports. All data classes and enums used by multiple diagnostics
modules should be defined here.

Components:
- PhaseSpec: Phase specification from requirements
- Decision: Result of goal-aware decision making
- DecisionType: Types of decisions (CLEAR_FIX, RISKY, etc.)
- RiskLevel: Risk assessment levels
- EvidenceGap: Missing evidence during investigation
- EvidenceGapType: Types of evidence gaps
- FixStrategy: Potential fix approach
- InvestigationResult: Result of multi-round investigation
- ExecutionResult: Result of decision execution
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from autopack.diagnostics.probes import ProbeCommand, ProbeRunResult

# ============================================================================
# Phase Specification
# ============================================================================


@dataclass
class PhaseSpec:
    """Phase specification from requirements.

    Attributes:
        phase_id: Unique phase identifier
        deliverables: List of files/paths to create
        acceptance_criteria: List of tests/checks to pass
        allowed_paths: Paths where changes are permitted
        protected_paths: Paths where changes require approval
        complexity: Phase complexity (simple/medium/complex)
        category: Phase category (feature/bugfix/refactor)
    """

    phase_id: str
    deliverables: List[str]
    acceptance_criteria: List[str]
    allowed_paths: List[str]
    protected_paths: List[str]
    complexity: str = "medium"
    category: str = "feature"


# ============================================================================
# Evidence Gap Analysis
# ============================================================================


class EvidenceGapType(Enum):
    """Types of evidence gaps identified during investigation."""

    MISSING_FILE_CONTENT = "missing_file_content"
    MISSING_COMMAND_OUTPUT = "missing_command_output"
    MISSING_TEST_OUTPUT = "missing_test_output"
    MISSING_ERROR_DETAILS = "missing_error_details"
    MISSING_DEPENDENCY_INFO = "missing_dependency_info"
    AMBIGUOUS_ROOT_CAUSE = "ambiguous_root_cause"


@dataclass
class EvidenceGap:
    """Missing evidence identified during investigation.

    Attributes:
        gap_type: Type of evidence gap
        description: Human-readable description
        priority: 1 (critical), 2 (high), 3 (medium)
        probe_suggestion: Suggested probe to fill gap
        rationale: Why this evidence is needed
    """

    gap_type: EvidenceGapType
    description: str
    priority: int
    probe_suggestion: Optional[ProbeCommand] = None
    rationale: Optional[str] = None


# ============================================================================
# Decision Making
# ============================================================================


class DecisionType(Enum):
    """Types of decisions the system can make."""

    CLEAR_FIX = "clear_fix"  # Low risk, goal-aligned, auto-apply
    NEED_MORE_EVIDENCE = "need_more"  # Continue investigation
    AMBIGUOUS = "ambiguous"  # Multiple valid approaches, ask human
    RISKY = "risky"  # High risk, block for approval


class RiskLevel(Enum):
    """Risk levels for decisions."""

    LOW = "LOW"  # <100 lines, within allowed_paths, no side effects
    MEDIUM = "MEDIUM"  # 100-200 lines, multiple files
    HIGH = "HIGH"  # >200 lines, protected paths, breaking changes
    UNKNOWN = "UNKNOWN"  # Cannot assess risk


@dataclass
class FixStrategy:
    """A potential fix approach.

    Attributes:
        description: Human-readable description of the fix
        files_to_modify: List of files to change
        estimated_lines_changed: Estimated lines added/removed
        touches_protected_paths: Whether protected paths are affected
        meets_deliverables: Deliverables this fix addresses
        passes_acceptance_criteria: Acceptance criteria this fix meets
        side_effects: Known side effects
        confidence: Confidence score (0.0 to 1.0)
    """

    description: str
    files_to_modify: List[str]
    estimated_lines_changed: int
    touches_protected_paths: bool
    meets_deliverables: List[str]
    passes_acceptance_criteria: List[str]
    side_effects: List[str]
    confidence: float


@dataclass
class Decision:
    """Result of goal-aware decision making.

    Attributes:
        type: Type of decision (CLEAR_FIX, RISKY, etc.)
        fix_strategy: Description of the fix approach
        rationale: Detailed explanation of the decision
        alternatives_considered: List of alternatives and why they were rejected
        risk_level: Risk assessment (LOW/MEDIUM/HIGH)
        deliverables_met: List of deliverables this fix addresses
        files_modified: List of files to be modified
        net_deletion: Net line deletion (lines removed - lines added)
        patch: Generated patch content (if applicable)
        questions_for_human: Questions to ask human (if AMBIGUOUS/RISKY)
        confidence: Confidence score (0.0 to 1.0)
    """

    type: DecisionType
    fix_strategy: str
    rationale: str
    alternatives_considered: List[str]
    risk_level: str
    deliverables_met: List[str]
    files_modified: List[str]
    net_deletion: int
    patch: Optional[str] = None
    questions_for_human: Optional[List[str]] = None
    confidence: float = 0.0


# ============================================================================
# Investigation Results
# ============================================================================


@dataclass
class InvestigationResult:
    """Result of multi-round investigation.

    Attributes:
        decision: The final decision made
        evidence: All collected evidence
        rounds: Number of investigation rounds executed
        probes_executed: List of all probe results
        timeline: Chronological audit trail
        total_time_seconds: Total investigation time
        gaps_identified: All evidence gaps identified
    """

    decision: Decision
    evidence: Dict[str, Any]
    rounds: int
    probes_executed: List[ProbeRunResult]
    timeline: List[str]
    total_time_seconds: float
    gaps_identified: List[EvidenceGap] = field(default_factory=list)


# ============================================================================
# Execution Results
# ============================================================================


@dataclass
class ExecutionResult:
    """Result of decision execution.

    Attributes:
        success: Whether execution succeeded
        decision_id: Unique decision identifier
        save_point: Git tag for rollback
        patch_applied: Whether patch was successfully applied
        deliverables_validated: Whether deliverables validation passed
        tests_passed: Whether acceptance tests passed
        rollback_performed: Whether rollback was executed
        error_message: Error message (if failed)
        commit_sha: Git commit SHA (if succeeded)
        conflict_lines: Lines that conflicted during patch application
        retry_context: Context information for retry attempts
    """

    success: bool
    decision_id: str
    save_point: Optional[str]
    patch_applied: bool
    deliverables_validated: bool
    tests_passed: bool
    rollback_performed: bool
    error_message: Optional[str] = None
    commit_sha: Optional[str] = None
    conflict_lines: Optional[List[int]] = None
    retry_context: Optional[Dict[str, Any]] = None
