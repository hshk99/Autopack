# BUILD-123v2: Deterministic Manifest Generator (Revised)

**Date:** 2025-12-22
**Status:** Implementation Ready
**Type:** Meta-Layer Enhancement (Replaces BUILD-123v1)

---

## Summary

**Revision Reason:** BUILD-123v1 (Plan Analyzer) had critical inefficiencies identified by GPT-5.2:
- High token overhead (N LLM calls per phase)
- No grounding (hallucinated paths)
- Governance mismatch (duplicate protection logic)
- Brittle (interactive prompts, unvalidated scopes)

**New Approach:** Deterministic manifest generation with minimal LLM fallback

**Key Changes:**
1. **Deterministic-first** - Rule-based scope discovery (0 LLM calls for common patterns)
2. **Repo-grounded** - Scans actual file structure, validates paths exist
3. **Reuses existing primitives** - Emits `scope.paths` for ContextSelector, no new execution paths
4. **Preflight validation** - Hard checks before execution, not during patch apply
5. **Adaptive scope expansion** - Controlled mechanism for underspecified manifests
6. **1-call-per-plan LLM fallback** - Only when deterministic confidence < 80%

---

## Architecture

```
┌─────────────────────┐
│ Minimal Plan        │  ← "Implement JWT auth"
└──────────┬──────────┘
           │
           ▼
┌─────────────────────────────────────────────┐
│  1. Repo Scanner (deterministic)            │  ← NEW
│                                             │
│  - Scan file tree (respect .gitignore)      │
│  - Detect anchor files (auth/, api/, etc.)  │
│  - Build directory map                      │
│  - 0 LLM calls                              │
└──────────┬──────────────────────────────────┘
           │
           ▼
┌─────────────────────────────────────────────┐
│  2. Pattern Matcher (deterministic)         │  ← NEW
│                                             │
│  - Match keywords → categories              │
│  - Compute confidence (earned, not assumed) │
│    - Match density                          │
│    - Anchor file presence                   │
│    - Directory locality                     │
│  - Discover candidate files (glob)          │
│  - Compile to EXPLICIT file/dir list        │
│  - 0 LLM calls                              │
└──────────┬──────────────────────────────────┘
           │
           ▼
┌─────────────────────────────────────────────┐
│  3. Confidence Check                        │
│                                             │
│  HIGH (>80%):                               │
│    - Matched known patterns                 │
│    - Anchor files present                   │
│    - Directory locality high                │
│    → Use deterministic manifest             │
│                                             │
│  LOW (<80%):                                │
│    - Ambiguous category                     │
│    - No anchor files                        │
│    - Cross-cutting concerns                 │
│    → LLM refinement (1 call for entire plan)│
└──────────┬──────────────────────────────────┘
           │
           ▼
┌─────────────────────────────────────────────┐
│  4. LLM Refinement (if needed, 1 call max)  │  ← Optional
│                                             │
│  Input (grounded):                          │
│  - Repo structure summary                   │
│  - Candidate manifests (deterministic)      │
│  - Governance constraints (ALLOWED_PATHS)   │
│                                             │
│  Output:                                    │
│  - Refined scope.paths (explicit files)     │
│  - Read-only context                        │
│  - 1 call for entire plan, not per phase    │
└──────────┬──────────────────────────────────┘
           │
           ▼
┌─────────────────────────────────────────────┐
│  5. Preflight Validator (hard checks)       │  ← NEW
│                                             │
│  - All paths exist in repo                  │
│  - Within ALLOWED_PATHS                     │
│  - No PROTECTED_PATHS violated              │
│  - Scope size < MAX_FILES_PER_PHASE         │
│  - Read-only ∩ write = ∅                    │
│  - Fail-fast if validation fails            │
└──────────┬──────────────────────────────────┘
           │
           ▼
┌─────────────────────────────────────────────┐
│  6. Enhanced Run Config                     │
│                                             │
│  {                                          │
│    "goal": "Implement JWT auth",            │
│    "scope": {  ← Existing schema, not new!  │
│      "paths": [                             │
│        "src/auth/jwt_service.py",  ← Explicit│
│        "src/api/endpoints/auth.py"          │
│      ],                                     │
│      "read_only_context": [                 │
│        "src/database/models.py"             │
│      ]                                      │
│    },                                       │
│    "deliverables": [...]                    │
│  }                                          │
└──────────┬──────────────────────────────────┘
           │
           ▼
┌─────────────────────────────────────────────┐
│  7. Executor → ContextSelector (existing)   │
│                                             │
│  ContextSelector.get_context_for_phase():   │
│  - Reads scope.paths (as it does today)     │
│  - Loads scoped context                     │
│  - Enforces token budget                    │
│                                             │
│  governed_apply (existing):                 │
│  - Enforces scope_paths at apply time       │
│  - Rejects patches outside scope            │
│  - No changes needed                        │
└─────────────────────────────────────────────┘
           │
           ▼
┌─────────────────────────────────────────────┐
│  8. Adaptive Scope Expansion (if needed)    │  ← NEW
│                                             │
│  Triggered by specific failures:            │
│  - "File not in scope" error                │
│  - "Missing import" error                   │
│                                             │
│  Expansion strategies (0-1 LLM call):       │
│  - Deterministic: file → parent dir         │
│  - Deterministic: add sibling module        │
│  - LLM (grounded): propose 1-3 paths        │
│                                             │
│  Governance: approval if sensitive area     │
└─────────────────────────────────────────────┘
```

---

## Key Principles (GPT-5.2 Recommendations)

### 1. Compile Globs → Explicit File List
**Problem:** `"src/*/auth/*.py"` is too permissive for enforcement

**Solution:**
```python
# Step 1: Use globs to discover candidates
candidates = glob.glob("src/*/auth/*.py")  # ["src/api/auth/jwt.py", ...]

# Step 2: Compile to explicit list
scope_paths = [str(Path(p).resolve()) for p in candidates]

# Step 3: Emit explicit list
{
  "scope": {
    "paths": [
      "src/api/auth/jwt.py",  # Explicit file
      "src/middleware/auth/"  # Or dir prefix
    ]
  }
}
```

### 2. Reuse Existing Schema (scope.paths)
**Don't create:** New `file_manifest` field

**Do use:** Existing `scope.paths` + `read_only_context` (ContextSelector already handles)

```python
# GOOD - uses existing schema
phase_spec = {
    "goal": "...",
    "scope": {
        "paths": [...],           # ContextSelector reads this
        "read_only_context": [...] # ContextSelector reads this
    }
}

# BAD - introduces new execution path
phase_spec = {
    "goal": "...",
    "file_manifest": {  # ← ContextSelector doesn't know about this
        "edit": [...],
        "read": [...]
    }
}
```

### 3. Preflight Validation (Not governed_apply)
**governed_apply** already enforces `scope_paths` at apply time - don't modify it

**Add:** New preflight validator that runs BEFORE execution

```python
# preflight_validator.py (NEW)
def validate_plan_preflight(plan: dict, workspace: Path) -> ValidationResult:
    """
    Validate plan before execution starts.

    governed_apply.py already enforces at patch time,
    this catches issues earlier.
    """
    for phase in plan["phases"]:
        scope_paths = phase.get("scope", {}).get("paths", [])

        # 1. All paths exist
        for path_pattern in scope_paths:
            resolved = workspace / path_pattern
            if not resolved.exists():
                return ValidationResult(valid=False,
                    error=f"Path not found: {path_pattern}")

        # 2. Within ALLOWED_PATHS
        for path in scope_paths:
            if not is_path_allowed(path):  # Uses governed_apply logic
                return ValidationResult(valid=False,
                    error=f"Protected path: {path}")

        # 3. Scope size caps
        if len(scope_paths) > MAX_FILES_PER_PHASE:
            return ValidationResult(valid=False,
                error=f"Scope too large: {len(scope_paths)} files")

    return ValidationResult(valid=True)
```

### 4. Earned Confidence Scores
**Don't assume:** `"confidence": 0.90` based on keyword match alone

**Do compute:** Confidence from multiple signals

```python
def compute_confidence(
    task_category: str,
    anchor_files_present: bool,
    match_density: float,
    directory_locality: float,
    recent_git_activity: bool
) -> float:
    """
    Earned confidence, not assumed.

    Signals:
    - Anchor files (e.g., src/auth/ exists for "authentication")
    - Match density (keyword frequency in goal text)
    - Directory locality (files clustered in one area)
    - Recent git activity (similar changes in history)
    """
    score = 0.0

    # Anchor files worth 40%
    if anchor_files_present:
        score += 0.40

    # Match density worth 30%
    score += match_density * 0.30

    # Directory locality worth 20%
    score += directory_locality * 0.20

    # Recent activity worth 10%
    if recent_git_activity:
        score += 0.10

    return min(score, 1.0)
```

### 5. Adaptive Scope Expansion
**Problem:** Manifest too narrow → Builder "can't complete"

**Solution:** Controlled expansion on specific failures

```python
class ScopeExpansionRequest:
    """Request to expand scope after failure"""
    phase_id: str
    failure_reason: Literal["file_not_in_scope", "missing_import", "scope_violation"]
    proposed_additions: List[str]  # New paths to add
    requires_approval: bool  # True if sensitive area

def expand_scope(
    phase_spec: dict,
    failure: ScopeExpansionRequest
) -> dict:
    """
    Expand scope with controlled mechanism.

    Strategies (prefer deterministic):
    1. File → parent dir
    2. Add sibling module
    3. LLM proposal (1 call, grounded)
    """

    if failure.failure_reason == "file_not_in_scope":
        # Deterministic: expand file to parent dir
        missing_file = failure.proposed_additions[0]
        parent_dir = str(Path(missing_file).parent)

        return {
            **phase_spec,
            "scope": {
                **phase_spec["scope"],
                "paths": phase_spec["scope"]["paths"] + [parent_dir + "/"]
            }
        }

    elif failure.failure_reason == "missing_import":
        # Deterministic: add import target
        import_target = resolve_import_path(failure.proposed_additions[0])

        return {
            **phase_spec,
            "scope": {
                **phase_spec["scope"],
                "read_only_context": phase_spec["scope"].get("read_only_context", []) + [import_target]
            }
        }

    else:
        # LLM fallback (grounded)
        if failure.requires_approval:
            # Request manual approval first
            raise ScopeExpansionRequiresApproval(failure)

        refined_scope = await llm_propose_expansion(
            phase_spec=phase_spec,
            failure=failure,
            repo_structure=scan_repo(),  # Grounded
            governance=ALLOWED_PATHS      # Aligned
        )

        return refined_scope
```

---

## Implementation Plan (Revised)

### Phase 1: Repo Scanner + Pattern Matcher (Day 1-2)

**Files to Create:**
1. `src/autopack/repo_scanner.py` - Deterministic repo structure analysis
2. `src/autopack/pattern_matcher.py` - Keyword → category → scope mapping

**repo_scanner.py:**
```python
"""Deterministic repository structure analysis"""

from pathlib import Path
from typing import Dict, List, Set
import gitignore_parser

class RepoScanner:
    """Scan repository structure (respects .gitignore)"""

    def __init__(self, workspace: Path):
        self.workspace = workspace
        self.gitignore = self._load_gitignore()

    def scan(self) -> Dict[str, any]:
        """
        Scan repo and build structure summary.

        Returns:
            {
                "tree": {...},           # Directory tree
                "anchor_files": {...},   # Key modules detected
                "file_count": int,
                "directory_map": {...}   # Path → category hints
            }
        """

        tree = {}
        anchor_files = self._detect_anchor_files()

        for root, dirs, files in os.walk(self.workspace):
            # Respect .gitignore
            dirs[:] = [d for d in dirs if not self._should_ignore(root / d)]
            files = [f for f in files if not self._should_ignore(root / f)]

            rel_root = Path(root).relative_to(self.workspace)
            tree[str(rel_root)] = {
                "dirs": dirs,
                "files": files
            }

        return {
            "tree": tree,
            "anchor_files": anchor_files,
            "file_count": sum(len(v["files"]) for v in tree.values()),
            "directory_map": self._build_directory_map(tree)
        }

    def _detect_anchor_files(self) -> Dict[str, List[str]]:
        """
        Detect anchor files/directories that hint at structure.

        Examples:
        - src/auth/ → authentication category
        - src/api/endpoints/ → api_endpoint category
        - tests/auth/ → test files for auth
        """
        anchors = {}

        # Authentication anchors
        if (self.workspace / "src" / "auth").is_dir():
            anchors["authentication"] = ["src/auth/"]

        # API endpoint anchors
        if (self.workspace / "src" / "api" / "endpoints").is_dir():
            anchors["api_endpoint"] = ["src/api/endpoints/"]

        # Frontend anchors
        if (self.workspace / "src" / "frontend").is_dir():
            anchors["frontend"] = ["src/frontend/"]

        return anchors

    def _should_ignore(self, path: Path) -> bool:
        """Check if path should be ignored (.gitignore)"""
        if self.gitignore:
            return self.gitignore(str(path))

        # Default ignores
        ignore_patterns = {".git", "venv", "node_modules", "__pycache__", ".pytest_cache"}
        return any(pattern in path.parts for pattern in ignore_patterns)
```

**pattern_matcher.py:**
```python
"""Pattern-based category matching with earned confidence"""

from typing import Dict, List, Tuple
from pathlib import Path

CATEGORY_PATTERNS = {
    "authentication": {
        "keywords": ["auth", "login", "jwt", "token", "session", "password"],
        "anchor_dirs": ["src/auth/", "src/authentication/"],
        "typical_scope_templates": [
            "src/{anchor}/**.py",
            "src/api/endpoints/auth*.py",
            "tests/{anchor}/**.py"
        ],
        "typical_readonly": [
            "src/database/models.py",
            "src/config.py"
        ]
    },
    "api_endpoint": {
        "keywords": ["endpoint", "api", "route", "rest", "graphql"],
        "anchor_dirs": ["src/api/", "src/endpoints/"],
        "typical_scope_templates": [
            "src/api/endpoints/**.py",
            "src/api/routers/**.py",
            "tests/api/**.py"
        ],
        "typical_readonly": [
            "src/main.py",
            "src/api/__init__.py"
        ]
    },
    # ... more categories
}

class PatternMatcher:
    """Match task descriptions to categories with earned confidence"""

    def __init__(self, repo_structure: Dict):
        self.repo_structure = repo_structure
        self.anchor_files = repo_structure["anchor_files"]

    def match(self, goal: str) -> Tuple[str, float, Dict]:
        """
        Match goal to category with confidence score.

        Returns:
            (category, confidence, manifest)
        """

        goal_lower = goal.lower()
        best_match = None
        best_confidence = 0.0

        for category, pattern in CATEGORY_PATTERNS.items():
            # Compute signals
            match_density = self._compute_match_density(goal_lower, pattern["keywords"])
            anchor_present = self._check_anchor_present(category, pattern["anchor_dirs"])
            locality = self._compute_locality(pattern)

            # Earned confidence
            confidence = self._compute_confidence(
                match_density=match_density,
                anchor_present=anchor_present,
                locality=locality
            )

            if confidence > best_confidence:
                best_confidence = confidence
                best_match = (category, pattern)

        if best_match:
            category, pattern = best_match
            manifest = self._generate_manifest(category, pattern)
            return category, best_confidence, manifest

        return "unknown", 0.0, {}

    def _compute_match_density(self, goal: str, keywords: List[str]) -> float:
        """Keyword frequency in goal text"""
        matches = sum(1 for kw in keywords if kw in goal)
        return min(matches / len(keywords), 1.0)

    def _check_anchor_present(self, category: str, anchor_dirs: List[str]) -> bool:
        """Check if anchor directory exists"""
        return category in self.anchor_files

    def _compute_locality(self, pattern: Dict) -> float:
        """How clustered are the expected files?"""
        # Simple heuristic: if all templates start with same prefix, high locality
        templates = pattern["typical_scope_templates"]
        if not templates:
            return 0.0

        common_prefix = os.path.commonprefix(templates)
        avg_prefix_ratio = len(common_prefix) / sum(len(t) for t in templates)

        return avg_prefix_ratio

    def _compute_confidence(
        self,
        match_density: float,
        anchor_present: bool,
        locality: float
    ) -> float:
        """
        Earned confidence from signals.

        Weights:
        - Anchor present: 40%
        - Match density: 30%
        - Locality: 20%
        - (Future: git history: 10%)
        """
        score = 0.0

        if anchor_present:
            score += 0.40

        score += match_density * 0.30
        score += locality * 0.20

        return score

    def _generate_manifest(self, category: str, pattern: Dict) -> Dict:
        """
        Generate manifest from pattern templates.

        Key: Compile globs to EXPLICIT file list.
        """
        import glob

        scope_paths = []

        # Expand templates to actual files
        for template in pattern["typical_scope_templates"]:
            # Replace {anchor} with actual anchor dir
            if category in self.anchor_files:
                anchor = self.anchor_files[category][0]
                template = template.replace("{anchor}", anchor.rstrip("/"))

            # Glob expansion
            matches = glob.glob(template, recursive=True)

            # Compile to explicit list
            scope_paths.extend([str(Path(m).resolve()) for m in matches])

        # Read-only context
        readonly = pattern.get("typical_readonly", [])

        return {
            "scope": {
                "paths": scope_paths,  # Explicit files, not globs
                "read_only_context": readonly
            }
        }
```

### Phase 2: Preflight Validator (Day 2-3)

**Files to Create:**
1. `src/autopack/preflight_validator.py` - Hard validation before execution

**preflight_validator.py:**
```python
"""Preflight validation (fail-fast before execution)"""

from pathlib import Path
from typing import List, Tuple
from dataclasses import dataclass

from autopack.governed_apply import is_path_allowed, is_protected_path

MAX_FILES_PER_PHASE = 20  # Configurable cap

@dataclass
class ValidationResult:
    valid: bool
    errors: List[str] = None
    warnings: List[str] = None

class PreflightValidator:
    """
    Validate plan before execution starts.

    governed_apply.py already enforces at patch time,
    this catches issues earlier and fails fast.
    """

    def __init__(self, workspace: Path):
        self.workspace = workspace

    def validate_plan(self, plan: dict) -> ValidationResult:
        """Validate entire plan"""

        errors = []
        warnings = []

        for phase in plan.get("phases", []):
            phase_result = self.validate_phase(phase)

            if not phase_result.valid:
                errors.extend(phase_result.errors or [])

            if phase_result.warnings:
                warnings.extend(phase_result.warnings)

        return ValidationResult(
            valid=len(errors) == 0,
            errors=errors if errors else None,
            warnings=warnings if warnings else None
        )

    def validate_phase(self, phase: dict) -> ValidationResult:
        """Validate single phase"""

        errors = []
        warnings = []

        phase_id = phase.get("phase_id", "unknown")
        scope = phase.get("scope", {})
        scope_paths = scope.get("paths", [])
        readonly_context = scope.get("read_only_context", [])

        # 1. All paths exist
        for path_pattern in scope_paths:
            resolved = self.workspace / path_pattern
            if not resolved.exists():
                errors.append(f"[{phase_id}] Path not found: {path_pattern}")

        # 2. Within ALLOWED_PATHS
        for path in scope_paths:
            if not is_path_allowed(path):
                errors.append(f"[{phase_id}] Not in ALLOWED_PATHS: {path}")

        # 3. No PROTECTED_PATHS violated
        for path in scope_paths:
            if is_protected_path(path):
                errors.append(f"[{phase_id}] Protected path: {path}")

        # 4. Scope size cap
        if len(scope_paths) > MAX_FILES_PER_PHASE:
            errors.append(f"[{phase_id}] Scope too large: {len(scope_paths)} files > {MAX_FILES_PER_PHASE}")

        # 5. Read-only ∩ write = ∅
        overlap = set(scope_paths) & set(readonly_context)
        if overlap:
            errors.append(f"[{phase_id}] Read-only and write overlap: {overlap}")

        # Warnings
        if len(scope_paths) == 0:
            warnings.append(f"[{phase_id}] Empty scope - Builder may fail")

        if len(scope_paths) > MAX_FILES_PER_PHASE * 0.8:
            warnings.append(f"[{phase_id}] Large scope ({len(scope_paths)} files) - consider splitting phase")

        return ValidationResult(
            valid=len(errors) == 0,
            errors=errors if errors else None,
            warnings=warnings if warnings else None
        )
```

### Phase 3: Adaptive Scope Expansion (Day 3-4)

**Files to Create:**
1. `src/autopack/scope_expander.py` - Controlled scope expansion on failures

**scope_expander.py:**
```python
"""Adaptive scope expansion (controlled, minimal LLM)"""

from dataclasses import dataclass
from typing import Literal, List, Optional
from pathlib import Path

@dataclass
class ScopeExpansionRequest:
    """Request to expand scope after failure"""
    phase_id: str
    failure_reason: Literal["file_not_in_scope", "missing_import", "scope_violation"]
    current_scope: List[str]
    proposed_additions: List[str]
    requires_approval: bool
    error_evidence: str  # Original error message

class ScopeExpander:
    """
    Controlled scope expansion on specific failures.

    Strategies (prefer deterministic):
    1. File → parent dir
    2. Add sibling module
    3. LLM proposal (0-1 call, grounded)
    """

    def __init__(self, workspace: Path):
        self.workspace = workspace

    def expand(
        self,
        request: ScopeExpansionRequest,
        max_expansions: int = 3
    ) -> Optional[List[str]]:
        """
        Expand scope with controlled mechanism.

        Returns:
            New scope (if expansion safe), or None (if requires approval)
        """

        if request.requires_approval:
            raise ScopeExpansionRequiresApproval(request)

        if request.failure_reason == "file_not_in_scope":
            return self._expand_file_to_parent(request)

        elif request.failure_reason == "missing_import":
            return self._expand_add_import_target(request)

        else:
            # Complex case - may need LLM
            return self._expand_llm_proposal(request)

    def _expand_file_to_parent(self, request: ScopeExpansionRequest) -> List[str]:
        """Deterministic: expand file → parent dir"""

        new_paths = []

        for proposed in request.proposed_additions:
            parent_dir = str(Path(proposed).parent) + "/"

            # Validate parent is safe
            if is_path_allowed(parent_dir):
                new_paths.append(parent_dir)
            else:
                # Can't expand - requires approval
                raise ScopeExpansionRequiresApproval(request)

        return request.current_scope + new_paths

    def _expand_add_import_target(self, request: ScopeExpansionRequest) -> List[str]:
        """Deterministic: add import target to read-only context"""

        # This should modify read_only_context, not scope.paths
        # Return import targets
        return request.proposed_additions

    async def _expand_llm_proposal(self, request: ScopeExpansionRequest) -> List[str]:
        """LLM fallback (grounded, 0-1 call)"""

        # Call LLM with grounded context
        from autopack.llm_service import LlmService

        llm = LlmService()

        prompt = f"""The following phase failed with a scope violation:

Phase: {request.phase_id}
Current scope: {request.current_scope}
Error: {request.error_evidence}

Propose 1-3 additional paths to add to scope. Respond with JSON:
{{
  "proposed_paths": ["path1", "path2"],
  "reason": "explanation"
}}

Constraints:
- Paths must exist in repo
- Paths must be within governance constraints
- Minimal expansion (prefer narrow scope)
"""

        response = await llm.call_llm(prompt, model="gpt-4o", temperature=0.1)

        # Parse and validate
        import json
        data = json.loads(response)
        proposed = data["proposed_paths"]

        # Validate all proposed paths
        for path in proposed:
            if not (self.workspace / path).exists():
                raise ValueError(f"LLM proposed non-existent path: {path}")

            if not is_path_allowed(path):
                raise ScopeExpansionRequiresApproval(request)

        return request.current_scope + proposed

class ScopeExpansionRequiresApproval(Exception):
    """Expansion touches sensitive area - requires manual approval"""
    pass
```

### Phase 4: Integration (Day 4-5)

**Files to Modify:**
1. `src/autopack/autonomous_executor.py` - Use preflight validator, scope expander

**Changes:**
```python
from autopack.repo_scanner import RepoScanner
from autopack.pattern_matcher import PatternMatcher
from autopack.preflight_validator import PreflightValidator
from autopack.scope_expander import ScopeExpander

class AutonomousExecutor:

    def execute_run(self, run_id: str, plan: dict):
        """Execute autonomous run with manifest generation"""

        # Step 1: Scan repo (deterministic)
        scanner = RepoScanner(self.workspace)
        repo_structure = scanner.scan()

        # Step 2: Generate manifests (deterministic)
        matcher = PatternMatcher(repo_structure)

        for phase in plan["phases"]:
            goal = phase.get("goal", "")

            # Match pattern
            category, confidence, manifest = matcher.match(goal)

            # Merge manifest into phase
            if "scope" not in phase:
                phase["scope"] = manifest.get("scope", {})

            # Store confidence for later
            phase["_confidence"] = confidence

        # Step 3: Preflight validation (fail-fast)
        validator = PreflightValidator(self.workspace)
        validation = validator.validate_plan(plan)

        if not validation.valid:
            raise PreflightValidationError(validation.errors)

        # Step 4: Execute phases (existing logic)
        for phase in plan["phases"]:
            try:
                self._execute_phase(phase)
            except ScopeViolationError as e:
                # Adaptive expansion
                expander = ScopeExpander(self.workspace)

                request = ScopeExpansionRequest(
                    phase_id=phase["phase_id"],
                    failure_reason="file_not_in_scope",
                    current_scope=phase["scope"]["paths"],
                    proposed_additions=e.missing_files,
                    requires_approval=False,
                    error_evidence=str(e)
                )

                new_scope = expander.expand(request)
                phase["scope"]["paths"] = new_scope

                # Retry phase with expanded scope
                self._execute_phase(phase)
```

---

## Token Savings Analysis

### BUILD-123v1 (Plan Analyzer)
- **Per phase:** ~2000 tokens (prompt) + ~500 tokens (response) = 2500 tokens
- **10 phases:** 10 × 2500 = **25,000 tokens**
- **LLM calls:** 10 (sequential)

### BUILD-123v2 (Manifest Generator)
- **Deterministic (>80% cases):** 0 tokens
- **LLM fallback (<20% cases):** 1 call × ~3000 tokens = **3,000 tokens**
- **LLM calls:** 0-1 (for entire plan)

**Savings:** 85-100% token reduction

---

## Next Steps

1. ✅ Implement repo_scanner.py (deterministic structure analysis)
2. ✅ Implement pattern_matcher.py (keyword → category with earned confidence)
3. ✅ Implement preflight_validator.py (hard checks before execution)
4. ✅ Implement scope_expander.py (controlled expansion on failures)
5. ⏳ Integrate with autonomous_executor.py
6. ⏳ Test on Lovable Phase 0 minimal plan
7. ⏳ Update documentation

---

**Created:** 2025-12-22 (BUILD-123v2)
**Status:** Implementation Ready
**Replaces:** BUILD-123v1 (Plan Analyzer)
**GPT-5.2 Validation:** Approved with recommended changes
