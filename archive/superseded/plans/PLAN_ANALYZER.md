# Plan Analyzer - Autonomous Pre-Flight Analysis

**Status:** BUILD-123 (2025-12-22)
**Purpose:** Automatically analyze any unorganized implementation plan and generate feasibility assessment, quality gates, and governance scope

---

## Overview

The **Plan Analyzer** is a meta-layer that runs BEFORE autonomous execution to ensure safe, structured implementation. It analyzes ANY implementation plan (organized or unorganized) and automatically generates:

1. **Feasibility Assessment** - Which phases can be implemented autonomously vs manually
2. **Quality Gates** - Validation criteria and success metrics for each phase
3. **Governance Scope** - Allowed paths, protected paths, and approval requirements
4. **Risk Classification** - Decision categories (CLEAR_FIX, THRESHOLD, RISKY, AMBIGUOUS)

This addresses the problem of over-specifying implementation details while still providing necessary constraints for safe autonomous execution.

---

## Architecture

```
┌─────────────────────┐
│ Unorganized Plan    │
│ (JSON/YAML/Markdown)│
└──────────┬──────────┘
           │
           ▼
┌─────────────────────────────────┐
│     Plan Analyzer (LLM)         │
│                                 │
│  1. Feasibility Assessment      │
│  2. File Scope Analysis         │
│  3. Risk Classification         │
│  4. Quality Gates Generation    │
│  5. Blocker Detection           │
│  6. Dependency Analysis         │
└──────────┬──────────────────────┘
           │
           ▼
┌─────────────────────────────────┐
│  Enhanced Run Config            │
│                                 │
│  - Governance scope (paths)     │
│  - Approval requirements        │
│  - Success criteria             │
│  - Validation tests             │
│  - Metrics targets              │
└──────────┬──────────────────────┘
           │
           ▼
┌─────────────────────────────────┐
│  Autonomous Executor            │
│                                 │
│  Builder interprets high-level  │
│  goals within governance scope  │
└─────────────────────────────────┘
```

---

## Usage

### Standalone Analysis

```bash
# Analyze a plan (outputs human-readable summary + JSON)
python scripts/analyze_plan.py my_plan.json

# Save detailed analysis to file
python scripts/analyze_plan.py my_plan.json --output analysis.json

# Specify workspace directory
python scripts/analyze_plan.py my_plan.json --workspace /path/to/project
```

### Integrated Execution

```bash
# Run with automatic pre-flight analysis
python scripts/run_with_analysis.py my_plan.json

# Skip analysis (trust existing plan)
python scripts/run_with_analysis.py my_plan.json --skip-analysis

# Customize execution
python scripts/run_with_analysis.py my_plan.json --run-id my-feature --max-iterations 20
```

---

## Input Format

The Plan Analyzer accepts **any** plan format with minimal structure:

### Minimal Plan (Unorganized)

```json
{
  "run_id": "my-feature",
  "description": "Add user authentication to the application",
  "phases": [
    {
      "phase_id": "auth-backend",
      "phase_name": "Backend Authentication",
      "goal": "Implement JWT-based authentication with login/logout endpoints"
    },
    {
      "phase_id": "auth-frontend",
      "phase_name": "Frontend Login Form",
      "goal": "Create login form component with token storage"
    }
  ]
}
```

### Organized Plan (With Details)

```json
{
  "run_id": "my-feature",
  "phases": [
    {
      "phase_id": "auth-backend",
      "phase_name": "Backend Authentication",
      "goal": "Implement JWT-based authentication",
      "description": "Add JWT token generation, validation, and refresh logic",
      "scope": {
        "paths": ["src/auth/", "src/api/endpoints/auth.py"],
        "read_only_context": ["src/database/models.py"]
      },
      "success_criteria": [
        "Login endpoint returns valid JWT token",
        "Protected endpoints reject invalid tokens"
      ]
    }
  ]
}
```

The analyzer will **enhance** minimal plans with missing fields.

---

## Output Format

### Analysis Result Structure

```json
{
  "run_id": "my-feature",
  "total_phases": 2,
  "can_implement_count": 1,
  "risky_count": 1,
  "manual_required_count": 0,

  "overall_feasibility": "RISKY",
  "overall_confidence": 0.65,
  "estimated_total_duration_days": 5.0,

  "critical_blockers": [
    "Frontend integration requires React expertise"
  ],

  "infrastructure_requirements": [
    "pip install pyjwt cryptography"
  ],

  "global_allowed_paths": [
    "src/auth/",
    "src/api/endpoints/auth.py",
    "src/frontend/components/LoginForm.tsx"
  ],

  "protected_paths": [
    ".git/",
    "venv/",
    ".autonomous_runs/*/gold_set/"
  ],

  "recommended_execution_order": [
    "auth-backend",
    "auth-frontend"
  ],

  "phases": [
    {
      "phase_id": "auth-backend",
      "phase_name": "Backend Authentication",
      "feasibility": "CAN_IMPLEMENT",
      "confidence": 0.80,
      "risk_level": "MEDIUM",
      "decision_category": "THRESHOLD",
      "auto_apply": false,

      "estimated_files_modified": 3,
      "core_files_affected": [
        "src/auth/jwt_service.py",
        "src/api/endpoints/auth.py"
      ],

      "allowed_paths": [
        "src/auth/",
        "src/api/endpoints/auth.py"
      ],

      "readonly_context": [
        "src/database/models.py",
        "src/config.py"
      ],

      "blockers": [],
      "risks": [
        "JWT secret key must be configured securely"
      ],

      "dependencies": [],

      "success_criteria": [
        "Login endpoint returns valid JWT token",
        "Token validation works correctly",
        "All auth tests pass"
      ],

      "validation_tests": [
        "pytest tests/auth/test_jwt.py -v",
        "pytest tests/api/test_auth_endpoints.py -v"
      ],

      "metrics": {
        "test_coverage": ">=90%",
        "security_vulnerabilities": "0"
      },

      "estimated_duration_days": 2.0,
      "complexity_score": 5
    },
    {
      "phase_id": "auth-frontend",
      "feasibility": "RISKY",
      "confidence": 0.50,
      "risk_level": "HIGH",
      "decision_category": "RISKY",
      "auto_apply": false,
      "blockers": [
        "Frontend integration requires React expertise"
      ],
      "estimated_duration_days": 3.0,
      "complexity_score": 7
    }
  ]
}
```

---

## Feasibility Classification

### CAN_IMPLEMENT (75-90% confidence)
**Autonomous execution safe**

Criteria:
- Clear, well-defined goal
- Isolated changes (few files)
- No external dependencies
- Low architectural impact
- Existing patterns to follow

Examples:
- Add data validation to existing model
- Create new API endpoint following existing patterns
- Add unit tests for existing functionality

### RISKY (45-65% confidence)
**Supervised execution recommended**

Criteria:
- Multiple files affected
- Some architectural changes
- Integration complexity
- Frontend/UI changes
- Medium external dependencies

Examples:
- Add frontend component (requires React knowledge)
- Refactor authentication flow
- Integrate third-party API

### MANUAL_REQUIRED (20-40% confidence)
**Manual implementation only**

Criteria:
- Major architectural changes
- External service dependencies
- Requires specialized expertise
- High-risk core functionality
- Unclear requirements

Examples:
- Migrate database schema
- Integrate external payment processor
- Rewrite core orchestration logic

---

## Decision Categories (BUILD-113)

### CLEAR_FIX (LOW risk)
**Auto-apply patches without approval**

Characteristics:
- Data files only (JSON, YAML, config)
- Isolated bug fixes
- No architectural changes
- Reversible changes

Example:
```json
{
  "decision_category": "CLEAR_FIX",
  "auto_apply": true,
  "risk_level": "LOW"
}
```

### THRESHOLD (MEDIUM risk)
**Manual review before apply**

Characteristics:
- 100-200 lines of changes
- Multiple files (2-5)
- Medium complexity
- Some integration points

Example:
```json
{
  "decision_category": "THRESHOLD",
  "auto_apply": false,
  "risk_level": "MEDIUM"
}
```

### RISKY (HIGH risk)
**Manual approval required**

Characteristics:
- Governance model changes
- Core architecture modifications
- Protected paths affected
- >200 lines of changes

Example:
```json
{
  "decision_category": "RISKY",
  "auto_apply": false,
  "risk_level": "HIGH"
}
```

### AMBIGUOUS
**Clarification needed**

Characteristics:
- Unclear requirements
- Multiple valid approaches
- Missing context
- Conflicting constraints

Example:
```json
{
  "decision_category": "AMBIGUOUS",
  "auto_apply": false,
  "blockers": ["UX approach unclear - modal vs inline form?"]
}
```

---

## Quality Gates

The analyzer generates **phase-specific quality gates**:

### Success Criteria
Measurable validation criteria:
- "All tests pass: pytest tests/auth/ -v"
- "API returns 200 status for valid credentials"
- "Token validation rejects expired tokens"

### Validation Tests
Specific test commands:
- "pytest tests/autopack/test_auth.py -v"
- "curl http://localhost:8000/api/auth/login -X POST -d '{...}'"

### Metrics
Quantitative targets:
- `{"test_coverage": ">=90%"}`
- `{"token_reduction": ">=40%"}`
- `{"security_vulnerabilities": "0"}`

---

## Governance Scope

### Allowed Paths
Files/patterns that MAY be modified:
```json
{
  "allowed_paths": [
    "src/auth/",
    "src/api/endpoints/auth.py",
    "tests/auth/"
  ]
}
```

### Read-Only Context
Files to read for context but NOT modify:
```json
{
  "readonly_context": [
    "src/database/models.py",
    "src/config.py",
    "src/main.py"
  ]
}
```

### Protected Paths
Files that should NEVER be modified:
```json
{
  "protected_paths": [
    ".git/",
    "venv/",
    ".autonomous_runs/*/gold_set/"
  ]
}
```

---

## Blocker Detection

The analyzer identifies **critical blockers** that must be resolved:

### Infrastructure Blockers
```json
{
  "blockers": [
    "Hash embeddings not semantic - Phase 1 requires semantic embeddings",
    "Morph API subscription required ($100/month)"
  ],
  "infrastructure_requirements": [
    "pip install sentence-transformers torch",
    "Morph API key (MORPH_API_KEY)"
  ]
}
```

### Expertise Blockers
```json
{
  "blockers": [
    "Frontend integration requires React expertise",
    "Database migration requires PostgreSQL DBA knowledge"
  ]
}
```

### Dependency Blockers
```json
{
  "blockers": [],
  "dependencies": [
    "auth-backend"  // Must complete before auth-frontend
  ]
}
```

---

## Execution Order

The analyzer recommends **optimal execution order** using:

1. **Topological sort** (dependencies)
2. **Feasibility priority** (CAN_IMPLEMENT > RISKY > MANUAL)
3. **Complexity scoring** (simpler first for quick wins)

Example:
```json
{
  "recommended_execution_order": [
    "auth-backend",     // CAN_IMPLEMENT, no dependencies
    "auth-middleware",  // CAN_IMPLEMENT, depends on auth-backend
    "auth-frontend",    // RISKY, depends on auth-backend
    "auth-admin-panel"  // MANUAL_REQUIRED, depends on all above
  ]
}
```

---

## Integration with Autonomous Executor

The Plan Analyzer **enhances** the run config before execution:

### Before Analysis (Minimal)

```json
{
  "phases": [
    {
      "phase_id": "auth-backend",
      "goal": "Implement JWT authentication"
    }
  ]
}
```

### After Analysis (Enhanced)

```json
{
  "phases": [
    {
      "phase_id": "auth-backend",
      "goal": "Implement JWT authentication",

      "analysis": {
        "feasibility": "CAN_IMPLEMENT",
        "confidence": 0.80,
        "risk_level": "MEDIUM",
        "decision_category": "THRESHOLD",
        "auto_apply": false
      },

      "scope": {
        "paths": ["src/auth/", "src/api/endpoints/auth.py"],
        "read_only_context": ["src/database/models.py"]
      },

      "success_criteria": [
        "Login endpoint returns valid JWT token",
        "Token validation works correctly"
      ],

      "validation_tests": [
        "pytest tests/auth/test_jwt.py -v"
      ]
    }
  ]
}
```

The **Builder** still interprets the high-level goal, but now works within the analyzed governance scope.

---

## Example Workflow

### 1. Create Minimal Plan

```json
{
  "run_id": "lovable-phase0",
  "phases": [
    {
      "phase_id": "protected-path",
      "goal": "Create src/autopack/lovable/ subtree and add governance allowlist"
    },
    {
      "phase_id": "semantic-embeddings",
      "goal": "Add sentence-transformers backend with fail-closed validation"
    }
  ]
}
```

### 2. Run Analysis

```bash
python scripts/run_with_analysis.py lovable_plan.json
```

### 3. Review Analysis Output

```
IMPLEMENTATION PLAN ANALYSIS
================================================================================

Run ID: lovable-phase0
Total Phases: 2

FEASIBILITY ASSESSMENT
================================================================================

✅ CAN IMPLEMENT: 2 phases (100%)
⚠️  RISKY: 0 phases (0%)
❌ MANUAL REQUIRED: 0 phases (0%)

Overall Feasibility: CAN_IMPLEMENT
Overall Confidence: 85.0%
Estimated Duration: 4.0 days

PHASE BREAKDOWN
================================================================================

✅ Protected-Path Strategy
   Feasibility: CAN_IMPLEMENT (90% confidence)
   Risk: MEDIUM | Decision: THRESHOLD
   Auto-apply: No
   Duration: 2.0 days | Complexity: 5/10
   Files to modify: ~2
   Core files: src/autopack/governed_apply.py

✅ Semantic Embeddings
   Feasibility: CAN_IMPLEMENT (80% confidence)
   Risk: MEDIUM | Decision: THRESHOLD
   Auto-apply: No
   Duration: 2.0 days | Complexity: 6/10
   Files to modify: ~2
   Core files: src/autopack/memory/embeddings.py

RECOMMENDED EXECUTION ORDER
================================================================================

 1. ✅ protected-path (2.0 days)
 2. ✅ semantic-embeddings (2.0 days)

GOVERNANCE SCOPE
================================================================================

Allowed Paths (4):
  ✓ src/autopack/lovable/
  ✓ src/autopack/governed_apply.py
  ✓ src/autopack/memory/embeddings.py
  ✓ tests/autopack/

Protected Paths (6):
  🔒 .git/
  🔒 venv/
  🔒 .autonomous_runs/*/gold_set/
```

### 4. Autonomous Execution Begins

The executor receives the **enhanced config** with:
- Governance scope (allowed paths)
- Success criteria (validation targets)
- Approval requirements (manual review)

The **Builder** interprets goals and generates patches **within scope**.

---

## Benefits

### 1. **No Over-Specification**
- Input: High-level goals only
- Builder figures out implementation details
- Maintains autonomous flexibility

### 2. **Safe Governance**
- Analyzed scope prevents unintended modifications
- Risk classification enforces approval gates
- Blocker detection prevents broken executions

### 3. **Quality Assurance**
- Automatic success criteria generation
- Validation test recommendations
- Metrics targets for go/no-go decisions

### 4. **Predictability**
- Confidence scores for stakeholder communication
- Duration estimates for planning
- Execution order for dependencies

---

## Limitations

### 1. **LLM-Dependent**
- Analysis quality depends on LLM capabilities
- May miss edge cases in unfamiliar codebases
- Requires good context about project structure

**Mitigation:** Use GPT-4 or Claude Opus for analysis (smarter models)

### 2. **Static Analysis**
- Doesn't execute code or run tests
- Can't detect runtime blockers
- File scope is estimated, not definitive

**Mitigation:** Execution still validates via BUILD-113 decision analysis

### 3. **Context Limits**
- Large codebases may exceed LLM context
- Limited codebase understanding without vector memory

**Mitigation:** Provide project context summary in plan description

---

## Future Enhancements

### 1. **Vector Memory Integration**
- Use MemoryService to search codebase for similar patterns
- Improve file scope accuracy with semantic search
- Detect similar past implementations

### 2. **Codebase Scanning**
- Automatically read key files (e.g., src/ structure)
- Extract architecture patterns
- Detect existing governance constraints

### 3. **Historical Analysis**
- Learn from past autonomous runs
- Adjust confidence based on actual outcomes
- Improve duration estimates over time

### 4. **Interactive Refinement**
- Allow user to override analysis results
- Adjust feasibility classifications
- Add custom blockers/risks

---

## Related Features

- **BUILD-113:** Autonomous Investigation (proactive decision analysis)
- **BUILD-114:** Structured Edit Support (large scope handling)
- **BUILD-115:** API-Only Mode (no direct DB dependencies)
- **governed_apply.py:** Symbol preservation + structural similarity
- **context_selector.py:** JIT context selection with scope config

---

**Created:** 2025-12-22 (BUILD-123)
**Status:** Implementation Ready
**Dependencies:** llm_service.py (LLM calls), autonomous_executor.py (integration)
