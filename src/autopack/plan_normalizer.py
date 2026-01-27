"""Plan Normalizer: Unstructured Plan → Structured Plan.

Phase 1 of True Autonomy roadmap (per IMPLEMENTATION_PLAN_TRUE_AUTONOMY.md).

Converts messy/unstructured plan inputs into execution-ready structured plans:
- Normalized deliverables
- Safe scope.paths (grounded in repo reality)
- read_only_context
- At least one runnable validation step
- Conservative budgets

Key principles:
- Deterministic-first (regex/heuristics, repo scanning)
- LLM usage only if low confidence and questions are specific
- Token-capped (bounded context, minimal calls)
- Fail-fast with actionable errors (no silent fallbacks)
- Memory integration for semantic guidance
"""

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .memory.memory_service import MemoryService
from .pattern_matcher import PatternMatcher
from .preflight_validator import PreflightValidator
from .project_intention import ProjectIntentionManager
from .repo_scanner import RepoScanner

logger = logging.getLogger(__name__)

# Normalization defaults
DEFAULT_TOKEN_CAP = 420000
DEFAULT_MAX_PHASES = 10
DEFAULT_MAX_DURATION_MINUTES = 120
MIN_CONFIDENCE_FOR_AUTO_NORMALIZE = 0.7


@dataclass
class NormalizationResult:
    """Result of plan normalization."""

    success: bool
    structured_plan: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    warnings: List[str] = field(default_factory=list)
    confidence: float = 0.0
    normalization_decisions: Dict[str, Any] = field(default_factory=dict)


class PlanNormalizer:
    """Normalize unstructured plans into structured execution plans.

    Responsibilities:
    - Extract deliverables from unstructured text
    - Infer task categories
    - Ground scope in actual repo layout
    - Add runnable validation steps
    - Apply conservative budgets
    - Use project intention for semantic guidance
    """

    def __init__(
        self,
        workspace: Path,
        run_id: str,
        project_id: Optional[str] = None,
        memory_service: Optional[MemoryService] = None,
        intention_manager: Optional[ProjectIntentionManager] = None,
    ):
        """Initialize plan normalizer.

        Args:
            workspace: Project workspace directory
            run_id: Run identifier
            project_id: Project identifier (optional)
            memory_service: Memory service for semantic guidance (optional)
            intention_manager: Project intention manager (optional)
        """
        self.workspace = Path(workspace)
        self.run_id = run_id
        self.project_id = project_id or "autopack"
        self.memory = memory_service
        self.intention_manager = intention_manager

        # Initialize repo analysis tools
        self.scanner = RepoScanner(self.workspace)
        self.matcher = PatternMatcher(self.scanner)
        self.validator = PreflightValidator(self.workspace)

    def normalize(
        self,
        raw_plan: str,
        run_config: Optional[Dict[str, Any]] = None,
    ) -> NormalizationResult:
        """Normalize unstructured plan into structured plan.

        Args:
            raw_plan: Unstructured plan text
            run_config: Optional run configuration overrides

        Returns:
            NormalizationResult with structured plan or error
        """
        logger.info(f"[PlanNormalizer] Starting normalization for run_id={self.run_id}")

        # Step 1: Extract deliverables (deterministic)
        deliverables = self._extract_deliverables(raw_plan)
        if not deliverables:
            return NormalizationResult(
                success=False,
                error="No deliverables detected in plan. Please specify explicit deliverables "
                "(files, features, behaviors) to implement.",
            )

        # Step 2: Infer task category (deterministic)
        category, category_confidence = self._infer_category(raw_plan)

        # Step 3: Ground scope in repo layout (deterministic)
        scope_paths, read_only_context, scope_confidence = self._ground_scope(
            raw_plan=raw_plan,
            deliverables=deliverables,
            category=category,
        )

        # Step 4: Infer validation steps (deterministic)
        validation_steps = self._infer_validation_steps(category, scope_paths)
        if not validation_steps:
            return NormalizationResult(
                success=False,
                error="Cannot safely infer validation steps (tests/build/probe). "
                "Please specify test commands or acceptance criteria explicitly.",
            )

        # Step 5: Apply conservative budgets
        token_cap = (run_config or {}).get("token_cap", DEFAULT_TOKEN_CAP)
        max_phases = (run_config or {}).get("max_phases", DEFAULT_MAX_PHASES)
        max_duration_minutes = (run_config or {}).get(
            "max_duration_minutes",
            DEFAULT_MAX_DURATION_MINUTES,
        )

        # Step 6: Retrieve intention context if available
        intention_context = self._get_intention_context()

        # Step 7: Compute overall confidence
        overall_confidence = (category_confidence + scope_confidence) / 2.0

        # Step 8: Build structured plan
        structured_plan = {
            "run": {
                "run_id": self.run_id,
                "safety_profile": "normal",
                "run_scope": "single_tier",
                "token_cap": token_cap,
                "max_phases": max_phases,
                "max_duration_minutes": max_duration_minutes,
            },
            "tiers": [
                {
                    "tier_id": "T0",
                    "tier_index": 0,
                    "name": f"Implementation: {category}",
                    "description": f"Normalized plan for: {raw_plan[:100]}...",
                }
            ],
            "phases": [
                {
                    "phase_id": f"{self.run_id}-phase-0",
                    "phase_index": 0,
                    "tier_id": "T0",
                    "name": f"{category.replace('_', ' ').title()} Implementation",
                    "description": f"Implement: {', '.join(deliverables[:3])}",
                    "task_category": category,
                    "complexity": "medium",
                    "builder_mode": "default",
                    "scope": {
                        "paths": scope_paths,
                        "read_only_context": [
                            {"path": p, "reason": "Referenced by implementation"}
                            for p in read_only_context
                        ],
                        "acceptance_criteria": deliverables,
                        "test_cmd": validation_steps[0] if validation_steps else None,
                    },
                }
            ],
        }

        # Step 9: Validate the structured plan
        validation_result = self.validator.validate_plan(structured_plan)
        if not validation_result.valid:
            return NormalizationResult(
                success=False,
                error=f"Generated plan failed validation: {validation_result.error}",
                warnings=validation_result.warnings,
            )

        # Step 10: Store normalization decisions in memory
        self._store_normalization_decisions(
            raw_plan=raw_plan,
            deliverables=deliverables,
            category=category,
            confidence=overall_confidence,
        )

        logger.info(
            f"[PlanNormalizer] Normalization succeeded: "
            f"deliverables={len(deliverables)}, scope_files={len(scope_paths)}, "
            f"confidence={overall_confidence:.2f}"
        )

        return NormalizationResult(
            success=True,
            structured_plan=structured_plan,
            confidence=overall_confidence,
            warnings=validation_result.warnings,
            normalization_decisions={
                "deliverables": deliverables,
                "category": category,
                "scope_paths": scope_paths,
                "read_only_context": read_only_context,
                "validation_steps": validation_steps,
                "intention_used": bool(intention_context),
            },
        )

    def _extract_deliverables(self, raw_plan: str) -> List[str]:
        """Extract candidate deliverables from raw plan text.

        Uses regex and heuristics to identify deliverables (deterministic).

        Args:
            raw_plan: Unstructured plan text

        Returns:
            List of deliverable strings
        """
        deliverables = []

        # Pattern 1: Bulleted lists (-, *, •)
        bullet_pattern = r"^[\s]*[-*•]\s+(.+)$"
        for match in re.finditer(bullet_pattern, raw_plan, re.MULTILINE):
            deliverables.append(match.group(1).strip())

        # Pattern 2: Numbered lists (1., 2., etc.)
        numbered_pattern = r"^[\s]*\d+\.\s+(.+)$"
        for match in re.finditer(numbered_pattern, raw_plan, re.MULTILINE):
            deliverables.append(match.group(1).strip())

        # Pattern 3: "Implement X", "Add Y", "Create Z" imperatives
        imperative_pattern = (
            r"\b(implement|add|create|build|write|update|fix|refactor)\s+([^\n.;]+)"
        )
        for match in re.finditer(imperative_pattern, raw_plan, re.IGNORECASE):
            deliverable = match.group(2).strip()
            if len(deliverable) > 10 and len(deliverable) < 200:
                deliverables.append(deliverable)

        # Pattern 4: File references (*.py, *.js, etc.)
        file_pattern = r"\b([\w/]+\.(?:py|js|ts|tsx|jsx|java|go|rs|md|json|yaml|yml))\b"
        for match in re.finditer(file_pattern, raw_plan):
            file_ref = match.group(1)
            deliverables.append(f"File: {file_ref}")

        # Deduplicate and limit
        seen = set()
        unique_deliverables = []
        for d in deliverables:
            normalized = d.lower().strip()
            if normalized not in seen and len(normalized) > 5:
                seen.add(normalized)
                unique_deliverables.append(d)

        # Limit to top 20 deliverables to avoid prompt bloat
        return unique_deliverables[:20]

    def _infer_category(self, raw_plan: str) -> Tuple[str, float]:
        """Infer task category from raw plan text.

        Uses keyword matching to categorize the task (deterministic).

        Args:
            raw_plan: Unstructured plan text

        Returns:
            Tuple of (category, confidence)
        """
        plan_lower = raw_plan.lower()

        # Category keyword scoring
        category_scores = {}

        keywords_map = {
            "authentication": ["auth", "login", "logout", "jwt", "token", "session", "password"],
            "api_endpoint": ["api", "endpoint", "route", "rest", "fastapi", "flask"],
            "database": ["database", "db", "model", "schema", "migration", "sql", "orm"],
            "frontend": ["frontend", "ui", "react", "vue", "component", "page"],
            "testing": ["test", "pytest", "unittest", "integration test", "e2e"],
            "documentation": ["docs", "documentation", "readme", "guide"],
            "backend": ["backend", "server", "service", "worker"],
        }

        for category, keywords in keywords_map.items():
            score = sum(1 for kw in keywords if kw in plan_lower)
            if score > 0:
                category_scores[category] = score

        # Default to "backend" if no clear match
        if not category_scores:
            return "backend", 0.3

        # Return highest scoring category
        best_category = max(category_scores, key=category_scores.get)
        max_score = category_scores[best_category]
        total_keywords = len(keywords_map[best_category])
        confidence = min(1.0, max_score / max(1, total_keywords / 2))

        return best_category, confidence

    def _ground_scope(
        self,
        raw_plan: str,
        deliverables: List[str],
        category: str,
    ) -> Tuple[List[str], List[str], float]:
        """Ground scope in actual repo layout.

        Uses repo scanner and pattern matcher to find relevant files.

        Args:
            raw_plan: Unstructured plan text
            deliverables: Extracted deliverables
            category: Inferred task category

        Returns:
            Tuple of (scope_paths, read_only_context, confidence)
        """
        # Scan repo structure
        repo_structure = self.scanner.scan()

        # Use pattern matcher to find relevant files
        match_result = self.matcher.match(
            goal=raw_plan[:500],  # Limit to first 500 chars for efficiency
            phase_id=self.run_id,
        )

        # Extract scope paths from match result
        scope_paths = match_result.scope_paths[:50]  # Limit to 50 files
        read_only_context = match_result.read_only_context[:20]  # Limit to 20 files

        # If no paths found, fall back to category-based defaults
        if not scope_paths:
            scope_paths = self._get_default_scope_for_category(category, repo_structure)

        # Confidence based on match quality
        confidence = match_result.confidence if match_result.confidence > 0 else 0.5

        return scope_paths, read_only_context, confidence

    def _get_default_scope_for_category(
        self,
        category: str,
        repo_structure: Dict[str, Any],
    ) -> List[str]:
        """Get default scope paths for a category when pattern matching fails.

        Args:
            category: Task category
            repo_structure: Repository structure from scanner

        Returns:
            List of default scope paths
        """
        all_files = repo_structure.get("all_files", [])

        # Filter by category
        if category == "frontend":
            return [f for f in all_files if f.endswith((".tsx", ".jsx", ".ts", ".js", ".css"))][:20]
        elif category == "testing":
            return [f for f in all_files if "test" in f.lower() and f.endswith(".py")][:20]
        elif category == "documentation":
            return [f for f in all_files if f.endswith((".md", ".rst", ".txt"))][:20]
        else:
            # Default to Python files for backend/api/database
            return [f for f in all_files if f.endswith(".py") and not f.startswith("tests/")][:20]

    def _infer_validation_steps(
        self,
        category: str,
        scope_paths: List[str],
    ) -> List[str]:
        """Infer runnable validation steps using toolchain detection.

        Args:
            category: Task category
            scope_paths: Scope file paths

        Returns:
            List of validation commands
        """
        from .toolchain.adapter import detect_toolchains

        validation_steps = []

        # Use toolchain detection to get appropriate test commands
        detected_toolchains = detect_toolchains(self.workspace)

        if detected_toolchains:
            # Use primary (highest confidence) toolchain
            primary = detected_toolchains[0]

            # Get adapter instance
            from .toolchain import (
                GoAdapter,
                JavaAdapter,
                NodeAdapter,
                PythonAdapter,
                RustAdapter,
            )

            adapter_map = {
                "python": PythonAdapter(),
                "node": NodeAdapter(),
                "go": GoAdapter(),
                "rust": RustAdapter(),
                "java": JavaAdapter(),
            }

            adapter = adapter_map.get(primary.name)
            if adapter:
                # Get test commands
                test_cmds = adapter.test_cmds(self.workspace)
                validation_steps.extend(test_cmds)

                # If no test commands, fall back to smoke checks
                if not validation_steps:
                    smoke_cmds = adapter.smoke_checks(self.workspace)
                    validation_steps.extend(smoke_cmds)

        # Legacy fallback for backward compatibility
        if not validation_steps:
            # Check for pytest (Python)
            if any(p.endswith(".py") for p in scope_paths):
                if (self.workspace / "pytest.ini").exists() or (self.workspace / "tests").exists():
                    validation_steps.append("pytest -q tests/")

            # Check for npm test (Node/JS)
            if any(p.endswith((".ts", ".tsx", ".js", ".jsx")) for p in scope_paths):
                if (self.workspace / "package.json").exists():
                    validation_steps.append("npm test")

            # Check for cargo test (Rust)
            if any(p.endswith(".rs") for p in scope_paths):
                if (self.workspace / "Cargo.toml").exists():
                    validation_steps.append("cargo test")

            # Check for go test (Go)
            if any(p.endswith(".go") for p in scope_paths):
                if (self.workspace / "go.mod").exists():
                    validation_steps.append("go test ./...")

        # Fallback: at least check that files are syntactically valid
        if not validation_steps:
            if any(p.endswith(".py") for p in scope_paths):
                validation_steps.append("python -m py_compile $(find . -name '*.py')")

        return validation_steps

    def _get_intention_context(self) -> Optional[str]:
        """Get project intention context for semantic guidance.

        Returns:
            Intention context string if available, None otherwise
        """
        if not self.intention_manager:
            return None

        try:
            context = self.intention_manager.get_intention_context(max_chars=1024)
            if context:
                logger.debug(f"[PlanNormalizer] Retrieved intention context: {len(context)} chars")
            return context
        except Exception as exc:
            logger.warning(f"[PlanNormalizer] Failed to retrieve intention: {exc}")
            return None

    def _store_normalization_decisions(
        self,
        raw_plan: str,
        deliverables: List[str],
        category: str,
        confidence: float,
    ) -> None:
        """Store normalization decisions in memory for later retrieval.

        Args:
            raw_plan: Original unstructured plan
            deliverables: Extracted deliverables
            category: Inferred category
            confidence: Overall confidence score
        """
        if not self.memory or not self.memory.enabled:
            logger.debug("[PlanNormalizer] Memory disabled; skipping decision storage")
            return

        try:
            summary = (
                f"Normalized plan into {len(deliverables)} deliverables. "
                f"Category: {category}. Confidence: {confidence:.2f}."
            )
            rationale = (
                f"Extracted deliverables via deterministic parsing. "
                f"Inferred category '{category}' from keyword analysis. "
                f"Grounded scope in repo structure via pattern matching."
            )

            self.memory.write_plan_change(
                summary=summary,
                rationale=rationale,
                project_id=self.project_id,
                run_id=self.run_id,
                phase_id=None,
                author="PlanNormalizer",
                status="active",
            )

            logger.debug("[PlanNormalizer] Stored normalization decisions in memory")
        except Exception as exc:
            logger.warning(f"[PlanNormalizer] Failed to store decisions: {exc}")


def normalize_plan(
    workspace: Path,
    run_id: str,
    raw_plan: str,
    project_id: Optional[str] = None,
    memory_service: Optional[MemoryService] = None,
    intention_manager: Optional[ProjectIntentionManager] = None,
    run_config: Optional[Dict[str, Any]] = None,
) -> NormalizationResult:
    """Convenience function: normalize unstructured plan.

    Args:
        workspace: Project workspace directory
        run_id: Run identifier
        raw_plan: Unstructured plan text
        project_id: Optional project identifier
        memory_service: Optional memory service
        intention_manager: Optional intention manager
        run_config: Optional run configuration overrides

    Returns:
        NormalizationResult
    """
    normalizer = PlanNormalizer(
        workspace=workspace,
        run_id=run_id,
        project_id=project_id,
        memory_service=memory_service,
        intention_manager=intention_manager,
    )

    return normalizer.normalize(raw_plan=raw_plan, run_config=run_config)
