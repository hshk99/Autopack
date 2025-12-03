# Autopack Implementation Plan

**Date**: 2025-12-01
**Version**: Phase 2 Complete, Planning Phase 3+

---

## 1. Implementation Summary by Phase

### Phase 1: Core Infrastructure (COMPLETE)

| Feature | Status | File(s) |
|---------|--------|---------|
| Debug Journal System | COMPLETE | `debug_journal.py`, `DEBUG_JOURNAL.md` |
| Proactive Startup Checks | COMPLETE | `autonomous_executor.py` |
| Error Recovery System | COMPLETE | `error_recovery.py` |
| Self-Troubleshooting | COMPLETE | `error_recovery.py` (escalation thresholds) |
| T0/T1 Health Checks | PARTIAL | Basic checks in executor |

### Phase 2: Quality & Recovery (COMPLETE)

| Feature | Status | File(s) |
|---------|--------|---------|
| Quality Gate Framework | COMPLETE | `quality_gate.py` |
| Patch Validation | COMPLETE | `patch_validator.py` |
| Run-Level Health Budget | COMPLETE | `autonomous_executor.py` |
| Model Escalation | COMPLETE | `model_router.py`, `llm_service.py` |
| Mid-Run Re-Planning | COMPLETE | `autonomous_executor.py` |
| Learned Rules System | COMPLETE | `learned_rules.py` |
| Protected Path Config | COMPLETE | `governed_apply.py` |
| Doctor Data Structures | COMPLETE | `error_recovery.py` |
| Doctor Model Routing | COMPLETE | `error_recovery.py`, `config/models.yaml` |
| Doctor LLM Invocation | COMPLETE | `llm_service.py` |
| Doctor Executor Integration | COMPLETE | `autonomous_executor.py` |
| Doctor Budgets | COMPLETE | `autonomous_executor.py` |

### Phase 3: Hardening & Observability (PLANNED)

| Feature | Status | Priority | Delegation |
|---------|--------|----------|------------|
| **Doctor `execute_fix` Action** | PLANNED | **Critical** | **MANUAL** |
| Config Loading from models.yaml | PLANNED | Medium | AUTOPACK |
| Doctor Unit Tests | PLANNED | High | AUTOPACK |
| Branch-Based Rollback | PLANNED | Medium | AUTOPACK |
| Dashboard / Metrics Aggregation | PLANNED | Low | AUTOPACK |
| T0/T1 Advanced Health Checks | PLANNED | Medium | AUTOPACK |
| Discovery Promotion Pipeline | PLANNED | Low | AUTOPACK |

#### Delegation Categories

**MANUAL (Claude Code must implement)**:
These tasks require schema changes, security-critical code, or foundational infrastructure that must be reviewed and implemented manually before Autopack can build on them:
- Schema changes in `error_recovery.py` (new `DoctorAction` type, `DoctorResponse` fields)
- Command whitelist and validation in `autonomous_executor.py` (security-critical)
- Config support in `models.yaml` (schema definition)
- Doctor prompt updates in `llm_service.py` (critical for correct behavior)

**AUTOPACK (Can be delegated to Autopack)**:
These tasks are standard implementation work that Autopack can handle autonomously, testing the recent improvements:
- Config Loading from models.yaml (create `DoctorConfig` dataclass, load from YAML)
- Doctor Unit Tests (test cases for `is_complex_failure`, `choose_doctor_model`, etc.)
- Branch-Based Rollback (git operations for `rollback_run` action)
- Dashboard / Metrics Aggregation (usage tracking additions)
- T0/T1 Advanced Health Checks (pre-run validation)
- Discovery Promotion Pipeline (learned rules promotion logic)

**Testing Recent Improvements**:
The Autopack-delegated phases will test these recently fixed limitations:
- [ ] GLM-4.6 + Gemini 2.5 Pro model routing works correctly
- [ ] Model escalation triggers when phase fails
- [ ] Mid-run re-planning detects approach flaws
- [ ] Self-healing recovers from transient errors
- [ ] Doctor LLM invocation succeeds with new model stack
- [ ] Run-level health budget prevents infinite loops
- [ ] CI flow (pytest) runs after patch application

---

## 2. Detailed Implementation Tasks

### 2.0 Doctor `execute_fix` Action (Phase 3 - Critical)

**Goal**: Enable Doctor to execute infrastructure-level fixes directly (git, file, docker commands) without going through Builder→Auditor pipeline.

**Background** (from GPT_RESPONSE9):
- Current Doctor can only emit hints passed to Builder
- Infrastructure failures (merge conflicts, missing files, Docker issues) cannot be self-healed
- `execute_fix` allows direct shell command execution with strict sandboxing

**Design Decisions** (agreed with GPT):

| Question | Decision |
|----------|----------|
| Separate action vs modifier? | **Separate `execute_fix` action** for auditing/policy control |
| Route through governed_apply? | **Direct subprocess** with same sandboxing principles |
| Fix type granularity | **Typed categories**: `git`, `file`, `python` (v1); `docker`, `shell` later |
| Whitelist vs AST parsing | **Whitelist + shlex + banned metacharacters** |
| User opt-in required? | **Yes** - disabled by default, enable via `models.yaml` |
| Sudo/admin commands | **Never execute** - reject and log as "requires manual intervention" |
| Failure handling | **One attempt per phase**, fallback to `retry_with_fix` or `mark_fatal` |
| Git checkpoint | **Commit-based** on integration branch before fix execution |
| Loop prevention | **Separate caps**: `MAX_EXECUTE_FIX_PER_PHASE=1`, error signature tracking |

**Implementation Tasks**:

1. **Schema changes** (`error_recovery.py`):
   - Add `"execute_fix"` to `DoctorAction` Literal
   - Add fields to `DoctorResponse`: `fix_commands: List[str]`, `fix_type: str`, `verify_command: str`

2. **Command validation** (`autonomous_executor.py` or new `command_sandbox.py`):
   - Implement `ALLOWED_FIX_COMMANDS` whitelist with regex patterns
   - Implement `_validate_fix_commands()` using `shlex.split()` + regex
   - Ban dangerous metacharacters: `;`, `&&`, `||`, backticks, `$()`, redirects
   - Enforce path restrictions (workspace only, no system dirs)

3. **Executor handler** (`autonomous_executor.py`):
   - Add `MAX_EXECUTE_FIX_PER_PHASE = 1` constant
   - Add `_execute_fix_per_phase` counter
   - Implement `elif action == "execute_fix":` handler in `_handle_doctor_action()`
   - Create git checkpoint (commit) before executing
   - Execute commands via subprocess
   - Run `verify_command` if provided
   - Re-invoke original failing operation to confirm fix

4. **Config support** (`config/models.yaml`):
   ```yaml
   doctor:
     allow_execute_fix_global: false
     max_execute_fix_per_phase: 1
     allowed_fix_types: ["git", "file"]
   ```

5. **Doctor prompt updates** (`llm_service.py`):
   - Add explicit guidance: "Use `execute_fix` ONLY for infrastructure issues"
   - Add few-shot examples for merge conflicts, missing files, Docker issues
   - Instruct: prefer conservative recovery commands (checkout, reset, restart)

6. **Testing**:
   - Unit tests for `_validate_fix_commands()`
   - Integration test: inject merge conflict → verify `execute_fix` resolves it

**Files to modify**:
- `src/autopack/error_recovery.py` (schema)
- `src/autopack/autonomous_executor.py` (handler, validation)
- `src/autopack/llm_service.py` (Doctor prompt)
- `config/models.yaml` (config)
- `tests/test_execute_fix.py` (new)

**Reference**: GPT_RESPONSE9.md, CLAUDE_RESPONSE9_TO_GPT.md

---

### 2.1 Config Loading from models.yaml (Phase 3)

**Goal**: Eliminate config drift between code constants and `models.yaml`.

**Tasks**:
1. Create `DoctorConfig` dataclass in `error_recovery.py`
2. Load `doctor_models` section from `config/models.yaml` at module init
3. Replace hardcoded constants with config values
4. Add sensible defaults for missing config keys
5. Add config validation on startup

**Files to modify**:
- `src/autopack/error_recovery.py`
- `config/models.yaml` (validate structure)

### 2.2 Doctor Unit Tests (Phase 3)

**Goal**: Ensure Doctor routing logic is thoroughly tested.

**Tests to write**:

1. `test_is_complex_failure()`:
   - Single category, 1 attempt, healthy budget -> False
   - 2+ categories -> True
   - 2+ patch errors -> True
   - Many attempts (>=4) -> True
   - Health ratio >= 0.8 -> True
   - Prior escalated action -> True

2. `test_choose_doctor_model()`:
   - Health ratio >= 0.8 always returns strong model
   - Routine failure returns cheap model
   - Complex failure returns strong model

3. `test_should_escalate_doctor_model()`:
   - Cheap model + low confidence + attempts >= 2 -> True
   - Strong model -> False (already escalated)
   - High confidence -> False

4. Integration test:
   - Simulate phase failure
   - Verify Doctor invocation
   - Verify action handling

**Files to create**:
- `tests/test_doctor_routing.py`

### 2.3 Branch-Based Rollback (Phase 3)

**Goal**: Implement git rollback for `rollback_run` Doctor action.

**Tasks**:
1. Create rollback branch before run starts (`autopack/pre-run-{run_id}`)
2. On rollback action, reset to pre-run branch
3. Clean up rollback branches after successful runs
4. Handle edge cases (uncommitted changes, conflicts)

**Files to modify**:
- `src/autopack/autonomous_executor.py`
- Consider new `src/autopack/git_rollback.py`

### 2.4 Dashboard / Metrics Aggregation (Phase 3+)

**Goal**: Provide visibility into Doctor usage and effectiveness.

**Tasks**:
1. Add Doctor call counts to usage dashboard
2. Track action distribution (retry_with_fix, replan, etc.)
3. Track cheap vs strong model ratio
4. Track escalation frequency
5. Add cost attribution for Doctor calls

**Files to modify**:
- `src/autopack/usage_recorder.py`
- Dashboard templates (if any)

### 2.5 T0/T1 Advanced Health Checks (Phase 3)

**Goal**: Comprehensive pre-run validation.

**T0 Checks** (quick, always run):
- API connectivity
- Database connectivity
- Required env vars present
- Workspace exists and is git repo

**T1 Checks** (longer, configurable):
- Test suite passes
- All dependencies installed
- No uncommitted changes
- Branch is up to date with remote

**Files to modify**:
- `src/autopack/autonomous_executor.py`
- Consider new `src/autopack/health_checks.py`

### 2.6 Discovery Promotion Pipeline (Phase 3+)

**Goal**: Promote validated fixes to permanent rules.

**Stages**:
1. NEW: Fix discovered during troubleshooting
2. APPLIED: Fix was attempted
3. CANDIDATE_RULE: Same pattern seen in >= 3 runs within 30 days
4. RULE: Confirmed via recurrence, no regressions, human approved

**Files to modify**:
- `src/autopack/learned_rules.py`
- `config/models.yaml` (discovery_promotion section already exists)

---

## 3. Implementation from GPT Responses

### From GPT_RESPONSE4 (Learned Rules)

| Recommendation | Status | Notes |
|----------------|--------|-------|
| Stage 0A: Within-run hints | IMPLEMENTED | `_run_hints` in executor |
| Stage 0B: Cross-run promotion | PARTIAL | `learned_rules.py` exists |
| Hint structure | IMPLEMENTED | category, hint_text, origin_phase |

### From GPT_RESPONSE5 (Health Budget)

| Recommendation | Status | Notes |
|----------------|--------|-------|
| Run-level health budget | IMPLEMENTED | `_run_total_failures`, etc. |
| Failure thresholds | IMPLEMENTED | MAX_HTTP_500_PER_RUN, etc. |
| T0/T1 health checks | PARTIAL | Basic checks implemented |

### From GPT_RESPONSE6 (Doctor Design)

| Recommendation | Status | Notes |
|----------------|--------|-------|
| DoctorRequest/Response schemas | IMPLEMENTED | In `error_recovery.py` |
| Run type validation | IMPLEMENTED | In `governed_apply.py` |
| Doctor as pre-filter | IMPLEMENTED | Full integration done |

### From GPT_RESPONSE7 (Doctor Model Routing)

| Recommendation | Status | Notes |
|----------------|--------|-------|
| DoctorContextSummary | IMPLEMENTED | In `error_recovery.py` |
| is_complex_failure() | IMPLEMENTED | Multi-axis classification |
| choose_doctor_model() | IMPLEMENTED | Health budget override |
| should_escalate_doctor_model() | IMPLEMENTED | Confidence-based |
| doctor_models config | IMPLEMENTED | In `models.yaml` |

### From GPT_RESPONSE8 (Doctor Integration)

| Recommendation | Status | Notes |
|----------------|--------|-------|
| execute_doctor() wrapper | IMPLEMENTED | In `llm_service.py` |
| Per-phase Doctor context | IMPLEMENTED | In executor |
| Health budget source of truth | IMPLEMENTED | `_get_health_budget()` |
| Per-phase Doctor limit | IMPLEMENTED | MAX_DOCTOR_CALLS_PER_PHASE=2 |
| Run-level Doctor budget | IMPLEMENTED | MAX_DOCTOR_CALLS_PER_RUN=10 |
| Structured logging | IMPLEMENTED | Key=value format |
| Config loading from YAML | PLANNED | Phase 3 |
| Unit tests | PLANNED | Phase 3 |

### From GPT_RESPONSE9 (execute_fix Action)

| Recommendation | Status | Notes |
|----------------|--------|-------|
| Separate `execute_fix` action type | **AGREED** | Different semantics from `retry_with_fix` |
| Direct subprocess (not governed_apply) | **AGREED** | Reuse sandboxing principles only |
| Typed fix categories (git, file, python) | **AGREED** | Shell disabled by default |
| Whitelist + shlex + banned metacharacters | **AGREED** | No AST parsing needed |
| User opt-in via models.yaml | **AGREED** | `allow_execute_fix_global: false` |
| Never execute sudo/admin commands | **AGREED** | Reject and log as manual |
| One `execute_fix` attempt per phase | **AGREED** | `MAX_EXECUTE_FIX_PER_PHASE=1` |
| Commit-based git checkpoint | **AGREED** | Prefer commit over stash |
| Error signature tracking for loops | **AGREED** | Hash category + stack + message |
| Explicit Doctor prompt guidance | **AGREED** | "Only for infrastructure issues" |
| Multi-layer fix validation | **AGREED** | Command exit, verify_command, re-run original op |

**All 11 recommendations from GPT_RESPONSE9 accepted without modification.**

---

## 4. Current Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                     AUTONOMOUS EXECUTOR                              │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐ │
│  │   BUILDER   │  │   AUDITOR   │  │QUALITY GATE │  │   DOCTOR    │ │
│  │ (LlmService)│  │ (LlmService)│  │(quality_gate)│  │ (LlmService)│ │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘ │
│         │                │                │                │        │
│         v                v                v                v        │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                      MODEL ROUTER                            │   │
│  │  - Complexity escalation                                     │   │
│  │  - Category-based routing                                    │   │
│  │  - Quota enforcement                                         │   │
│  └─────────────────────────────────────────────────────────────┘   │
│         │                                                           │
│         v                                                           │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                    ERROR RECOVERY                            │   │
│  │  - Error classification                                      │   │
│  │  - Self-healing                                              │   │
│  │  - Doctor routing (is_complex_failure, choose_doctor_model)  │   │
│  └─────────────────────────────────────────────────────────────┘   │
│         │                                                           │
│         v                                                           │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                    GOVERNED APPLY                            │   │
│  │  - Protected paths                                           │   │
│  │  - Workspace isolation                                       │   │
│  │  - Patch application                                         │   │
│  └─────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 5. Key Files Reference

| File | Purpose |
|------|---------|
| `src/autopack/autonomous_executor.py` | Main orchestrator, Doctor integration |
| `src/autopack/llm_service.py` | LLM calls (Builder, Auditor, Doctor) |
| `src/autopack/error_recovery.py` | Error handling, Doctor data structures |
| `src/autopack/model_router.py` | Model selection and escalation |
| `src/autopack/quality_gate.py` | Quality assessment framework |
| `src/autopack/patch_validator.py` | Patch validation |
| `src/autopack/governed_apply.py` | Workspace isolation |
| `src/autopack/learned_rules.py` | Cross-run learning |
| `config/models.yaml` | Model routing and Doctor config |

---

## 6. Testing Strategy

### Unit Tests (Existing)
- `tests/test_*.py` - Core functionality tests

### Unit Tests (Planned)
- `tests/test_doctor_routing.py` - Doctor model selection
- `tests/test_health_checks.py` - T0/T1 validation

### Integration Tests
- Real run execution with mock LLM responses
- End-to-end phase failure -> Doctor -> recovery flow

---

## 7. Next Immediate Steps

1. **Validate current implementation** - Run executor with real phases
2. **Monitor Doctor logs** - Check structured logging output
3. **Tune thresholds** - Adjust based on real cheap/strong ratios
4. **Write Doctor tests** - Start with `test_is_complex_failure()`
5. **Update documentation** - README.md, CONSOLIDATED_BUILD.md

---

**Document maintained by Claude (Opus 4.5)**
**Last updated**: 2025-12-01
