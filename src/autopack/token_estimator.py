"""
Token Budget Estimator for BUILD-129 Phase 1.

Deliverable-based output token estimation to reduce truncation from 50% → 30%.
Per TOKEN_BUDGET_ANALYSIS_REVISED.md (GPT-5.2 reviewed).
"""
from dataclasses import dataclass, field
from typing import List, Dict, Optional
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

    # Empirical weights from BUILD-126/127/128 telemetry
    TOKEN_WEIGHTS = {
        "new_file_backend": 800,     # New backend file (create)
        "new_file_frontend": 1200,   # New frontend file (JSX/TSX verbose)
        "new_file_test": 600,        # New test file
        "new_file_doc": 200,         # New documentation
        "new_file_config": 400,      # New config/migration
        "modify_backend": 300,       # Modify existing backend
        "modify_frontend": 450,      # Modify existing frontend
        "modify_test": 250,          # Modify existing test
        "modify_doc": 150,           # Modify existing doc
        "modify_config": 200,        # Modify existing config
    }

    # Category multipliers (boilerplate overhead)
    CATEGORY_MULTIPLIERS = {
        "backend": 1.2,      # SQLAlchemy models, pydantic, typing
        "database": 1.2,     # Migrations, schema updates
        "frontend": 1.4,     # JSX/TSX verbosity, hooks, state management
        "deployment": 1.1,   # Docker, k8s configs
        "testing": 1.0,      # Tests are typically concise
        "documentation": 0.8, # Docs are text-heavy but shorter
        "implementation": 1.15, # General implementation overhead
    }

    # Safety margins
    SAFETY_MARGIN = 1.3  # +30% for boilerplate, imports, error handling
    BUFFER_MARGIN = 1.2  # +20% buffer for final budget selection

    def __init__(self, workspace: Optional[Path] = None):
        """
        Initialize token estimator.

        Args:
            workspace: Workspace path for file analysis (optional)
        """
        self.workspace = workspace or Path(".")

    def estimate(
        self,
        deliverables: List[str],
        category: str,
        complexity: str,
        scope_paths: Optional[List[str]] = None
    ) -> TokenEstimate:
        """
        Estimate output tokens required for phase.

        Args:
            deliverables: List of required deliverables (paths or descriptions)
            category: Phase category (backend, frontend, testing, etc.)
            complexity: Phase complexity (low, medium, high)
            scope_paths: Optional scope paths for file complexity analysis

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
                confidence=0.5  # Low confidence without deliverables
            )

        breakdown = {}
        total_tokens = 0

        for deliverable in deliverables:
            tokens = self._estimate_deliverable(deliverable, category)
            total_tokens += tokens

            # Track breakdown by type
            deliverable_type = self._classify_deliverable(deliverable, category)
            breakdown[deliverable_type] = breakdown.get(deliverable_type, 0) + tokens

        # Apply safety margin (+30%)
        total_tokens = int(total_tokens * self.SAFETY_MARGIN)

        # Apply category multiplier
        multiplier = self.CATEGORY_MULTIPLIERS.get(category, 1.0)
        total_tokens = int(total_tokens * multiplier)

        # Calculate confidence based on deliverable specificity
        confidence = self._calculate_confidence(deliverables)

        return TokenEstimate(
            estimated_tokens=total_tokens,
            deliverable_count=len(deliverables),
            category=category,
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

        # Detect if new file vs modification
        is_new = any(verb in deliverable.lower() for verb in ["create", "new", "add"])
        is_test = "test" in path.lower()
        is_doc = path.startswith("docs/") or path.endswith(".md")
        is_config = any(path.endswith(ext) for ext in [".yaml", ".json", ".toml", ".txt", ".ini"])
        is_migration = "alembic/versions" in path or "migration" in path.lower()
        is_frontend = any(path.endswith(ext) for ext in [".tsx", ".jsx", ".vue", ".svelte"])

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
        is_new = any(verb in deliverable.lower() for verb in ["create", "new", "add"])

        if "test" in path.lower():
            return "test_new" if is_new else "test_modify"
        elif path.endswith(".md") or path.startswith("docs/"):
            return "doc_new" if is_new else "doc_modify"
        elif any(path.endswith(ext) for ext in [".yaml", ".json", ".toml", ".txt"]):
            return "config_new" if is_new else "config_modify"
        elif any(path.endswith(ext) for ext in [".tsx", ".jsx", ".vue"]):
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
