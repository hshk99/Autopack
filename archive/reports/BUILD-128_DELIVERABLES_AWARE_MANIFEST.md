# BUILD-128: Deliverables-Aware Manifest System

## Problem Statement

### What Happened (BUILD-127 Failure)
BUILD-127 Phase 1 failed with incorrect manifest generation:
- **Expected**: Backend Python files (`phase_finalizer.py`, `test_baseline_tracker.py`, `governance_request_handler.py`)
- **Got**: Frontend TypeScript files (`App.tsx`, `BuildView.tsx`, etc.)
- **Root Cause**: Manifest generator ignored `deliverables` field and pattern-matched on `goal` text

### Why This Is Critical
This type of bug causes:
1. **Complete phase failures** - Builder produces wrong files
2. **Wasted tokens** - Entire build iteration wasted
3. **Confusing errors** - Deliverables validation fails with cryptic messages
4. **User frustration** - Autonomous execution fails silently

### The Bug Chain

```
Phase YAML
  ├─ deliverables: ["src/autopack/phase_finalizer.py", ...]  ✓ Specified correctly
  ├─ scope.paths: NOT SET (since we're creating new files)
  └─ goal: "Implement authoritative completion gates..."

      ↓

autonomous_executor.py:_prepare_phase_context_and_scope()
  ├─ Checks: if not scope_config.get("paths")
  ├─ Decision: Generate manifest (correct)
  └─ Calls: manifest_generator.generate_manifest()

      ↓

manifest_generator.py:_enhance_phase()
  ├─ Line 312: existing_scope = phase.get("scope", {})
  ├─ Line 313: if existing_scope.get("paths"):  ❌ ONLY checks paths, not deliverables
  ├─ Decision: Run pattern matching
  └─ Calls: matcher.match(goal="Implement authoritative completion gates...")

      ↓

pattern_matcher.py:match()
  ├─ Scans repo for files matching keywords in goal
  ├─ Finds: "completion" matches in frontend dashboard files
  ├─ Returns: category="frontend", paths=[frontend files]
  └─ Confidence: 62% (above threshold)

      ↓

autonomous_executor.py:_execute_phase()
  ├─ Loads scope: ["src/frontend/App.tsx", ...]  ❌ WRONG
  ├─ Builder generates: Frontend TypeScript changes
  └─ Deliverables validation: FAILED (expected Python, got nothing)
```

## Root Cause Analysis

### Design Flaw
**ManifestGenerator only checks `scope.paths`, not `deliverables`**

```python
# manifest_generator.py:312-315
existing_scope = phase.get("scope", {})
if existing_scope.get("paths"):
    logger.info(f"Phase '{phase_id}' already has scope - skipping generation")
    return phase, 1.0, []
```

This assumes:
- ✓ If `scope.paths` exists → phase is fully specified
- ❌ If `deliverables` exists → **IGNORED**, runs pattern matching anyway

### Why This Happens
**Semantic mismatch between two different concepts:**

| Concept | Purpose | Example | Populated When |
|---------|---------|---------|----------------|
| `scope.paths` | Files to **modify** (input context) | `["src/autopack/models.py"]` | Refactoring, editing existing files |
| `deliverables` | Files to **create** (output validation) | `["src/autopack/phase_finalizer.py"]` | New feature implementation |

**BUILD-127 scenario**: Creating new files, so:
- `scope.paths` is empty (no existing files to modify)
- `deliverables` is populated (new files to create)
- **Bug**: ManifestGenerator treats empty `scope.paths` as "undefined scope" and runs pattern matching

## Solution Design: Deliverables-Aware Manifest System

### Key Insight
**Deliverables contain rich semantic information:**
- File paths reveal category: `src/autopack/*.py` → backend, `src/frontend/*.tsx` → frontend
- File existence reveals type: New files → creation, existing files → modification
- Deliverables are **explicit user intent**, not heuristic guesses

### Solution Architecture

```
┌─────────────────────────────────────────────────────────────┐
│ Phase YAML                                                  │
│  - goal: "..."                                              │
│  - deliverables: [...]                                      │
│  - scope.paths: [...]  (optional)                           │
└─────────────────────────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────────┐
│ ManifestGenerator._enhance_phase()                          │
│                                                              │
│ 1. Check if scope already provided:                         │
│    if scope.paths OR deliverables:                          │
│        return phase (skip pattern matching)                 │
│                                                              │
│ 2. If deliverables provided:                                │
│    - Infer category from deliverable paths                  │
│    - Use deliverables as scope.paths baseline               │
│    - Add related files as read_only_context                 │
│    - Confidence = 1.0 (explicit user intent)                │
│                                                              │
│ 3. Otherwise:                                               │
│    - Run pattern matching (existing behavior)               │
└─────────────────────────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────────┐
│ Enhanced Phase                                              │
│  - scope.paths: [inferred from deliverables]               │
│  - scope.deliverables: [preserved from input]               │
│  - metadata.category: "backend" (inferred)                  │
│  - metadata.confidence: 1.0                                 │
│  - metadata.inferred_from: "deliverables"                   │
└─────────────────────────────────────────────────────────────┘
```

### Implementation Components

#### Component 1: Deliverables Category Inference

```python
# manifest_generator.py (new method)
def _infer_category_from_deliverables(
    self,
    deliverables: List[str]
) -> Tuple[str, float]:
    """Infer task category from deliverable file paths.

    Args:
        deliverables: List of file paths to create/modify

    Returns:
        Tuple of (category, confidence)

    Examples:
        ["src/autopack/phase_finalizer.py"] → ("backend", 1.0)
        ["src/frontend/components/Button.tsx"] → ("frontend", 1.0)
        ["tests/test_feature.py"] → ("tests", 1.0)
        ["src/autopack/models.py", "alembic/versions/xyz.py"] → ("database", 0.9)
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
        for category, patterns in category_patterns.items():
            for pattern in patterns:
                if re.match(pattern, deliverable):
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
```

#### Component 2: Deliverables-Based Scope Expansion

```python
# manifest_generator.py (new method)
def _expand_scope_from_deliverables(
    self,
    deliverables: List[str],
    category: str,
    phase_id: str
) -> Tuple[List[str], List[str]]:
    """Expand scope from deliverables to include related files.

    Args:
        deliverables: List of files to create/modify
        category: Inferred category
        phase_id: Phase identifier

    Returns:
        Tuple of (scope_paths, read_only_context)

    Logic:
        - scope_paths: deliverables + immediate dependencies
        - read_only_context: related files for Builder context
    """
    scope_paths = list(deliverables)  # Start with deliverables
    read_only_context = []

    # Add category-specific related files
    if category == "backend":
        # Add models.py if creating new backend modules
        if any("src/autopack/" in d for d in deliverables):
            models_path = "src/autopack/models.py"
            if self.scanner.file_exists(models_path):
                read_only_context.append(models_path)

        # Add database.py for database-related work
        if "database" in phase_id.lower() or "models" in str(deliverables):
            db_path = "src/autopack/database.py"
            if self.scanner.file_exists(db_path):
                read_only_context.append(db_path)

    elif category == "tests":
        # Add conftest.py for test configuration
        conftest_candidates = ["tests/conftest.py", "conftest.py"]
        for path in conftest_candidates:
            if self.scanner.file_exists(path):
                read_only_context.append(path)

    elif category == "database":
        # Add models and alembic config
        read_only_context.extend([
            "src/autopack/models.py",
            "alembic.ini",
            "alembic/env.py"
        ])
        read_only_context = [p for p in read_only_context if self.scanner.file_exists(p)]

    # Remove duplicates, preserve order
    scope_paths = list(dict.fromkeys(scope_paths))
    read_only_context = list(dict.fromkeys(read_only_context))

    return scope_paths, read_only_context
```

#### Component 3: Enhanced Phase Enhancement Logic

```python
# manifest_generator.py:_enhance_phase() - MODIFIED
def _enhance_phase(
    self,
    phase: Dict
) -> tuple[Dict, float, List[str]]:
    """Enhance single phase with scope (BUILD-128: Deliverables-aware)."""

    phase_id = phase.get("phase_id", "unknown")
    goal = phase.get("goal", "")
    description = phase.get("description", "")

    warnings = []

    # BUILD-128: Check if scope OR deliverables already provided
    existing_scope = phase.get("scope", {})
    existing_deliverables = existing_scope.get("deliverables", [])

    if existing_scope.get("paths"):
        logger.info(f"Phase '{phase_id}' already has scope.paths - skipping generation")
        return phase, 1.0, []

    # BUILD-128: NEW - Check deliverables and infer scope
    if existing_deliverables:
        logger.info(f"Phase '{phase_id}' has deliverables - inferring scope from deliverables")

        # Infer category from deliverables
        category, category_confidence = self._infer_category_from_deliverables(existing_deliverables)
        logger.info(f"Inferred category '{category}' from deliverables (confidence={category_confidence:.1%})")

        # Expand scope from deliverables
        scope_paths, read_only_context = self._expand_scope_from_deliverables(
            deliverables=existing_deliverables,
            category=category,
            phase_id=phase_id
        )

        # Build enhanced phase with inferred scope
        enhanced_phase = {
            **phase,
            "scope": {
                "paths": scope_paths,
                "deliverables": existing_deliverables,  # Preserve original
                "read_only_context": read_only_context
            },
            "metadata": {
                "category": category,
                "confidence": category_confidence,
                "inferred_from": "deliverables",
                "deliverables_count": len(existing_deliverables)
            }
        }

        return enhanced_phase, category_confidence, []

    # Existing logic: Run pattern matching if no scope and no deliverables
    try:
        match_result = self.matcher.match(
            goal=goal,
            phase_id=phase_id,
            description=description
        )
    except Exception as e:
        logger.error(f"Pattern matching failed for phase '{phase_id}': {e}")
        # ... rest of existing error handling
```

### Validation and Safety

#### Preflight Checks
Add to `PreflightValidator`:

```python
def _check_deliverables_scope_consistency(self, phase: Dict) -> List[str]:
    """Check deliverables and scope.paths are consistent.

    Warnings:
    - Deliverables in scope.paths that don't exist (creation expected)
    - Deliverables outside scope.paths (may not be created)
    - Mixed categories (frontend + backend in same phase)
    """
    warnings = []

    scope = phase.get("scope", {})
    deliverables = scope.get("deliverables", [])
    scope_paths = scope.get("paths", [])

    if not deliverables:
        return warnings

    # Check if deliverables are in scope
    missing_from_scope = set(deliverables) - set(scope_paths)
    if missing_from_scope:
        warnings.append(
            f"Phase '{phase.get('phase_id')}': {len(missing_from_scope)} deliverable(s) "
            f"not in scope.paths (may not be created)"
        )

    # Check category consistency
    categories = set()
    for path in deliverables:
        if "frontend" in path:
            categories.add("frontend")
        elif "src/autopack" in path or "tests" in path:
            categories.add("backend")

    if len(categories) > 1:
        warnings.append(
            f"Phase '{phase.get('phase_id')}': Mixed categories in deliverables "
            f"({categories}) - consider splitting into separate phases"
        )

    return warnings
```

### Error Recovery

Add to `ErrorRecoverySystem`:

```python
class ManifestCategoryMismatchError(Exception):
    """Raised when manifest category doesn't match deliverables."""
    pass

# In error_recovery.py
RECOVERABLE_ERRORS.append("ManifestCategoryMismatchError")

def detect_manifest_category_mismatch(
    phase: Dict,
    builder_output: str
) -> Optional[Dict]:
    """Detect if Builder is working on wrong category of files.

    Returns recovery hint if mismatch detected.
    """
    deliverables = phase.get("scope", {}).get("deliverables", [])
    scope_paths = phase.get("scope", {}).get("paths", [])

    if not deliverables or not scope_paths:
        return None

    # Check if deliverables are backend but scope is frontend
    deliverables_backend = any("src/autopack" in d for d in deliverables)
    scope_frontend = any("frontend" in p for p in scope_paths)

    if deliverables_backend and scope_frontend:
        return {
            "error_type": "ManifestCategoryMismatchError",
            "recovery_action": "regenerate_manifest",
            "hint": "Deliverables are backend Python files but scope includes frontend TypeScript files",
            "suggested_fix": {
                "category": "backend",
                "scope_paths": deliverables,  # Use deliverables as scope
            }
        }

    return None
```

## Implementation Plan

### Phase 1: Core Deliverables Inference (HIGH)
**Files**: `manifest_generator.py`
**Changes**:
1. Add `_infer_category_from_deliverables()` method
2. Add `_expand_scope_from_deliverables()` method
3. Modify `_enhance_phase()` to check deliverables before pattern matching
4. Add `inferred_from` metadata field

**Success Criteria**:
- BUILD-127 retry generates correct backend scope
- Deliverables-based category inference 95%+ accurate

### Phase 2: Validation and Consistency Checks (MEDIUM)
**Files**: `preflight_validator.py`
**Changes**:
1. Add `_check_deliverables_scope_consistency()` to PreflightValidator
2. Warn on mixed categories in deliverables
3. Warn on deliverables outside scope.paths

**Success Criteria**:
- Detects inconsistencies in test cases
- No false positives on valid configurations

### Phase 3: Error Detection and Recovery (MEDIUM)
**Files**: `error_recovery.py`, `autonomous_executor.py`
**Changes**:
1. Add `detect_manifest_category_mismatch()` to error recovery
2. Add regenerate_manifest recovery action
3. Log when deliverables inference is used vs pattern matching

**Success Criteria**:
- Detects category mismatches automatically
- Suggests manifest regeneration as recovery

### Phase 4: Testing and Validation (HIGH)
**Files**: `tests/test_manifest_generator.py`
**New Tests**:
1. `test_infer_category_from_deliverables_backend()`
2. `test_infer_category_from_deliverables_frontend()`
3. `test_infer_category_from_deliverables_mixed()`
4. `test_expand_scope_from_deliverables_backend()`
5. `test_enhance_phase_with_deliverables_skips_pattern_matching()`
6. `test_build127_scenario_generates_backend_scope()`

**Success Criteria**:
- All tests pass
- BUILD-127 scenario test validates correct behavior

## Benefits

### Immediate Benefits
1. **✅ Fixes BUILD-127** - Correct backend scope generated
2. **✅ Prevents future mismatches** - Deliverables are primary source of truth
3. **✅ Better UX** - Clear error messages when category mismatches occur
4. **✅ Faster execution** - Skips pattern matching when deliverables provided

### Long-Term Benefits
1. **Higher confidence scores** - Explicit deliverables → 1.0 confidence
2. **Reduced token waste** - Fewer failed iterations due to wrong scope
3. **Better autonomous behavior** - System respects explicit user intent
4. **Easier debugging** - Logs show "inferred from deliverables" vs "pattern matched"

## Metrics and Validation

### Success Metrics
- **Category accuracy**: >95% when deliverables provided
- **Manifest generation time**: <100ms (skip pattern matching)
- **False completion rate**: <1% (down from current ~5%)
- **BUILD-127 retry**: COMPLETE on first attempt

### Validation Tests
1. **Unit Tests**: 15+ tests for inference and expansion logic
2. **Integration Tests**: End-to-end BUILD-127 scenario
3. **Regression Tests**: Existing pattern matching still works when no deliverables
4. **Edge Cases**: Empty deliverables, mixed categories, non-existent files

## Rollout Plan

### Stage 1: Implementation (1-2 days)
- Implement core inference logic
- Add validation checks
- Write comprehensive tests

### Stage 2: Testing (1 day)
- Run test suite
- Retry BUILD-127 with fix
- Validate on BUILD-126 scenarios

### Stage 3: Monitoring (ongoing)
- Log inference vs pattern matching ratio
- Track category accuracy
- Monitor false completion rate

## Conclusion

The Deliverables-Aware Manifest System is a fundamental fix that:
1. **Respects explicit user intent** (deliverables) over heuristics (pattern matching)
2. **Prevents entire class of bugs** (category mismatches)
3. **Improves autonomous execution** (higher confidence, fewer failures)
4. **Maintains backward compatibility** (pattern matching still works)

This is a **required fix** for BUILD-127 and will prevent similar issues in all future builds.
