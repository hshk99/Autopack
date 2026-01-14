"""
Token Budget Estimator for BUILD-129 Phase 1.

Deliverable-based output token estimation to reduce truncation from 50% → 30%.
Per TOKEN_BUDGET_ANALYSIS_REVISED.md (GPT-5.2 reviewed).
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any, Tuple
from pathlib import Path
from functools import lru_cache
import re
import logging

logger = logging.getLogger(__name__)


@dataclass
class TokenEstimate:
    """Token estimate for a phase."""

    estimated_tokens: int
    deliverable_count: int
    category: str
    complexity: str
    breakdown: Dict[str, int] = field(default_factory=dict)
    confidence: float = 0.0  # 0.0-1.0


class TokenEstimator:
    """
    Estimates output tokens required for a phase based on deliverables.

    Per GPT-5.2 recommendations (TOKEN_BUDGET_ANALYSIS_REVISED.md):
    - Uses deliverable types (new file vs modification vs test vs doc)
    - Category-specific multipliers (frontend, backend, etc.)
    - File complexity heuristics (LOC, imports, nesting)
    - Conservative safety margins (1.2x-1.5x)

    Replaces file-count heuristic with accurate prediction.
    """

    # Calibration version tracking
    CALIBRATION_VERSION = "v5-step1"  # BUILD-141 Part 9: damped partial calibration
    CALIBRATION_DATE = "2025-12-29"
    CALIBRATION_SAMPLES = 25  # Clean samples from telemetry-collection-v5

    # BUILD-129 Phase 2 Revision: Overhead model to avoid deliverables scaling trap
    # Base coefficients represent marginal cost per deliverable (not total phase cost)
    # Overhead is added separately based on category/complexity to capture fixed costs
    TOKEN_WEIGHTS = {
        "new_file_backend": 2000,  # Marginal cost for new backend file
        "new_file_frontend": 2800,  # Marginal cost for new frontend file (JSX/TSX verbose)
        "new_file_test": 1400,  # Marginal cost for new test file
        "new_file_doc": 500,  # Marginal cost for new documentation
        "new_file_config": 1000,  # Marginal cost for new config/migration
        "modify_backend": 700,  # Marginal cost for modifying backend
        "modify_frontend": 1100,  # Marginal cost for modifying frontend
        "modify_test": 600,  # Marginal cost for modifying test
        "modify_doc": 400,  # Marginal cost for modifying doc
        "modify_config": 500,  # Marginal cost for modifying config
    }

    # Phase overhead: fixed cost based on category and complexity
    # BUILD-129 Phase 2 Revision: Captures context setup, boilerplate, coordination costs
    # This replaces the problematic deliverables scaling multipliers
    #
    # BUILD-141 Part 9-10: v5+v6 Combined Calibration (Hybrid Option C)
    # Step 1 (v5): 25 samples, sqrt-damped reductions
    # Step 2 (v5+v6): 45 samples, sqrt-damped second round with cost-aware analysis
    # - implementation/low: 1120 → 634 (ratio=0.32, waste=10.3x, sqrt≈0.57, -43.4%)
    # - implementation/medium: 1860 → 1176 (ratio=0.40, waste=6.4x, sqrt≈0.63, -36.8%)
    # - tests/low: 1500 → 915 (v5 only, ratio=0.370, sqrt≈0.61, -39%)
    # Source: 45 clean samples (25 v5 + 20 v6), 77% confidence on impl groups
    # Docs coefficients unchanged (need ±50% reduction cap safety margin first)
    PHASE_OVERHEAD = {
        # (category, complexity) → base overhead tokens
        (
            "implementation",
            "low",
        ): 634,  # BUILD-141-C: v5+v6 combined (45 samples), sqrt-damped (was 1120, -43.4%)
        (
            "implementation",
            "medium",
        ): 1176,  # BUILD-141-C: v5+v6 combined (45 samples), sqrt-damped (was 1860, -36.8%)
        ("implementation", "high"): 5000,
        ("refactoring", "low"): 2500,
        ("refactoring", "medium"): 3500,
        ("refactoring", "high"): 5500,
        ("configuration", "low"): 800,
        ("configuration", "medium"): 1500,
        ("configuration", "high"): 2500,
        ("integration", "low"): 3000,
        ("integration", "medium"): 4000,
        ("integration", "high"): 6000,
        ("testing", "low"): 915,  # BUILD-141: v5 calibration (was 1500, -39%)
        ("testing", "medium"): 2500,
        ("testing", "high"): 4000,
        ("documentation", "low"): 1500,
        ("documentation", "medium"): 2500,
        ("documentation", "high"): 3500,
        ("docs", "low"): 1500,
        ("docs", "medium"): 2500,
        ("docs", "high"): 3500,
        ("backend", "low"): 2000,
        ("backend", "medium"): 3000,
        ("backend", "high"): 5000,
        ("frontend", "low"): 2500,
        ("frontend", "medium"): 3500,
        ("frontend", "high"): 5500,
        ("database", "low"): 2000,
        ("database", "medium"): 3000,
        ("database", "high"): 5000,
        ("deployment", "low"): 2000,
        ("deployment", "medium"): 3000,
        ("deployment", "high"): 5000,
    }

    # Safety margins - BUILD-129 Phase 2 Revision: Restored to original conservative values
    # Keep these constant during coefficient tuning to avoid compounding errors
    SAFETY_MARGIN = 1.3  # +30% for boilerplate, imports, error handling
    BUFFER_MARGIN = 1.2  # +20% buffer for final budget selection

    def __init__(self, workspace: Optional[Path] = None):
        """
        Initialize token estimator.

        Args:
            workspace: Workspace path for file analysis (optional)
        """
        self.workspace = workspace or Path(".")

    @staticmethod
    def normalize_deliverables(deliverables: Any) -> List[str]:
        """
        Normalize deliverables into a flat list of strings.

        BUILD-129 Phase 3: Production phases sometimes store deliverables as nested dicts like:
          {"tests": [...], "docs": [...], "polish": [...]}
        This helper flattens dict/list/tuple/set structures safely.
        """
        if deliverables is None:
            return []

        # Single string
        if isinstance(deliverables, str):
            return [deliverables]

        out: List[str] = []

        def _walk(x: Any) -> None:
            if x is None:
                return
            if isinstance(x, str):
                s = x.strip()
                if s:
                    out.append(s)
                return
            if isinstance(x, dict):
                for v in x.values():
                    _walk(v)
                return
            if isinstance(x, (list, tuple, set)):
                for v in x:
                    _walk(v)
                return
            # Fallback: stringify unknown types (avoid hard failure in production)
            try:
                s = str(x).strip()
                if s:
                    out.append(s)
            except Exception:
                return

        _walk(deliverables)
        return out

    @staticmethod
    def _is_doc_deliverable(deliverable: str) -> bool:
        p = (deliverable or "").strip().lower().replace("\\", "/")
        return p.startswith("docs/") or p.endswith(".md")

    @classmethod
    def _all_doc_deliverables(cls, deliverables: List[str]) -> bool:
        return bool(deliverables) and all(cls._is_doc_deliverable(d) for d in deliverables)

    def _extract_doc_features(
        self, deliverables: List[str], task_description: str = ""
    ) -> Dict[str, bool]:
        """
        Extract features that signal documentation synthesis vs pure writing.

        Features:
        - api_reference_required: Needs API docs (e.g., API_REFERENCE.md, endpoints)
        - examples_required: Needs code examples (e.g., EXAMPLES.md, snippets)
        - research_required: Task description hints at "from scratch" or investigation
        - usage_guide_required: Needs usage documentation

        Args:
            deliverables: List of deliverable file paths/descriptions
            task_description: Optional task description for additional context

        Returns:
            Dict of boolean features
        """
        deliverables_text = " ".join(deliverables).lower()
        task_text = (task_description or "").lower()
        combined = f"{deliverables_text} {task_text}"

        # API reference signals
        api_reference_required = bool(
            "api_reference" in combined
            or "api reference" in combined
            or "api.md" in combined
            or "endpoints" in combined
            or "rest api" in combined
        )

        # Examples signals
        examples_required = bool(
            "examples.md" in combined
            or "example" in combined
            or "snippets" in combined
            or "sample code" in combined
            or "usage example" in combined
        )

        # Research/investigation signals
        research_required = bool(
            "from scratch" in task_text
            or "create documentation for" in task_text
            or "document the" in task_text
            or "comprehensive" in task_text
            or "investigate" in task_text
        )

        # Usage guide signals
        usage_guide_required = bool(
            "usage_guide" in combined
            or "user guide" in combined
            or "getting started" in combined
            or "tutorial" in combined
        )

        return {
            "api_reference_required": api_reference_required,
            "examples_required": examples_required,
            "research_required": research_required,
            "usage_guide_required": usage_guide_required,
        }

    def _is_doc_synthesis(self, deliverables: List[str], task_description: str = "") -> bool:
        """
        Determine if documentation task is DOC_SYNTHESIS (code investigation + writing)
        vs DOC_WRITE (pure writing).

        DOC_SYNTHESIS indicators:
        - API_REFERENCE.md (requires API extraction)
        - EXAMPLES.md (requires code examples)
        - Multiple documentation files from scratch
        - Task description mentions "from scratch" or "investigate"

        Args:
            deliverables: List of deliverable file paths/descriptions
            task_description: Optional task description

        Returns:
            True if this is DOC_SYNTHESIS, False if DOC_WRITE
        """
        features = self._extract_doc_features(deliverables, task_description)

        # DOC_SYNTHESIS if any of these conditions are met:
        # 1. API reference required (needs code investigation)
        # 2. Examples required AND research required (needs code extraction)
        # 3. Multiple specialized docs (API, examples, usage) suggesting comprehensive effort

        is_synthesis = (
            features["api_reference_required"]
            or (features["examples_required"] and features["research_required"])
            or (features["examples_required"] and features["usage_guide_required"])
        )

        return is_synthesis

    @staticmethod
    def _is_sot_file(deliverable: str) -> bool:
        """
        Detect if deliverable is a Source of Truth (SOT) file.

        SOT files are structured ledgers requiring global context reconstruction:
        - BUILD_LOG.md: Phase execution log
        - BUILD_HISTORY.md: Historical build record
        - CHANGELOG.md: Version change log
        - HISTORY.md: General project history
        - RELEASE_NOTES.md: Release documentation

        BUILD-129 Phase 3 P3: SOT files show 84.2% SMAPE with DOC_SYNTHESIS model
        because they need different estimation (context + entries + overhead).

        Args:
            deliverable: File path or description

        Returns:
            True if deliverable is an SOT file
        """
        path_lower = deliverable.lower().replace("\\", "/")
        basename = Path(path_lower).name

        # SOT file basenames (case-insensitive)
        sot_basenames = {
            "build_log.md",
            "build_history.md",
            "changelog.md",
            "history.md",
            "release_notes.md",
        }

        return basename in sot_basenames

    def _estimate_doc_sot_update(
        self,
        deliverables: List[str],
        complexity: str,
        scope_paths: Optional[List[str]] = None,
        task_description: str = "",
    ) -> TokenEstimate:
        """
        Estimate tokens for Source of Truth (SOT) file updates.

        SOT files differ from regular docs:
        - Require global context reconstruction (repo/run state)
        - Output is structured ledger (not narrative)
        - Cost scales with number of entries, not investigation depth

        BUILD-129 Phase 3 P3 Model:
        1. Context reconstruction: 1500-3000 tokens (depends on context quality)
        2. Write entries: 600-1200 tokens per entry (proxy: deliverable_count)
        3. Consistency overhead: +10-20% (cross-references, formatting)

        Args:
            deliverables: List of deliverable file paths (should contain SOT file)
            complexity: Phase complexity (affects context reconstruction)
            scope_paths: Optional scope paths (context quality indicator)
            task_description: Task description

        Returns:
            TokenEstimate for SOT update
        """
        deliverable_count = len(deliverables)

        # Component 1: Context reconstruction (fixed cost)
        # Depends on scope_paths (proxy for context quality)
        context_quality = (
            "none" if not scope_paths else ("strong" if len(scope_paths) > 10 else "some")
        )
        if context_quality == "none":
            context_tokens = 3000  # Must reconstruct from entire repo
        elif context_quality == "some":
            context_tokens = 2200  # Some guidance provided
        else:
            context_tokens = 1500  # Strong context (recent run data)

        # Component 2: Write entries (scaled by deliverable_count)
        # deliverable_count proxies for number of entries to write
        # Single BUILD_LOG.md deliverable → 1 entry
        # Multiple files → multiple updates
        entry_count = max(1, deliverable_count)
        write_per_entry = 900  # Mid-range: 600-1200 tokens per entry
        write_tokens = write_per_entry * entry_count

        # Component 3: Consistency overhead (10-20%)
        # Cross-references, formatting, phase linking
        consistency_overhead_pct = 0.15  # 15% mid-range
        consistency_tokens = int(write_tokens * consistency_overhead_pct)

        # Sum components
        base_tokens = context_tokens + write_tokens + consistency_tokens

        # Apply safety margin (+30%, same as DOC_SYNTHESIS)
        total_tokens = int(base_tokens * self.SAFETY_MARGIN)

        # Breakdown for telemetry
        breakdown = {
            "sot_context_reconstruction": context_tokens,
            "sot_write_entries": write_tokens,
            "sot_consistency_overhead": consistency_tokens,
        }

        # Extract SOT file name for telemetry
        sot_file_name = None
        for d in deliverables:
            if self._is_sot_file(d):
                sot_file_name = Path(d.lower().replace("\\", "/")).name
                break

        logger.info(
            f"[TokenEstimator] DOC_SOT_UPDATE detected: context={context_tokens}, "
            f"write={write_tokens}, consistency={consistency_tokens}, "
            f"base={base_tokens}, final={total_tokens}, entries={entry_count}, "
            f"context_quality={context_quality}, sot_file={sot_file_name}"
        )

        return TokenEstimate(
            estimated_tokens=total_tokens,
            deliverable_count=deliverable_count,
            category="doc_sot_update",  # New category for telemetry tracking
            complexity=complexity,
            breakdown=breakdown,
            confidence=0.70,  # Slightly lower than DOC_SYNTHESIS (less data)
        )

    def _estimate_doc_synthesis(
        self,
        deliverables: List[str],
        complexity: str,
        scope_paths: Optional[List[str]] = None,
        task_description: str = "",
    ) -> TokenEstimate:
        """
        Phase-based estimation for DOC_SYNTHESIS tasks.

        DOC_SYNTHESIS = code investigation + API extraction + examples + writing + coordination

        Additive phases:
        1. Investigation phase: 2500 tokens (if no code context) or 1500 (if context provided)
        2. API extraction phase: 1200 tokens (if API reference required)
        3. Examples generation: 1400 tokens (if examples required)
        4. Writing phase: 850 tokens per deliverable (baseline)
        5. Coordination overhead: 12% of writing if ≥5 deliverables

        Args:
            deliverables: List of deliverable file paths/descriptions
            complexity: Phase complexity (low, medium, high)
            scope_paths: Optional scope paths (proxy for context quality)
            task_description: Task description

        Returns:
            TokenEstimate with phase breakdown
        """
        features = self._extract_doc_features(deliverables, task_description)
        deliverable_count = len(deliverables)

        # Phase 1: Investigation (depends on context quality)
        # Context quality proxy: scope_paths count
        context_quality = (
            "none" if not scope_paths else ("strong" if len(scope_paths) > 10 else "some")
        )
        if context_quality == "none":
            investigate_tokens = 2500  # Must read entire codebase
        elif context_quality == "some":
            investigate_tokens = 2000  # Some guidance
        else:
            investigate_tokens = 1500  # Strong context provided

        # Phase 2: API extraction (if needed)
        api_extract_tokens = 1200 if features["api_reference_required"] else 0

        # Phase 3: Examples generation (if needed)
        examples_tokens = 1400 if features["examples_required"] else 0

        # Phase 4: Writing (per deliverable)
        writing_tokens = 850 * deliverable_count

        # Phase 5: Coordination overhead (if many deliverables)
        coordination_tokens = int(0.12 * writing_tokens) if deliverable_count >= 5 else 0

        # Sum all phases
        base_tokens = (
            investigate_tokens
            + api_extract_tokens
            + examples_tokens
            + writing_tokens
            + coordination_tokens
        )

        # Apply safety margin (+30%)
        total_tokens = int(base_tokens * self.SAFETY_MARGIN)

        # Breakdown for telemetry
        breakdown = {
            "doc_synthesis_investigate": investigate_tokens,
            "doc_synthesis_api_extract": api_extract_tokens,
            "doc_synthesis_examples": examples_tokens,
            "doc_synthesis_writing": writing_tokens,
            "doc_synthesis_coordination": coordination_tokens,
        }

        logger.info(
            f"[TokenEstimator] DOC_SYNTHESIS detected: investigate={investigate_tokens}, "
            f"api_extract={api_extract_tokens}, examples={examples_tokens}, "
            f"writing={writing_tokens}, coordination={coordination_tokens}, "
            f"base={base_tokens}, final={total_tokens}, deliverables={deliverable_count}, "
            f"context_quality={context_quality}"
        )

        return TokenEstimate(
            estimated_tokens=total_tokens,
            deliverable_count=deliverable_count,
            category="doc_synthesis",  # Override category for telemetry tracking
            complexity=complexity,
            breakdown=breakdown,
            confidence=0.75,  # Higher confidence with explicit phase model
        )

    @staticmethod
    @lru_cache(maxsize=256)
    def _estimate_cached(
        deliverables_tuple: Tuple[str, ...],
        category: str,
        complexity: str,
        scope_paths_tuple: Optional[Tuple[str, ...]] = None,
        task_description: str = "",
        workspace_str: str = ".",
    ) -> TokenEstimate:
        """
        Cached version of estimation logic.

        IMP-P05: Cache token estimation results to avoid repeated workspace analysis.
        Converts mutable arguments to hashable tuples for caching.

        Args:
            deliverables_tuple: Tuple of deliverable paths/descriptions
            category: Phase category
            complexity: Phase complexity (low, medium, high)
            scope_paths_tuple: Optional tuple of scope paths
            task_description: Task description for feature extraction
            workspace_str: Workspace path as string

        Returns:
            TokenEstimate with predicted tokens and breakdown
        """
        # Convert back to mutable types for internal processing
        deliverables = list(deliverables_tuple)
        scope_paths = list(scope_paths_tuple) if scope_paths_tuple else None
        workspace = Path(workspace_str)

        # Create temporary instance for processing
        # Note: This is safe because all state-dependent methods are static or use passed args
        temp_estimator = TokenEstimator(workspace=workspace)

        # Delegate to internal estimation logic
        return temp_estimator._estimate_internal(
            deliverables=deliverables,
            category=category,
            complexity=complexity,
            scope_paths=scope_paths,
            task_description=task_description,
        )

    def estimate(
        self,
        deliverables: Any,
        category: str,
        complexity: str,
        scope_paths: Optional[List[str]] = None,
        task_description: str = "",
    ) -> TokenEstimate:
        """
        Estimate output tokens required for phase.

        Args:
            deliverables: List of required deliverables (paths or descriptions)
            category: Phase category (backend, frontend, testing, etc.)
            complexity: Phase complexity (low, medium, high)
            scope_paths: Optional scope paths for file complexity analysis
            task_description: Optional task description for feature extraction

        Returns:
            TokenEstimate with predicted tokens and breakdown
        """
        deliverables = self.normalize_deliverables(deliverables)

        # IMP-P05: Use cached estimation when possible
        # Convert mutable arguments to hashable tuples
        deliverables_tuple = tuple(deliverables)
        scope_paths_tuple = tuple(scope_paths) if scope_paths else None
        workspace_str = str(self.workspace)

        return self._estimate_cached(
            deliverables_tuple=deliverables_tuple,
            category=category,
            complexity=complexity,
            scope_paths_tuple=scope_paths_tuple,
            task_description=task_description,
            workspace_str=workspace_str,
        )

    def _estimate_internal(
        self,
        deliverables: List[str],
        category: str,
        complexity: str,
        scope_paths: Optional[List[str]] = None,
        task_description: str = "",
    ) -> TokenEstimate:
        """
        Internal estimation logic (extracted from estimate() for caching).

        Args:
            deliverables: Normalized list of deliverables
            category: Phase category
            complexity: Phase complexity
            scope_paths: Optional scope paths
            task_description: Task description

        Returns:
            TokenEstimate with predicted tokens and breakdown
        """

        if not deliverables:
            # No deliverables → use complexity default
            base_budgets = {"low": 8192, "medium": 12288, "high": 16384}
            return TokenEstimate(
                estimated_tokens=base_budgets.get(complexity, 8192),
                deliverable_count=0,
                category=category,
                complexity=complexity,
                confidence=0.5,  # Low confidence without deliverables
            )

        # BUILD-129 Phase 3: DOC_SYNTHESIS detection and phase-based estimation
        # Production safety: some phases are missing category metadata; infer "documentation"
        # for pure-doc phases so DOC_SYNTHESIS can activate.
        is_pure_doc = self._all_doc_deliverables(deliverables)
        effective_category = category
        if is_pure_doc and category not in [
            "documentation",
            "docs",
            "doc_synthesis",
            "doc_sot_update",
        ]:
            effective_category = "documentation"

        # BUILD-129 Phase 3 P3: SOT file detection (highest priority)
        # Check for SOT files first, as they need specialized estimation
        if is_pure_doc:
            has_sot_file = any(self._is_sot_file(d) for d in deliverables)
            if has_sot_file:
                return self._estimate_doc_sot_update(
                    deliverables=deliverables,
                    complexity=complexity,
                    scope_paths=scope_paths,
                    task_description=task_description,
                )

        # DOC_SYNTHESIS only applies to *pure documentation* phases; mixed phases should
        # use the regular overhead + marginal-cost model to account for code/test work too.
        if is_pure_doc and effective_category in ["documentation", "docs"]:
            is_synthesis = self._is_doc_synthesis(deliverables, task_description)
            if is_synthesis:
                return self._estimate_doc_synthesis(
                    deliverables=deliverables,
                    complexity=complexity,
                    scope_paths=scope_paths,
                    task_description=task_description,
                )

        breakdown = {}
        marginal_cost = 0

        for deliverable in deliverables:
            tokens = self._estimate_deliverable(deliverable, effective_category)
            marginal_cost += tokens

            # Track breakdown by type
            deliverable_type = self._classify_deliverable(deliverable, effective_category)
            breakdown[deliverable_type] = breakdown.get(deliverable_type, 0) + tokens

        # BUILD-129 Phase 2 Revision: Overhead model
        # total = overhead(category, complexity) + Σ(marginal cost per deliverable)
        overhead = self.PHASE_OVERHEAD.get((effective_category, complexity), 2000)
        base_tokens = overhead + marginal_cost

        # Apply safety margin (+30%)
        total_tokens = int(base_tokens * self.SAFETY_MARGIN)

        # Calculate confidence based on deliverable specificity
        confidence = self._calculate_confidence(deliverables)

        logger.debug(
            f"[TokenEstimator] Overhead model: overhead={overhead}, marginal_cost={marginal_cost}, "
            f"base={base_tokens}, safety={self.SAFETY_MARGIN:.1f}x, final={total_tokens}, "
            f"deliverables={len(deliverables)}"
        )

        return TokenEstimate(
            estimated_tokens=total_tokens,
            deliverable_count=len(deliverables),
            category=effective_category,
            complexity=complexity,
            breakdown=breakdown,
            confidence=confidence,
        )

    @staticmethod
    def _normalize_category(category: str) -> str:
        """
        Normalize category name to canonical form.

        Maps variations to standard names:
        - documentation/docs → docs
        - testing/tests → tests
        - implementation/IMPLEMENT_FEATURE → implementation

        Args:
            category: Raw category name

        Returns:
            Normalized category name
        """
        category_lower = category.lower()

        # Documentation variants
        if category_lower in ["documentation", "doc_write", "doc"]:
            return "docs"

        # Testing variants
        if category_lower in ["testing"]:
            return "tests"

        # Implementation variants
        if category_lower in ["implement_feature"]:
            return "implementation"

        # Keep special categories as-is
        if category_lower in ["doc_synthesis", "doc_sot_update"]:
            return category_lower

        # Default: return lowercase original
        return category_lower

    def select_budget(self, estimate: TokenEstimate, complexity: str) -> int:
        """
        Select final token budget from estimate.

        Per GPT-5.2: max(complexity_base, estimated * buffer) capped at 64k.

        BUILD-129 Phase 3 P7: Confidence-based buffering to reduce truncation.
        - Low confidence (<0.7): 1.4x buffer instead of 1.2x
        - High deliverable count (>=8): 1.5x buffer
        - High-risk categories (IMPLEMENT_FEATURE, integration) + high complexity: 1.6x buffer
        - Documentation (low complexity): 2.2x buffer (triage shows 2.12x underestimation)

        BUILD-142: Category-aware base budget floors to reduce waste.
        - docs/low: 4096 (down from 8192) - telemetry shows 84.6% hit base floor with 2.41x waste
        - tests/low: 6144 (down from 8192) - telemetry shows 10.11x waste at base floor
        - doc_synthesis/doc_sot_update: keep higher floors for safety (existing 2.2x buffer)

        Args:
            estimate: Token estimate
            complexity: Phase complexity

        Returns:
            Selected budget (tokens)
        """
        # BUILD-142: Category-aware base budgets
        # Normalize category for consistent lookup
        normalized_category = self._normalize_category(estimate.category)

        # Define base budgets by (category, complexity)
        # Falls back to universal base if not specified
        BASE_BUDGET_BY_CATEGORY = {
            ("docs", "low"): 4096,  # BUILD-142: down from 8192 (84.6% base dominance, 2.41x waste)
            ("docs", "medium"): 8192,  # Keep current
            ("docs", "high"): 12288,  # Keep current
            ("tests", "low"): 6144,  # BUILD-142: down from 8192 (10.11x waste)
            ("tests", "medium"): 8192,  # Keep current
            ("tests", "high"): 12288,  # Keep current
            ("implementation", "low"): 8192,  # Keep current (high variance)
            ("implementation", "medium"): 12288,
            ("implementation", "high"): 16384,
            # Special categories keep higher floors for safety
            ("doc_synthesis", "low"): 8192,
            ("doc_synthesis", "medium"): 12288,
            ("doc_synthesis", "high"): 16384,
            ("doc_sot_update", "low"): 8192,
            ("doc_sot_update", "medium"): 12288,
            ("doc_sot_update", "high"): 16384,
        }

        # Universal fallback for complexity if category not found
        UNIVERSAL_BASE_BUDGETS = {"low": 8192, "medium": 12288, "high": 16384}

        # Try category-specific lookup first, fall back to universal
        base = BASE_BUDGET_BY_CATEGORY.get(
            (normalized_category, complexity), UNIVERSAL_BASE_BUDGETS.get(complexity, 8192)
        )

        # BUILD-129 Phase 3 P7: Adaptive buffer margin based on risk factors
        buffer_margin = self.BUFFER_MARGIN  # Default 1.2

        # Factor 1: Low confidence → increase buffer
        if estimate.confidence < 0.7:
            buffer_margin = max(buffer_margin, 1.4)

        # Factor 2: High deliverable count → increase buffer
        # Accounts for builder_mode/change_size overrides that force max_tokens=16384
        if estimate.deliverable_count >= 8:
            buffer_margin = max(buffer_margin, 1.6)

        # Factor 3: High-risk categories + high complexity → increase buffer
        if estimate.category in ["IMPLEMENT_FEATURE", "integration"] and complexity == "high":
            buffer_margin = max(buffer_margin, 1.6)

        # Factor 4: DOC_SYNTHESIS/SOT updates → aggressive buffer (triage finding)
        # BUILD-129 Phase 3 P9: Narrow 2.2x buffer to only doc_synthesis/doc_sot_update
        # Triage shows 2.12x underestimation for category=documentation, complexity=low
        # But this was too broad - regular DOC_WRITE doesn't need 2.2x
        if estimate.category in ["doc_synthesis", "doc_sot_update"]:
            buffer_margin = 2.2

        # Add buffer to estimate
        estimated_with_buffer = int(estimate.estimated_tokens * buffer_margin)

        # Select max(base, estimated_with_buffer)
        selected = max(base, estimated_with_buffer)

        # Cap at 64k (Anthropic Sonnet 4.5 max)
        budget = min(selected, 64000)

        logger.info(
            f"[TokenEstimator] Budget selection: base={base}, estimated={estimate.estimated_tokens}, "
            f"with_buffer={estimated_with_buffer}, selected={budget}, "
            f"confidence={estimate.confidence:.1%}, buffer_margin={buffer_margin:.2f}x"
        )

        return budget

    def _estimate_deliverable(self, deliverable: str, category: str) -> int:
        """
        Estimate tokens for single deliverable.

        Args:
            deliverable: Deliverable path or description
            category: Phase category

        Returns:
            Estimated tokens
        """
        path = self._sanitize_deliverable_path(deliverable)
        normalized_path = path.replace("\\", "/")

        # Detect if new file vs modification
        is_new = any(verb in deliverable.lower() for verb in ["create", "new", "add"])

        # If deliverables are plain paths (common), infer "new" by filesystem existence.
        # This avoids systematic underestimation where new files were treated as modifications.
        if not is_new and self.workspace:
            try:
                inferred_path = self.workspace / path
                if not inferred_path.exists():
                    is_new = True
            except Exception:
                pass

        # Test file detection: avoid substring matches like "contest" or "src/.../test_utils.py"
        # Prefer path-based conventions.
        lower_norm = normalized_path.lower()
        basename = Path(lower_norm).name
        is_test = (
            lower_norm.startswith("tests/")
            or "/tests/" in lower_norm
            or basename.startswith("test_")
            or basename.endswith("_test.py")
            or basename.endswith(".spec.ts")
            or basename.endswith(".spec.tsx")
            or basename.endswith(".test.ts")
            or basename.endswith(".test.tsx")
        )

        is_doc = lower_norm.startswith("docs/") or lower_norm.endswith(".md")
        is_config = any(
            lower_norm.endswith(ext) for ext in [".yml", ".yaml", ".json", ".toml", ".txt", ".ini"]
        )
        is_migration = "alembic/versions" in lower_norm or "migration" in lower_norm
        is_frontend = any(lower_norm.endswith(ext) for ext in [".tsx", ".jsx", ".vue", ".svelte"])

        # Select weight category
        if is_doc:
            weight_key = "new_file_doc" if is_new else "modify_doc"
        elif is_config or is_migration:
            weight_key = "new_file_config" if is_new else "modify_config"
        elif is_test:
            weight_key = "new_file_test" if is_new else "modify_test"
        elif is_frontend or category == "frontend":
            weight_key = "new_file_frontend" if is_new else "modify_frontend"
        elif category in ["backend", "database"]:
            weight_key = "new_file_backend" if is_new else "modify_backend"
        else:
            # Default: backend weights
            weight_key = "new_file_backend" if is_new else "modify_backend"

        tokens = self.TOKEN_WEIGHTS.get(weight_key, 500)

        # File complexity heuristics (if file exists)
        if not is_new and self.workspace:
            file_path = self.workspace / path
            if file_path.exists():
                complexity_multiplier = self._analyze_file_complexity(file_path)
                tokens = int(tokens * complexity_multiplier)

        return tokens

    def _classify_deliverable(self, deliverable: str, category: str) -> str:
        """
        Classify deliverable type for breakdown tracking.

        Args:
            deliverable: Deliverable path or description
            category: Phase category

        Returns:
            Classification label
        """
        path = self._sanitize_deliverable_path(deliverable)
        normalized_path = path.replace("\\", "/")
        lower_norm = normalized_path.lower()

        is_new = any(verb in deliverable.lower() for verb in ["create", "new", "add"])
        if not is_new and self.workspace:
            try:
                inferred_path = self.workspace / path
                if not inferred_path.exists():
                    is_new = True
            except Exception:
                pass

        basename = Path(lower_norm).name
        is_test = (
            lower_norm.startswith("tests/")
            or "/tests/" in lower_norm
            or basename.startswith("test_")
            or basename.endswith("_test.py")
            or basename.endswith(".spec.ts")
            or basename.endswith(".spec.tsx")
            or basename.endswith(".test.ts")
            or basename.endswith(".test.tsx")
        )

        if is_test:
            return "test_new" if is_new else "test_modify"
        elif lower_norm.endswith(".md") or lower_norm.startswith("docs/"):
            return "doc_new" if is_new else "doc_modify"
        elif any(
            lower_norm.endswith(ext) for ext in [".yml", ".yaml", ".json", ".toml", ".txt", ".ini"]
        ):
            return "config_new" if is_new else "config_modify"
        elif any(lower_norm.endswith(ext) for ext in [".tsx", ".jsx", ".vue"]):
            return "frontend_new" if is_new else "frontend_modify"
        else:
            return "backend_new" if is_new else "backend_modify"

    def _sanitize_deliverable_path(self, deliverable: str) -> str:
        """
        Extract file path from deliverable description.

        Args:
            deliverable: Deliverable (may include description like "Create src/foo.py")

        Returns:
            Sanitized path
        """
        # Extract path from common patterns:
        # - "Create src/foo.py"
        # - "Modify src/foo.py to add X"
        # - "src/foo.py"
        # - "src/foo.py (new file)"

        # Try to extract path from description
        path_match = re.search(r"([a-zA-Z0-9_\-./]+\.[a-zA-Z0-9]+)", deliverable)
        if path_match:
            return path_match.group(1)

        # Fallback: strip common prefixes
        path = deliverable.lower()
        for prefix in ["create ", "modify ", "update ", "add ", "new file: ", "new: "]:
            if path.startswith(prefix):
                path = path[len(prefix) :]

        # Remove trailing descriptions in parentheses
        path = re.sub(r"\s*\([^)]*\)\s*$", "", path)

        return path.strip()

    def _analyze_file_complexity(self, file_path: Path) -> float:
        """
        Analyze file complexity to adjust token estimate.

        Heuristics:
        - LOC (lines of code)
        - Import count (dependencies)
        - Nesting depth (control flow complexity)

        Args:
            file_path: Path to existing file

        Returns:
            Complexity multiplier (0.5-2.0)
        """
        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
            lines = content.split("\n")

            # Count non-empty, non-comment lines
            code_lines = [
                line for line in lines if line.strip() and not line.strip().startswith("#")
            ]

            # LOC factor (more code → higher estimate)
            if len(code_lines) < 50:
                loc_factor = 0.7  # Small file
            elif len(code_lines) < 200:
                loc_factor = 1.0  # Normal file
            elif len(code_lines) < 500:
                loc_factor = 1.3  # Large file
            else:
                loc_factor = 1.5  # Very large file

            # Import count (more dependencies → more context)
            import_lines = [line for line in code_lines if "import " in line]
            if len(import_lines) < 5:
                import_factor = 0.9
            elif len(import_lines) < 15:
                import_factor = 1.0
            else:
                import_factor = 1.2

            # Nesting depth (complex logic → more explanation needed)
            max_indent = max([len(line) - len(line.lstrip()) for line in code_lines] + [0])
            if max_indent < 8:
                nesting_factor = 0.9
            elif max_indent < 16:
                nesting_factor = 1.0
            else:
                nesting_factor = 1.2

            # Combined multiplier
            multiplier = loc_factor * import_factor * nesting_factor

            # Clamp to reasonable range
            return max(0.5, min(2.0, multiplier))

        except Exception as e:
            logger.debug(f"[TokenEstimator] Could not analyze {file_path}: {e}")
            return 1.0  # Default

    def _calculate_confidence(self, deliverables: List[str]) -> float:
        """
        Calculate confidence in estimate based on deliverable specificity.

        Higher confidence when:
        - Deliverables are specific file paths (not vague descriptions)
        - Multiple deliverables (better averaging)
        - Deliverables include verbs (create, modify, update)

        Args:
            deliverables: List of deliverables

        Returns:
            Confidence score (0.0-1.0)
        """
        if not deliverables:
            return 0.0

        confidence = 0.5  # Base confidence

        # Specificity: Do deliverables contain file extensions?
        has_extension = sum(1 for d in deliverables if re.search(r"\.[a-zA-Z0-9]{2,4}", d))
        specificity = has_extension / len(deliverables)
        confidence += specificity * 0.3  # +0.0 to +0.3

        # Clarity: Do deliverables have action verbs?
        has_verb = sum(
            1
            for d in deliverables
            if any(verb in d.lower() for verb in ["create", "modify", "update", "add", "new"])
        )
        clarity = has_verb / len(deliverables)
        confidence += clarity * 0.2  # +0.0 to +0.2

        return min(1.0, confidence)
