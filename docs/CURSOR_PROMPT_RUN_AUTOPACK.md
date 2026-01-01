# Cursor Prompt: Running Autopack Autonomous Executor

**Purpose**: This prompt provides a comprehensive guide for AI assistants (like Cursor) to successfully run Autopack autonomous builds with all necessary context, error patterns, and operational procedures.

---

## Quick Start Command Template

```bash
# Standard run with telemetry and CI checks disabled
PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="sqlite:///autopack.db" \
TELEMETRY_DB_ENABLED=1 AUTOPACK_SKIP_CI=1 \
python scripts/create_run_from_json.py <run-config-file.json>
```

**Common variations**:
- **Full CI enabled**: Remove `AUTOPACK_SKIP_CI=1`
- **PostgreSQL**: `DATABASE_URL="postgresql://autopack:autopack@localhost:5432/autopack"`
- **With Qdrant vector store**: Add `QDRANT_HOST="http://localhost:6333"`
- **Timeout for long runs**: Prefix with `timeout 7200` (2 hours)

---

## Pre-Flight Checklist

### 1. **Environment Setup**
- [ ] Python environment activated (`venv/Scripts/activate` on Windows, `source venv/bin/activate` on Unix)
- [ ] Dependencies installed: `pip install -r requirements.txt`
- [ ] Database exists (or use `sqlite:///autopack.db` for quick runs)
- [ ] API keys set if using external LLMs:
  - `ANTHROPIC_API_KEY` for Claude models
  - `OPENAI_API_KEY` for GPT models
  - `GLM_API_KEY` for Zhipu GLM models

### 2. **Database State**
Check if the run already exists to avoid conflicts:
```bash
PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="sqlite:///autopack.db" python -c "
from autopack.database import SessionLocal
from autopack.models import Run
s = SessionLocal()
run = s.query(Run).filter(Run.id == '<run-id>').first()
print(f'Run exists: {run is not None}')
if run:
    print(f'State: {run.state}')
s.close()
"
```

If run exists and you need to start fresh:
```bash
PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="sqlite:///autopack.db" python -c "
from autopack.database import SessionLocal
from autopack.models import Run, Tier, Phase
s = SessionLocal()
rid = '<run-id>'
s.query(Phase).filter(Phase.run_id == rid).delete(synchronize_session=False)
s.query(Tier).filter(Tier.run_id == rid).delete(synchronize_session=False)
s.query(Run).filter(Run.id == rid).delete(synchronize_session=False)
s.commit()
s.close()
print(f'Deleted run {rid}')
"
```

### 3. **Configuration Files**
Verify these exist and are current:
- `config/models.yaml` - LLM model mappings (complexity tiers, routing policies)
- `config/learned_rules.yaml` - Discovered failure patterns (optional, loaded if exists)
- Run config JSON (e.g., `scripts/runs/my-build.json`)

---

## Critical Environment Variables

| Variable | Purpose | Default | Required? |
|----------|---------|---------|-----------|
| `PYTHONPATH` | Must include `src` | - | **YES** |
| `DATABASE_URL` | Database connection string | - | **YES** |
| `PYTHONUTF8=1` | Fix Windows encoding issues | - | **Recommended on Windows** |
| `TELEMETRY_DB_ENABLED` | Enable token/phase telemetry | `false` | No |
| `AUTOPACK_SKIP_CI` | Skip CI validation (faster dev) | `false` | No |
| `AUTOPACK_ENABLE_MEMORY` | Enable vector memory | `false` | No |
| `AUTOPACK_ENABLE_SOT_MEMORY_INDEXING` | Index SOT docs to vector store | `false` | No |
| `AUTOPACK_SOT_RETRIEVAL_ENABLED` | Include SOT in retrieval | `false` | No |
| `QDRANT_HOST` | Qdrant URL (if using) | - | Only if vector memory enabled |
| `ANTHROPIC_API_KEY` | Claude API key | - | If using Claude models |
| `OPENAI_API_KEY` | OpenAI API key | - | If using GPT models |
| `GLM_API_KEY` | Zhipu GLM API key | - | If using GLM models |

**SOT Memory Feature (BUILD-147)**:
- All SOT features are **opt-in** and disabled by default
- Requires both `AUTOPACK_ENABLE_MEMORY=true` and `AUTOPACK_ENABLE_SOT_MEMORY_INDEXING=true` to index
- Requires `AUTOPACK_SOT_RETRIEVAL_ENABLED=true` to include SOT in context retrieval
- See `IMPROVEMENTS_PLAN_SOT_RUNTIME_AND_MODEL_INTEL.md` for full details

---

## Monitoring a Running Build

### Real-Time Progress
```bash
# Watch phase state changes
PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="sqlite:///autopack.db" python -c "
from autopack.database import SessionLocal
from autopack.models import Phase, PhaseState
s = SessionLocal()
phases = s.query(Phase).filter(Phase.run_id == '<run-id>').all()
print(f'Phase states:')
for state in [PhaseState.QUEUED, PhaseState.EXECUTING, PhaseState.COMPLETE, PhaseState.FAILED]:
    count = sum(1 for p in phases if p.state == state)
    print(f'  {state.value}: {count}')
s.close()
"
```

### Check Specific Phase
```bash
PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="sqlite:///autopack.db" python -c "
from autopack.database import SessionLocal
from autopack.models import Phase
s = SessionLocal()
p = s.query(Phase).filter(Phase.phase_id == '<phase-id>').first()
if p:
    print(f'State: {p.state}')
    print(f'Attempts: {len(p.attempt_history or [])}')
    print(f'Deliverables: {len((p.scope or {}).get(\"deliverables\", []))}')
s.close()
"
```

### Token Usage
```bash
PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="sqlite:///autopack.db" python -c "
from autopack.database import SessionLocal
from autopack.models import Run
s = SessionLocal()
run = s.query(Run).filter(Run.id == '<run-id>').first()
if run:
    print(f'Tokens used: {run.tokens_used:,} / {run.token_cap:,}')
    print(f'Utilization: {run.tokens_used / run.token_cap * 100:.1f}%')
s.close()
"
```

---

## Common Error Patterns & Solutions

### 1. **Settings Singleton Not Reloading (Test Infrastructure)**
**Symptom**: Tests fail with "expected True, got False" on settings flags even when environment variables are patched.

**Root Cause**: `autopack.config.settings` is a module-level singleton loaded once at import. Environment patches in tests don't affect already-loaded settings.

**Solution**: Reload the config module after patching environment:
```python
with patch.dict(os.environ, {
    "AUTOPACK_ENABLE_MEMORY": "true",
    "AUTOPACK_ENABLE_SOT_MEMORY_INDEXING": "true",
}):
    import sys
    import importlib
    if "autopack.config" in sys.modules:
        importlib.reload(sys.modules["autopack.config"])

    # Now settings will reflect the patched environment
    service = MemoryService(enabled=True, use_qdrant=False)
```

**Location**: Fixed in `tests/test_sot_memory_indexing.py` (7 test functions, BUILD-147 Phase A P11)

---

### 2. **KeyError on Retrieve Context Return Structure**
**Symptom**: `KeyError: 'sot'` when checking `'sot' in results` from `retrieve_context()`.

**Root Cause**: `retrieve_context()` initialized an empty dict `{}` then conditionally added keys. If a collection wasn't included, its key never existed.

**Solution**: Pre-initialize dict with all 8 keys:
```python
results = {
    "code": [],
    "summaries": [],
    "errors": [],
    "hints": [],
    "planning": [],
    "plan_changes": [],
    "decisions": [],
    "sot": [],
}
```

**Location**: Fixed in `src/autopack/memory/memory_service.py:1279-1288` (BUILD-147 Phase A P11)

---

### 3. **Module Import Errors ("No module named autopack")**
**Symptom**: `ModuleNotFoundError: No module named 'autopack'`

**Solution**: Always set `PYTHONPATH=src` when running scripts from repo root.

**Wrong**:
```bash
python scripts/create_run_from_json.py run.json
```

**Correct**:
```bash
PYTHONPATH=src python scripts/create_run_from_json.py run.json
```

---

### 4. **Windows Encoding Crashes**
**Symptom**: `UnicodeEncodeError` or garbled output on Windows terminals.

**Solution**: Set `PYTHONUTF8=1` environment variable.

```bash
PYTHONUTF8=1 PYTHONPATH=src python ...
```

---

### 5. **Phase Stuck in EXECUTING State**
**Symptom**: Phase shows `EXECUTING` but no progress for >10 minutes.

**Possible Causes**:
- Process crashed without updating DB
- Infinite loop in executor
- LLM API timeout without proper handling

**Investigation**:
1. Check process is still running: `tasklist | findstr python` (Windows) or `ps aux | grep python` (Unix)
2. Check logs in `.autonomous_runs/<run-id>/logs/`
3. Check last attempt in phase:
```python
from autopack.database import SessionLocal
from autopack.models import Phase
s = SessionLocal()
p = s.query(Phase).filter(Phase.phase_id == '<phase-id>').first()
attempts = p.attempt_history or []
if attempts:
    last = attempts[-1]
    print(f"Last attempt: {last.get('outcome')}")
    print(f"Error: {last.get('error_details')}")
s.close()
```

**Recovery**: Manually set phase to FAILED and let the system retry or escalate:
```python
from autopack.database import SessionLocal
from autopack.models import Phase, PhaseState
s = SessionLocal()
p = s.query(Phase).filter(Phase.phase_id == '<phase-id>').first()
p.state = PhaseState.FAILED
s.commit()
s.close()
```

---

### 6. **Database Lock Errors (SQLite)**
**Symptom**: `database is locked` errors.

**Cause**: SQLite doesn't support high concurrency. Multiple processes trying to write simultaneously.

**Solution**:
- Use PostgreSQL for production/concurrent runs
- For dev: ensure only one executor process runs at a time
- Add retry logic with backoff (already in codebase for most operations)

---

### 7. **Vector Store Connection Failures**
**Symptom**: `Failed to connect to Qdrant at http://localhost:6333`

**Solution**:
1. Verify Qdrant is running: `curl http://localhost:6333/collections`
2. Start Qdrant if needed: `docker-compose up -d qdrant`
3. For dev without vector store: don't set `AUTOPACK_ENABLE_MEMORY=true`

---

### 8. **Model Not Found / API Key Errors**
**Symptom**: `Invalid API key` or `Model 'xyz' not found`

**Solution**:
1. Check API keys are set in environment
2. Verify model names in `config/models.yaml` are current
3. Use model audit script to find hardcoded model strings:
```bash
python scripts/model_audit.py --glob "src/**/*.py" --filter "glm-4.6"
```

**Note**: As of BUILD-147, tidy system uses `glm-4.7` (configured in `config/models.yaml:154`)

---

## Run Config JSON Structure

Minimal example:
```json
{
  "run_id": "my-feature-build",
  "goal": "Implement user authentication with JWT tokens",
  "token_cap": 500000,
  "workspace": ".",
  "tiers": [
    {
      "tier_index": 0,
      "tier_name": "Foundation",
      "phases": [
        {
          "phase_id": "auth-schema",
          "phase_index": 0,
          "task_name": "Create user table and JWT schema",
          "task_category": "schema_contract_change_additive",
          "complexity": "medium",
          "scope": {
            "paths": ["src/models/", "migrations/"],
            "deliverables": ["user table migration", "auth models"]
          }
        }
      ]
    }
  ]
}
```

**Key Fields**:
- `run_id`: Unique identifier (no spaces, use hyphens)
- `goal`: High-level objective (used for context)
- `token_cap`: Total token budget across all phases
- `task_category`: Maps to routing policies in `config/models.yaml`
- `complexity`: `low` | `medium` | `high` (determines model tier)
- `scope.paths`: Filesystem paths the phase can modify (relative to workspace)
- `scope.deliverables`: Expected outputs (used by auditor)

**Advanced Fields**:
- `approval_required`: `true` to pause before applying patch
- `escalation_policy`: Override default complexity escalation
- `max_attempts`: Custom retry limit (default: 5)

See existing configs in `scripts/runs/` for examples.

---

## Post-Run Analysis

### Success Rate
```bash
PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="sqlite:///autopack.db" python -c "
from autopack.database import SessionLocal
from autopack.models import Phase, PhaseState
s = SessionLocal()
phases = s.query(Phase).filter(Phase.run_id == '<run-id>').all()
total = len(phases)
complete = sum(1 for p in phases if p.state == PhaseState.COMPLETE)
failed = sum(1 for p in phases if p.state == PhaseState.FAILED)
print(f'Success rate: {complete}/{total} ({complete/total*100:.1f}%)')
print(f'Failed: {failed}')
s.close()
"
```

### Token Telemetry (if enabled)
```bash
PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="sqlite:///autopack.db" \
python scripts/analyze_token_telemetry_v3.py --run-id <run-id>
```

### Doctor Usage Stats
```bash
PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="sqlite:///autopack.db" python -c "
from autopack.database import SessionLocal
from autopack.models import Phase
s = SessionLocal()
phases = s.query(Phase).filter(Phase.run_id == '<run-id>').all()
doctor_calls = sum(len(p.doctor_history or []) for p in phases)
print(f'Total doctor calls: {doctor_calls}')
s.close()
"
```

---

## Cleanup & Maintenance

### Archive Old Runs
```bash
# Move completed run artifacts to archive
mkdir -p archive/runs
mv .autonomous_runs/<run-id> archive/runs/
```

### Database Cleanup
```bash
# Remove old test runs (be careful!)
PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="sqlite:///autopack.db" python -c "
from autopack.database import SessionLocal
from autopack.models import Run, Tier, Phase
s = SessionLocal()
# Delete runs matching pattern
runs = s.query(Run).filter(Run.id.like('test-%')).all()
for run in runs:
    s.query(Phase).filter(Phase.run_id == run.id).delete()
    s.query(Tier).filter(Tier.run_id == run.id).delete()
    s.delete(run)
s.commit()
print(f'Deleted {len(runs)} test runs')
s.close()
"
```

### Run Tidy/Consolidation
```bash
# Consolidate documentation archives into SOT files
PYTHONUTF8=1 python scripts/tidy/run_tidy_all.py --semantic --project autopack-framework
```

**Tidy Safety Notes**:
- Uses **append-only** approach (never deletes SOT files)
- Processes archive files matching patterns, consolidates to `BUILD_HISTORY.md`, `DEBUG_LOG.md`, `ARCHITECTURE_DECISIONS.md`
- Excludes: `archive/prompts/`, `archive/research/active/`, `ARCHIVE_INDEX.md`, `README.md`
- Uses `glm-4.7` for semantic classification (configured in `config/models.yaml:154`)
- Safe to run repeatedly (idempotent)

---

## Testing Before Production Runs

### Unit Tests
```bash
# Run core executor tests
PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="sqlite:///:memory:" timeout 120 pytest tests/autopack/test_autonomous_executor.py -v

# Run SOT memory tests (BUILD-147)
PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="sqlite:///:memory:" timeout 180 pytest tests/test_sot_memory_indexing.py -v
```

### Smoke Test with Minimal Run
Create a 1-phase test run:
```json
{
  "run_id": "smoke-test",
  "goal": "Verify executor works",
  "token_cap": 50000,
  "workspace": ".",
  "tiers": [{
    "tier_index": 0,
    "tier_name": "Test",
    "phases": [{
      "phase_id": "smoke-phase",
      "phase_index": 0,
      "task_name": "Add a comment to README.md",
      "task_category": "docs",
      "complexity": "low",
      "scope": {
        "paths": ["."],
        "deliverables": ["comment in README.md"]
      }
    }]
  }]
}
```

Run:
```bash
PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="sqlite:///test.db" \
AUTOPACK_SKIP_CI=1 \
python scripts/create_run_from_json.py smoke-test.json
```

Expected: Phase completes in <2 minutes, README.md has new comment.

---

## Key Architecture Concepts

### Phase Lifecycle
1. **QUEUED** → Waiting for execution
2. **EXECUTING** → Builder generating patch
3. **PENDING_REVIEW** → Auditor reviewing patch (if dual audit enabled)
4. **PENDING_APPROVAL** → Human approval required (if configured)
5. **COMPLETE** → Patch applied, CI passed (if enabled), deliverables met
6. **FAILED** → Exhausted retries or fatal error

### Retry & Escalation
- Default: 5 attempts per phase
- Complexity escalation: after 2 failures at current tier, escalate to next tier
  - low → medium → high
  - Model gets stronger (e.g., Sonnet → Opus)
- Doctor intervention: after 2+ failures, Doctor analyzes error and suggests fix or skip

### Routing Policies
Defined in `config/models.yaml` under `llm_routing_policies`:
- **best_first**: Start with strongest model (e.g., security changes)
- **progressive**: Start cheap, escalate on failure (e.g., docs, tests)
- **cheap_first**: (deprecated) Use cheapest model first

### Doctor System
- **Cheap model** (`claude-sonnet-4-5`): Fast triage for low-risk errors
- **Strong model** (`claude-opus-4-5`): Deep analysis for high-risk/complex errors
- Actions: `skip`, `retry`, `execute_fix` (whitelisted commands only), `escalate`, `replan`
- Telemetry: `doctor_cheap_calls`, `doctor_strong_calls`, `doctor_escalations`

### Model Intelligence (BUILD-146 P18)
- Centralized model registry: `config/models.yaml` + `src/autopack/model_registry.py`
- Audit enforcement: `python scripts/model_audit.py --fail-on "glm-4.6"` to block old model strings
- Refresh workflow: `python scripts/model_intel.py refresh-all` to update pricing/benchmarks

### SOT Memory Integration (BUILD-147)
- 6-file SOT set: `PROJECT_INDEX.json`, `BUILD_HISTORY.md`, `DEBUG_LOG.md`, `ARCHITECTURE_DECISIONS.md`, `FUTURE_PLAN.md`, `LEARNED_RULES.json`
- Indexing: Chunks SOT docs → vector store with stable IDs
- Retrieval: Includes SOT context in executor prompts when enabled
- **All opt-in**: disabled by default, requires explicit env flags

---

## Debugging Checklist

When a run fails or behaves unexpectedly:

1. **Check environment variables**: Did you set `PYTHONPATH=src` and `DATABASE_URL`?
2. **Check run state**: Is run in correct state (not already complete/failed)?
3. **Check phase state**: Is phase stuck in EXECUTING? Check process is alive.
4. **Check logs**: `.autonomous_runs/<run-id>/logs/` has detailed execution logs
5. **Check attempt history**: Last attempt outcome reveals failure mode
6. **Check token budget**: Did run exhaust token cap?
7. **Check model config**: Are model names in `config/models.yaml` valid and API keys set?
8. **Check scope paths**: Are paths in phase scope correct and accessible?
9. **Check database state**: Query Phase/Run tables directly to see raw state
10. **Check recent code changes**: Did a recent commit break something? `git log --oneline -10`

---

## Quick Reference: File Locations

| File | Purpose |
|------|---------|
| `src/autopack/autonomous_executor.py` | Main executor loop |
| `src/autopack/memory/memory_service.py` | Vector memory + SOT indexing |
| `src/autopack/memory/sot_indexing.py` | SOT chunking helpers |
| `src/autopack/model_registry.py` | Model config loader |
| `config/models.yaml` | Model mappings, routing policies, quotas |
| `scripts/create_run_from_json.py` | Run creation entry point |
| `scripts/model_audit.py` | Model string audit/enforcement |
| `scripts/tidy/run_tidy_all.py` | Tidy orchestrator |
| `scripts/tidy/tidy_workspace.py` | Core tidy logic |
| `docs/BUILD_HISTORY.md` | Authoritative build completion log |
| `docs/DEBUG_LOG.md` | Problem-solving history |
| `docs/ARCHITECTURE_DECISIONS.md` | Design rationale |
| `docs/IMPROVEMENTS_PLAN_SOT_RUNTIME_AND_MODEL_INTEL.md` | SOT implementation plan |

---

## Final Checklist Before Running

- [ ] Environment variables set (`PYTHONPATH`, `DATABASE_URL`, `PYTHONUTF8` on Windows)
- [ ] API keys configured (if using external LLMs)
- [ ] Run config JSON validated (valid paths, deliverables, complexity)
- [ ] Database checked (run doesn't already exist, or cleaned up)
- [ ] Dependencies installed (`pip install -r requirements.txt`)
- [ ] Workspace is clean (no uncommitted changes if using git integration)
- [ ] Token budget is reasonable (50k-500k for typical runs)
- [ ] CI checks disabled for dev (`AUTOPACK_SKIP_CI=1`) or enabled for prod
- [ ] Monitoring setup (how will you track progress?)
- [ ] Rollback plan (can you revert if something goes wrong?)

---

## Example: Full Production Run

```bash
# 1. Activate environment
source venv/bin/activate  # or venv\Scripts\activate on Windows

# 2. Set environment
export PYTHONUTF8=1
export PYTHONPATH=src
export DATABASE_URL="postgresql://autopack:autopack@localhost:5432/autopack"
export QDRANT_HOST="http://localhost:6333"
export ANTHROPIC_API_KEY="sk-ant-..."
export OPENAI_API_KEY="sk-..."
export AUTOPACK_ENABLE_MEMORY=true
export AUTOPACK_ENABLE_SOT_MEMORY_INDEXING=true
export AUTOPACK_SOT_RETRIEVAL_ENABLED=true
export TELEMETRY_DB_ENABLED=1

# 3. Verify database is clean
PYTHONPATH=src python -c "from autopack.database import SessionLocal; from autopack.models import Run; s=SessionLocal(); print('Existing runs:', [r.id for r in s.query(Run).all()]); s.close()"

# 4. Run build (with 2-hour timeout)
timeout 7200 python scripts/create_run_from_json.py scripts/runs/my-feature.json

# 5. Monitor progress (in another terminal)
watch -n 10 'PYTHONPATH=src python -c "from autopack.database import SessionLocal; from autopack.models import Phase, PhaseState; s=SessionLocal(); phases=s.query(Phase).filter(Phase.run_id==\"my-feature-build\").all(); print(f\"QUEUED: {sum(1 for p in phases if p.state==PhaseState.QUEUED)}\"); print(f\"EXECUTING: {sum(1 for p in phases if p.state==PhaseState.EXECUTING)}\"); print(f\"COMPLETE: {sum(1 for p in phases if p.state==PhaseState.COMPLETE)}\"); print(f\"FAILED: {sum(1 for p in phases if p.state==PhaseState.FAILED)}\"); s.close()"'

# 6. After completion, analyze results
PYTHONPATH=src python scripts/analyze_token_telemetry_v3.py --run-id my-feature-build

# 7. Update SOT documentation
# (Manually update BUILD_HISTORY.md, DEBUG_LOG.md, etc. based on results)

# 8. Run tidy to consolidate
PYTHONUTF8=1 python scripts/tidy/run_tidy_all.py --semantic --project autopack-framework

# 9. Commit results
git add .
git commit -m "feat: BUILD-XXX <feature-name>

<Brief description>

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
git push
```

---

## Additional Resources

- **Full SOT implementation details**: `docs/IMPROVEMENTS_PLAN_SOT_RUNTIME_AND_MODEL_INTEL.md`
- **Build history**: `docs/BUILD_HISTORY.md`
- **Debug log**: `docs/DEBUG_LOG.md`
- **Architecture decisions**: `docs/ARCHITECTURE_DECISIONS.md`
- **Model intelligence**: `docs/MODEL_INTELLIGENCE.md` (if exists)
- **Tidy system**: `scripts/tidy/README.md` (if exists)

---

**Document Version**: BUILD-147 Phase A P11 (2026-01-01)
**Maintained by**: Autopack Core Team
**Last Updated**: After SOT runtime validation hardening
