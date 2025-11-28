# Autopack Quickstart Guide - Building Your First Application

**Last Updated**: 2025-11-26
**Status**: Phase 1b Complete - Ready for First Application Build

---

## Pre-Flight Checklist

Before building your first application, verify that Phase 1b is complete:

### ✅ Infrastructure Status

```bash
# 1. Database running
docker-compose ps  # Should show autopack-db and autopack-api as "Up"

# 2. All probes green
bash scripts/autonomous_probe_complete.sh  # Should show "All chunks implemented successfully!"

# 3. API healthy
curl http://localhost:8000/health  # Should return {"status": "ok"}
```

### ✅ Configuration Verified (Nov 26, 2025)

Per [docs/CLAUDE_FINAL_CONSENSUS_GPT_ROUND4.md](docs/CLAUDE_FINAL_CONSENSUS_GPT_ROUND4.md):

- **Models**: Claude Opus 4.5 (Nov 24 release), Claude Sonnet 4.5, GPT-5, gpt-4o, gpt-4o-mini ✅
- **Routing**: 8 fine-grained categories (security, schema, external feature reuse, etc.) ✅
- **Budget warnings**: Alert system (not hard blocks) ✅
- **Context ranking**: JIT loading (targets 30-50% token savings) ✅
- **Risk scorer**: LOC delta, critical paths, test coverage, hygiene ✅

---

## Recommended First Application: Simple Task Tracker

**Why This Application**:
- **Small scope**: 20-50 phases (ideal for first run)
- **Manual tracking**: No Phase 2 automation needed yet
- **Validates**: Routing, budgets, context selection, learned rules
- **Low risk**: No security-critical or destructive migrations

---

## Step-by-Step: Build Your First App

### Step 1: Define Your Application

Create a project spec file:

```bash
# Create project directory
mkdir -p .autonomous_runs/task-tracker

# Create spec
cat > .autonomous_runs/task-tracker/project_spec.json <<'EOF'
{
  "project_id": "task-tracker",
  "project_type": "web_app",
  "description": "Simple task tracker with FastAPI backend and React frontend",
  "features": [
    "Create, read, update, delete tasks",
    "Mark tasks as complete/incomplete",
    "Filter tasks by status",
    "Simple UI with task list"
  ],
  "tech_stack": {
    "backend": "FastAPI + PostgreSQL",
    "frontend": "React + Vite",
    "testing": "pytest + React Testing Library"
  }
}
EOF
```

### Step 2: Create Manual Tracking Sheet

Create a simple tracking file for this first build:

```bash
cat > .autonomous_runs/task-tracker/MANUAL_TRACKING.md <<'EOF'
# Manual Phase Tracking - task-tracker

## Run Info
- Run ID: task-tracker-v1
- Started: 2025-11-26
- Project ID: task-tracker

## Phases Executed

### Phase 1: Setup database schema
- **Date**: 2025-11-26 10:00
- **Category**: schema_contract_change_additive (manually assigned)
- **Complexity**: medium
- **Attempts**: 1 (succeeded first try)
- **Models**: gpt-4o builder, claude-sonnet-4-5 auditor
- **Tokens (approx)**: 8k input, 2k output
- **Issues**: None
- **Notes**: Worked great! Added Task table with id, title, description, completed, created_at.

### Phase 2: Create API endpoints
- **Date**: 2025-11-26 10:15
- **Category**: core_backend_high (manually assigned)
- **Complexity**: medium
- **Attempts**: 1
- **Models**: gpt-4o builder, claude-sonnet-4-5 auditor
- **Tokens (approx)**: 12k input, 4k output
- **Issues**: Minor - missing type hints (auditor caught it)
- **Notes**: Added CRUD endpoints. Auditor flagged missing type annotations, builder fixed immediately.

### Phase 3: [Next phase...]
- **Date**:
- **Category**:
- **Notes**:

## Summary Stats (manual calculation)
- **Total phases**: 2 (so far)
- **Total attempts**: 2
- **Total tokens (approx)**: ~26k
- **Category distribution**:
  - schema_contract_change_additive: 1
  - core_backend_high: 1
- **Escalations**: 0
- **Learned rules recorded**: 1 (type hints)

## Observations
- Context ranking seems effective - didn't load unnecessary files
- Risk scorer flagged Phase 2 as medium (50 points - LOC delta + critical path)
- Budget warnings: None yet (well under 50M OpenAI cap)
- Dual auditing: Only used for security categories (none yet in this build)

## Next Steps
- [ ] Complete frontend phases
- [ ] Add tests
- [ ] Review learned rules effectiveness after 20-50 phases
EOF
```

### Step 3: Start Services

```bash
# Ensure services are running
docker-compose up -d

# Verify
docker-compose ps
```

### Step 4: Launch First Build (Manual Supervised Approach)

**Recommended for first build**: Run phases manually to understand the system.

```python
# Create run_first_build.py
cat > run_first_build.py <<'PYTHON'
"""
Manual supervised build for task-tracker (first application).
Run phases one at a time to observe behavior.
"""

import requests
import json
from datetime import datetime

API_URL = "http://localhost:8000"
PROJECT_ID = "task-tracker"
RUN_ID = f"task-tracker-v1-{datetime.now().strftime('%Y%m%d')}"

def create_run():
    """Create a new run."""
    response = requests.post(f"{API_URL}/runs", json={
        "run_id": RUN_ID,
        "project_id": PROJECT_ID,
        "description": "First build: Simple task tracker application",
        "tiers": [
            {"tier_id": "tier-1", "tier_num": 1, "title": "Backend Setup"},
            {"tier_id": "tier-2", "tier_num": 2, "title": "Frontend Setup"},
            {"tier_id": "tier-3", "tier_num": 3, "title": "Testing"}
        ],
        "phases": [
            # Tier 1: Backend
            {
                "phase_id": "phase-1-db-schema",
                "tier_id": "tier-1",
                "description": "Create database schema for Task model",
                "task_category": "schema_contract_change_additive",
                "complexity": "medium"
            },
            {
                "phase_id": "phase-2-api-endpoints",
                "tier_id": "tier-1",
                "description": "Create CRUD API endpoints for tasks",
                "task_category": "core_backend_high",
                "complexity": "medium"
            },
            # Add more phases as needed...
        ]
    })
    print(f"Run created: {response.json()}")
    return response.json()

def execute_phase_manually(phase_id: str):
    """
    Execute a single phase manually.
    This is a placeholder - you'll call Builder/Auditor here.
    """
    print(f"\n=== Executing {phase_id} ===")

    # TODO: Call Builder, Auditor, etc.
    # For now, just update phase status
    response = requests.put(f"{API_URL}/runs/{RUN_ID}/phases/{phase_id}", json={
        "state": "DONE_SUCCESS",
        "notes": "Manually executed for first build observation"
    })
    print(f"Phase {phase_id} completed: {response.json()}")

if __name__ == "__main__":
    print("=== Starting First Build ===")
    print(f"Project: {PROJECT_ID}")
    print(f"Run ID: {RUN_ID}")

    # Create run
    run_data = create_run()

    # Execute first phase
    execute_phase_manually("phase-1-db-schema")

    print("\n=== Next Steps ===")
    print("1. Review phase execution in dashboard: http://localhost:8000/dashboard")
    print("2. Check learned rules: python scripts/analyze_learned_rules.py --project-id task-tracker")
    print("3. Update MANUAL_TRACKING.md with observations")
    print("4. Continue with next phases")
PYTHON

# Run it
python run_first_build.py
```

### Step 5: Monitor Progress

**Dashboard** (recommended):
```bash
# Open in Cursor: Ctrl+Shift+P → "Simple Browser: Show"
# URL: http://localhost:8000/dashboard
```

**API Status**:
```bash
# Check run status
curl http://localhost:8000/runs/task-tracker-v1-20251126

# Check usage
curl http://localhost:8000/dashboard/usage
```

### Step 6: Review After 20-50 Phases

After completing your first build, review effectiveness:

```bash
# 1. Analyze learned rules
python scripts/analyze_learned_rules.py --project-id task-tracker

# 2. Review your manual tracking
cat .autonomous_runs/task-tracker/MANUAL_TRACKING.md

# 3. Check key metrics:
#    - Category distribution: Are categories correctly assigned?
#    - Escalation frequency: Did progressive strategies escalate too often?
#    - Token usage: Is context ranking providing ~30-50% savings?
#    - Risk scorer accuracy: Did high-risk scores correlate with actual issues?
```

---

## What to Track Manually (First 20-50 Phases)

Per [docs/IMPLEMENTATION_STATUS_AND_MONITORING_PLAN.md](docs/IMPLEMENTATION_STATUS_AND_MONITORING_PLAN.md), track these:

### 1. Category Distribution
```
Track:
- How many phases in each category?
- Are security_auth_change, external_feature_reuse_remote rare (<10%)?
- Are docs/tests using cheap_first correctly?

Goal: Validate category detection heuristics
```

### 2. Escalation Frequency
```
Track:
- How often did progressive strategies escalate (gpt-4o → gpt-5)?
- After how many attempts?

Goal: Tune escalate_to.after_attempts values
```

### 3. Token Savings (Context Ranking)
```
Track (estimate):
- Tokens before context ranking (all files loaded)
- Tokens after context ranking (JIT loading)

Goal: Validate 30-50% savings claim
```

### 4. Risk Scorer Calibration
```
Track:
- Risk score for each phase (0-100)
- Which phases had issues/failures?
- Correlation between high scores and actual problems?

Goal: Calibrate risk thresholds with real incident data
```

### 5. Budget Warnings
```
Track:
- Did you hit 80% soft limit warnings?
- Did you exhaust quotas?
- Were warnings helpful?

Goal: Ensure alert-based system is sufficient (vs hard blocks)
```

---

## Expected Outcomes (First Build)

### Success Criteria ✅

1. **Build completes** with 20-50 phases
2. **No quota exhaustion** (should be well under 50M OpenAI cap)
3. **Learned rules recorded** (at least 3-5 hints)
4. **Category routing works** (security phases use best_first, docs use cheap_first)
5. **Context ranking functional** (no file-not-found errors)

### What You'll Learn 📊

- **Which categories are most common** in your builds
- **Whether escalation thresholds are tuned correctly** (progressive strategies)
- **If context ranking actually saves tokens** (validate 30-50% claim)
- **Risk scorer accuracy** (do high scores predict issues?)
- **Budget warning effectiveness** (are alerts helpful?)

---

## After First Build: Decide on Phase 2

Per earlier conversation, **only implement Phase 2 features that prove necessary**:

### Implement If:
- ✅ Manual tracking is tedious (≥50 phases)
- ✅ Need weekly reports for stakeholders
- ✅ Dashboard needs historical charts

### Skip If:
- ❌ Manual tracking for 20-50 phases was fine
- ❌ Don't need automated reporting yet
- ❌ Current dashboard real-time view is sufficient

---

## Troubleshooting

### Issue: Tests Failing
```bash
# Some tests require OPENAI_API_KEY
export OPENAI_API_KEY=your_key_here
pytest tests/ -v
```

### Issue: Database Not Connecting
```bash
# Check containers
docker-compose ps

# Restart if needed
docker-compose down
docker-compose up -d
```

### Issue: Context Ranking Not Working
```bash
# Check logs
docker-compose logs autopack-api | grep "context_selector"

# Verify files exist
ls -la .autonomous_runs/task-tracker/
```

---

## Reference Documents

- **[README.md](README.md)** - Complete system overview
- **[docs/CLAUDE_FINAL_CONSENSUS_GPT_ROUND4.md](docs/CLAUDE_FINAL_CONSENSUS_GPT_ROUND4.md)** - Model selection consensus (Nov 2025)
- **[docs/IMPLEMENTATION_STATUS_AND_MONITORING_PLAN.md](docs/IMPLEMENTATION_STATUS_AND_MONITORING_PLAN.md)** - What's complete vs monitoring
- **[docs/FUTURE_CONSIDERATIONS_TRACKING.md](docs/FUTURE_CONSIDERATIONS_TRACKING.md)** - 29 deferred items with decision criteria
- **[config/models.yaml](config/models.yaml)** - Model routing configuration

---

## Next Steps

1. **✅ Complete first build** (20-50 phases)
2. **✅ Review manual tracking** data
3. **✅ Analyze learned rules** effectiveness
4. **✅ Decide on Phase 2** implementation (based on actual needs)
5. **✅ Build 2nd application** with refined config

---

**You're Ready!** 🚀

The system is production-ready for your first build. Start with the simple task tracker, track manually, and let the data guide Phase 2 decisions.

Good luck! 🎯
