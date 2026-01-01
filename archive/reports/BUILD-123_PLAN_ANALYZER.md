# BUILD-123: Plan Analyzer - Autonomous Pre-Flight Analysis

**Date:** 2025-12-22
**Status:** ✅ Implementation Ready
**Type:** Meta-Layer Enhancement

---

## Summary

**Problem:** Previous approach over-specified implementation details (exact file paths, code snippets, step-by-step instructions), which defeats the purpose of autonomous execution where the Builder should figure out implementation details.

**Solution:** Created a **Plan Analyzer** meta-layer that analyzes ANY unorganized implementation plan and automatically generates:
1. Feasibility assessment (CAN/RISKY/MANUAL classification)
2. Quality gates (validation criteria, success metrics)
3. Governance scope (allowed paths, approval requirements)
4. Risk classification (CLEAR_FIX, THRESHOLD, RISKY, AMBIGUOUS)

**Key Insight:** Separate **WHAT to achieve** (goals, constraints) from **HOW to achieve it** (implementation details). The Builder interprets goals within analyzed governance scope.

---

## What Was Created

### Core Module
**File:** [src/autopack/plan_analyzer.py](../src/autopack/plan_analyzer.py)

**Key Classes:**
- `PlanAnalyzer` - Main analysis engine (uses LLM to analyze phases)
- `PhaseAnalysis` - Analysis results for a single phase
- `PlanAnalysisResult` - Complete analysis of an implementation plan

**Key Functions:**
- `analyze_plan(run_id, phases, context)` - Analyze multi-phase plan
- `_analyze_phase(phase_spec, context)` - LLM-based phase analysis
- `_recommend_execution_order(phases)` - Topological sort + priority
- `_generate_global_governance(phases)` - Aggregate allowed/protected paths

### CLI Tools
**Files:**
- [scripts/analyze_plan.py](../scripts/analyze_plan.py) - Standalone analysis tool
- [scripts/run_with_analysis.py](../scripts/run_with_analysis.py) - Integrated execution wrapper

**Usage:**
```bash
# Standalone analysis
python scripts/analyze_plan.py my_plan.json --output analysis.json

# Integrated execution (analysis + autonomous run)
python scripts/run_with_analysis.py my_plan.json
```

### Documentation
**File:** [docs/PLAN_ANALYZER.md](PLAN_ANALYZER.md)

---

## Architecture

```
┌─────────────────────┐
│ Minimal Plan        │  ← User provides high-level goals only
│ (JSON/YAML)         │     "Implement JWT authentication"
└──────────┬──────────┘
           │
           ▼
┌─────────────────────────────────┐
│     Plan Analyzer (LLM)         │  ← GPT-4/Claude analyzes each phase
│                                 │
│  Generates:                     │
│  - Feasibility (CAN/RISKY/MAN)  │
│  - File scope (allowed paths)   │
│  - Risk level (LOW/MED/HIGH)    │
│  - Decision category (BUILD-113)│
│  - Quality gates (success       │
│    criteria, validation tests)  │
│  - Blockers (infrastructure,    │
│    expertise, dependencies)     │
└──────────┬──────────────────────┘
           │
           ▼
┌─────────────────────────────────┐
│  Enhanced Run Config            │  ← Config enriched with analysis
│                                 │
│  Original:                      │
│  {                              │
│    "goal": "Implement JWT auth" │
│  }                              │
│                                 │
│  Enhanced:                      │
│  {                              │
│    "goal": "Implement JWT auth",│
│    "scope": {                   │
│      "paths": ["src/auth/"]     │
│    },                           │
│    "success_criteria": [...]    │
│  }                              │
└──────────┬──────────────────────┘
           │
           ▼
┌─────────────────────────────────┐
│  Autonomous Executor            │  ← Builder interprets goal
│  (Builder + Auditor)            │     within governance scope
│                                 │
│  Builder:                       │
│  - Reads goal                   │
│  - Explores codebase            │
│  - Generates implementation     │
│  - Works within scope.paths     │
│                                 │
│  Governed Apply:                │
│  - Enforces allowed_paths       │
│  - Symbol preservation          │
│  - Structural similarity        │
└─────────────────────────────────┘
```

---

## Key Features

### 1. Feasibility Classification

**CAN_IMPLEMENT (75-90% confidence)**
- Clear, well-defined goal
- Isolated changes (few files)
- No external dependencies
- Existing patterns to follow

**RISKY (45-65% confidence)**
- Multiple files affected
- Some architectural changes
- Frontend/UI complexity
- Medium external dependencies

**MANUAL_REQUIRED (20-40% confidence)**
- Major architectural changes
- External service dependencies
- Requires specialized expertise
- High-risk core functionality

### 2. LLM-Based Analysis

The analyzer uses GPT-4/Claude to analyze each phase:

**Input (Minimal):**
```json
{
  "phase_id": "auth-backend",
  "goal": "Implement JWT authentication"
}
```

**LLM Prompt:**
```
Analyze this phase and provide:
1. Feasibility (CAN_IMPLEMENT/RISKY/MANUAL_REQUIRED)
2. Confidence (0.0-1.0)
3. Risk level (LOW/MEDIUM/HIGH/VERY_HIGH)
4. Decision category (CLEAR_FIX/THRESHOLD/RISKY/AMBIGUOUS)
5. Estimated files to modify
6. Core files affected (list file paths)
7. Allowed paths (governance scope)
8. Blockers (critical issues to resolve)
9. Success criteria (validation criteria)
10. Validation tests (test commands)
11. Metrics (quantitative targets)
...
```

**Output (Structured):**
```json
{
  "feasibility": "CAN_IMPLEMENT",
  "confidence": 0.80,
  "risk_level": "MEDIUM",
  "decision_category": "THRESHOLD",
  "estimated_files_modified": 3,
  "core_files_affected": ["src/auth/jwt_service.py"],
  "allowed_paths": ["src/auth/", "src/api/endpoints/auth.py"],
  "blockers": [],
  "success_criteria": ["Login endpoint returns valid JWT"],
  "metrics": {"test_coverage": ">=90%"}
}
```

### 3. Governance Scope Generation

**Allowed Paths** (MAY modify):
```json
{
  "allowed_paths": [
    "src/autopack/lovable/",           // New subtree
    "src/autopack/governed_apply.py",  // Specific files
    "tests/autopack/lovable/"          // Test files
  ]
}
```

**Read-Only Context** (context but NOT modify):
```json
{
  "readonly_context": [
    "src/autopack/autonomous_executor.py",
    "src/autopack/context_selector.py"
  ]
}
```

**Protected Paths** (NEVER modify):
```json
{
  "protected_paths": [
    ".git/",
    "venv/",
    ".autonomous_runs/*/gold_set/"
  ]
}
```

### 4. Quality Gates

**Success Criteria:**
- "All tests pass: pytest tests/autopack/lovable/ -v"
- "Semantic similarity test: cosine_sim(related) > 0.7"
- "API endpoint returns 200 for valid requests"

**Validation Tests:**
- "pytest tests/autopack/test_lovable.py -v"
- "curl http://localhost:8000/api/browser/telemetry -X POST"

**Metrics:**
```json
{
  "token_reduction": ">=40%",
  "patch_success": ">=85%",
  "test_coverage": ">=90%"
}
```

### 5. Blocker Detection

**Infrastructure Blockers:**
- "Hash embeddings not semantic - install sentence-transformers"
- "Morph API subscription required ($100/month)"

**Expertise Blockers:**
- "Frontend integration requires React expertise"
- "Database migration requires PostgreSQL DBA knowledge"

**Dependency Blockers:**
- Phase A depends on Phase B (topological sort)

### 6. Execution Order Optimization

**Algorithm:**
1. Topological sort (resolve dependencies)
2. Feasibility priority (CAN_IMPLEMENT > RISKY > MANUAL)
3. Complexity scoring (simpler first for quick wins)

**Example:**
```json
{
  "recommended_execution_order": [
    "protected-path",      // CAN_IMPLEMENT, no deps, complexity: 5
    "semantic-embeddings", // CAN_IMPLEMENT, no deps, complexity: 6
    "browser-telemetry",   // CAN_IMPLEMENT, no deps, complexity: 7
    "frontend-integration" // RISKY, depends on telemetry, complexity: 8
  ]
}
```

---

## Benefits

### 1. No Over-Specification ✅
**Before (BUILD-122):**
- Created phase docs with exact file paths
- Provided code snippets showing implementation
- Step-by-step instructions for Builder

**Problem:** Defeats autonomous execution purpose

**After (BUILD-123):**
- Minimal plan: High-level goals only
- Builder figures out implementation details
- Analysis provides constraints, not instructions

### 2. Safe Governance ✅
- Analyzed scope prevents unintended modifications
- Risk classification enforces approval gates
- Blocker detection prevents broken executions

### 3. Automatic Quality Assurance ✅
- Success criteria generated automatically
- Validation tests recommended
- Metrics targets for go/no-go decisions

### 4. Predictability ✅
- Confidence scores for stakeholder communication
- Duration estimates for planning
- Execution order for dependencies

---

## Integration with Existing Features

### BUILD-113: Autonomous Investigation
**Synergy:** Plan Analyzer runs BEFORE execution, BUILD-113 runs DURING execution

- **Plan Analyzer:** Pre-flight analysis (feasibility, scope, gates)
- **BUILD-113:** Runtime decision analysis (patch risk, auto-apply)

**Flow:**
1. Plan Analyzer: "Phase is THRESHOLD, manual review required"
2. Builder: Generates patch
3. BUILD-113: "Patch is CLEAR_FIX, auto-apply safe" → Override to auto-apply

### governed_apply.py: Symbol Preservation
**Synergy:** Plan Analyzer defines scope, governed_apply enforces

- **Plan Analyzer:** `allowed_paths: ["src/auth/"]`
- **governed_apply:** Rejects patches outside allowed_paths

### context_selector.py: Scope Configuration
**Synergy:** Plan Analyzer generates scope, context_selector uses it

- **Plan Analyzer:** `scope.paths`, `scope.read_only_context`
- **context_selector:** `get_context_for_phase(phase_spec)` reads scope config

---

## Example: Lovable Phase 0

### Input (Minimal Plan)

```json
{
  "run_id": "lovable-phase0",
  "phases": [
    {
      "phase_id": "protected-path",
      "goal": "Create src/autopack/lovable/ and add governance allowlist"
    },
    {
      "phase_id": "semantic-embeddings",
      "goal": "Add sentence-transformers backend with fail-closed validation"
    },
    {
      "phase_id": "browser-telemetry",
      "goal": "Implement POST /api/browser/telemetry endpoint"
    }
  ]
}
```

### Analysis Output

```
✅ CAN IMPLEMENT: 3 phases (100%)
⚠️  RISKY: 0 phases (0%)
❌ MANUAL REQUIRED: 0 phases (0%)

Overall Confidence: 85.0%
Estimated Duration: 7.0 days

PHASE BREAKDOWN:

✅ Protected-Path Strategy
   Feasibility: CAN_IMPLEMENT (90% confidence)
   Risk: HIGH | Decision: RISKY
   Auto-apply: No (manual approval required)
   Files to modify: ~2
   Core files: src/autopack/governed_apply.py

✅ Semantic Embeddings
   Feasibility: CAN_IMPLEMENT (85% confidence)
   Risk: MEDIUM | Decision: THRESHOLD
   Auto-apply: No
   Files to modify: ~2
   Core files: src/autopack/memory/embeddings.py
   ⛔ Blockers: sentence-transformers not installed

✅ Browser Telemetry
   Feasibility: CAN_IMPLEMENT (80% confidence)
   Risk: MEDIUM | Decision: THRESHOLD
   Auto-apply: No
   Files to modify: ~3
   Core files: src/autopack/main.py

INFRASTRUCTURE REQUIREMENTS:
  - pip install sentence-transformers torch

GOVERNANCE SCOPE:
  Allowed Paths:
    ✓ src/autopack/lovable/
    ✓ src/autopack/governed_apply.py
    ✓ src/autopack/memory/embeddings.py
    ✓ src/autopack/main.py

  Protected Paths:
    🔒 .git/
    🔒 .autonomous_runs/*/gold_set/
```

### Enhanced Config (for Execution)

```json
{
  "phases": [
    {
      "phase_id": "protected-path",
      "goal": "Create src/autopack/lovable/ and add governance allowlist",

      "analysis": {
        "feasibility": "CAN_IMPLEMENT",
        "confidence": 0.90,
        "risk_level": "HIGH",
        "decision_category": "RISKY",
        "auto_apply": false
      },

      "scope": {
        "paths": ["src/autopack/lovable/", "src/autopack/governed_apply.py"],
        "read_only_context": ["src/autopack/autonomous_executor.py"]
      },

      "success_criteria": [
        "src/autopack/lovable/ directory created",
        "LOVABLE_ALLOWED_PATHS added to governed_apply.py",
        "Symbol preservation: No existing functions removed"
      ],

      "validation_tests": [
        "pytest tests/autopack/test_governed_apply.py -v"
      ]
    }
  ]
}
```

---

## Limitations

### 1. LLM-Dependent
**Issue:** Analysis quality depends on LLM capabilities

**Mitigation:**
- Use GPT-4o or Claude Opus for analysis (smarter models)
- Temperature=0.1 for consistent analysis
- Structured JSON output reduces hallucination

### 2. Static Analysis
**Issue:** Doesn't execute code or run tests

**Mitigation:**
- BUILD-113 validates during execution
- governed_apply enforces at runtime
- Post-phase validation catches issues

### 3. Context Limits
**Issue:** Large codebases may exceed LLM context

**Mitigation:**
- Provide project context summary in plan description
- Future: Integrate with MemoryService for semantic search

---

## Future Enhancements

### 1. Vector Memory Integration
- Use MemoryService to search codebase for similar patterns
- Improve file scope accuracy with semantic search
- Detect similar past implementations

### 2. Codebase Scanning
- Automatically read key files (src/ structure)
- Extract architecture patterns
- Detect existing governance constraints

### 3. Historical Learning
- Learn from past autonomous runs
- Adjust confidence based on actual outcomes
- Improve duration estimates over time

### 4. Interactive Refinement
- Allow user to override analysis results
- Adjust feasibility classifications
- Add custom blockers/risks

---

## Files Created

```
src/autopack/
└── plan_analyzer.py                 ← Core analysis engine

scripts/
├── analyze_plan.py                  ← Standalone CLI tool
└── run_with_analysis.py             ← Integrated execution wrapper

docs/
├── PLAN_ANALYZER.md                 ← User documentation
└── BUILD-123_PLAN_ANALYZER.md       ← THIS FILE
```

---

## Testing

### Unit Tests (To Be Created)
```bash
# Test feasibility classification
pytest tests/autopack/test_plan_analyzer.py::test_feasibility_classification

# Test LLM response parsing
pytest tests/autopack/test_plan_analyzer.py::test_parse_phase_analysis

# Test execution order algorithm
pytest tests/autopack/test_plan_analyzer.py::test_recommend_execution_order

# Test blocker detection
pytest tests/autopack/test_plan_analyzer.py::test_extract_infrastructure_requirements
```

### Integration Tests
```bash
# Analyze Lovable Phase 0 plan
python scripts/analyze_plan.py .autonomous_runs/lovable-integration-v1/minimal_plan.json

# Run with analysis
python scripts/run_with_analysis.py .autonomous_runs/lovable-integration-v1/minimal_plan.json
```

---

## Comparison: Before vs After

### Before BUILD-123 (Manual Specification)

**Phase Documentation:**
```markdown
### Phase 0.2: Semantic Embeddings (2 days)

**Implementation Steps:**

**Day 1:**
1. Open `src/autopack/memory/embeddings.py`
2. Add function:
   ```python
   def _sentence_transformers_embed(text: str) -> np.ndarray:
       model = SentenceTransformer('all-MiniLM-L6-v2')
       return model.encode(text)
   ```
3. Update `embed_text()` to call `_sentence_transformers_embed()`

**Day 2:**
1. Add validation function:
   ```python
   def validate_semantic_embeddings_for_lovable():
       backend = get_embedding_backend()
       if backend == "hash":
           raise RuntimeError("Lovable requires semantic embeddings")
   ```
2. Write unit tests in `tests/autopack/memory/test_embeddings.py`
```

**Problem:** Over-specifies HOW, defeats autonomous purpose

### After BUILD-123 (Autonomous Analysis)

**Minimal Plan:**
```json
{
  "phase_id": "semantic-embeddings",
  "goal": "Add sentence-transformers backend with fail-closed validation for Lovable features"
}
```

**Analyzed Plan:**
```json
{
  "phase_id": "semantic-embeddings",
  "goal": "Add sentence-transformers backend...",

  "analysis": {
    "feasibility": "CAN_IMPLEMENT",
    "confidence": 0.85,
    "decision_category": "THRESHOLD"
  },

  "scope": {
    "paths": ["src/autopack/memory/embeddings.py"],
    "read_only_context": ["src/autopack/memory/memory_service.py"]
  },

  "success_criteria": [
    "Semantic similarity test passes: cosine_sim(related) > 0.7"
  ]
}
```

**Execution:**
- Builder reads goal
- Builder explores `src/autopack/memory/embeddings.py`
- Builder generates implementation (figures out HOW)
- Governed apply enforces scope
- BUILD-113 validates patch

**Benefit:** Builder autonomy preserved, governance enforced

---

## Conclusion

BUILD-123 solves the **over-specification problem** by separating:
- **WHAT to achieve** (goals, constraints) ← Plan Analyzer generates
- **HOW to achieve it** (implementation) ← Builder figures out

This maintains autonomous flexibility while ensuring safe, structured execution through analyzed governance scope and quality gates.

**Status:** ✅ Implementation Ready
**Next Step:** Test on Lovable Phase 0 minimal plan

---

**Created:** 2025-12-22
**Author:** Claude Sonnet 4.5
**Build:** BUILD-123
