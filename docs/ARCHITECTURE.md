# Autopack Architecture

**Last Updated**: 2025-12-28  
**Purpose**: High-level system overview for developers and contributors

---

## System Overview

Autopack is an **autonomous build system** that executes multi-phase implementation plans using LLMs (Claude, GPT, Gemini). It provides:

- **Autonomous Execution**: Phases execute without human intervention (with safety gates)
- **Quality Enforcement**: Test baselines, deliverables validation, risk assessment
- **Self-Healing**: Diagnostics, deep retrieval, iterative investigation
- **Governance**: Protected paths, approval workflows, audit trails

---

## Core Components

### 1. Autonomous Executor
**File**: `src/autopack/autonomous_executor.py` (8000+ lines)  
**Purpose**: Main orchestration engine

- Fetches phases from API (`GET /runs/{run_id}`)
- Executes phases via Builder → Auditor → Quality Gate pipeline
- Handles retries, escalation, approval requests
- Integrates diagnostics, learning system, telemetry

**Key Methods**:
- `execute_phase()` - Main phase execution loop
- `_execute_phase_with_recovery()` - Retry/escalation logic
- `_load_repository_context()` - Smart context loading (scope-aware, targeted, heuristic)

### 2. Builder (LLM Code Generation)
**Files**: `src/autopack/anthropic_clients.py`, `src/autopack/openai_clients.py`, `src/autopack/gemini_clients.py`  
**Purpose**: Generate code changes via LLM

- Supports multiple providers (Anthropic, OpenAI, Gemini)
- Two output modes: **unified diff** (traditional) or **structured edits** (JSON operations)
- Token budget management with dynamic escalation
- Model selection: Sonnet 4.5 (default) → Opus 4 (escalation) → GPT-4o (fallback)

**Output Formats**:
- **Unified Diff**: `diff --git a/file.py b/file.py` (for small scopes)
- **Structured Edits**: JSON with `create_file`, `modify_file`, `delete_file` operations (for large scopes ≥30 files)

### 3. Governed Apply (Patch Application)
**File**: `src/autopack/governed_apply.py`  
**Purpose**: Safe patch application with governance checks

- **Protected Paths**: `.git/`, `.autonomous_runs/`, `autopack.db` (never modified)
- **Allowed Paths**: Scope-based validation (only modify files in phase scope)
- **Symbol Preservation**: Prevents accidental deletion of functions/classes
- **Structural Similarity**: Validates patches match file structure

**Safety Mechanisms**:
- Pre-apply validation (scope, protected paths, symbols)
- Git save points before risky changes
- Automatic rollback on validation failure

### 4. Quality Gate
**File**: `src/autopack/quality_gate.py`  
**Purpose**: Enforce quality standards before phase completion

- **Risk Assessment**: Analyzes patch for protected paths, large deletions, complexity
- **Test Validation**: Runs pytest, compares against baseline
- **Deliverables Check**: Ensures required files created/modified
- **Blocking Conditions**: New test failures, collection errors, missing deliverables

**Quality Levels**:
- `passed` - All checks passed, phase can complete
- `needs_review` - Warnings present, human review recommended
- `blocked` - Critical issues, phase cannot complete

### 5. Phase Finalizer
**File**: `src/autopack/phase_finalizer.py`  
**Purpose**: Authoritative completion gate (replaces old quality gate)

- **Test Baseline Comparison**: Detects new failures, regressions, flaky tests
- **Deliverables Validation**: Verifies files exist on filesystem
- **Quality Report Integration**: Considers risk, coverage, test results
- **Decision**: `COMPLETE`, `BLOCKED`, or `FAILED`

**Key Insight**: Separates pre-existing failures from new regressions (delta-based gating)

### 6. Diagnostics System
**Files**: `src/autopack/diagnostics/`  
**Purpose**: Autonomous troubleshooting and failure analysis

**Components**:
- **DiagnosticsAgent**: Runs probes, collects evidence, generates reports
- **Deep Retrieval**: Escalates to SOT docs, memory, run artifacts when Stage 1 insufficient
- **Second Opinion**: Optional strong-model triage (Claude Opus 4)
- **Handoff Bundle**: Generates Cursor-ready context for human takeover

**Trigger Conditions**:
- Empty/minimal error messages
- Repeated failures (≥2 attempts)
- Ambiguous root cause
- Generic error phrases ("unknown error", "internal error")

### 7. Learning System
**File**: `src/autopack/learned_rules.py`  
**Purpose**: Capture and reuse patterns from past runs

- **Learned Rules**: Persistent patterns (e.g., "Always add __init__.py for new packages")
- **Run Hints**: Temporary guidance for current run (e.g., "Wrong path: tracer_bullet/ → src/autopack/research/tracer_bullet/")
- **Promotion**: Hints promoted to rules after 3+ occurrences
- **Scope Matching**: Rules apply to specific file patterns or globally

### 8. Manifest Generator
**File**: `src/autopack/manifest_generator.py`  
**Purpose**: Generate phase plans from high-level goals

- **Deliverables-Aware**: Infers category from file paths (not just goal text)
- **Pattern Matching**: Uses keyword anchors, file patterns, category templates
- **Scope Expansion**: Adds context files (tests, docs, related modules)
- **Plan Analyzer Integration**: Optional LLM-based feasibility assessment

**Category Inference** (BUILD-128):
- `src/autopack/*.py` → backend
- `tests/*.py` → tests
- `docs/*.md` → docs
- `alembic/versions/*.py` → database

---

## Data Flow

### Phase Execution Pipeline

```
1. API Fetch
   GET /runs/{run_id} → phases (QUEUED)
   ↓
2. Context Loading
   Scope-aware → Targeted → Heuristic
   ↓
3. Builder (LLM)
   Goal + Context → Patch (diff or structured edits)
   ↓
4. BUILD-113 Decision (if enabled)
   Risk assessment → CLEAR_FIX / RISKY / AMBIGUOUS
   ↓
5. Governed Apply
   Validate scope → Check protected paths → Apply patch
   ↓
6. Quality Gate
   Run tests → Check deliverables → Assess risk
   ↓
7. Phase Finalizer
   Compare baseline → Validate deliverables → COMPLETE / BLOCKED
   ↓
8. API Update
   PUT /runs/{run_id}/phases/{phase_id} (status=COMPLETE)
```

### Failure Recovery Flow

```
1. Phase Fails
   ↓
2. Diagnostics Agent (Stage 1)
   Run probes → Collect evidence → Generate handoff bundle
   ↓
3. Deep Retrieval (Stage 2 - if triggered)
   Retrieve SOT docs → Memory entries → Run artifacts
   ↓
4. Second Opinion (optional)
   Strong model triage → Hypotheses → Next probes
   ↓
5. Retry with Enhanced Context
   Learning hints + diagnostics → Builder retry
   ↓
6. Escalation (if retry fails)
   Sonnet → Opus → GPT-4o → Human approval
```

---

## Key Architectural Patterns

### 1. Scope-First Context Loading
**Problem**: Targeted context loaders (frontend, docker) loaded root-level files, violating scope  
**Solution**: Check `scope.paths` FIRST, before pattern-based targeting

### 2. Deliverables-Aware Manifest
**Problem**: Pattern matching on goal text unreliable ("completion" matched frontend dashboard)  
**Solution**: Infer category from deliverable file paths (BUILD-128)

### 3. Delta-Based Test Gating
**Problem**: Pre-existing test failures blocked new phases  
**Solution**: Capture T0 baseline, only block on NEW failures (Phase Finalizer)

### 4. Overhead Model Token Estimation
**Problem**: Linear scaling (tokens ∝ deliverables) caused severe overestimation  
**Solution**: Separate fixed overhead + marginal cost per file (BUILD-129)

### 5. Structured Edit Fallback
**Problem**: Large scopes (≥30 files) hit truncation with unified diff  
**Solution**: Auto-switch to structured edits (JSON operations) for large contexts (BUILD-114)

---

## Safety Mechanisms

### Protected Paths (Never Modified)
- `.git/` - Git internals
- `.autonomous_runs/` - Run artifacts, gold sets
- `autopack.db` - Database file
- `src/autopack/governed_apply.py` - Governance system itself

### Approval Workflows
- **Telegram Integration**: Mobile approval for risky changes (BUILD-107)
- **Deletion Safeguards**: Block >200 line deletions, notify 100-200 lines (BUILD-108)
- **Governance Requests**: Self-negotiation for protected path access (BUILD-127)

### Rollback Mechanisms
- **Git Save Points**: Tag before risky changes (`save-before-{phase_id}`)
- **Automatic Rollback**: Revert on test failure or validation error
- **Audit Trail**: All decisions logged with rationale

---

## Integration Points

### API Server
**File**: `src/autopack/main.py`  
**Endpoints**:
- `GET /runs/{run_id}` - Fetch run state
- `PUT /runs/{run_id}/phases/{phase_id}` - Update phase status
- `POST /approval/request` - Request human approval
- `GET /approval/status/{id}` - Poll approval decision

### Database
**File**: `src/autopack/models.py`  
**Tables**:
- `runs` - Run metadata (id, state, created_at)
- `phases` - Phase state (phase_id, status, retry_attempt)
- `approval_requests` - Governance approvals
- `token_estimation_v2_events` - Telemetry data

### Telemetry
**Files**: `src/autopack/anthropic_clients.py` (logging), `scripts/analyze_token_telemetry_v3.py` (analysis)  
**Purpose**: Track token predictions vs actuals for calibration

---

## Configuration

### Environment Variables
```bash
ANTHROPIC_API_KEY=sk-...          # Claude API key
OPENAI_API_KEY=sk-...             # GPT API key (fallback)
DATABASE_URL=sqlite:///autopack.db
TELEGRAM_BOT_TOKEN=...            # Approval notifications
TELEMETRY_DB_ENABLED=1            # Enable telemetry persistence
```

### Feature Flags
```bash
--enable-autonomous-fixes         # BUILD-113 proactive decisions
--enable-deep-retrieval           # Stage 2 diagnostics
--enable-second-opinion           # Strong model triage
--enable-plan-analyzer            # Pre-flight feasibility
```

---

## References

**Key Documentation**:
- [README.md](../README.md) - Getting started, usage examples
- [CONTRIBUTING.md](CONTRIBUTING.md) - Development setup, testing
- [BUILD_HISTORY.md](BUILD_HISTORY.md) - Feature changelog
- [DEBUG_LOG.md](DEBUG_LOG.md) - Issue tracking

**Implementation Guides**:
- [BUILD-112: Diagnostics Parity](BUILD-112_DIAGNOSTICS_PARITY_CURSOR.md)
- [BUILD-113: Autonomous Investigation](BUILD-113_ITERATIVE_AUTONOMOUS_INVESTIGATION.md)
- [BUILD-127: Self-Healing Governance](BUILD-127_REVISED_PLAN.md)
- [BUILD-128: Deliverables-Aware Manifest](BUILD-128_ROOT_CAUSE_AND_PREVENTION.md)
- [BUILD-129: Token Budget Intelligence](BUILD-129_PHASE1_VALIDATION_COMPLETE.md)

---

**Total Lines**: 180 (within ≤180 line constraint)  
**Style**: Bullet-style with code examples  
**Scope**: High-level overview, no detailed API docs
