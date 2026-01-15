# Operator Runbook: Multi-Device Operation

**Purpose**: Safe operational guidance for running Autopack across multiple devices, backup/restore procedures, and secure non-local access.

**Last Updated**: 2026-01-15

---

## Table of Contents

1. [Scope](#scope)
2. [Safe Defaults](#safe-defaults)
3. [Backup and Restore](#backup-and-restore)
4. [Non-Local Access Checklist](#non-local-access-checklist)
5. [Upgrade and Migration](#upgrade-and-migration)
6. [Incident Recovery](#incident-recovery)
7. [Multi-Device Coordination](#multi-device-coordination)

---

## Scope

This runbook covers:

- **Multi-device operation**: Running Autopack on different machines (dev, staging, production)
- **Data consistency**: Keeping SQLite/PostgreSQL and SOT ledgers in sync across devices
- **Safe remote access**: Enabling non-localhost access without compromising security
- **Backup/restore workflows**: Full and incremental backup strategies
- **Incident recovery**: Rollback, data integrity checks, and failure modes

**Out of scope**:
- Kubernetes/cloud-native deployments (use cloud provider documentation)
- Advanced clustering (Autopack is single-instance; use load balancer if needed)
- Custom authentication systems (use environment variables to integrate with yours)

---

## Safe Defaults

### Principle: Localhost-First + API Key Required

**ALWAYS** start with these defaults in `.env`:

```bash
# Binding (NEVER expose port 8000 without deliberate action)
AUTOPACK_API_HOST=127.0.0.1
AUTOPACK_API_PORT=8000

# Authentication (REQUIRED - empty key allows unauthenticated access)
AUTOPACK_API_KEY=<generate-strong-key-here>

# Database (SQLite default; switch to PostgreSQL for production)
DATABASE_URL=sqlite:///./autopack.db

# Logging
LOG_LEVEL=INFO
DEBUG_MODE=false
```

### Enabling Non-Local Access

**ONLY if explicitly needed** for multi-device deployment:

```bash
# 1. Generate strong API key
AUTOPACK_API_KEY=$(python -c "import secrets; print(secrets.token_urlsafe(32))")

# 2. Set binding to 0.0.0.0 (NOT :: for IPv6)
AUTOPACK_API_HOST=0.0.0.0

# 3. Use reverse proxy (nginx/Caddy) with TLS
# Example nginx upstream:
# upstream autopack {
#     server 127.0.0.1:8000;
# }
# server {
#     listen 443 ssl http2;
#     location / {
#         proxy_pass http://autopack;
#         proxy_set_header X-API-Key $http_x_api_key;
#     }
# }

# 4. Set trusted proxies for X-Forwarded-For headers
AUTOPACK_TRUSTED_PROXIES=127.0.0.1,nginx-container-ip

# 5. Set API base URL for frontend
VITE_AUTOPACK_API_BASE=https://autopack.yourdomain.com
```

### Verifying Safe Defaults

```bash
# 1. Check port binding
netstat -an | grep 8000  # Should show 127.0.0.1:8000

# 2. Verify API key is set (not empty)
echo $AUTOPACK_API_KEY | wc -c  # Should be > 10 chars

# 3. Test authentication
curl -H "X-API-Key: $AUTOPACK_API_KEY" http://localhost:8000/health

# 4. Confirm unauthenticated requests are rejected
curl http://localhost:8000/health  # Should return 401/403
```

---

## Backup and Restore

### What to Backup

Autopack maintains two critical data sources that **MUST be backed up together**:

| Component | Format | Location | Purpose |
|-----------|--------|----------|---------|
| **Application DB** | SQLite / PostgreSQL | `./autopack.db` or `$DATABASE_URL` | Runs, tiers, phases, telemetry |
| **SOT Ledgers** | Markdown | `docs/BUILD_HISTORY.md`, `docs/DEBUG_LOG.md` | Authoritative decisions, execution history |
| **Config State** | YAML/JSON | `config/*.yaml`, `.env` | Features, policies, settings |

### Full Backup Procedure

**Frequency**: Daily for production, after major runs for dev

```bash
#!/bin/bash
set -e

BACKUP_DIR="./backups/$(date +%Y%m%d-%H%M%S)"
mkdir -p "$BACKUP_DIR"

# 1. Stop running instances
# (or use `--readonly` flag if supported)

# 2. Backup database
if [[ "$DATABASE_URL" == sqlite* ]]; then
    cp ./autopack.db "$BACKUP_DIR/autopack.db"
    echo "✓ SQLite backup: $BACKUP_DIR/autopack.db"
else
    # PostgreSQL: use pg_dump
    pg_dump "$DATABASE_URL" > "$BACKUP_DIR/autopack-postgres.sql"
    echo "✓ PostgreSQL backup: $BACKUP_DIR/autopack-postgres.sql"
fi

# 3. Backup SOT ledgers
cp docs/BUILD_HISTORY.md "$BACKUP_DIR/"
cp docs/DEBUG_LOG.md "$BACKUP_DIR/"
cp docs/ARCHITECTURE_DECISIONS.md "$BACKUP_DIR/"
echo "✓ SOT ledgers backed up"

# 4. Backup configuration
cp .env "$BACKUP_DIR/.env.backup"
cp -r config/ "$BACKUP_DIR/config_backup"
echo "✓ Config backed up"

# 5. Create manifest
cat > "$BACKUP_DIR/MANIFEST.json" << EOF
{
  "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "version": "$(cat pyproject.toml | grep '^version' | cut -d= -f2 | tr -d ' \"')",
  "database_type": "$(echo $DATABASE_URL | cut -d: -f1)",
  "sot_entries": $(wc -l docs/BUILD_HISTORY.md | awk '{print $1}')
}
EOF

echo "✓ Backup complete: $BACKUP_DIR"
ls -lh "$BACKUP_DIR"
```

### Incremental Backup (SOT Only)

For frequent backups without copying the entire database:

```bash
#!/bin/bash
BACKUP_DIR="./backups/incremental-$(date +%Y%m%d)"
mkdir -p "$BACKUP_DIR"

# Backup only SOT changes since last full backup
git diff HEAD~1 docs/BUILD_HISTORY.md > "$BACKUP_DIR/build-history.patch"
git diff HEAD~1 docs/DEBUG_LOG.md > "$BACKUP_DIR/debug-log.patch"

tar czf "$BACKUP_DIR/sot-incremental-$(date +%s).tar.gz" "$BACKUP_DIR"/*.patch
echo "✓ Incremental SOT backup: $BACKUP_DIR"
```

### Restore from Backup

```bash
#!/bin/bash
set -e

BACKUP_PATH="$1"  # e.g., ./backups/20260115-120000

if [[ ! -d "$BACKUP_PATH" ]]; then
    echo "❌ Backup not found: $BACKUP_PATH"
    exit 1
fi

echo "⚠️  RESTORE PROCEDURE - Will overwrite current data"
read -p "Continue? (yes/no) " response
if [[ "$response" != "yes" ]]; then
    echo "Cancelled."
    exit 0
fi

# 1. Stop application
echo "1. Stopping Autopack..."
pkill -f "uvicorn.*autopack" || true
sleep 2

# 2. Restore database
echo "2. Restoring database..."
if [[ -f "$BACKUP_PATH/autopack.db" ]]; then
    cp "$BACKUP_PATH/autopack.db" ./autopack.db
    echo "   ✓ SQLite restored"
elif [[ -f "$BACKUP_PATH/autopack-postgres.sql" ]]; then
    psql "$DATABASE_URL" < "$BACKUP_PATH/autopack-postgres.sql"
    echo "   ✓ PostgreSQL restored"
fi

# 3. Restore SOT ledgers
echo "3. Restoring SOT ledgers..."
cp "$BACKUP_PATH/BUILD_HISTORY.md" docs/
cp "$BACKUP_PATH/DEBUG_LOG.md" docs/
cp "$BACKUP_PATH/ARCHITECTURE_DECISIONS.md" docs/
echo "   ✓ SOT ledgers restored"

# 4. Restore configuration
echo "4. Restoring configuration..."
cp "$BACKUP_PATH/.env.backup" .env
cp -r "$BACKUP_PATH/config_backup" config
echo "   ✓ Config restored"

# 5. Verify data integrity
echo "5. Verifying integrity..."
sqlite3 ./autopack.db "SELECT COUNT(*) FROM runs;" > /dev/null
echo "   ✓ Database integrity verified"

echo "✅ Restore complete. Start Autopack and verify health."
```

### Cross-Device Restore

When moving from one machine to another:

```bash
# On source machine
tar czf autopack-backup-$(date +%Y%m%d).tar.gz \
    autopack.db docs/*.md config/ .env

# Transfer to target machine (e.g., via SCP)
scp autopack-backup-20260115.tar.gz target-machine:/tmp/

# On target machine
cd /path/to/autopack
tar xzf /tmp/autopack-backup-20260115.tar.gz
# Then run restore script above
```

---

## Non-Local Access Checklist

**Before enabling external access, complete ALL items**:

### ✅ Prerequisites

- [ ] Running Autopack with explicit `AUTOPACK_API_KEY` set (not empty)
- [ ] Reverse proxy (nginx, Caddy, etc.) deployed in front of Autopack
- [ ] TLS/SSL certificate installed on reverse proxy (not self-signed)
- [ ] Firewall rules restrict access to proxy only (not direct port 8000)

### ✅ Configuration

- [ ] `AUTOPACK_API_HOST=0.0.0.0` (or specific interface)
- [ ] Reverse proxy configured with:
  - [ ] TLS 1.2+ only (disable TLS 1.0/1.1)
  - [ ] Strong ciphers (no RC4, DES, MD5)
  - [ ] HSTS header: `Strict-Transport-Security: max-age=31536000`
  - [ ] X-API-Key pass-through header
- [ ] Frontend `.env` configured:
  - [ ] `VITE_AUTOPACK_API_BASE=https://yourdomain.com` (not http://)
  - [ ] `VITE_AUTOPACK_API_KEY` not committed to version control

### ✅ Network

- [ ] Firewall blocks direct access to port 8000 from public internet
- [ ] Only HTTPS (443) exposed via reverse proxy
- [ ] API rate limiting enabled (if proxy supports it)
- [ ] VPN or IP allowlist configured (if available)

### ✅ Monitoring

- [ ] Audit logging enabled (`LOG_LEVEL=INFO`)
- [ ] Failed authentication attempts logged
- [ ] Regular log review scheduled (e.g., weekly)
- [ ] Alerting configured for repeated auth failures

### ✅ Verification

```bash
# Test from external machine
curl -k https://yourdomain.com/health  # Should fail (no API key)
curl -k -H "X-API-Key: $AUTOPACK_API_KEY" https://yourdomain.com/health  # Should work

# Verify direct access blocked
nc -zv your-autopack-ip 8000  # Should timeout/be blocked
```

---

## Upgrade and Migration

### Pre-Upgrade Checklist

```bash
# 1. Stop running processes
pkill -f "uvicorn.*autopack"
pkill -f "autonomous_executor"

# 2. Full backup
./scripts/backup.sh

# 3. Verify git state
git status  # Should be clean
git log --oneline -3

# 4. Note current version
grep '^version' pyproject.toml
```

### Upgrade Steps

```bash
# 1. Pull latest code
git fetch origin
git checkout origin/main

# 2. Run database migrations (SQLite only)
python scripts/run_migrations.py
# Output: "✓ Migrations applied"

# 3. Regenerate dependencies (if needed)
bash scripts/regenerate_requirements.sh

# 4. Verify health
PYTHONPATH=src python -m uvicorn autopack.main:app --host 127.0.0.1 --port 8000
# In another terminal: curl http://localhost:8000/health

# 5. Run smoke tests
pytest tests/api/test_health.py -v

# 6. Restart normally
```

### Rollback (if upgrade fails)

```bash
# 1. Stop application
pkill -f "uvicorn.*autopack"

# 2. Restore from pre-upgrade backup
./scripts/restore.sh ./backups/20260115-120000

# 3. Checkout previous version
git checkout <previous-tag>

# 4. Restart and verify
PYTHONPATH=src python -m uvicorn autopack.main:app --host 127.0.0.1 --port 8000
```

### PostgreSQL Migration (SQLite → PostgreSQL)

For scaling to production:

```bash
# 1. Backup SQLite
cp autopack.db autopack.db.backup

# 2. Set PostgreSQL connection
export DATABASE_URL=postgresql://user:pass@host:5432/autopack

# 3. Run migrations
python scripts/run_migrations.py

# 4. Copy data (if tool available; otherwise manual)
# TODO: Add migration tool for data export/import

# 5. Test with PostgreSQL
PYTHONPATH=src python -m uvicorn autopack.main:app --host 127.0.0.1 --port 8000
```

---

## Incident Recovery

### Issue: Database Corruption

**Symptoms**: SQL errors, runs not appearing, telemetry missing

**Recovery steps**:

```bash
# 1. Check database integrity
sqlite3 ./autopack.db "PRAGMA integrity_check;"
# Output: "ok" (healthy) or list of errors

# 2. If corrupted, restore from backup
./scripts/restore.sh ./backups/<most-recent>

# 3. If no backup available, reset and replay
rm autopack.db
python scripts/run_migrations.py
# (Data before corruption is lost)

# 4. Verify
sqlite3 ./autopack.db "SELECT COUNT(*) FROM runs;"
```

### Issue: API Key Compromised

**Symptoms**: Unauthorized access attempts in logs

**Immediate response**:

```bash
# 1. Rotate API key
AUTOPACK_API_KEY=$(python -c "import secrets; print(secrets.token_urlsafe(32))")
echo "AUTOPACK_API_KEY=$AUTOPACK_API_KEY" >> .env

# 2. Restart Autopack
pkill -f "uvicorn.*autopack"
sleep 2
PYTHONPATH=src python -m uvicorn autopack.main:app &

# 3. Review audit logs
tail -n 100 /var/log/autopack/access.log | grep "401\|403"

# 4. Update frontend config
# Edit src/frontend/.env to reflect new key
export VITE_AUTOPACK_API_KEY=$AUTOPACK_API_KEY
npm run build
```

### Issue: Runs Stuck in EXECUTING State

**Symptoms**: Runs not progressing, API responsive

**Recovery steps**:

```bash
# 1. Check for orphaned processes
ps aux | grep autonomous_executor

# 2. Kill orphaned processes
pkill -9 -f autonomous_executor

# 3. Reset stuck runs (SQLite)
sqlite3 ./autopack.db << EOF
UPDATE runs SET status = 'FAILED_SYSTEM_ERROR'
WHERE status = 'EXECUTING'
AND updated_at < datetime('now', '-1 hour');
EOF

# 4. Restart executor
python src/autopack/autonomous_executor.py --run-id <run-id>
```

### Issue: Out of Disk Space

**Symptoms**: Runs fail to save, API errors on phase save

**Recovery steps**:

```bash
# 1. Identify largest files
du -sh ./* | sort -rh | head -10

# 2. Archive old runs (if you have an archive location)
mkdir -p archive/runs
mv .autonomous_runs/autopack/runs/old/* archive/runs/

# 3. Vacuum database
sqlite3 ./autopack.db "VACUUM;"

# 4. Consider enabling artifact caching/cleanup
# Edit config/storage_policy.yaml
# Set max_artifact_age_days: 30
```

### Issue: SOT Ledgers Out of Sync with Database

**Symptoms**: BUILD_HISTORY.md entries missing or duplicated

**Recovery steps**:

```bash
# 1. Check for uncommitted changes
git status

# 2. Re-run tidy to regenerate
python scripts/tidy/consolidate_docs.py --execute

# 3. Review changes
git diff docs/BUILD_HISTORY.md

# 4. Commit
git add docs/BUILD_HISTORY.md
git commit -m "fix(sot): resync ledgers after recovery"
```

---

## Multi-Device Coordination

### Setup for Multiple Developers

**Scenario**: 3 developers on 3 machines, shared database (PostgreSQL)

```bash
# Shared configuration (.env - committed to git)
DATABASE_URL=postgresql://autopack:secret@shared-db.internal:5432/autopack
AUTOPACK_API_HOST=127.0.0.1  # Each machine is localhost-only
AUTOPACK_API_PORT=8000
AUTOPACK_API_KEY=shared-dev-key-for-testing

# Developer machine 1
git clone autopack.git
cd autopack
python -m venv venv && source venv/bin/activate
pip install -r requirements-dev.txt
PYTHONPATH=src python -m uvicorn autopack.main:app

# Developer machine 2 & 3 (same steps)
```

### Setup for Staging + Production Machines

**Scenario**: Staging machine syncs to production after testing

```bash
# Staging (.env)
DATABASE_URL=postgresql://autopack:stage-pass@stage-db:5432/autopack
AUTOPACK_API_KEY=<staging-key>
AUTOPACK_READONLY=false  # Allow writes

# Production (.env)
DATABASE_URL=postgresql://autopack:prod-pass@prod-db:5432/autopack
AUTOPACK_API_KEY=<prod-key>
AUTOPACK_READONLY=true   # Disable writes (read-only copy)

# Sync workflow (from staging to production)
# 1. Run tidy on staging → generates latest SOT
# 2. Backup production database
# 3. Export staging runs → Import to production
# 4. Verify on production (read-only mode)
```

### Setup for Geo-Distributed Deployment

**Scenario**: Autopack running in multiple regions

```bash
# Region 1 (US-East) - Primary
AUTOPACK_REGION=us-east-primary
DATABASE_URL=postgresql://autopack@us-east-db.internal/autopack

# Region 2 (EU-Central) - Secondary
AUTOPACK_REGION=eu-central-secondary
DATABASE_URL=postgresql://autopack@eu-central-db.internal/autopack

# Coordination
# - Each region maintains its own database
# - Run IDs include region prefix: us-east-run-001, eu-run-001
# - Cross-region queries use federated view (if needed)
# - Nightly sync of SOT ledgers to shared repo
```

---

## See Also

- **[Deployment Guide](DEPLOYMENT.md)** - Docker setup, environment variables
- **[Autopilot Operations](AUTOPILOT_OPERATIONS.md)** - Running autonomous scans and plans
- **[Memory Service Guide](MEMORY_SERVICE_OPERATOR_GUIDE.md)** - Vector DB setup and tuning
- **[TROUBLESHOOTING.md](TROUBLESHOOTING.md)** - Common issues and solutions
- **[CONFIG_GUIDE.md](CONFIG_GUIDE.md)** - Configuration surface area reference
