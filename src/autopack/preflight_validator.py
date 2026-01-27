"""
Preflight Plan Validator

Validates implementation plans BEFORE execution starts.
Catches errors early with hard checks (fail-fast).

Separate from governed_apply.py which enforces at patch time.
This validator catches issues earlier in the pipeline.

Key Features:
- Path existence validation
- Governance checks (reuses governed_apply logic)
- Scope size caps
- Quality gate validation
- 0 LLM calls (deterministic)

Usage:
    validator = PreflightValidator(workspace)
    result = validator.validate_plan(plan_data)

    if not result.valid:
        print(f"Plan validation failed: {result.error}")
        for warning in result.warnings:
            print(f"Warning: {warning}")
"""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from autopack.governed_apply import GovernedApplyPath

logger = logging.getLogger(__name__)


# Validation limits
MAX_FILES_PER_PHASE = 100  # Maximum files in scope per phase
MAX_TOTAL_FILES = 500  # Maximum files across all phases
MAX_SCOPE_SIZE_MB = 50  # Maximum total file size in scope (MB)


@dataclass
class ValidationResult:
    """Result of preflight validation"""

    valid: bool
    error: Optional[str] = None
    warnings: List[str] = None
    stats: Dict = None

    def __post_init__(self):
        if self.warnings is None:
            self.warnings = []
        if self.stats is None:
            self.stats = {}


class PreflightValidator:
    """
    Validate implementation plans before execution.

    Performs hard checks that fail-fast if violated:
    1. All paths exist
    2. Paths within governance scope
    3. Scope size caps
    4. Quality gate validation
    """

    def __init__(
        self, workspace: Path, autopack_internal_mode: bool = False, run_type: str = "project_build"
    ):
        """
        Initialize validator.

        Args:
            workspace: Project workspace directory
            autopack_internal_mode: If True, allows src/autopack/ writes
            run_type: Type of run (project_build, autopack_maintenance, etc.)
        """
        self.workspace = Path(workspace)
        self.autopack_internal_mode = autopack_internal_mode
        self.run_type = run_type

    def validate_plan(self, plan: Dict) -> ValidationResult:
        """
        Validate entire implementation plan.

        Args:
            plan: Implementation plan with phases

        Returns:
            ValidationResult with valid/invalid status and details
        """

        warnings = []
        all_files_count = 0
        all_files_size = 0

        phases = plan.get("phases", [])
        if not phases:
            return ValidationResult(valid=False, error="Plan has no phases")

        # Dependency DAG validation (fail-fast)
        dep_result = self.validate_dependencies(plan)
        if not dep_result.valid:
            return ValidationResult(
                valid=False,
                error=dep_result.error,
                warnings=dep_result.warnings,
            )

        # Plan complexity warning (non-blocking)
        if len(phases) > 20:
            warnings.append(
                f"Plan has {len(phases)} phases; consider splitting into smaller runs "
                f"to reduce scope pressure and improve iteration speed."
            )

        # Validate each phase
        for i, phase in enumerate(phases):
            phase_id = phase.get("phase_id", f"phase-{i}")
            phase_result = self.validate_phase(phase, phase_id)

            if not phase_result.valid:
                return ValidationResult(
                    valid=False,
                    error=f"Phase '{phase_id}' validation failed: {phase_result.error}",
                    warnings=warnings + phase_result.warnings,
                )

            # Accumulate warnings
            warnings.extend(phase_result.warnings)

            # Accumulate stats
            all_files_count += phase_result.stats.get("file_count", 0)
            all_files_size += phase_result.stats.get("total_size_bytes", 0)

        # Global limits
        if all_files_count > MAX_TOTAL_FILES:
            return ValidationResult(
                valid=False,
                error=f"Total file count exceeds limit: {all_files_count} > {MAX_TOTAL_FILES}",
                warnings=warnings,
            )

        max_size_bytes = MAX_SCOPE_SIZE_MB * 1024 * 1024
        if all_files_size > max_size_bytes:
            size_mb = all_files_size / (1024 * 1024)
            return ValidationResult(
                valid=False,
                error=f"Total file size exceeds limit: {size_mb:.1f}MB > {MAX_SCOPE_SIZE_MB}MB",
                warnings=warnings,
            )

        return ValidationResult(
            valid=True,
            warnings=warnings,
            stats={
                "total_phases": len(phases),
                "total_files": all_files_count,
                "total_size_mb": all_files_size / (1024 * 1024),
            },
        )

    def validate_phase(self, phase: Dict, phase_id: str) -> ValidationResult:
        """
        Validate a single phase.

        Args:
            phase: Phase configuration
            phase_id: Phase identifier

        Returns:
            ValidationResult for this phase
        """

        warnings = []

        # Extract scope
        scope = phase.get("scope", {})
        scope_paths = scope.get("paths", [])
        readonly_context = scope.get("read_only_context", [])
        allowed_paths = scope.get("allowed_paths", [])  # From constraints.allowed_paths

        # Check 1: Scope not empty
        if not scope_paths:
            warnings.append(
                f"Phase '{phase_id}' has empty scope - Builder will need to request expansion"
            )

        # Check 2: Path existence
        missing_paths = []
        file_count = 0
        total_size = 0

        for path_pattern in scope_paths:
            resolved = self.workspace / path_pattern

            # Handle directory patterns (end with /)
            if path_pattern.endswith("/"):
                if not resolved.exists() or not resolved.is_dir():
                    missing_paths.append(path_pattern)
                else:
                    # Count files in directory
                    for file_path in resolved.rglob("*"):
                        if file_path.is_file():
                            file_count += 1
                            total_size += file_path.stat().st_size
            else:
                # Exact file path
                if not resolved.exists():
                    # Allow new files to be created
                    warnings.append(f"File will be created: {path_pattern}")
                else:
                    if resolved.is_file():
                        file_count += 1
                        total_size += resolved.stat().st_size

        if missing_paths and len(missing_paths) == len(scope_paths):
            # All paths missing - likely error
            return ValidationResult(
                valid=False, error=f"All scope paths not found: {', '.join(missing_paths[:3])}..."
            )

        # Check 3: Governance validation
        # Reuse governed_apply logic
        governance_result = self._check_governance(scope_paths, readonly_context, allowed_paths)
        if not governance_result.valid:
            return governance_result

        # Check 4: Scope size caps
        if file_count > MAX_FILES_PER_PHASE:
            return ValidationResult(
                valid=False,
                error=f"Scope too large: {file_count} files > {MAX_FILES_PER_PHASE} limit",
            )

        # Check 5: Quality gates (optional)
        success_criteria = phase.get("success_criteria", [])
        if not success_criteria:
            warnings.append(
                f"Phase '{phase_id}' has no success criteria - harder to validate completion"
            )

        return ValidationResult(
            valid=True,
            warnings=warnings,
            stats={
                "file_count": file_count,
                "total_size_bytes": total_size,
                "missing_paths": len(missing_paths),
            },
        )

    def _check_governance(
        self, scope_paths: List[str], readonly_context: List[str], allowed_paths: List[str] = None
    ) -> ValidationResult:
        """
        Check governance rules using governed_apply logic.

        Critical: Reuse existing governance enforcement, don't duplicate.

        Args:
            scope_paths: Paths that will be modified
            readonly_context: Paths that will be read only
            allowed_paths: Additional paths that are explicitly allowed (from constraints)
        """

        # Create temporary GovernedApplyPath to check paths
        gov = GovernedApplyPath(
            workspace=self.workspace,
            autopack_internal_mode=self.autopack_internal_mode,
            run_type=self.run_type,
            scope_paths=scope_paths,
            allowed_paths=allowed_paths or [],
        )

        protected_violations = []

        # Check each scope path
        for path in scope_paths:
            normalized = path.replace("\\", "/")

            # Check if protected
            is_protected = False
            for protected_prefix in gov.protected_paths:
                if normalized.startswith(protected_prefix.replace("\\", "/")):
                    is_protected = True
                    break

            if is_protected:
                # Check if allowed (overrides protection)
                is_allowed = False
                for allowed_prefix in gov.allowed_paths:
                    if normalized.startswith(allowed_prefix.replace("\\", "/")):
                        is_allowed = True
                        break

                if not is_allowed:
                    protected_violations.append(path)

        if protected_violations:
            return ValidationResult(
                valid=False,
                error=f"Protected paths in scope: {', '.join(protected_violations[:3])}...",
            )

        return ValidationResult(valid=True)

    def validate_success_criteria(self, phase: Dict, phase_id: str) -> ValidationResult:
        """
        Validate success criteria are well-formed.

        Success criteria should be:
        - Specific (not vague)
        - Measurable (can be validated)
        - Actionable (clear what to check)
        """

        warnings = []

        criteria = phase.get("success_criteria", [])
        if not criteria:
            warnings.append(f"No success criteria defined for phase '{phase_id}'")
            return ValidationResult(valid=True, warnings=warnings)

        for i, criterion in enumerate(criteria):
            if not criterion or not criterion.strip():
                warnings.append(f"Empty success criterion #{i + 1} in phase '{phase_id}'")
                continue

            # Check for vague criteria
            vague_words = ["should", "may", "might", "probably", "generally"]
            if any(word in criterion.lower() for word in vague_words):
                warnings.append(f"Vague success criterion in phase '{phase_id}': '{criterion}'")

        return ValidationResult(valid=True, warnings=warnings)

    def validate_validation_tests(self, phase: Dict, phase_id: str) -> ValidationResult:
        """
        Validate validation tests are executable.

        Tests should be:
        - Valid shell commands
        - Exist in the repo (for pytest tests)
        """

        warnings = []

        tests = phase.get("validation_tests", [])
        if not tests:
            warnings.append(f"No validation tests defined for phase '{phase_id}'")
            return ValidationResult(valid=True, warnings=warnings)

        for test_cmd in tests:
            if not test_cmd or not test_cmd.strip():
                warnings.append(f"Empty validation test in phase '{phase_id}'")
                continue

            # Check for pytest tests
            if "pytest" in test_cmd:
                # Extract test file path
                parts = test_cmd.split()
                for part in parts:
                    if part.endswith(".py"):
                        test_file = self.workspace / part
                        if not test_file.exists():
                            warnings.append(f"Test file not found: {part}")

        return ValidationResult(valid=True, warnings=warnings)

    def validate_dependencies(self, plan: Dict) -> ValidationResult:
        """
        Validate phase dependencies form valid DAG (no cycles).

        Args:
            plan: Full implementation plan

        Returns:
            ValidationResult with cycle detection
        """

        phases = plan.get("phases", [])
        phase_ids = {p.get("phase_id") for p in phases}

        # Build dependency graph
        graph = {}
        for phase in phases:
            phase_id = phase.get("phase_id")
            dependencies = phase.get("dependencies", [])
            graph[phase_id] = dependencies

        # Check all dependencies exist
        for phase_id, deps in graph.items():
            for dep in deps:
                if dep not in phase_ids:
                    return ValidationResult(
                        valid=False,
                        error=f"Phase '{phase_id}' depends on non-existent phase '{dep}'",
                    )

        # Detect cycles using DFS
        visited = set()
        rec_stack = set()

        def has_cycle(node):
            visited.add(node)
            rec_stack.add(node)

            for neighbor in graph.get(node, []):
                if neighbor not in visited:
                    if has_cycle(neighbor):
                        return True
                elif neighbor in rec_stack:
                    return True

            rec_stack.remove(node)
            return False

        for phase_id in graph:
            if phase_id not in visited:
                if has_cycle(phase_id):
                    return ValidationResult(
                        valid=False,
                        error=f"Circular dependency detected involving phase '{phase_id}'",
                    )

        return ValidationResult(valid=True)

    def get_execution_order(self, plan: Dict) -> Tuple[bool, List[str], Optional[str]]:
        """
        Get topologically sorted execution order.

        Args:
            plan: Full implementation plan

        Returns:
            Tuple of (success, ordered_phase_ids, error_message)
        """

        phases = plan.get("phases", [])

        # Validate dependencies first
        dep_result = self.validate_dependencies(plan)
        if not dep_result.valid:
            return False, [], dep_result.error

        # Build graph
        graph = {}
        in_degree = {}
        for phase in phases:
            phase_id = phase.get("phase_id")
            dependencies = phase.get("dependencies", [])
            graph[phase_id] = dependencies
            in_degree[phase_id] = 0

        for phase_id, deps in graph.items():
            for dep in deps:
                in_degree[phase_id] += 1

        # Topological sort (Kahn's algorithm)
        queue = [pid for pid, deg in in_degree.items() if deg == 0]
        result = []

        while queue:
            node = queue.pop(0)
            result.append(node)

            # Reduce in-degree for neighbors
            for phase_id, deps in graph.items():
                if node in deps:
                    in_degree[phase_id] -= 1
                    if in_degree[phase_id] == 0:
                        queue.append(phase_id)

        if len(result) != len(phases):
            return False, [], "Unable to determine execution order (circular dependency)"

        return True, result, None
