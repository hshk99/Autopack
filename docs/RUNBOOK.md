# Autopack Operational Runbook

## Daily Operations

### Starting Autopack

```bash
# Start API server
PYTHONPATH=src python -m uvicorn autopack.main:app --host 127.0.0.1 --port 8000

# Start executor
python src/autopack/autonomous_executor.py --run-id <run-id>
```

### Stopping Autopack

```bash
# Graceful stop
echo "stop:<run-id>" > .autonomous_runs/.stop_executor

# Force kill (emergency only)
pkill -f autonomous_executor
```

## Upgrades

### Database Migrations

```bash
# Check current schema version
python scripts/db_version.py

# Run migrations
python scripts/run_migrations.py
```

### Dependency Updates

```bash
# Update requirements
bash scripts/regenerate_requirements.sh

# Verify compatibility
pytest tests/test_integration.py
```

## Incident Recovery

### Stuck Run Recovery

1. Check executor logs: `tail -f .autonomous_runs/<run-id>/executor.log`
2. Identify stuck phase: `sqlite3 autopack.db "SELECT * FROM phases WHERE status='EXECUTING'"`
3. Force phase timeout: `echo "timeout:<phase-id>" > .autonomous_runs/.force_timeout`

### Database Corruption

1. Stop all executors
2. Restore from backup: `autopack restore --input backup-YYYY-MM-DD.tar.gz`
3. Verify integrity: `sqlite3 autopack.db "PRAGMA integrity_check"`

### SOT Ledger Conflicts

1. If docs/BUILD_HISTORY.md has merge conflicts, manually resolve (append-only structure)
2. Run tidy to consolidate: `python scripts/tidy/run_tidy.py`
3. Verify SOT integrity: `pytest tests/test_sot_integrity.py`

## Monitoring

### Key Metrics

- Token usage: Check dashboard at http://localhost:8000/dashboard
- Circuit breaker health: `curl http://localhost:8000/health`
- Connection pool: Check `db_pool_health` in health endpoint

### Alert Thresholds

- Token usage >80% of cap: Review run efficiency
- HTTP 500 errors >5 in 10 min: Check API logs
- Circuit breaker OPEN: Check external service health

## Multi-Device Sync

### Laptop to Desktop Sync

```bash
# On laptop:
autopack backup --output ~/autopack-backup.tar.gz
# Copy file to desktop

# On desktop:
autopack restore --input ~/autopack-backup.tar.gz
```

### Safe Non-Local API Binding

```bash
# For cross-device API access, use explicit bind address:
export AUTOPACK_BIND_ADDRESS=192.168.1.100  # Your machine's IP
export AUTOPACK_ALLOW_NON_LOCAL=1  # Required for non-localhost
PYTHONPATH=src python -m uvicorn autopack.main:app --host $AUTOPACK_BIND_ADDRESS --port 8000

# Access from other device:
curl http://192.168.1.100:8000/health
```

## Troubleshooting

### Connection Pool Exhaustion

```bash
# Check pool stats
sqlite3 autopack.db "SELECT COUNT(*) FROM pg_stat_activity"

# Force cleanup stale connections
python -c "from autopack.db_leak_detector import DBLeakDetector; DBLeakDetector().force_cleanup_stale_connections()"
```

### Token Budget Exceeded

```bash
# Check current run budget
sqlite3 autopack.db "SELECT run_id, SUM(prompt_tokens + completion_tokens) as total FROM llm_usage_events WHERE run_id='<run-id>' GROUP BY run_id"

# Abort run if runaway
echo "abort:<run-id>" > .autonomous_runs/.abort_run
```

### Circuit Breaker Stuck Open

```bash
# Check circuit state
curl http://localhost:8000/health | jq '.circuit_breakers'

# Force reset (use with caution)
python -c "from autopack.circuit_breaker_registry import CircuitBreakerRegistry; CircuitBreakerRegistry().reset_all()"
```

## Cost Management

### Per-Run Budget Enforcement

```bash
# Check run token usage
sqlite3 autopack.db "SELECT run_id, SUM(prompt_tokens + completion_tokens) FROM llm_usage_events WHERE run_id='<run-id>'"

# Run will automatically abort if token_cap exceeded (default: 5M tokens)
# Adjust cap in config: export AUTOPACK_RUN_TOKEN_CAP=10000000
```

### Per-Phase Budget Monitoring

```bash
# Check phase-level token usage
sqlite3 autopack.db "SELECT phase_id, phase_name, SUM(prompt_tokens + completion_tokens) as total FROM llm_usage_events WHERE run_id='<run-id>' GROUP BY phase_id"

# Phase will abort if exceeding allocated budget (default: 500k tokens per phase)
# Adjust phase caps in config (see src/autopack/config.py phase_token_cap_multipliers)
```

## Security

### Rate Limiter Status

```bash
# Check rate limiter memory usage
python -c "from autopack.auth.rate_limiter import login_rate_limiter; print(f'Tracked IPs: {login_rate_limiter.get_tracked_ip_count()}')"

# Rate limiter automatically cleans up when cap reached (default: 10k IPs)
```

### Bind Address Verification

```bash
# Verify API server bind address (should be 127.0.0.1 for localhost)
curl http://localhost:8000/health | jq '.bind_address'

# For multi-device access, ensure AUTOPACK_ALLOW_NON_LOCAL=1 is set
```

## Backup Schedule Recommendations

### Daily Backups (Automated)

```bash
# Add to crontab for daily backups:
0 2 * * * cd /path/to/autopack && autopack backup --output backups/autopack-backup-$(date +\%Y\%m\%d).tar.gz
```

### Pre-Upgrade Backups (Manual)

```bash
# Before any upgrade:
autopack backup --output backups/pre-upgrade-$(date +\%Y\%m\%d).tar.gz
```

### Backup Retention

- Keep daily backups for 7 days
- Keep weekly backups for 4 weeks
- Keep monthly backups for 6 months

## Related Documentation

- Architecture Decisions: docs/ARCHITECTURE_DECISIONS.md
- Build History: docs/BUILD_HISTORY.md
- Debug Log: docs/DEBUG_LOG.md
- Testing Guide: docs/TESTING.md
