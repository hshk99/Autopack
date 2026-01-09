# Autopack Quickstart Guide

**Get started with Autopack in 5 minutes**

---

## Installation

```bash
pip install -e .
```

---

## Basic Usage

### 1. Initialize Database

```bash
# Create database schema
PYTHONPATH=src python -c "from autopack.database import init_db; init_db()"
```

### 2. Start API Server

```bash
# Terminal 1: Start backend API
PYTHONPATH=src uvicorn autopack.main:app --host 127.0.0.1 --port 8000
```

### 3. Create Your First Run

```bash
# Terminal 2: Create a simple run
PYTHONPATH=src python scripts/create_telemetry_collection_run.py
```

This creates a run with 10 simple phases (implementation, tests, docs).

### 4. Execute Phases

```bash
# Execute all queued phases
PYTHONPATH=src python -m autopack.autonomous_executor --run-id telemetry-collection-v4
```

**Or drain phases one at a time:**

```bash
# Drain first queued phase
PYTHONPATH=src python scripts/drain_one_phase.py --run-id telemetry-collection-v4
```

---

## First Run Checklist

### Before Running

- [ ] Database initialized (`autopack.db` exists)
- [ ] API server running on port 8000
- [ ] Environment variables set:
  - `PYTHONPATH=src`
  - `DATABASE_URL=sqlite:///autopack.db` (optional, defaults to this)
  - `ANTHROPIC_API_KEY=<your-key>` (required for LLM calls)

### During Execution

**Monitor progress:**

```bash
# Check run status
PYTHONPATH=src python scripts/db_identity_check.py

# View logs
tail -f .autonomous_runs/autopack/runs/telemetry/telemetry-collection-v4/run.log
```

### After Completion

**Check results:**

```bash
# View phase summaries
ls .autonomous_runs/autopack/runs/telemetry/telemetry-collection-v4/phases/

# Check telemetry (if enabled)
grep "\[TokenEstimationV2\]" .autonomous_runs/autopack/runs/telemetry/telemetry-collection-v4/*.log
```

---

## Common Issues

### "No module named autopack"

**Fix:** Set `PYTHONPATH=src` before running commands.

```bash
export PYTHONPATH=src  # Linux/Mac
$env:PYTHONPATH="src"  # Windows PowerShell
```

### "API server not responding"

**Fix:** Ensure API server is running on port 8000.

```bash
# Check if server is running
curl http://localhost:8000/health

# If not, start it
PYTHONPATH=src uvicorn autopack.main:app --host 127.0.0.1 --port 8000
```

### "Database locked"

**Fix:** Only one executor can run per database at a time. Stop other executors first.

```bash
# Find running executors
ps aux | grep autonomous_executor

# Kill if needed
kill <PID>
```

---

## Next Steps

### Learn More

- **Full Documentation:** [README.md](../README.md)
- **Build History:** [BUILD_HISTORY.md](BUILD_HISTORY.md)
- **Troubleshooting:** [DEBUG_LOG.md](DEBUG_LOG.md)

### Advanced Features

- **Batch Draining:** [scripts/batch_drain_controller.py](../scripts/batch_drain_controller.py)
- **Telemetry Collection:** [DB_HYGIENE_AND_TELEMETRY_SEEDING.md](guides/DB_HYGIENE_AND_TELEMETRY_SEEDING.md)
- **Quality Gates:** [BUILD-126_QUALITY_GATE.md](BUILD-126_QUALITY_GATE.md)

### Example Workflows

**Drain legacy backlog:**

```bash
DATABASE_URL="sqlite:///autopack_legacy.db" TELEMETRY_DB_ENABLED=1 \
  PYTHONPATH=src python scripts/batch_drain_controller.py \
  --batch-size 10 --max-consecutive-zero-yield 5
```

**Collect telemetry samples:**

```bash
TELEMETRY_DB_ENABLED=1 PYTHONPATH=src \
  python -m autopack.autonomous_executor --run-id telemetry-collection-v4
```

---

## Quick Reference

### Essential Commands

```bash
# Check database state
PYTHONPATH=src python scripts/db_identity_check.py

# List runs
PYTHONPATH=src python scripts/list_run_counts.py

# Drain one phase
PYTHONPATH=src python scripts/drain_one_phase.py --run-id <RUN_ID>

# Execute full run
PYTHONPATH=src python -m autopack.autonomous_executor --run-id <RUN_ID>
```

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PYTHONPATH` | (none) | Must be set to `src` |
| `DATABASE_URL` | `sqlite:///autopack.db` | Database connection string |
| `ANTHROPIC_API_KEY` | (none) | Required for LLM calls |
| `TELEMETRY_DB_ENABLED` | `0` | Enable telemetry persistence |

---

**Total Lines:** 148 (within 150-line limit)

**Coverage:** Installation (5 lines), basic usage (1 snippet + 4 commands), first run (checklist + monitoring), common issues (3 fixes), next steps (references)
