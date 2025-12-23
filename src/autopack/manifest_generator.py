"""
Manifest Generator - Deterministic Scope Generation

Main entry point for BUILD-123v2 Manifest Generator.
Orchestrates repo scanning, pattern matching, and scope generation.

Replaces BUILD-123v1 LLM-based plan analyzer with deterministic approach.

Key Features:
- 0 LLM calls for common patterns (>80% cases)
- Repo-grounded (scans actual file structure)
- Earned confidence scoring
- Preflight validation
- Adaptive scope expansion
- Reuses existing primitives (scope.paths)

Architecture:
    Minimal Plan → RepoScanner → PatternMatcher → PreflightValidator
        → scope.paths → ContextSelector → governed_apply

Usage:
    generator = ManifestGenerator(workspace)

    # Enhance minimal plan with scope
    enhanced_plan = generator.generate_manifest(
        plan_data={
            "run_id": "my-feature",
            "phases": [
                {
                    "phase_id": "auth-backend",
                    "goal": "Add JWT authentication"
                }
            ]
        }
    )

    # enhanced_plan now has:
    # - scope.paths (explicit file list)
    # - read_only_context
    # - validation_tests
    # - success_criteria
"""

import asyncio
import concurrent.futures
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple

from autopack.repo_scanner import RepoScanner
from autopack.pattern_matcher import PatternMatcher, MatchResult
from autopack.preflight_validator import PreflightValidator, ValidationResult


logger = logging.getLogger(__name__)

# BUILD-124 Phase D:
# Integration tests patch `autopack.manifest_generator.PlanAnalyzer`. Keep a
# module-level symbol so patching works even though the real import is lazy.
PlanAnalyzer = None  # set lazily in _get_or_create_plan_analyzer()


def run_async_safe(coro):
    """
    Safely run an async coroutine from sync context.

    Handles the case where an event loop may already be running
    (e.g., inside an async application like FastAPI).

    BUILD-124: Used for optional PlanAnalyzer integration.
    """
    try:
        # Try to get running loop
        loop = asyncio.get_running_loop()
        # Loop exists - run in a thread to avoid RuntimeError
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(lambda: asyncio.run(coro))
            return future.result()
    except RuntimeError:
        # No running loop - safe to use asyncio.run()
        return asyncio.run(coro)


@dataclass
class PlanAnalysisMetadata:
    """Metadata for optional PlanAnalyzer integration (BUILD-124)"""
    enabled: bool
    status: str  # "disabled" | "skipped" | "ran" | "failed"
    warnings: List[str]
    error: Optional[str] = None


@dataclass
class ManifestGenerationResult:
    """Result of manifest generation"""
    success: bool
    enhanced_plan: Dict
    confidence_scores: Dict[str, float]
    warnings: List[str]
    error: Optional[str] = None
    plan_analysis: Optional[PlanAnalysisMetadata] = None


class ManifestGenerator:
    """
    Generate deterministic scope manifests for implementation plans.

    This is the main entry point for BUILD-123v2.
    Orchestrates all components to enhance minimal plans with scope.
    """

    # Minimum confidence threshold for deterministic scope
    # Lowered to 0.15 to allow template-only matches (no anchors)
    MIN_CONFIDENCE_THRESHOLD = 0.15

    def __init__(
        self,
        workspace: Path,
        autopack_internal_mode: bool = False,
        run_type: str = "project_build",
        enable_plan_analyzer: bool = False
    ):
        """
        Initialize manifest generator.

        Args:
            workspace: Project workspace directory
            autopack_internal_mode: If True, allows src/autopack/ writes
            run_type: Type of run (project_build, autopack_maintenance, etc.)
            enable_plan_analyzer: If True, run LLM-based feasibility analysis on low-confidence phases (BUILD-124)
        """
        self.workspace = Path(workspace)
        self.autopack_internal_mode = autopack_internal_mode
        self.run_type = run_type
        self.enable_plan_analyzer = enable_plan_analyzer

        # Initialize components
        self.scanner = RepoScanner(workspace)
        self.matcher = PatternMatcher(
            self.scanner,
            autopack_internal_mode=autopack_internal_mode,
            run_type=run_type,
        )
        self.validator = PreflightValidator(
            workspace,
            autopack_internal_mode=autopack_internal_mode,
            run_type=run_type
        )

        # PlanAnalyzer initialized lazily only if enabled (BUILD-124)
        self._plan_analyzer = None
        self._context_builder = None  # Phase C lazy init (BUILD-124)

    def generate_manifest(
        self,
        plan_data: Dict,
        skip_validation: bool = False
    ) -> ManifestGenerationResult:
        """
        Generate scope manifest for implementation plan.

        Args:
            plan_data: Minimal implementation plan
            skip_validation: If True, skip preflight validation

        Returns:
            ManifestGenerationResult with enhanced plan
        """

        logger.info(f"Generating manifest for run: {plan_data.get('run_id')}")

        warnings = []
        confidence_scores = {}

        # Scan repo structure (cached)
        try:
            self.scanner.scan(use_cache=True)
            logger.info("Repo structure scanned successfully")
        except Exception as e:
            logger.error(f"Failed to scan repo structure: {e}")
            # BUILD-124: Include plan_analysis even on failure
            plan_analysis_metadata = PlanAnalysisMetadata(
                enabled=self.enable_plan_analyzer,
                status="disabled" if not self.enable_plan_analyzer else "skipped",
                warnings=[]
            )
            return ManifestGenerationResult(
                success=False,
                enhanced_plan=plan_data,
                confidence_scores={},
                warnings=[],
                error=f"Repo scan failed: {e}",
                plan_analysis=plan_analysis_metadata
            )

        # Enhance each phase
        enhanced_phases = []
        for phase in plan_data.get("phases", []):
            phase_id = phase.get("phase_id", "unknown")

            # Generate scope for phase
            enhanced_phase, phase_confidence, phase_warnings = self._enhance_phase(phase)

            enhanced_phases.append(enhanced_phase)
            confidence_scores[phase_id] = phase_confidence
            warnings.extend(phase_warnings)

        # Build enhanced plan
        enhanced_plan = {
            **plan_data,
            "phases": enhanced_phases
        }

        # BUILD-124 Phase D: Optional PlanAnalyzer integration
        plan_analysis_warnings = []
        if self.enable_plan_analyzer:
            plan_analysis_warnings = self._run_plan_analyzer_on_phases(
                enhanced_phases,
                confidence_scores
            )
            warnings.extend(plan_analysis_warnings)


        # Preflight validation
        if not skip_validation:
            validation_result = self.validator.validate_plan(enhanced_plan)

            if not validation_result.valid:
                logger.error(f"Plan validation failed: {validation_result.error}")
                # BUILD-124: Include plan_analysis even on failure
                plan_analysis_metadata = PlanAnalysisMetadata(
                    enabled=self.enable_plan_analyzer,
                    status="disabled" if not self.enable_plan_analyzer else "skipped",
                    warnings=[]
                )
                return ManifestGenerationResult(
                    success=False,
                    enhanced_plan=enhanced_plan,
                    confidence_scores=confidence_scores,
                    warnings=warnings + validation_result.warnings,
                    error=validation_result.error,
                    plan_analysis=plan_analysis_metadata
                )

            warnings.extend(validation_result.warnings)

        # BUILD-124: Optional PlanAnalyzer integration (disabled by default)
        if not self.enable_plan_analyzer:
            plan_analysis_status = "disabled"
            plan_analysis_error = None
        else:
            # Derive overall status from per-phase plan_analysis metadata
            per_phase_statuses = [
                p.get("metadata", {}).get("plan_analysis", {}).get("status")
                for p in enhanced_phases
                if p.get("metadata", {}).get("plan_analysis") is not None
            ]
            any_failed = any(s == "failed" for s in per_phase_statuses)
            any_ran = any(s == "ran" for s in per_phase_statuses)

            plan_analysis_status = "failed" if any_failed else ("ran" if any_ran else "skipped")

            # Surface first error (tests accept "timeout" or "error" substrings)
            plan_analysis_error = None
            if any_failed:
                for p in enhanced_phases:
                    err = p.get("metadata", {}).get("plan_analysis", {}).get("error")
                    if err:
                        plan_analysis_error = str(err)
                        break
                if not plan_analysis_error:
                    plan_analysis_error = "LLM timeout or error"

        plan_analysis_metadata = PlanAnalysisMetadata(
            enabled=self.enable_plan_analyzer,
            status=plan_analysis_status,
            warnings=list(plan_analysis_warnings),
            error=plan_analysis_error,
        )

        return ManifestGenerationResult(
            success=True,
            enhanced_plan=enhanced_plan,
            confidence_scores=confidence_scores,
            warnings=warnings,
            plan_analysis=plan_analysis_metadata
        )

    def _infer_category_from_deliverables(
        self,
        deliverables: List[str]
    ) -> Tuple[str, float]:
        """Infer task category from deliverable file paths.

        BUILD-128: Prevent manifest category mismatches by inferring from deliverables.

        Args:
            deliverables: List of file paths to create/modify

        Returns:
            Tuple of (category, confidence)

        Examples:
            ["src/autopack/phase_finalizer.py"] → ("backend", 1.0)
            ["src/frontend/components/Button.tsx"] → ("frontend", 1.0)
            ["tests/test_feature.py"] → ("tests", 1.0)
        """
        if not deliverables:
            return "unknown", 0.0

        # Category detection rules
        category_patterns = {
            "backend": [
                r"^src/autopack/.*\.py$",
                r"^src/.*(?<!test_)\.py$",  # Python files not in tests
            ],
            "frontend": [
                r"^src/frontend/.*\.(tsx?|jsx?)$",
                r"^.*\.(html|css|scss)$",
            ],
            "tests": [
                r"^tests/.*\.py$",
                r"^.*test_.*\.py$",
            ],
            "database": [
                r"^alembic/versions/.*\.py$",
                r"^.*migrations?/.*\.py$",
            ],
            "api_endpoint": [
                r"^.*routes?/.*\.py$",
                r"^.*api/.*\.py$",
            ],
            "documentation": [
                r"^docs/.*\.md$",
                r"^README.*\.md$",
            ],
        }

        # Count matches per category
        category_scores = {}
        for deliverable in deliverables:
            # Extract path from deliverable (handle "path with description" format)
            # E.g., "src/autopack/test.py with TestClass" → "src/autopack/test.py"
            path = deliverable.split(" with ")[0].split(" (")[0].strip()

            for category, patterns in category_patterns.items():
                for pattern in patterns:
                    if re.match(pattern, path):
                        category_scores[category] = category_scores.get(category, 0) + 1
                        break

        if not category_scores:
            return "unknown", 0.0

        # Pick category with most matches
        top_category = max(category_scores.items(), key=lambda x: x[1])
        category, match_count = top_category

        # Confidence based on match ratio
        confidence = min(1.0, match_count / len(deliverables))

        return category, confidence

    def _expand_scope_from_deliverables(
        self,
        deliverables: List[str],
        category: str,
        phase_id: str
    ) -> Tuple[List[str], List[str]]:
        """Expand scope from deliverables to include related files.

        BUILD-128: Add context files relevant to deliverables category.

        Args:
            deliverables: List of files to create/modify
            category: Inferred category
            phase_id: Phase identifier

        Returns:
            Tuple of (scope_paths, read_only_context)
        """
        # Extract paths from deliverables (handle "path with description" format)
        scope_paths = []
        for d in deliverables:
            path = d.split(" with ")[0].split(" (")[0].strip()
            scope_paths.append(path)

        read_only_context = []

        # Add category-specific related files
        if category == "backend":
            # Add models.py if creating new backend modules
            if any("src/autopack/" in p for p in scope_paths):
                models_path = "src/autopack/models.py"
                if self.scanner.path_exists(models_path):
                    read_only_context.append(models_path)

            # Add database.py for database-related work
            if "database" in phase_id.lower() or any("models" in d for d in deliverables):
                db_path = "src/autopack/database.py"
                if self.scanner.path_exists(db_path):
                    read_only_context.append(db_path)

        elif category == "tests":
            # Add conftest.py for test configuration
            conftest_candidates = ["tests/conftest.py", "conftest.py"]
            for path in conftest_candidates:
                if self.scanner.path_exists(path):
                    read_only_context.append(path)

        elif category == "database":
            # Add models and alembic config
            candidates = [
                "src/autopack/models.py",
                "alembic.ini",
                "alembic/env.py"
            ]
            read_only_context.extend([p for p in candidates if self.scanner.path_exists(p)])

        # Remove duplicates, preserve order
        scope_paths = list(dict.fromkeys(scope_paths))
        read_only_context = list(dict.fromkeys(read_only_context))

        return scope_paths, read_only_context

    def _add_token_estimate_metadata(
        self,
        phase: Dict,
        deliverables: List[str],
        category: str
    ) -> None:
        """
        Add token estimation metadata to phase (BUILD-129 Phase 1 integration).

        Optional optimization: Pre-compute token estimates during manifest generation
        so executor can reuse instead of recalculating.

        Args:
            phase: Phase dict to enhance (modified in-place)
            deliverables: List of deliverable paths
            category: Phase category (backend, frontend, tests, etc.)
        """
        from datetime import datetime, timezone
        from autopack.token_estimator import TokenEstimator

        try:
            estimator = TokenEstimator()

            complexity = phase.get("complexity", "medium")
            scope_cfg = phase.get("scope") or {}
            scope_paths = scope_cfg.get("paths", []) if isinstance(scope_cfg, dict) else []
            scope_paths = [p for p in scope_paths if isinstance(p, str)]

            # Estimate output tokens based on deliverables.
            # Note: execution-time estimation may refine this using workspace-aware file complexity.
            estimate = estimator.estimate(
                deliverables=deliverables,
                category=category or "implementation",
                complexity=complexity,
                scope_paths=scope_paths,
            )

            # Add to phase metadata for executors/telemetry to reuse.
            phase["_estimated_output_tokens"] = estimate.estimated_tokens
            phase.setdefault("metadata", {})["token_prediction"] = {
                "predicted_output_tokens": estimate.estimated_tokens,
                "deliverable_count": estimate.deliverable_count,
                "confidence": estimate.confidence,
                "category": category or "implementation",
                "complexity": complexity,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "source": "manifest_generator",
            }

            logger.info(
                f"[BUILD-129] Added token estimate to phase: {estimate.estimated_tokens} output tokens "
                f"({len(deliverables)} deliverables, confidence={estimate.confidence:.2f})"
            )
        except Exception as e:
            # Non-critical - log and continue
            logger.warning(f"[BUILD-129] Token estimation failed: {e}")

    def _enhance_phase(
        self,
        phase: Dict
    ) -> tuple[Dict, float, List[str]]:
        """
        Enhance single phase with scope.

        Args:
            phase: Phase configuration

        Returns:
            Tuple of (enhanced_phase, confidence, warnings)
        """

        phase_id = phase.get("phase_id", "unknown")
        goal = phase.get("goal", "")
        description = phase.get("description", "")

        warnings = []

        # Check if scope already provided
        # Some runs may serialize scope as null; treat that as empty scope.
        existing_scope = phase.get("scope") or {}
        if existing_scope.get("paths"):
            logger.info(f"Phase '{phase_id}' already has scope.paths - skipping generation")
            return phase, 1.0, []

        # BUILD-128: Check deliverables and infer scope (prevents category mismatches)
        existing_deliverables = existing_scope.get("deliverables", [])
        if existing_deliverables:
            logger.info(f"[BUILD-128] Phase '{phase_id}' has deliverables - inferring scope from deliverables")

            # Infer category from deliverables
            category, category_confidence = self._infer_category_from_deliverables(existing_deliverables)
            logger.info(f"[BUILD-128] Inferred category '{category}' from deliverables (confidence={category_confidence:.1%})")

            # Expand scope from deliverables
            scope_paths, read_only_context = self._expand_scope_from_deliverables(
                deliverables=existing_deliverables,
                category=category,
                phase_id=phase_id
            )

            # Build enhanced phase with inferred scope
            # Preserve allowed_paths and protected_paths from existing_scope
            enhanced_phase = {
                **phase,
                # Keep a top-level deliverables list for downstream consumers (builder/token estimator).
                "deliverables": existing_deliverables,
                "scope": {
                    "paths": scope_paths,
                    "deliverables": existing_deliverables,  # Preserve original
                    "read_only_context": read_only_context,
                    "allowed_paths": existing_scope.get("allowed_paths", []),  # BUILD-128: Preserve from constraints
                    "protected_paths": existing_scope.get("protected_paths", [])  # BUILD-128: Preserve from constraints
                },
                "metadata": {
                    "category": category,
                    "confidence": category_confidence,
                    "inferred_from": "deliverables",
                    "deliverables_count": len(existing_deliverables)
                }
            }

            logger.info(f"[BUILD-128] Generated scope: {len(scope_paths)} paths, {len(read_only_context)} context files")

            # BUILD-129 Phase 1: Optional token estimation during manifest generation
            self._add_token_estimate_metadata(enhanced_phase, existing_deliverables, category)

            return enhanced_phase, category_confidence, []

        # Match goal to category and generate scope (existing behavior)
        try:
            match_result = self.matcher.match(
                goal=goal,
                phase_id=phase_id,
                description=description
            )
        except Exception as e:
            logger.error(f"Pattern matching failed for phase '{phase_id}': {e}")
            warnings.append(f"Pattern matching failed: {e}")
            match_result = MatchResult(
                category="unknown",
                confidence=0.0,
                scope_paths=[],
                read_only_context=[],
                confidence_breakdown={},
                anchor_files_found=[],
                match_density=0.0,
                directory_locality=0.0
            )

        # Check confidence threshold
        if match_result.confidence < self.MIN_CONFIDENCE_THRESHOLD:
            warnings.append(
                f"Phase '{phase_id}' has low confidence ({match_result.confidence:.1%}) - "
                f"may require LLM fallback or manual scope definition"
            )

        # Build enhanced phase
        enhanced_phase = {
            **phase,
            "scope": {
                "paths": match_result.scope_paths,
                "read_only_context": match_result.read_only_context
            },
            "metadata": {
                "category": match_result.category,
                "confidence": match_result.confidence,
                "confidence_breakdown": match_result.confidence_breakdown,
                "anchor_files_found": match_result.anchor_files_found
            }
        }

        # Add default success criteria if not present
        if not phase.get("success_criteria"):
            enhanced_phase["success_criteria"] = self._generate_default_success_criteria(
                category=match_result.category,
                goal=goal
            )

        # Add default validation tests if not present
        if not phase.get("validation_tests"):
            test_scope = self.matcher.get_test_scope(match_result.category)
            if test_scope:
                enhanced_phase["validation_tests"] = [
                    f"pytest {test_file} -v"
                    for test_file in test_scope[:3]  # Limit to 3 test files
                ]

        # Store match_result in phase metadata for PlanAnalyzer (BUILD-124)
        enhanced_phase["metadata"]["_match_result"] = match_result

        # BUILD-129 Phase 1: Optional token estimation during manifest generation
        deliverables = existing_scope.get("deliverables", [])
        if deliverables:
            self._add_token_estimate_metadata(enhanced_phase, deliverables, match_result.category)

        return enhanced_phase, match_result.confidence, warnings

    def _generate_default_success_criteria(
        self,
        category: str,
        goal: str
    ) -> List[str]:
        """
        Generate default success criteria based on category.

        Returns basic validation criteria that should always apply.
        """

        criteria = [
            "All syntax errors resolved",
            "No breaking changes to existing functionality"
        ]

        # Category-specific criteria
        if category == "authentication":
            criteria.extend([
                "Authentication endpoints return valid responses",
                "Token validation works correctly"
            ])
        elif category == "api_endpoint":
            criteria.extend([
                "API endpoints return expected status codes",
                "Request/response schema validation passes"
            ])
        elif category == "database":
            criteria.extend([
                "Database migrations apply successfully",
                "No data loss or corruption"
            ])
        elif category == "tests":
            criteria.extend([
                "All new tests pass",
                "Test coverage meets minimum threshold"
            ])

        # Goal-specific criteria
        goal_lower = goal.lower()
        if "test" in goal_lower:
            criteria.append("All tests pass")
        if "fix" in goal_lower or "bug" in goal_lower:
            criteria.append("Bug no longer reproduces")

        return criteria

    def get_scope_statistics(self, plan_data: Dict) -> Dict:
        """
        Get statistics about generated scope.

        Returns:
            {
                "total_files": int,
                "total_directories": int,
                "categories": Dict[str, int],
                "confidence_avg": float
            }
        """

        total_files = 0
        total_directories = 0
        categories = {}
        confidences = []

        for phase in plan_data.get("phases", []):
            scope = phase.get("scope", {})
            scope_paths = scope.get("paths", [])

            for path in scope_paths:
                if path.endswith("/"):
                    total_directories += 1
                else:
                    total_files += 1

            # Category stats
            metadata = phase.get("metadata", {})
            category = metadata.get("category", "unknown")
            categories[category] = categories.get(category, 0) + 1

            # Confidence
            confidence = metadata.get("confidence", 0.0)
            if confidence > 0:
                confidences.append(confidence)

        return {
            "total_files": total_files,
            "total_directories": total_directories,
            "categories": categories,
            "confidence_avg": sum(confidences) / len(confidences) if confidences else 0.0
        }

    def validate_scope_expansion_safe(
        self,
        current_scope: List[str],
        proposed_expansion: List[str]
    ) -> tuple[bool, Optional[str]]:
        """
        Check if scope expansion is safe.

        Args:
            current_scope: Current scope paths
            proposed_expansion: Proposed expanded scope

        Returns:
            Tuple of (is_safe, error_message)
        """

        added_paths = set(proposed_expansion) - set(current_scope)

        # Check governance
        gov_result = self.validator._check_governance(
            scope_paths=list(added_paths),
            readonly_context=[]
        )

        if not gov_result.valid:
            return False, gov_result.error

        # Check size limits
        from autopack.preflight_validator import MAX_FILES_PER_PHASE

        if len(proposed_expansion) > MAX_FILES_PER_PHASE:
            return False, f"Expanded scope too large: {len(proposed_expansion)} > {MAX_FILES_PER_PHASE}"

        return True, None

    # BUILD-124 Phase D: PlanAnalyzer Integration Methods

    MAX_PHASES_TO_ANALYZE = 3  # Cost control limit

    def _get_or_create_plan_analyzer(self):
        """Lazy initialization of PlanAnalyzer (only when needed)"""
        if self._plan_analyzer is None:
            # Use module-level symbol so tests can patch `autopack.manifest_generator.PlanAnalyzer`.
            global PlanAnalyzer
            if PlanAnalyzer is None:
                # Lazy import (only when actually needed)
                from autopack.plan_analyzer import PlanAnalyzer as ImportedPlanAnalyzer
                PlanAnalyzer = ImportedPlanAnalyzer

            self._plan_analyzer = PlanAnalyzer(
                repo_scanner=self.scanner,
                pattern_matcher=self.matcher,
                workspace=self.workspace,
            )
        return self._plan_analyzer

    def _get_or_create_context_builder(self):
        """Lazy initialization of GroundedContextBuilder"""
        if self._context_builder is None:
            from autopack.plan_analyzer_grounding import GroundedContextBuilder
            self._context_builder = GroundedContextBuilder(
                repo_scanner=self.scanner,
                pattern_matcher=self.matcher,
                max_chars=4000
            )
        return self._context_builder

    def _should_trigger_plan_analyzer(
        self,
        confidence: float,
        scope: List[str],
        category: str
    ) -> bool:
        """
        Determine if PlanAnalyzer should run for this phase.

        Trigger logic (per Phase D guidance):
        - High confidence (>= 0.70): Skip (deterministic is working well)
        - Low confidence (< 0.15) + empty scope: Always trigger
        - Medium confidence (0.15-0.30) + small scope/unknown category: Trigger
        """
        if not self.enable_plan_analyzer:
            return False

        # High confidence - skip (deterministic matcher is working)
        if confidence >= 0.70:
            return False

        # Low confidence with empty scope - ALWAYS trigger
        if confidence < 0.15 and len(scope) == 0:
            return True

        # Medium confidence - trigger ONLY if ambiguous
        if 0.15 <= confidence < 0.30:
            # Ambiguous if: small scope (< 3 files) OR category is "unknown"
            if len(scope) < 3 or category == "unknown":
                return True

        return False

    def _select_phases_for_analysis(
        self,
        phases: List[Dict],
        confidence_scores: Dict[str, float]
    ) -> List[Dict]:
        """
        Select up to MAX_PHASES_TO_ANALYZE phases, prioritizing lowest confidence.

        Returns list of phases to analyze, sorted by confidence (lowest first).
        """
        # Filter phases that should trigger PlanAnalyzer
        candidates = []
        for phase in phases:
            phase_id = phase.get("phase_id", "")
            confidence = confidence_scores.get(phase_id, 1.0)
            scope = phase.get("scope", {}).get("paths", [])
            category = phase.get("metadata", {}).get("category", "unknown")

            if self._should_trigger_plan_analyzer(confidence, scope, category):
                candidates.append((phase, confidence))

        # Sort by confidence (lowest first)
        candidates.sort(key=lambda x: x[1])

        # Take top MAX_PHASES_TO_ANALYZE
        selected = [phase for phase, _ in candidates[:self.MAX_PHASES_TO_ANALYZE]]

        # Log if we skipped any
        if len(candidates) > self.MAX_PHASES_TO_ANALYZE:
            skipped = len(candidates) - self.MAX_PHASES_TO_ANALYZE
            logger.info(
                f"Selected {self.MAX_PHASES_TO_ANALYZE} lowest-confidence phases for analysis, "
                f"skipped {skipped} additional candidates"
            )

        return selected

    async def _run_plan_analyzer_with_timeout(
        self,
        analyzer: Any,
        phase: Dict,
        grounded_context: Any
    ) -> Optional[Any]:
        """
        Run PlanAnalyzer with 30-second timeout protection.

        Returns analysis result on success, None on timeout/error.
        """
        try:
            # 30 second timeout (per Phase D guidance)
            analysis = await asyncio.wait_for(
                analyzer.analyze_phase(
                    phase_spec=phase,
                    context=grounded_context.to_prompt_section()
                ),
                timeout=30.0
            )
            return analysis

        except asyncio.TimeoutError:
            logger.warning(
                f"PlanAnalyzer timeout for phase {phase.get('phase_id', 'unknown')} "
                f"(exceeded 30s)"
            )
            return None

        except Exception as e:
            # Sanitize error message (max 200 chars)
            error_msg = str(e)[:200]
            logger.error(
                f"PlanAnalyzer failed for phase {phase.get('phase_id', 'unknown')}: "
                f"{type(e).__name__}: {error_msg}"
            )
            return None

    def _attach_plan_analysis_metadata(
        self,
        phase: Dict,
        analysis: Optional[Any],
        status: str,
        error: Optional[str] = None
    ) -> None:
        """
        Attach PlanAnalyzer results as metadata (NEVER override deterministic scope).

        Status values: "ran", "failed", "timeout", "skipped", "disabled"
        """
        metadata = {
            "status": status,
            "timestamp": datetime.now().isoformat(),
        }

        if status == "ran" and analysis:
            def _safe_list(value: Any) -> List[Any]:
                """
                Convert common list-like values to a list.

                Important for tests: `Mock` returns Mock objects for missing attrs,
                which are truthy but not iterable.
                """
                if value is None:
                    return []
                if isinstance(value, list):
                    return value
                if isinstance(value, tuple):
                    return list(value)
                if isinstance(value, set):
                    return list(value)
                return []

            recommended_scope = _safe_list(getattr(analysis, "recommended_scope", None))
            concerns = _safe_list(getattr(analysis, "concerns", None))
            recommendations = _safe_list(getattr(analysis, "recommendations", None))

            metadata.update({
                "feasible": getattr(analysis, "feasible", True),
                "confidence": getattr(analysis, "confidence", 0.0),
                "llm_recommended_scope": recommended_scope,  # Advisory only
                "concerns": concerns,
                "recommendations": recommendations,
            })

            # Flag discrepancies between deterministic and LLM scope
            deterministic_scope = set(phase.get("scope", {}).get("paths", []))
            llm_scope = set(recommended_scope)

            if llm_scope and llm_scope != deterministic_scope:
                diff = llm_scope - deterministic_scope
                if diff:
                    metadata["scope_discrepancy"] = {
                        "llm_suggested_additional": list(diff),
                        "note": "These files were suggested by LLM but not in deterministic scope"
                    }

        if error:
            metadata["error"] = error

        # CRITICAL: Attach to metadata, NEVER to scope
        if "metadata" not in phase:
            phase["metadata"] = {}
        phase["metadata"]["plan_analysis"] = metadata

    def _run_plan_analyzer_on_phases(
        self,
        phases: List[Dict],
        confidence_scores: Dict[str, float]
    ) -> List[str]:
        """
        Run PlanAnalyzer on selected low-confidence phases.

        Returns list of warnings encountered during analysis.
        """
        warnings = []

        # Select phases to analyze (max 3, lowest confidence first)
        selected_phases = self._select_phases_for_analysis(phases, confidence_scores)

        if not selected_phases:
            logger.info("No phases selected for PlanAnalyzer (all high confidence)")
            return warnings

        logger.info(f"Running PlanAnalyzer on {len(selected_phases)} phases")

        # Get lazy-initialized components
        analyzer = self._get_or_create_plan_analyzer()
        context_builder = self._get_or_create_context_builder()

        # Analyze each selected phase sequentially
        for phase in selected_phases:
            phase_id = phase.get("phase_id", "unknown")

            try:
                # Get stored match_result from phase metadata
                match_result = phase.get("metadata", {}).get("_match_result")

                # Build grounded context (reuse match_result if available)
                grounded_context = context_builder.build_context(
                    goal=phase.get("goal", ""),
                    phase_id=phase_id,
                    description=phase.get("description", ""),
                    match_result=match_result
                )

                if grounded_context.truncated:
                    logger.info(
                        f"Grounded context truncated for phase {phase_id} "
                        f"({grounded_context.total_chars} chars)"
                    )

                # Run PlanAnalyzer with timeout using Phase B helper
                analysis = run_async_safe(
                    self._run_plan_analyzer_with_timeout(
                        analyzer,
                        phase,
                        grounded_context
                    )
                )

                if analysis is None:
                    # Timeout or error occurred
                    self._attach_plan_analysis_metadata(
                        phase,
                        None,
                        "failed",
                        "LLM timeout or error (see logs)"
                    )
                    warnings.append(f"Phase '{phase_id}' PlanAnalyzer failed")
                else:
                    # Success
                    self._attach_plan_analysis_metadata(
                        phase,
                        analysis,
                        "ran"
                    )
                    logger.info(f"PlanAnalyzer completed for phase {phase_id}")

            except Exception as e:
                # Unexpected error (shouldn't happen due to internal error handling)
                error_msg = str(e)[:200]
                logger.error(f"Unexpected error analyzing phase {phase_id}: {error_msg}")
                self._attach_plan_analysis_metadata(
                    phase,
                    None,
                    "failed",
                    f"Unexpected error: {error_msg}"
                )
                warnings.append(f"Phase '{phase_id}' PlanAnalyzer failed unexpectedly")

        # Clean up match_result from metadata (temporary storage)
        for phase in phases:
            if "_match_result" in phase.get("metadata", {}):
                del phase["metadata"]["_match_result"]

        return warnings
