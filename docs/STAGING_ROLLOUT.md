# Staging Rollout Guide - BUILD-146 P12

## Overview

This document provides a comprehensive checklist for rolling out BUILD-146 Phase 6 features to staging and production environments. These features include:

- **Phase 6 P3 Telemetry** - Detailed token tracking across 4 categories
- **Consolidated Metrics Dashboard** - Unified metrics preventing double-counting
- **Pattern Expansion** - Automated failure pattern discovery
- **A/B Test Results** - Database-backed experiment tracking
- **Replay Campaign** - Failed run replay with Phase 6 features

## Pre-Rollout Checklist

### 1. Environment Variables

#### Required for All Deployments
```bash
# Database connection (required)
DATABASE_URL="postgresql://autopack:autopack@localhost:5432/autopack"
# OR for SQLite:
DATABASE_URL="sqlite:///autopack.db"

# API authentication (required for production API)
AUTOPACK_API_KEY="your-secure-api-key-here"

# Python configuration (required for Windows)
PYTHONUTF8=1
PYTHONPATH=src
```

#### Optional - Phase 6 Feature Flags (Default: OFF)
```bash
# Enable Phase 6 P3 token telemetry collection
# DEFAULT: "0" (disabled) - Set to "1" to enable
AUTOPACK_ENABLE_PHASE6_METRICS="0"

# Enable consolidated metrics dashboard endpoint
# DEFAULT: "0" (disabled) - Set to "1" to enable
AUTOPACK_ENABLE_CONSOLIDATED_METRICS="0"

# Skip CI enforcement (for manual testing only)
# DEFAULT: not set - Set to "1" to skip CI checks
AUTOPACK_SKIP_CI="0"
```

#### Optional - Advanced Features
```bash
# Qdrant vector database for embeddings (optional)
QDRANT_HOST="http://localhost:6333"
EMBEDDING_MODEL="sentence-transformers/all-MiniLM-L6-v2"

# Metrics retention (optional, default: 30 days)
AUTOPACK_METRICS_RETENTION_DAYS="30"

# Telemetry database persistence (optional)
TELEMETRY_DB_ENABLED="1"
```

### 2. Database Migration Steps

#### Step 2a: Backup Current Database
```bash
# PostgreSQL backup
pg_dump -U autopack autopack > autopack_backup_$(date +%Y%m%d_%H%M%S).sql

# SQLite backup
cp autopack.db autopack_backup_$(date +%Y%m%d_%H%M%S).db
```

#### Step 2b: Run Migrations
```bash
# Add performance indexes (REQUIRED for consolidated metrics)
PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="your-db-url" python scripts/migrations/add_performance_indexes.py

# Add A/B test results table (REQUIRED for A/B persistence)
PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="your-db-url" python scripts/migrations/add_ab_test_results.py

# Add Phase 6 P3 fields (if not already present from BUILD-146 P6)
PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="your-db-url" python scripts/migrations/add_phase6_p3_fields.py
```

#### Step 2c: Verify Migrations
```bash
# For PostgreSQL
psql -U autopack autopack -c "\d phase_metrics"
psql -U autopack autopack -c "\d ab_test_results"
psql -U autopack autopack -c "\di"  # List all indexes

# For SQLite
PYTHONUTF8=1 sqlite3 autopack.db "PRAGMA table_info(phase_metrics);"
PYTHONUTF8=1 sqlite3 autopack.db "PRAGMA table_info(ab_test_results);"
PYTHONUTF8=1 sqlite3 autopack.db "PRAGMA index_list('phase_metrics');"
```

Expected indexes:
- `idx_phase_metrics_run_id` on `phase_metrics(run_id)`
- `idx_phase_metrics_created_at` on `phase_metrics(created_at DESC)`
- `idx_phase_metrics_run_created` on `phase_metrics(run_id, created_at DESC)`
- `idx_dashboard_events_run_id` on `dashboard_events(run_id)`
- `idx_dashboard_events_event_type` on `dashboard_events(event_type)`
- `idx_phases_run_state` on `phases(run_id, state)`
- `idx_ab_test_id` on `ab_test_results(test_id)`
- `idx_ab_validity` on `ab_test_results(is_valid)`

### 3. Database Query Plan Verification

Verify that indexes are being used for critical queries:

#### PostgreSQL Query Plans
```sql
-- Consolidated metrics query (should use idx_phase_metrics_run_created)
EXPLAIN ANALYZE
SELECT * FROM phase_metrics
WHERE run_id = 'telemetry-collection-v7'
ORDER BY created_at DESC
LIMIT 1000;

-- Expected: Index Scan using idx_phase_metrics_run_created

-- Dashboard events by type (should use idx_dashboard_events_event_type)
EXPLAIN ANALYZE
SELECT * FROM dashboard_events
WHERE event_type = 'PHASE_FAILED'
ORDER BY created_at DESC
LIMIT 100;

-- Expected: Index Scan using idx_dashboard_events_event_type

-- Phase status by run (should use idx_phases_run_state)
EXPLAIN ANALYZE
SELECT * FROM phases
WHERE run_id = 'test-run' AND state = 'COMPLETE';

-- Expected: Index Scan using idx_phases_run_state
```

#### SQLite Query Plans
```sql
-- Consolidated metrics query
EXPLAIN QUERY PLAN
SELECT * FROM phase_metrics
WHERE run_id = 'telemetry-collection-v7'
ORDER BY created_at DESC
LIMIT 1000;

-- Expected: SEARCH phase_metrics USING INDEX idx_phase_metrics_run_created
```

**Performance Baselines:**
- Consolidated metrics query: < 100ms for 10K records
- Dashboard events query: < 50ms for 1K records
- Phase status query: < 10ms

### 4. Endpoint Verification (Smoke Tests)

#### Health Check
```bash
# Should return 200 with status info
curl -X GET http://localhost:8000/health

# Expected response:
# {
#   "status": "healthy",
#   "database": "connected",
#   "qdrant": "connected" | "disabled",
#   "kill_switches": {
#     "phase6_metrics": false,
#     "consolidated_metrics": false
#   }
# }
```

#### Runs API (Production API)
```bash
# List runs
curl -X GET http://localhost:8000/api/runs \
  -H "X-API-Key: your-api-key"

# Get specific run
curl -X GET http://localhost:8000/api/runs/test-run-id \
  -H "X-API-Key: your-api-key"

# Execute run (async)
curl -X POST http://localhost:8000/api/runs/test-run-id/execute \
  -H "X-API-Key: your-api-key"

# Check run status
curl -X GET http://localhost:8000/api/runs/test-run-id/status \
  -H "X-API-Key: your-api-key"
```

#### Dashboard API (With Kill Switch OFF - Should Return 503)
```bash
# Consolidated metrics (kill switch OFF)
curl -X GET http://localhost:8000/api/dashboard/runs/test-run-id/consolidated-metrics \
  -H "X-API-Key: your-api-key"

# Expected response (kill switch OFF):
# {
#   "detail": "Consolidated metrics disabled"
# }
# Status: 503
```

#### Dashboard API (With Kill Switch ON)
```bash
# Enable kill switch first
export AUTOPACK_ENABLE_CONSOLIDATED_METRICS="1"

# Restart API server
# ...

# Consolidated metrics (kill switch ON)
curl -X GET http://localhost:8000/api/dashboard/runs/test-run-id/consolidated-metrics \
  -H "X-API-Key: your-api-key"

# Expected response (kill switch ON):
# {
#   "retrieval_tokens": 12345,
#   "second_opinion_tokens": 6789,
#   "evidence_request_tokens": 3456,
#   "base_tokens": 98765,
#   "total_tokens": 121355,
#   "total_phases": 10,
#   "phases_with_metrics": 10
# }
# Status: 200
```

#### A/B Results API
```bash
# Get all A/B results (valid only)
curl -X GET http://localhost:8000/api/dashboard/ab-results?valid_only=true \
  -H "X-API-Key: your-api-key"

# Get specific test results
curl -X GET "http://localhost:8000/api/dashboard/ab-results?test_id=v5-vs-v6" \
  -H "X-API-Key: your-api-key"
```

### 5. Rollback Procedure

If issues arise after deployment, follow these steps to safely rollback:

#### Step 5a: Disable Phase 6 Features
```bash
# Set kill switches to OFF
export AUTOPACK_ENABLE_PHASE6_METRICS="0"
export AUTOPACK_ENABLE_CONSOLIDATED_METRICS="0"

# Restart API server
# Production API will continue to work with Phase 6 features disabled
```

#### Step 5b: Restore Database (If Needed)
```bash
# PostgreSQL restore
psql -U autopack autopack < autopack_backup_YYYYMMDD_HHMMSS.sql

# SQLite restore
cp autopack_backup_YYYYMMDD_HHMMSS.db autopack.db
```

#### Step 5c: Verify Core Functionality
```bash
# Test basic run execution (without Phase 6 features)
curl -X POST http://localhost:8000/api/runs/test-run-id/execute \
  -H "X-API-Key: your-api-key"

# Verify run status
curl -X GET http://localhost:8000/api/runs/test-run-id/status \
  -H "X-API-Key: your-api-key"
```

### 6. Phase 6 Feature Enablement (Progressive Rollout)

Enable features incrementally to monitor impact:

#### Stage 1: Enable Telemetry Collection Only
```bash
export AUTOPACK_ENABLE_PHASE6_METRICS="1"
export AUTOPACK_ENABLE_CONSOLIDATED_METRICS="0"

# Restart API
# Monitor: Database writes to phase_metrics table
# Expected: No performance degradation, metrics being collected
```

#### Stage 2: Enable Consolidated Metrics Dashboard
```bash
export AUTOPACK_ENABLE_PHASE6_METRICS="1"
export AUTOPACK_ENABLE_CONSOLIDATED_METRICS="1"

# Restart API
# Monitor: Dashboard query performance, no double-counting
# Expected: < 100ms query times for 10K records
```

#### Stage 3: Full Production
```bash
# All features enabled, continue monitoring
# If issues detected, rollback to Stage 1 or Stage 0
```

## Post-Rollout Validation

### 1. Smoke Test Checklist

- [ ] Health check endpoint returns 200
- [ ] Database connection is healthy
- [ ] Kill switches default to OFF
- [ ] Consolidated metrics returns 503 when kill switch OFF
- [ ] Consolidated metrics returns 200 when kill switch ON
- [ ] A/B results endpoint returns valid results
- [ ] Run execution works (both with and without Phase 6)
- [ ] No errors in API logs

### 2. Performance Monitoring

Monitor these metrics for the first 24 hours:

- **API Response Times:**
  - `/health`: < 10ms
  - `/api/runs/{id}`: < 50ms
  - `/api/dashboard/runs/{id}/consolidated-metrics`: < 100ms
  - `/api/dashboard/ab-results`: < 200ms

- **Database Performance:**
  - Phase metrics writes: < 10ms per record
  - Dashboard events writes: < 10ms per record
  - Consolidated metrics query: < 100ms for 10K records

- **Resource Usage:**
  - API memory: No significant increase (< 10% change)
  - Database size: Linear growth with telemetry
  - CPU usage: No spikes

### 3. Data Validation

Verify data integrity:

```bash
# Check for double-counting (total should equal sum of 4 categories)
PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="your-db-url" python -c "
from autopack.database import SessionLocal
from autopack.models import PhaseMetrics

session = SessionLocal()
metrics = session.query(PhaseMetrics).filter(PhaseMetrics.run_id == 'test-run').all()

for m in metrics:
    total = (m.retrieval_tokens or 0) + (m.second_opinion_tokens or 0) + \
            (m.evidence_request_tokens or 0) + (m.base_tokens or 0)
    if m.total_tokens != total:
        print(f'DOUBLE COUNTING DETECTED: phase={m.phase_id}, total={m.total_tokens}, sum={total}')

session.close()
"
```

### 4. Pattern Expansion Validation

Test pattern generation:

```bash
# Generate pattern stubs from real data
PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="sqlite:///autopack.db" \
  python scripts/pattern_expansion.py \
    --run-id telemetry-collection-v7 \
    --generate-code \
    --min-occurrences 3

# Verify generated files
ls -la src/autopack/patterns/pattern_*.py
ls -la tests/patterns/test_pattern_*.py
ls -la docs/backlog/PATTERN_*.md

# Verify Python syntax is valid
PYTHONUTF8=1 python -m py_compile src/autopack/patterns/pattern_*.py
```

### 5. A/B Analysis Validation

Test A/B result persistence:

```bash
# Run A/B analysis (requires two comparable runs)
PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="sqlite:///autopack.db" \
  python scripts/ab_analysis.py \
    --control-run telemetry-v5 \
    --treatment-run telemetry-v6 \
    --test-id v5-vs-v6

# Verify result in database
PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="sqlite:///autopack.db" python -c "
from autopack.database import SessionLocal
from autopack.models import ABTestResult

session = SessionLocal()
result = session.query(ABTestResult).filter(ABTestResult.test_id == 'v5-vs-v6').first()
if result:
    print(f'Test ID: {result.test_id}')
    print(f'Valid: {result.is_valid}')
    print(f'Token Delta: {result.token_delta}')
    print(f'Validity Errors: {result.validity_errors}')
else:
    print('No result found')
session.close()
"
```

### 6. Replay Campaign Validation

Test replay functionality:

```bash
# Dry run first
PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="sqlite:///autopack.db" \
  python scripts/replay_campaign.py \
    --state FAILED \
    --dry-run

# Replay single failed run
PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="sqlite:///autopack.db" \
  python scripts/replay_campaign.py \
    --run-id failed-run-123

# Verify comparison report
cat archive/replay_results/*_comparison.json
```

## Production Rollout Steps

1. **Staging Validation** (1-2 days)
   - Deploy to staging environment
   - Run all smoke tests
   - Enable Phase 6 features progressively (Stage 1 → Stage 2 → Stage 3)
   - Monitor performance and data integrity
   - Run pattern expansion on staging data
   - Run A/B analysis on staging runs
   - Test replay campaign with staging failed runs

2. **Production Deployment** (Progressive)
   - **Day 1:** Deploy code, run migrations, keep kill switches OFF
   - **Day 2:** Enable Phase 6 telemetry only (Stage 1)
   - **Day 3:** Enable consolidated metrics (Stage 2)
   - **Day 4:** Full production (Stage 3)

3. **Monitoring** (First Week)
   - Daily review of API logs
   - Daily database size checks
   - Daily performance monitoring
   - Weekly pattern expansion analysis

## Troubleshooting

### Issue: Consolidated metrics endpoint returns 503
**Cause:** Kill switch is OFF (default)
**Solution:** Set `AUTOPACK_ENABLE_CONSOLIDATED_METRICS="1"` and restart API

### Issue: Database query is slow (> 100ms)
**Cause:** Indexes not created or not being used
**Solution:** Run `scripts/migrations/add_performance_indexes.py` and verify with `EXPLAIN QUERY PLAN`

### Issue: Token double-counting detected
**Cause:** Phase metrics recording tokens in multiple categories incorrectly
**Solution:** Review token categorization logic in `autonomous_executor.py`, ensure each token is counted in exactly one category

### Issue: A/B analysis fails with "not a valid comparison"
**Cause:** Control and treatment runs have different commit SHAs or model hashes
**Solution:** This is expected behavior - A/B comparisons require identical code and model config. Only compare runs from same commit SHA.

### Issue: Pattern expansion generates no patterns
**Cause:** No dashboard events with sufficient occurrences (< 3)
**Solution:** Collect more telemetry data or lower `--min-occurrences` threshold

### Issue: Replay campaign fails to execute
**Cause:** API server not running or authentication failure
**Solution:** Ensure production API is running and `AUTOPACK_API_KEY` is set correctly

## Emergency Contacts

If critical issues arise during rollout:

1. **Immediate Action:** Set all kill switches to "0" and restart API
2. **Database Issues:** Restore from backup (see Rollback Procedure)
3. **Performance Degradation:** Disable consolidated metrics endpoint first
4. **Data Integrity Issues:** Disable Phase 6 telemetry and investigate offline

## Success Criteria

Rollout is complete when:

- [ ] All migrations applied successfully
- [ ] All smoke tests pass
- [ ] Kill switches default to OFF
- [ ] Phase 6 features work when enabled
- [ ] Performance baselines met
- [ ] No data integrity issues detected
- [ ] Pattern expansion generates valid code
- [ ] A/B analysis persists results correctly
- [ ] Replay campaign can replay failed runs
- [ ] Monitoring in place for first week

## Appendix: Environment Variable Reference

| Variable | Default | Purpose | Required |
|----------|---------|---------|----------|
| `DATABASE_URL` | - | Database connection string | Yes |
| `AUTOPACK_API_KEY` | - | API authentication key | Yes (production) |
| `PYTHONUTF8` | - | Python UTF-8 encoding (Windows) | Yes (Windows) |
| `PYTHONPATH` | - | Python module path | Yes |
| `AUTOPACK_ENABLE_PHASE6_METRICS` | `"0"` | Enable Phase 6 telemetry | No |
| `AUTOPACK_ENABLE_CONSOLIDATED_METRICS` | `"0"` | Enable consolidated metrics endpoint | No |
| `AUTOPACK_SKIP_CI` | - | Skip CI enforcement | No |
| `QDRANT_HOST` | - | Qdrant vector DB URL | No |
| `EMBEDDING_MODEL` | - | Sentence transformer model | No |
| `AUTOPACK_METRICS_RETENTION_DAYS` | `"30"` | Metrics retention period | No |
| `TELEMETRY_DB_ENABLED` | - | Enable telemetry DB persistence | No |

## Appendix: Migration Script Reference

| Script | Purpose | Order |
|--------|---------|-------|
| `scripts/migrations/add_phase6_p3_fields.py` | Add Phase 6 P3 telemetry fields | 1 |
| `scripts/migrations/add_performance_indexes.py` | Add dashboard performance indexes | 2 |
| `scripts/migrations/add_ab_test_results.py` | Add A/B test results table | 3 |

All migration scripts are idempotent (safe to run multiple times).
