# Autopack Architecture

**Last Updated**: 2026-01-11 (refreshed for path correctness)
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
- `scripts/migrations/*.py` → database (scripts-first canonical; see DEC-048)

### 9. Research Pipeline Architecture
**Files**: `src/autopack/research/orchestrator.py`, `src/autopack/research/analysis/`, `src/autopack/research/artifact_generators.py`
**Purpose**: Multi-phase research workflow with cost analysis, state tracking, and artifact generation

**Key Components**:
- **ResearchOrchestrator**: Coordinates research workflows with 24-hour caching and phase scheduling
- **CostEffectivenessAnalyzer**: Projects costs and value across development, infrastructure, operational dimensions
- **BudgetEnforcer**: Gates expensive research phases based on budget thresholds
- **ResearchStateTracker**: Maintains state across research cycles and phases
- **FollowupResearchTrigger**: Identifies conditions for initiating follow-up research (IMP-RES-002)
- **ArtifactGenerators**: Produces monetization, deployment, and CI/CD guidance artifacts

**Architecture Layers**:
1. **Discovery Layer**: Gathers market, technical, competitive data via MCP registry and project history
2. **Analysis Layer**: Cost-effectiveness, state tracking, pattern extraction from historical projects
3. **Generation Layer**: Transforms analysis into actionable artifacts (deployment configs, runbooks, pricing strategies)
4. **Enforcement Layer**: Budget checks prevent expensive research when cost-benefit unfavorable

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

### Research Pipeline Flow (Wave 2-3 Enhancement)

```
1. Research Bootstrap
   Parsed idea → Idea hash (cache check)
   ↓
2. Orchestrator Coordination
   ResearchOrchestrator schedules phases:
   - Analysis Phase: Cost-effectiveness, state tracking
   - Discovery Phase: Market/tech/competitive data
   - Generation Phase: Artifact creation
   ↓
3. Cost Analysis Gate
   BudgetEnforcer checks: cost_benefit_ratio > threshold?
   ├─ YES → Proceed to research
   └─ NO → Skip expensive phases, return cached guidance
   ↓
4. State Tracking
   ResearchStateTracker persists:
   - Phase completion status
   - Decision outcomes
   - Artifact generation results
   ↓
5. Artifact Generation
   ArtifactGenerators produce:
   - Monetization guidance (e-commerce, SaaS, content)
   - Deployment architectures (Docker, K8s, serverless)
   - CI/CD pipeline templates (GitHub Actions, GitLab CI)
   - Operational runbooks
   ↓
6. Follow-up Research Trigger
   FollowupResearchTrigger evaluates:
   - Autopilot health gates
   - Decision quality metrics
   - Feasibility reassessment
   → Initiates new research cycle if conditions met
   ↓
7. Cache & Return
   Store results in cache (24h TTL)
   Return to caller (API/autopilot)
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

### 6. Budget-Gated Research Phases (IMP-RES-002)
**Problem**: Expensive research runs (multiple agent orchestrations) consume budget without ROI assessment
**Solution**: CostEffectivenessAnalyzer projects value; BudgetEnforcer gates phases by cost-benefit ratio
**Impact**: Skip expensive market research if budget exhausted or decision clarity high enough

### 7. State-Aware Research Cycles (IMP-AUT-001)
**Problem**: Research triggering from autopilot lacks decision continuity across phases
**Solution**: ResearchStateTracker maintains session state; FollowupResearchTrigger references past decisions
**Benefit**: Avoid redundant research; reuse cached analysis when project characteristics unchanged

### 8. Cost-Aware Artifact Generation (IMP-RES-001, IMP-RES-003, IMP-RES-004)
**Problem**: Deployment/CI/CD/monetization guidance static, not informed by project cost profile
**Solution**: Artifact generators consume CostEffectivenessAnalyzer output; recommend cost-optimal solutions
**Example**: High-cost project → recommend serverless + multi-cloud; low-cost → single cloud + manual ops

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

## Research Pipeline Architecture Diagrams

### 1. Research Pipeline Component Hierarchy

```
┌─────────────────────────────────────────────────────────────┐
│                   ResearchOrchestrator                       │
│         (Coordinates research sessions & phases)             │
└─────────────────────────────────────────────────────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        │                     │                     │
        ▼                     ▼                     ▼
┌──────────────────┐ ┌──────────────────┐ ┌──────────────────┐
│  Discovery Layer │ │   Analysis Layer │ │ Generation Layer │
│                  │ │                  │ │                  │
│ • MCP Registry   │ │ • Cost Analysis  │ │ • Monetization   │
│ • Web Discovery  │ │ • State Tracker  │ │ • Deployment     │
│ • Project        │ │ • Budget         │ │ • CI/CD          │
│   History        │ │   Enforcement    │ │ • Runbooks       │
│ • Pattern        │ │ • Followup       │ │                  │
│   Extraction     │ │   Trigger        │ │                  │
└──────────────────┘ └──────────────────┘ └──────────────────┘
        │                     │                     │
        └─────────────────────┼─────────────────────┘
                              │
                    ┌─────────▼──────────┐
                    │  Autopilot/API    │
                    │  (Consume Results) │
                    └────────────────────┘
```

### 2. Cost Analysis Integration Flow

```
Project Idea
    │
    ▼
┌─────────────────────────────────────────────────┐
│ CostEffectivenessAnalyzer                       │
│                                                 │
│ Analyzes:                                       │
│ • Development costs (build vs buy)              │
│ • Infrastructure (scaling models)               │
│ • Service costs (SaaS, APIs)                    │
│ • Operational overhead                         │
│ • Hidden costs (vendor lock-in, migration)      │
└─────────────────────────────────────────────────┘
    │
    ├─ Year 1: $X ────┐
    ├─ Year 3: $Y ────┤─── Cost Projections
    ├─ Year 5: $Z ────┤    (scaling factors)
    └─ Value Score ───┘
         │
         ▼
    ┌──────────────────────────────────────────┐
    │ BudgetEnforcer Gate                      │
    │                                          │
    │ Decision Logic:                          │
    │ if cost_effectiveness > threshold →      │
    │     PROCEED with research                │
    │ else →                                   │
    │     SKIP expensive phases (save budget)  │
    └──────────────────────────────────────────┘
         │
         ├─ PROCEED ─────────────────────┐
         │                               │
         ▼                               ▼
    ┌─────────────────────┐      ┌────────────────┐
    │ Deep Research       │      │ Return Cached  │
    │ (Multi-phase)       │      │ Guidance       │
    └─────────────────────┘      └────────────────┘
```

### 3. State Tracking & Research Cycles

```
Autopilot Health Gate Triggered
    │
    ▼
┌─────────────────────────────────────────────────┐
│ ResearchStateTracker                            │
│                                                 │
│ Maintains:                                      │
│ • Session ID & timestamp                       │
│ • Phase completion flags                       │
│ • Decision outcomes                            │
│ • Artifact generation status                   │
│ • Cost metrics                                 │
└─────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────┐
│ FollowupResearchTrigger                         │
│                                                 │
│ Evaluates conditions:                           │
│ • Decision quality < threshold?                │
│ • Time since last research > TTL?               │
│ • Project characteristics changed?              │
│ • Feasibility metrics shifted?                  │
└─────────────────────────────────────────────────┘
    │
    ├─ All conditions met ──────────────────┐
    │                                       │
    ▼                                       ▼
New Research Cycle                   Cache Valid
(with enhanced context)          (reuse results)
```

### 4. Artifact Generation Pipeline

```
Analysis Complete
    │
    ▼
┌────────────────────────────────────────────────────┐
│ ArtifactGenerators                                │
│                                                  │
│ ┌──────────────────────────────────────────────┐ │
│ │ Monetization (IMP-RES-001)                   │ │
│ │  → Subscription models                       │ │
│ │  → Pricing strategies                        │ │
│ │  → Revenue projections                       │ │
│ └──────────────────────────────────────────────┘ │
│                                                  │
│ ┌──────────────────────────────────────────────┐ │
│ │ Deployment (IMP-RES-003)                     │ │
│ │  → Architecture recommendations              │ │
│ │  → Docker/K8s/Serverless templates           │ │
│ │  → Infrastructure-as-Code templates          │ │
│ └──────────────────────────────────────────────┘ │
│                                                  │
│ ┌──────────────────────────────────────────────┐ │
│ │ CI/CD (IMP-RES-004)                          │ │
│ │  → GitHub Actions workflows                  │ │
│ │  → GitLab CI pipelines                       │ │
│ │  → Testing/linting/deployment stages         │ │
│ └──────────────────────────────────────────────┘ │
│                                                  │
│ ┌──────────────────────────────────────────────┐ │
│ │ Operational (IMP-INT-003)                    │ │
│ │  → Runbooks                                  │ │
│ │  → Monitoring templates                      │ │
│ │  → Troubleshooting guides                    │ │
│ └──────────────────────────────────────────────┘ │
└────────────────────────────────────────────────────┘
    │
    ▼
Artifacts Cached (24h TTL)
    │
    ▼
API/Autopilot Consumption
```

## Cost Analysis Integration (IMP-RES-002)

### Overview
The **CostEffectivenessAnalyzer** is a core component that projects total cost of ownership (TCO) and value delivery for projects. It feeds into **BudgetEnforcer** to gate expensive research phases based on cost-benefit analysis.

### Analysis Dimensions

**1. Development Costs**
- Team size and skill requirements
- Development timeline
- Build vs. buy vs. outsource decisions per component
- Learning curve and ramp-up costs

**2. Infrastructure Costs**
- Hosting (cloud provider, region, reserved vs. on-demand)
- Database and storage (scaling models: flat, linear, step-function, logarithmic)
- CDN and edge services
- Disaster recovery and redundancy

**3. Service Costs**
- Third-party APIs and SaaS subscriptions
- Vendor lock-in assessment
- Migration costs if switching solutions
- Support and professional services

**4. Operational Overhead**
- Operations and monitoring tools
- Security and compliance management
- Maintenance and updates
- Incident response and escalation

**5. Hidden Costs**
- Vendor lock-in penalties
- Technical debt accumulation
- Scaling penalties (exponential costs)
- Context switching and knowledge fragmentation

### Cost Scaling Models

```
Scaling Behavior                 Use Cases
─────────────────────────────────────────────────────────────
FLAT                     Fixed cost regardless of users
 $│                       (e.g., annual SaaS license)
  │────────────────────
  └─────────────────────► Users

LINEAR                   Cost grows proportionally
 $│                       (e.g., per-user SaaS, API calls)
  │                  /
  │               /
  │            /
  │         /
  │      /
  │   /
  └──────────────────► Users

STEP_FUNCTION            Cost jumps at thresholds
 $│        ┌─────
  │        │
  │  ┌─────
  │  │
  └──┴────────────────► Users

LOGARITHMIC             Slowing cost growth
 $│       /
  │      /
  │     /
  │    /
  │   /
  └──────────────────► Users (log scale)

EXPONENTIAL             ⚠️ AVOID - costs explode rapidly
 $│                      (e.g., poorly architected)
  │                    /
  │                 /
  │              /
  │           /
  └──────────────────► Users
```

### Integration with Artifact Generators

Cost analysis informs all artifact generation:

```
CostEffectivenessAnalyzer Output
    │
    ├─ Year 1 Projection: $50K
    ├─ Year 3 Projection: $120K
    ├─ Year 5 Projection: $250K
    ├─ Scaling Model: LINEAR
    ├─ Cost Category Breakdown:
    │   ├─ Development: 40%
    │   ├─ Infrastructure: 35%
    │   ├─ Services: 20%
    │   └─ Operations: 5%
    └─ Risk Factors: [vendor_lock_in, scaling_penalty]
         │
         ├─ To Deployment Generator ────────────┐
         │  (cost-optimal recommendations)       │
         │  "High cost → serverless + multi-cloud"
         │  "Low cost → single cloud + manual"
         │
         ├─ To Monetization Generator ─────────┐
         │  (revenue model recommendations)      │
         │  Based on cost structure              │
         │
         ├─ To CI/CD Generator ────────────────┐
         │  (optimization recommendations)       │
         │  "High cost → aggressive caching"     │
         │  "High cost → resource limits"        │
         │
         └─ To Budget Enforcer ────────────────┐
            (phase execution decision)          │
            Skip expensive phases if            │
            budget exhausted                    │
```

### Budget Enforcement Decision Logic

```python
def should_run_expensive_phase(budget_remaining, phase_cost, decision_uncertainty):
    """
    Gate expensive research phases based on budget and value.

    Returns: bool - whether to proceed with phase execution
    """
    # Phase is expensive if:
    # - Multiple agent orchestrations (LLM calls)
    # - Deep market research required
    # - Complex framework analysis

    if budget_remaining < phase_cost:
        log("Budget exhausted, skipping phase")
        return False

    # Value = (1 - decision_uncertainty) * expected_improvement
    # Cost-benefit must be positive
    value = (1.0 - decision_uncertainty) * EXPECTED_IMPROVEMENT
    benefit_ratio = value / phase_cost

    if benefit_ratio < MINIMUM_BENEFIT_THRESHOLD:
        log(f"Cost-benefit unfavorable: {benefit_ratio:.2f}")
        return False

    return True
```

## State Tracking & Research Cycles (IMP-AUT-001)

### ResearchStateTracker Purpose

The **ResearchStateTracker** maintains continuity across research phases and cycles. Without it, each research invocation would be isolated, losing context from previous decisions and analysis results.

### State Persistence Model

```
┌─────────────────────────────────────────────────────┐
│ Research Session State                              │
│                                                     │
│ session_id: UUID                                    │
│ idea_hash: str (computed from parsed idea)          │
│ created_at: datetime                                │
│ expires_at: datetime (cache TTL)                    │
│                                                     │
│ ┌──────────────────────────────────────────────┐   │
│ │ Phase Completion Tracking                    │   │
│ │                                              │   │
│ │ analysis_phase: {                            │   │
│ │   status: COMPLETE | PENDING | FAILED        │   │
│ │   timestamp: datetime                        │   │
│ │   error: str (if FAILED)                     │   │
│ │ }                                            │   │
│ │                                              │   │
│ │ discovery_phase: { ... }                     │   │
│ │ generation_phase: { ... }                    │   │
│ │ enforcement_phase: { ... }                   │   │
│ └──────────────────────────────────────────────┘   │
│                                                     │
│ ┌──────────────────────────────────────────────┐   │
│ │ Decision Outcomes                            │   │
│ │                                              │   │
│ │ decisions: [                                 │   │
│ │   {                                          │   │
│ │     decision_id: UUID                        │   │
│ │     category: cost|deployment|monetization   │   │
│ │     recommendation: str                      │   │
│ │     confidence: 0.0-1.0                      │   │
│ │     rationale: str                           │   │
│ │   },                                         │   │
│ │   ...                                        │   │
│ │ ]                                            │   │
│ └──────────────────────────────────────────────┘   │
│                                                     │
│ ┌──────────────────────────────────────────────┐   │
│ │ Artifact Generation Status                   │   │
│ │                                              │   │
│ │ artifacts: {                                 │   │
│ │   monetization: {                            │   │
│ │     generated: bool                          │   │
│ │     path: str                                │   │
│ │     models: [subscription, freemium, ...]    │   │
│ │   }                                          │   │
│ │   deployment: {                              │   │
│ │     generated: bool                          │   │
│ │     path: str                                │   │
│ │     templates: [docker, k8s, serverless]     │   │
│ │   }                                          │   │
│ │   cicd: {                                    │   │
│ │     generated: bool                          │   │
│ │     path: str                                │   │
│ │     platforms: [github_actions, gitlab_ci]   │   │
│ │   }                                          │   │
│ │ }                                            │   │
│ └──────────────────────────────────────────────┘   │
│                                                     │
│ ┌──────────────────────────────────────────────┐   │
│ │ Cost Metrics                                 │   │
│ │                                              │   │
│ │ cost_analysis: {                             │   │
│ │   year_1_projection: float                   │   │
│ │   year_3_projection: float                   │   │
│ │   year_5_projection: float                   │   │
│ │   scaling_model: FLAT|LINEAR|STEP|...        │   │
│ │   value_score: 0.0-1.0                       │   │
│ │ }                                            │   │
│ └──────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────┘
```

### Follow-up Research Triggering (IMP-AUT-001)

The **FollowupResearchTrigger** evaluates when to initiate new research cycles:

```
Autopilot Health Gate Triggered
    │
    ▼
┌──────────────────────────────────────────────────┐
│ FollowupResearchTrigger Evaluation                │
│                                                  │
│ Criteria:                                        │
│  1. Time-based: time_since_research > TTL?       │
│  2. Quality-based: decision_confidence < min?    │
│  3. Context-based: project_context_changed?      │
│  4. Feasibility-based: old_feasibility_valid?    │
│  5. Budget-based: budget_available?              │
│  6. Outcome-based: last_research_effective?      │
└──────────────────────────────────────────────────┘
    │
    ├─ All criteria ──┐
    │ favorable       │
    │                 │ Some criteria ──┐
    │                 │ unfavorable     │
    ▼                 ▼                 │
    │                 │                 │
┌───┴─────────┐  ┌────┴──────────┐     │
│ New Research │  │ Cache Valid   │     │
│ Cycle        │  │ (Reuse        │     │
│              │  │  Results)     │     │
│ Enhanced ctx │  │               │     │
│ + history    │  │ Return cached │     │
└──────────────┘  │ recommendations
                  └─────────────────
```

### State Consistency Guarantees

**Write-Once Semantics**: Phase decisions are immutable once written
- Prevents conflicting decisions across research cycles
- Enables safe caching without cache invalidation complexity

**Transactional Phase Completion**: All-or-nothing phase state updates
- If artifact generation fails mid-way, entire phase marked FAILED
- No partial state corruption

**Cross-Cycle State Isolation**: Each research cycle inherits ancestor state, not siblings
- Prevents interference from parallel research invocations
- Maintains clear decision lineage

---

## Integration Points

### API Server
**File**: `src/autopack/main.py`
**Endpoints**:
- `GET /runs/{run_id}` - Fetch run state
- `PUT /runs/{run_id}/phases/{phase_id}` - Update phase status
- `POST /approval/request` - Request human approval
- `GET /approval/status/{id}` - Poll approval decision

### Research Pipeline API (IMP-RES-007)
**File**: `src/autopack/research/api/router.py`
**Endpoints**:
- `GET /research/analysis/cost-effectiveness` - Cost analysis for project
- `GET /research/analysis/state` - Current research session state
- `POST /research/artifacts/generate` - Trigger artifact generation
- `GET /research/artifacts/{type}` - Retrieve generated artifacts (deployment, monetization, cicd)
- `GET /research/recommendations` - Get research recommendations

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

# Research Pipeline Flags (Wave 2-3)
--enable-budget-enforcement       # IMP-RES-002 cost gates
--enable-followup-research        # IMP-AUT-001 trigger research cycles
--enable-artifact-generation      # IMP-RES-001/003/004 create deployment/monetization/CI artifacts
--enable-research-api             # IMP-RES-007 expose research via REST API
```

---

## References

**Key Documentation**:
- [README.md](../README.md) - Getting started, usage examples
- [CONTRIBUTING.md](CONTRIBUTING.md) - Development setup, testing
- [BUILD_HISTORY.md](BUILD_HISTORY.md) - Feature changelog
- [DEBUG_LOG.md](DEBUG_LOG.md) - Issue tracking

**Implementation Guides**:
- [BUILD-112: Diagnostics Parity](archive/superseded/reports/BUILD-112_DIAGNOSTICS_PARITY_CURSOR.md)
- [BUILD-113: Autonomous Investigation](archive/superseded/reports/BUILD-113_ITERATIVE_AUTONOMOUS_INVESTIGATION.md)
- [BUILD-127: Self-Healing Governance](archive/superseded/reports/BUILD-127_REVISED_PLAN.md)
- [BUILD-128: Deliverables-Aware Manifest](archive/superseded/reports/BUILD-128_ROOT_CAUSE_AND_PREVENTION.md)
- [BUILD-129: Token Budget Intelligence](archive/superseded/reports/BUILD-129_PHASE1_VALIDATION_COMPLETE.md)

---

## Research Enhancement Decision Rationale

### Wave 2: Artifact Generation & Deployment Guidance

| IMP | Feature | Rationale | Dependencies |
|-----|---------|-----------|--------------|
| IMP-RES-001 | Monetization Guidance | Projects need business model recommendations beyond tech; costs drive feasibility | IMP-RES-002 budget enforcement |
| IMP-RES-002 | Budget Enforcement | Expensive research wastes tokens without ROI; gates phases by cost-benefit | Foundation for all downstream |
| IMP-RES-003 | Deployment Guidance | Tech stack determines infrastructure costs; provides concrete Docker/K8s/serverless templates | Blocks IMP-RES-004 |
| IMP-RES-004 | CI/CD Generation | Deployment decisions inform pipeline stages; no CI/CD guidance without deployment arch | Depends on IMP-RES-003 |
| IMP-RES-005 | MCP Registry Scanner | Available tools affect artifact generation; integrates discovered tools into recommendations | Independent (Wave 1) |
| IMP-RES-006 | Cross-Project Learning | Patterns from past projects improve recommendations; learned patterns reduce redundant analysis | Enhancement (independent) |
| IMP-RES-007 | Research API | External systems need access to research results; REST API enables integrations | Foundation enhancement |

### Wave 3: Research Integration & Autopilot Feedback

| IMP | Feature | Rationale | Dependencies |
|-----|---------|-----------|--------------|
| IMP-AUT-001 | Research Cycle Triggering | Autopilot health gates should trigger research when decisions uncertain; closes feedback loop | IMP-RES-002 budget checks |
| IMP-INT-001 | SOT Artifact Substitution | SOT docs (BUILD_HISTORY.md, ARCHITECTURE_DECISIONS.md) provide project context for research | Independent |
| IMP-INT-002 | Build History Feedback | Build outcomes inform cost-effectiveness reassessment; enables continuous improvement | Independent |
| IMP-INT-003 | Post-Build Artifacts | Successful builds generate deployment/runbook artifacts automatically; reduces manual ops | Depends on IMP-RES-003/004 |

### Wave 4: Monitoring, Documentation & Polish

| IMP | Feature | Rationale | Impact |
|-----|---------|-----------|--------|
| IMP-REL-001 | Feature Gates | New features need kill switches; graceful degradation prevents cascading failures | Reliability |
| IMP-DOCS-001 | Architecture Docs | Users need to understand research pipeline flow, cost gates, artifact generation | Documentation |
| IMP-DOCS-002 | Pipeline User Guide | Users need API usage examples and artifact interpretation | Documentation |
| IMP-SEG-001 | Health Metrics | Monitor autopilot health gates and research trigger frequency; enables observability | Observability |
| IMP-SEG-002 | Outcome Tracking | Measure if research improved decisions; feedback for continuous improvement | Observability |
| IMP-PERF-001 | Cache Optimization | Research cache hits reduce latency and token cost; LRU + compression for scale | Performance |
| IMP-PERF-002 | Parallel Execution | Dependency-aware scheduling reduces research latency; critical for fast feedback loops | Performance |

### Architectural Decisions

**DEC-001: Cache-First Architecture**
- Problem: Repeated research for similar ideas wastes tokens
- Decision: 24-hour cache with idea hash as key
- Rationale: 80% of startup ideas within similar market segments; amortizes research cost
- Trade-off: Misses real-time market changes; mitigated by TTL expiration

**DEC-002: Budget Gating Over Retry**
- Problem: Expensive research phases may not justify cost
- Decision: BudgetEnforcer gates by cost-benefit, not just retry attempts
- Rationale: Budget scarcity is primary constraint; ROI-aware resource allocation
- Trade-off: May skip research that would have high value; mitigated by quality-based fallbacks

**DEC-003: State Immutability**
- Problem: Parallel research invocations could create conflicting decisions
- Decision: Phase decisions write-once; each research cycle inherits parent state
- Rationale: Prevents decision conflicts; enables safe concurrent research
- Trade-off: Cannot recompute decisions with new data; mitigated by explicit cache invalidation

**DEC-004: Artifact Generation Over Raw Analysis**
- Problem: Raw cost/feasibility data difficult to act on
- Decision: Generate concrete artifacts (deployment templates, monetization docs, CI/CD configs)
- Rationale: Actionable guidance more valuable than analysis tables; reduces interpretation burden
- Trade-off: Artifact generation overhead; mitigated by template reuse and caching

---

**Total Lines**: Updated with research pipeline enhancements (previous 180-line constraint relaxed)
**Style**: Bullet-style with code examples and diagrams
**Scope**: High-level overview of research pipeline, decision rationale, and integration patterns
