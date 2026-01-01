# Production Rollout Checklist

**BUILD-146 Phase A P17**: Safe staged rollout guide for Autopack autonomy features.

## Overview

This checklist ensures safe, monitored rollout of Autopack's autonomous execution features in production environments. Follow the staged approach below to minimize risk and maximize observability.

---

## Environment Variables Matrix

### Core Configuration

| Variable | Purpose | Default | Production Value |
|----------|---------|---------|------------------|
| `DATABASE_URL` | Database connection | `sqlite:///autopack.db` | `postgresql://user:pass@host:5432/autopack` |
| `AUTOPACK_API_URL` | API endpoint | `http://localhost:8000` | Production API URL |
| `AUTOPACK_API_KEY` | API authentication | None | Production API key |

### LLM Provider Keys

| Variable | Purpose | Required |
|----------|---------|----------|
| `GLM_API_KEY` | Zhipu AI (primary) | Yes |
| `GLM_API_BASE` | GLM base URL | No (defaults to `https://open.bigmodel.cn/api/paas/v4`) |
| `ANTHROPIC_API_KEY` | Claude models | No (fallback) |
| `OPENAI_API_KEY` | GPT models | No (fallback) |

### Feature Toggles

| Variable | Feature | Default | Production Recommendation |
|----------|---------|---------|---------------------------|
| `ARTIFACT_HISTORY_PACK_ENABLED` | History pack generation | `false` | `true` (Stage 2+) |
| `ARTIFACT_SUBSTITUTE_SOT_DOCS` | SOT doc substitution | `false` | `true` (Stage 2+) |
| `ARTIFACT_EXTENDED_CONTEXTS_ENABLED` | Extended contexts | `false` | `true` (Stage 3+) |
| `TELEMETRY_DB_ENABLED` | Telemetry recording | `false` | `true` (All stages) |
| `AUTOPACK_SKIP_CI` | Skip CI checks | `false` | `false` (Never skip in prod) |

### Observability Settings

| Variable | Purpose | Default | Production Value |
|----------|---------|---------|------------------|
| `ARTIFACT_HISTORY_PACK_MAX_TIERS` | Max tiers in history pack | `5` | `5-10` |
| `ARTIFACT_HISTORY_PACK_MAX_PHASES` | Max phases in history pack | `10` | `10-20` |
| `TELEGRAM_BOT_TOKEN` | Telegram notifications | None | Production bot token |
| `TELEGRAM_CHAT_ID` | Telegram chat ID | None | Production chat ID |

---

## Database Tables to Monitor

### 1. LLM Usage (`llm_usage_events`)
**Purpose**: Track all LLM API calls and token consumption.

**Key Metrics**:
- `total_tokens`: Total tokens per call
- `provider`: Which LLM provider was used
- `role`: builder, auditor, doctor, etc.
- `is_doctor_call`: Whether this was a Doctor intervention

**Queries**:
```sql
-- Total token spend per run
SELECT run_id, SUM(total_tokens) as total_tokens
FROM llm_usage_events
WHERE run_id = 'your-run-id'
GROUP BY run_id;

-- Doctor call distribution
SELECT doctor_model, COUNT(*) as calls
FROM llm_usage_events
WHERE is_doctor_call = true
GROUP BY doctor_model;
```

### 2. Token Efficiency (`token_efficiency_metrics`)
**Purpose**: Track artifact/budgeting savings.

**Key Metrics**:
- `artifact_substitutions`: Number of files substituted with artifacts
- `tokens_saved_artifacts`: Tokens saved via artifact summaries
- `budget_mode`: semantic or lexical
- `files_omitted`: Files excluded due to budget constraints
- `phase_outcome`: COMPLETE, FAILED, BLOCKED, etc.

**Queries**:
```sql
-- Artifact savings per run
SELECT run_id,
       SUM(artifact_substitutions) as total_subs,
       SUM(tokens_saved_artifacts) as total_saved
FROM token_efficiency_metrics
WHERE run_id = 'your-run-id'
GROUP BY run_id;

-- Budget mode distribution
SELECT budget_mode, COUNT(*) as phases
FROM token_efficiency_metrics
GROUP BY budget_mode;
```

### 3. Phase 6 Metrics (`phase6_metrics`)
**Purpose**: Track Phase 6 autonomy features (failure hardening, intention context).

**Key Metrics**:
- `failure_hardening_triggered`: Whether failure pattern was detected
- `doctor_call_skipped`: Whether Doctor was skipped due to hardening
- `doctor_tokens_avoided_estimate`: Estimated tokens saved by skipping Doctor
- `intention_context_injected`: Whether intention context was added

**Queries**:
```sql
-- Failure hardening effectiveness
SELECT
  COUNT(*) as total_phases,
  SUM(CASE WHEN failure_hardening_triggered THEN 1 ELSE 0 END) as hardening_triggered,
  SUM(CASE WHEN doctor_call_skipped THEN 1 ELSE 0 END) as doctor_skipped,
  SUM(doctor_tokens_avoided_estimate) as total_tokens_avoided
FROM phase6_metrics
WHERE run_id = 'your-run-id';
```

### 4. Budget Escalation (`token_budget_escalation_events`)
**Purpose**: Track budget escalation decisions.

**Key Metrics**:
- `escalation_reason`: Why escalation was triggered
- `new_budget_tokens`: New budget after escalation
- `escalation_count`: Number of escalations for this phase

---

## Staged Rollout Plan

### Stage 0: Pre-Production Validation (Required)

**Objective**: Validate setup and baseline metrics.

**Steps**:
1. ✅ Run smoke test script (see below)
2. ✅ Verify all DB tables are accessible
3. ✅ Confirm LLM provider keys are valid
4. ✅ Run core test suite: `pytest -m "not research and not aspirational"`
5. ✅ Collect baseline metrics (no autonomy features)

**Success Criteria**:
- Smoke test reports "GO" status
- Core tests pass (100%)
- Database is reachable and schema is current
- At least one successful phase execution with telemetry recorded

**Stop Conditions**:
- Smoke test reports "NO-GO"
- Core test failures
- Database connection failures
- LLM API authentication failures

---

### Stage 1: Telemetry-Only Rollout (Safe)

**Objective**: Enable telemetry recording without autonomy features.

**Environment**:
```bash
TELEMETRY_DB_ENABLED=true
ARTIFACT_HISTORY_PACK_ENABLED=false
ARTIFACT_SUBSTITUTE_SOT_DOCS=false
ARTIFACT_EXTENDED_CONTEXTS_ENABLED=false
```

**What to Monitor**:
- `llm_usage_events`: Verify all calls are recorded
- `token_efficiency_metrics`: Verify metrics are captured per phase
- `phase6_metrics`: Verify Phase 6 metrics are recorded

**Success Criteria**:
- All phases have corresponding telemetry rows
- No duplicate telemetry entries per `(run_id, phase_id, outcome)` (P17.1 idempotency)
- Token categories are non-overlapping (budget_used vs tokens_saved_artifacts)

**Duration**: 1-3 runs minimum

**Stop Conditions**:
- Missing telemetry rows
- Duplicate telemetry entries (idempotency failures)
- Database write failures

---

### Stage 2: Artifact History Pack + SOT Substitution (Moderate)

**Objective**: Enable history pack and SOT doc substitution for token savings.

**Environment**:
```bash
TELEMETRY_DB_ENABLED=true
ARTIFACT_HISTORY_PACK_ENABLED=true
ARTIFACT_SUBSTITUTE_SOT_DOCS=true
ARTIFACT_EXTENDED_CONTEXTS_ENABLED=false
ARTIFACT_HISTORY_PACK_MAX_TIERS=5
ARTIFACT_HISTORY_PACK_MAX_PHASES=10
```

**What to Monitor**:
- `token_efficiency_metrics.artifact_substitutions`: Should be > 0 for phases with SOT docs
- `token_efficiency_metrics.tokens_saved_artifacts`: Should show savings
- History pack generation in `.autonomous_runs/{run_id}/history_pack.md`

**Success Criteria**:
- SOT docs (BUILD_HISTORY, BUILD_LOG) are substituted with history pack
- `tokens_saved_artifacts` > 0 for applicable phases
- No substitutions occur for non-SOT files (safety rule)
- Caps are strictly enforced (max_tiers, max_phases)

**Duration**: 3-5 runs minimum

**Stop Conditions**:
- Silent substitutions of regular code files (security risk)
- History pack generation failures
- Cap violations (more tiers/phases than configured max)

---

### Stage 3: Full Autonomy Features (Advanced)

**Objective**: Enable all autonomy features including extended contexts.

**Environment**:
```bash
TELEMETRY_DB_ENABLED=true
ARTIFACT_HISTORY_PACK_ENABLED=true
ARTIFACT_SUBSTITUTE_SOT_DOCS=true
ARTIFACT_EXTENDED_CONTEXTS_ENABLED=true
ARTIFACT_HISTORY_PACK_MAX_TIERS=10
ARTIFACT_HISTORY_PACK_MAX_PHASES=20
```

**What to Monitor**:
- All Stage 1 + Stage 2 metrics
- `phase6_metrics.failure_hardening_triggered`: Failure patterns detected
- `phase6_metrics.doctor_call_skipped`: Doctor interventions avoided
- `phase6_metrics.intention_context_injected`: Intention context usage

**Success Criteria**:
- All autonomy features active and working
- Token savings from extended contexts
- Failure hardening prevents some Doctor calls
- No regressions in phase success rate

**Duration**: Continuous monitoring

**Stop Conditions**:
- Phase success rate drops > 10% vs baseline
- Extended context substitutions cause build failures
- Memory usage exceeds limits

---

## Kill Switches

### Emergency Rollback to Stage 1 (Telemetry-Only)

```bash
# Disable all autonomy features
export ARTIFACT_HISTORY_PACK_ENABLED=false
export ARTIFACT_SUBSTITUTE_SOT_DOCS=false
export ARTIFACT_EXTENDED_CONTEXTS_ENABLED=false

# Telemetry remains enabled
export TELEMETRY_DB_ENABLED=true
```

### Complete Shutdown (No Autonomy)

```bash
# Disable all features including telemetry
export TELEMETRY_DB_ENABLED=false
export ARTIFACT_HISTORY_PACK_ENABLED=false
export ARTIFACT_SUBSTITUTE_SOT_DOCS=false
export ARTIFACT_EXTENDED_CONTEXTS_ENABLED=false
```

### Partial Rollback (Disable Extended Contexts Only)

```bash
# Keep history pack and SOT substitution, disable extended contexts
export ARTIFACT_EXTENDED_CONTEXTS_ENABLED=false
```

---

## Success Metrics to Watch

### Primary Metrics (Must Monitor)

1. **Phase Success Rate**: % of phases completing successfully
   - Baseline: Measure in Stage 0
   - Target: No regression > 5% in later stages

2. **Token Efficiency**: Average tokens saved per phase
   - Stage 1: 0 (baseline)
   - Stage 2: > 0 for phases with SOT docs
   - Stage 3: > 0 for phases with extended contexts

3. **Telemetry Completeness**: % of phases with telemetry records
   - Target: 100% (one record per terminal outcome)

### Secondary Metrics (Nice to Have)

4. **Doctor Avoidance Rate**: % of failures handled without Doctor
   - Stage 3 only: `doctor_call_skipped` / total failures

5. **Budget Mode Distribution**: semantic vs lexical
   - Prefer semantic mode when embedding budget allows

6. **Embedding Cache Hit Rate**: cache hits / total embedding calls
   - Target: > 50% in long-running runs

---

## Smoke Test Script

Run before each deployment:

```bash
PYTHONUTF8=1 PYTHONPATH=src python scripts/smoke_autonomy_features.py
```

**Output**: GO/NO-GO status with feature summary.

See [scripts/smoke_autonomy_features.py](../scripts/smoke_autonomy_features.py) for implementation.

---

## CI Gate Configuration

### Core Gate (Always Run)
```bash
pytest -m "not research and not aspirational" -v
```

**Purpose**: Validate production code paths.

**Required**: MUST pass before deployment.

### Aspirational Gate (Nice to Have)
```bash
pytest -m "aspirational" -v
```

**Purpose**: Validate future features.

**Required**: Should pass, but failures are non-blocking.

### Research Gate (Collect Only)
```bash
pytest -m "research" -v
```

**Purpose**: Data collection for research modules.

**Required**: Failures are non-blocking.

---

## Troubleshooting

### Issue: Duplicate telemetry entries

**Symptom**: Multiple `TokenEfficiencyMetrics` rows for same `(run_id, phase_id, outcome)`.

**Cause**: Idempotency guard failure (P17.1).

**Fix**:
1. Verify `phase_outcome` is being passed to `record_token_efficiency_metrics()`
2. Check DB transaction isolation level
3. Inspect executor retry logic for double-recording

### Issue: No artifact substitutions

**Symptom**: `artifact_substitutions` = 0 for all phases.

**Cause**: Feature toggles disabled or no SOT docs in phase context.

**Fix**:
1. Verify `ARTIFACT_SUBSTITUTE_SOT_DOCS=true`
2. Verify `ARTIFACT_HISTORY_PACK_ENABLED=true`
3. Check that history pack file exists: `.autonomous_runs/{run_id}/history_pack.md`
4. Confirm phase context includes SOT docs (BUILD_HISTORY.md, BUILD_LOG.md)

### Issue: Cap violations

**Symptom**: History pack includes more tiers/phases than configured max.

**Cause**: Cap enforcement failure (P17.2).

**Fix**:
1. Check `ARTIFACT_HISTORY_PACK_MAX_TIERS` and `ARTIFACT_HISTORY_PACK_MAX_PHASES` values
2. Verify `artifact_loader.build_history_pack()` respects caps
3. Inspect test suite: `TestP17SafetyAndFallback.test_max_tiers_cap_strictly_enforced`

### Issue: Silent substitutions of regular files

**Symptom**: Non-SOT files (e.g., `src/main.py`) are being substituted.

**Cause**: **CRITICAL SECURITY ISSUE** - Safety rule violation (P17.2).

**Fix**:
1. **IMMEDIATE ROLLBACK** to Stage 1 (telemetry-only)
2. Inspect `artifact_loader.should_substitute_sot_doc()` logic
3. Verify whitelist includes ONLY: BUILD_HISTORY.md, BUILD_LOG.md, DEBUG_LOG.md
4. Run safety tests: `TestP17SafetyAndFallback.test_no_silent_substitutions_in_regular_files`

---

## Contact & Escalation

- **Slack**: #autopack-ops
- **On-call**: Check PagerDuty rotation
- **Docs**: [BUILD_HISTORY.md](BUILD_HISTORY.md) for architecture context

---

**Last Updated**: 2025-12-31 (BUILD-146 Phase A P17)
