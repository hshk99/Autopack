"""
Token Budget Estimator for BUILD-129 Phase 1.

Deliverable-based output token estimation to reduce truncation from 50% → 30%.
Per TOKEN_BUDGET_ANALYSIS_REVISED.md (GPT-5.2 reviewed).
"""
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any, Iterable
from pathlib import Path
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

    # BUILD-129 Phase 2 Revision: Overhead model to avoid deliverables scaling trap
    # Base coefficients represent marginal cost per deliverable (not total phase cost)
    # Overhead is added separately based on category/complexity to capture fixed costs
    TOKEN_WEIGHTS = {
        "new_file_backend": 2000,    # Marginal cost for new backend file
        "new_file_frontend": 2800,   # Marginal cost for new frontend file (JSX/TSX verbose)
        "new_file_test": 1400,       # Marginal cost for new test file
        "new_file_doc": 500,         # Marginal cost for new documentation
        "new_file_config": 1000,     # Marginal cost for new config/migration
        "modify_backend": 700,       # Marginal cost for modifying backend
        "modify_frontend": 1100,     # Marginal cost for modifying frontend
        "modify_test": 600,          # Marginal cost for modifying test
        "modify_doc": 400,           # Marginal cost for modifying doc
        "modify_config": 500,        # Marginal cost for modifying config
    }

    # Phase overhead: fixed cost based on category and complexity
    # BUILD-129 Phase 2 Revision: Captures context setup, boilerplate, coordination costs
    # This replaces the problematic deliverables scaling multipliers
    PHASE_OVERHEAD = {
        # (category, complexity) → base overhead tokens
        ("implementation", "low"): 2000,
        ("implementation", "medium"): 3000,
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
        ("testing", "low"): 1500,
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

    def _extract_doc_features(self, deliverables: List[str], task_description: str = "") -> Dict[str, bool]:
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

    def _estimate_doc_synthesis(
        self,
        deliverables: List[str],
        complexity: str,
        scope_paths: Optional[List[str]] = None,
        task_description: str = ""
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
        context_quality = "none" if not scope_paths else ("strong" if len(scope_paths) > 10 else "some")
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
            confidence=0.75  # Higher confidence with explicit phase model
        )

    def estimate(
        self,
        deliverables: Any,
        category: str,
        complexity: str,
        scope_paths: Optional[List[str]] = None,
        task_description: str = ""
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

        if not deliverables:
            # No deliverables → use complexity default
            base_budgets = {"low": 8192, "medium": 12288, "high": 16384}
            return TokenEstimate(
                estimated_tokens=base_budgets.get(complexity, 8192),
                deliverable_count=0,
                category=category,
                complexity=complexity,
                confidence=0.5  # Low confidence without deliverables
            )

        # BUILD-129 Phase 3: DOC_SYNTHESIS detection and phase-based estimation
        # Production safety: some phases are missing category metadata; infer "documentation"
        # for pure-doc phases so DOC_SYNTHESIS can activate.
        is_pure_doc = self._all_doc_deliverables(deliverables)
        effective_category = category
        if is_pure_doc and category not in ["documentation", "docs", "doc_synthesis"]:
            effective_category = "documentation"

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
            confidence=confidence
        )

    def select_budget(
        self,
        estimate: TokenEstimate,
        complexity: str
    ) -> int:
        """
        Select final token budget from estimate.

        Per GPT-5.2: max(complexity_base, estimated * buffer) capped at 64k.

        Args:
            estimate: Token estimate
            complexity: Phase complexity

        Returns:
            Selected budget (tokens)
        """
        # Base budgets from complexity
        base_budgets = {"low": 8192, "medium": 12288, "high": 16384}
        base = base_budgets.get(complexity, 8192)

        # Add buffer to estimate (+20%)
        estimated_with_buffer = int(estimate.estimated_tokens * self.BUFFER_MARGIN)

        # Select max(base, estimated_with_buffer)
        selected = max(base, estimated_with_buffer)

        # Cap at 64k (Anthropic Sonnet 4.5 max)
        budget = min(selected, 64000)

        logger.info(
            f"[TokenEstimator] Budget selection: base={base}, estimated={estimate.estimated_tokens}, "
            f"with_buffer={estimated_with_buffer}, selected={budget}, "
            f"confidence={estimate.confidence:.1%}"
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
        is_config = any(lower_norm.endswith(ext) for ext in [".yml", ".yaml", ".json", ".toml", ".txt", ".ini"])
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
        elif any(lower_norm.endswith(ext) for ext in [".yml", ".yaml", ".json", ".toml", ".txt", ".ini"]):
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
        path_match = re.search(r'([a-zA-Z0-9_\-./]+\.[a-zA-Z0-9]+)', deliverable)
        if path_match:
            return path_match.group(1)

        # Fallback: strip common prefixes
        path = deliverable.lower()
        for prefix in ["create ", "modify ", "update ", "add ", "new file: ", "new: "]:
            if path.startswith(prefix):
                path = path[len(prefix):]

        # Remove trailing descriptions in parentheses
        path = re.sub(r'\s*\([^)]*\)\s*$', '', path)

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
            content = file_path.read_text(encoding='utf-8', errors='ignore')
            lines = content.split('\n')

            # Count non-empty, non-comment lines
            code_lines = [
                line for line in lines
                if line.strip() and not line.strip().startswith('#')
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
            import_lines = [line for line in code_lines if 'import ' in line]
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
        has_extension = sum(
            1 for d in deliverables
            if re.search(r'\.[a-zA-Z0-9]{2,4}', d)
        )
        specificity = has_extension / len(deliverables)
        confidence += specificity * 0.3  # +0.0 to +0.3

        # Clarity: Do deliverables have action verbs?
        has_verb = sum(
            1 for d in deliverables
            if any(verb in d.lower() for verb in ["create", "modify", "update", "add", "new"])
        )
        clarity = has_verb / len(deliverables)
        confidence += clarity * 0.2  # +0.0 to +0.2

        return min(1.0, confidence)
