# Autopack Ideal State Definition

This document defines what "done" looks like for Autopack's evolution toward its README ideal state.

**Version**: 1.0.0
**Last Updated**: 2026-01-17

---

## Core Self-Improvement Loop

The self-improvement architecture must form a complete cycle:

```
Telemetry Collection → Memory Persistence → Context Injection → Task Generation → Task Execution → [repeat]
```

### Telemetry Pipeline

| Check | Verification | Status |
|-------|--------------|--------|
| TelemetryAnalyzer collects metrics | `grep -n "class TelemetryAnalyzer" src/autopack/telemetry/analyzer.py` | |
| Cost sinks tracked | Check for `cost_sinks` in analyzer output | |
| Failure modes captured | Check for `failure_modes` tracking | |
| Telemetry persists to memory | `telemetry_to_memory_bridge.py` calls MemoryService | |

**Verification Command:**
```bash
python -c "
from autopack.telemetry.analyzer import TelemetryAnalyzer
ta = TelemetryAnalyzer()
print('TelemetryAnalyzer: OK')
"
```

### Memory Service

| Check | Verification | Status |
|-------|--------------|--------|
| MemoryService.retrieve_insights() exists | `grep -n 'def retrieve_insights' src/autopack/memory/memory_service.py` | |
| Method queries telemetry_insights namespace | Check implementation queries correct namespace | |
| Returns list of insight dicts | Method returns `List[Dict]` | |

**Verification Command:**
```bash
python -c "
from autopack.memory.memory_service import MemoryService
ms = MemoryService()
# Check method exists
assert hasattr(ms, 'retrieve_insights'), 'retrieve_insights method missing'
print('MemoryService.retrieve_insights: OK')
"
```

### Task Generation

| Check | Verification | Status |
|-------|--------------|--------|
| TaskGenerator.generate_tasks() works | Method exists and callable | |
| _generate_improvement_tasks() is CALLED | Called in `_finalize_execution()`, not just defined | |
| Tasks generated from insights | TaskGenerator uses memory.retrieve_insights() | |

**Verification Command:**
```bash
# Check task generation is wired (should show call site, not just definition)
grep -n "_generate_improvement_tasks" src/autopack/executor/autonomous_loop.py | grep -v "def _generate"
```

Expected output should show a CALL like:
```
588:        self._generate_improvement_tasks()
```

NOT just the definition.

### Task Persistence

| Check | Verification | Status |
|-------|--------------|--------|
| GeneratedTask has database model | `class GeneratedTaskModel` in models.py | |
| Migration exists | `migrations/add_generated_tasks.sql` or equivalent | |
| TaskGenerator.persist_tasks() saves to DB | Method exists and uses session | |

**Verification Command:**
```bash
grep -n "class GeneratedTask" src/autopack/models.py
# Should show SQLAlchemy model, not just dataclass
```

### Task Retrieval

| Check | Verification | Status |
|-------|--------------|--------|
| get_pending_tasks() method exists | In TaskGenerator or dedicated service | |
| Returns tasks with status='pending' | Filters by status | |
| Executor loads tasks at run start | _load_improvement_tasks() called in initialization | |

**Verification Command:**
```bash
python -c "
from autopack.roadc.task_generator import TaskGenerator
tg = TaskGenerator()
assert hasattr(tg, 'get_pending_tasks'), 'get_pending_tasks method missing'
print('TaskGenerator.get_pending_tasks: OK')
"
```

---

## ROAD Framework (12 Components)

All 12 ROAD components must be operational:

| Component | Purpose | File Location | Status |
|-----------|---------|---------------|--------|
| ROAD-A | Phase outcome telemetry | `src/autopack/roada/` | |
| ROAD-B | Telemetry analysis | `src/autopack/roadb/` | |
| ROAD-C | Autonomous task generator | `src/autopack/roadc/task_generator.py` | |
| ROAD-G | Real-time anomaly detection | `src/autopack/roadg/` | |
| ROAD-H | Causal analysis | `src/autopack/roadh/` | |
| ROAD-I | Regression protection | `src/autopack/roadi/regression_protector.py` | |
| ROAD-J | Self-healing engine | `src/autopack/roadj/` | |
| ROAD-K | Meta-metrics | `src/autopack/roadk/` | |
| ROAD-L | Model selection optimization | `src/autopack/roadl/` | |

**Verification Command:**
```bash
# Check all ROAD directories exist
ls -la src/autopack/road*/
```

---

## Quality Gates

| Check | Target | Verification |
|-------|--------|--------------|
| Core tests passing | 4,901 tests | `pytest tests/ -v --tb=short` |
| No CRITICAL IMPs | 0 | Check AUTOPACK_IMPS_MASTER.json |
| No HIGH IMPs blocking loop | 0 | Check IMPs with category=automation |
| CI time | < 30 min | Check recent CI runs |

---

## Automation Safety

| Check | Verification | Status |
|-------|--------------|--------|
| High-impact actions require approval | Check for approval gates in task execution | |
| Audit logging for irreversible actions | Check for audit log writes | |
| Idempotency for task execution | Tasks can be re-run safely | |
| Rate limiting on external APIs | Circuit breaker and rate limits configured | |

---

## Full Verification Script

Run this to check all ideal state criteria:

```bash
#!/bin/bash
echo "=== Autopack Ideal State Verification ==="
echo ""

PASS=0
FAIL=0

# 1. retrieve_insights
echo -n "1. MemoryService.retrieve_insights(): "
if grep -q "def retrieve_insights" src/autopack/memory/memory_service.py 2>/dev/null; then
    echo "PASS"
    PASS=$((PASS+1))
else
    echo "FAIL - method not found"
    FAIL=$((FAIL+1))
fi

# 2. Task generation wired
echo -n "2. Task generation wired to executor: "
if grep "_generate_improvement_tasks" src/autopack/executor/autonomous_loop.py 2>/dev/null | grep -qv "def "; then
    echo "PASS"
    PASS=$((PASS+1))
else
    echo "FAIL - not called in executor"
    FAIL=$((FAIL+1))
fi

# 3. Task persistence model
echo -n "3. GeneratedTask database model: "
if grep -q "class GeneratedTaskModel\|class GeneratedTask.*Base" src/autopack/models.py 2>/dev/null; then
    echo "PASS"
    PASS=$((PASS+1))
else
    echo "FAIL - no database model"
    FAIL=$((FAIL+1))
fi

# 4. Task retrieval
echo -n "4. get_pending_tasks() method: "
if grep -q "def get_pending_tasks" src/autopack/roadc/task_generator.py 2>/dev/null; then
    echo "PASS"
    PASS=$((PASS+1))
else
    echo "FAIL - method not found"
    FAIL=$((FAIL+1))
fi

# 5. ROAD components
echo -n "5. ROAD framework directories: "
ROAD_COUNT=$(ls -d src/autopack/road*/ 2>/dev/null | wc -l)
if [ "$ROAD_COUNT" -ge 9 ]; then
    echo "PASS ($ROAD_COUNT components)"
    PASS=$((PASS+1))
else
    echo "FAIL (only $ROAD_COUNT components)"
    FAIL=$((FAIL+1))
fi

# 6. No CRITICAL IMPs
echo -n "6. No CRITICAL IMPs remaining: "
CRITICAL_COUNT=$(python -c "
import json
try:
    d = json.load(open('C:/Users/hshk9/OneDrive/Backup/Desktop/AUTOPACK_IMPS_MASTER.json'))
    critical = [i for i in d.get('unimplemented_imps', []) if i.get('priority') == 'critical']
    print(len(critical))
except:
    print(-1)
" 2>/dev/null)
if [ "$CRITICAL_COUNT" = "0" ]; then
    echo "PASS"
    PASS=$((PASS+1))
elif [ "$CRITICAL_COUNT" = "-1" ]; then
    echo "SKIP - could not read IMP file"
else
    echo "FAIL ($CRITICAL_COUNT critical IMPs)"
    FAIL=$((FAIL+1))
fi

echo ""
echo "=== RESULTS ==="
echo "PASSED: $PASS"
echo "FAILED: $FAIL"
echo ""

if [ "$FAIL" -eq 0 ]; then
    echo "IDEAL_STATE_REACHED: true"
    exit 0
else
    echo "IDEAL_STATE_REACHED: false"
    exit 1
fi
```

---

## Summary Checklist

Copy this for quick status tracking:

```
AUTOPACK IDEAL STATE CHECKLIST
==============================

SELF-IMPROVEMENT LOOP:
[ ] Telemetry collection operational
[ ] Telemetry → memory persistence working
[ ] MemoryService.retrieve_insights() implemented
[ ] _generate_improvement_tasks() called in executor
[ ] GeneratedTask has database model
[ ] get_pending_tasks() retrieves for next run
[ ] Tasks influence phase planning

ROAD FRAMEWORK:
[ ] ROAD-A: Phase outcome telemetry
[ ] ROAD-B: Telemetry analysis
[ ] ROAD-C: Task generator (AND WIRED)
[ ] ROAD-G: Anomaly detection
[ ] ROAD-H: Causal analysis
[ ] ROAD-I: Regression protection
[ ] ROAD-J: Self-healing
[ ] ROAD-K: Meta-metrics
[ ] ROAD-L: Model selection

QUALITY:
[ ] All core tests passing
[ ] No CRITICAL IMPs
[ ] No HIGH IMPs blocking self-improvement

SAFETY:
[ ] Approval gates for high-impact actions
[ ] Audit logging implemented
[ ] Idempotent task execution
```
