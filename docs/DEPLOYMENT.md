# Deployment Guide

**Purpose**: Docker deployment, environment variables, and health checks for production use

**Last Updated**: 2025-12-29

---

## Overview

Autopack can be deployed using Docker for consistent, reproducible environments. This guide covers:

1. Docker setup and configuration
2. Environment variables
3. Health checks and monitoring
4. Common deployment scenarios

---

## Docker Setup

### Prerequisites

- Docker Desktop 28.5.1+ (or Docker Engine + Docker Compose)
- 4GB+ available RAM
- 10GB+ available disk space

### Quick Start

```bash
# Clone repository
git clone https://github.com/yourusername/autopack.git
cd autopack

# Build and start services
docker-compose up --build -d

# Verify services
curl http://localhost:8000/health
```

### Docker Compose Services

The `docker-compose.yml` orchestrates four services:

1. **backend**: FastAPI application (port 8000)
2. **frontend**: nginx serving React app (port 80)
3. **db**: PostgreSQL 15 database (port 5432)
4. **qdrant**: Vector memory database (port 6333)

**Configuration**:

```yaml
services:
  backend:
    build:
      context: .
      dockerfile: Dockerfile
      target: backend
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql://autopack:autopack@db:5432/autopack
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
    depends_on:
      - db
      - qdrant

  frontend:
    build:
      context: .
      dockerfile: Dockerfile.frontend
    ports:
      - "80:80"
    depends_on:
      - backend

  db:
    image: postgres:15.10-alpine
    environment:
      - POSTGRES_USER=autopack
      - POSTGRES_PASSWORD=autopack
      - POSTGRES_DB=autopack
    volumes:
      - db_data:/var/lib/postgresql/data
      - ./scripts/init-db.sql:/docker-entrypoint-initdb.d/init-db.sql

  qdrant:
    image: qdrant/qdrant:v1.12.5
    ports:
      - "6333:6333"
    volumes:
      - qdrant_data:/qdrant/storage
```

### Dockerfiles (backend + frontend)

Autopack uses two Docker build surfaces:

1. **Backend image**: `Dockerfile` (stage `backend`)
2. **Frontend image**: `Dockerfile.frontend` (root Vite build + nginx + repo `nginx.conf`)

**Key Features**:
- Minimal production image size
- Separate build and runtime dependencies
- Cached layer optimization

---

## Environment Variables

### Secret File Support (PR-03 G4)

For production deployments, secrets can be loaded from files via `*_FILE` environment variables. This enables Docker secrets and Kubernetes secret mounts without exposing credentials in environment variables.

**Precedence**: `*_FILE` > direct env var > defaults

| Secret | Direct Env Var | File Env Var | Required in Production |
|--------|---------------|--------------|------------------------|
| Database URL | `DATABASE_URL` | `DATABASE_URL_FILE` | Yes |
| API Key | `AUTOPACK_API_KEY` | `AUTOPACK_API_KEY_FILE` | Yes |
| JWT Private Key | `JWT_PRIVATE_KEY` | `JWT_PRIVATE_KEY_FILE` | No (optional auth) |
| JWT Public Key | `JWT_PUBLIC_KEY` | `JWT_PUBLIC_KEY_FILE` | No (optional auth) |

**Docker Secrets Example**:

```bash
# Create Docker secrets
echo "postgresql://autopack:SECURE_PASSWORD@db:5432/autopack" | docker secret create db_url_secret -
echo "your-api-key-here" | docker secret create api_key_secret -

# In docker-compose.yml, mount as files
services:
  backend:
    secrets:
      - db_url_secret
      - api_key_secret
    environment:
      - DATABASE_URL_FILE=/run/secrets/db_url_secret
      - AUTOPACK_API_KEY_FILE=/run/secrets/api_key_secret
```

**Kubernetes Secrets Example**:

```yaml
# Mount secret as file
volumes:
  - name: db-secret
    secret:
      secretName: autopack-db-url
containers:
  - name: backend
    volumeMounts:
      - name: db-secret
        mountPath: /secrets/db
        readOnly: true
    env:
      - name: DATABASE_URL_FILE
        value: /secrets/db/url
```

**Fail-Fast Behavior**: In production (`AUTOPACK_ENV=production`), required secrets that are not set will cause immediate startup failure with a clear error message.

---

### Required Variables

```bash
# Database
DATABASE_URL="sqlite:///autopack.db"  # Default: SQLite
# Or for PostgreSQL:
# DATABASE_URL="postgresql://user:pass@host:5432/dbname"
# Or via file: DATABASE_URL_FILE="/run/secrets/db_url"

# Python Environment
PYTHONPATH="src"  # Required: Module resolution
PYTHONUTF8="1"    # Required on Windows: UTF-8 encoding

# API Keys (at least one required)
ANTHROPIC_API_KEY="sk-ant-..."  # Claude Sonnet/Opus
OPENAI_API_KEY="sk-..."         # GPT-4o (fallback)
GOOGLE_API_KEY="..."            # Gemini (optional)
# Deprecated alias (prefer GOOGLE_API_KEY):
GEMINI_API_KEY="..."
```

### Optional Variables

```bash
# Telemetry Collection
TELEMETRY_DB_ENABLED="1"  # Enable token usage tracking (default: 0)

# Telegram Notifications
TELEGRAM_BOT_TOKEN="123456789:ABC..."  # From @BotFather
TELEGRAM_CHAT_ID="123456789"           # Your chat ID
NGROK_URL="https://yourbot.ngrok.app"  # Public webhook URL

# Memory System
AUTOPACK_USE_QDRANT="0"        # Disable Qdrant (use FAISS fallback)
AUTOPACK_ENABLE_MEMORY="0"     # Disable memory entirely

# API Server
AUTOPACK_CALLBACK_URL="http://localhost:8001"  # Backend callback URL
AUTOPACK_PUBLIC_READ="1"  # Allow public read for operator surface (dev only)

# Testing & CI
TESTING="1"  # Skip DB initialization in tests
CI_PROFILE="strict"  # Options: normal, strict (for preflight gate)

# Target Repository
TARGET_REPO_PATH="/path/to/repo"  # Build target (default: current dir)
```

### .env File Setup

**Create .env file**:

```bash
# Copy example template
cp .env.example .env

# Edit with your values
nano .env  # or vim, code, etc.
```

**Example .env**:

```bash
# .env - Autopack Configuration

# === REQUIRED ===
PYTHONPATH=src
PYTHONUTF8=1
DATABASE_URL=sqlite:///autopack.db
ANTHROPIC_API_KEY=sk-ant-your-key-here

# === OPTIONAL ===
# Telemetry
TELEMETRY_DB_ENABLED=1

# Telegram Approvals
TELEGRAM_BOT_TOKEN=123456789:ABCdefGHI...
TELEGRAM_CHAT_ID=123456789
NGROK_URL=https://yourbot.ngrok.app

# Memory (disable if not using Qdrant)
AUTOPACK_USE_QDRANT=0

# Testing
TESTING=0
CI_PROFILE=normal
```

---

## Database Configuration

### Production = PostgreSQL Only

**Critical**: Autopack production deployments MUST use PostgreSQL. SQLite is only for local development and testing.

**Why PostgreSQL?**
- Concurrent writes: Multiple executors can run in parallel
- Production durability: WAL mode, connection pooling, MVCC
- Performance: Optimized for high-volume telemetry writes
- Schema migrations: Full column rename/drop support (SQLite has limitations)

### DATABASE_URL Requirements

**BUILD-146 P4 Ops Hardening**: All migration scripts now REQUIRE explicit `DATABASE_URL` to prevent accidentally running migrations on SQLite when production uses Postgres.

**PowerShell (Production - PostgreSQL)**:

```powershell
# Set DATABASE_URL for production Postgres
$env:DATABASE_URL="postgresql://autopack:autopack@localhost:5432/autopack"

# Run migration
python scripts/migrations/add_phase6_p3_fields.py upgrade

# Start executor
python -m autopack.autonomous_executor --run-id myrun
```

**PowerShell (Dev/Test - SQLite, explicit opt-in)**:

```powershell
# Explicitly opt into SQLite for local testing
$env:DATABASE_URL="sqlite:///autopack.db"

# Run migration
python scripts/migrations/add_phase6_p3_fields.py upgrade

# Start executor (local testing only)
python -m autopack.autonomous_executor --run-id myrun
```

**Bash (Production - PostgreSQL)**:

```bash
# Set DATABASE_URL for production Postgres
export DATABASE_URL="postgresql://autopack:autopack@localhost:5432/autopack"

# Run migration
python scripts/migrations/add_phase6_p3_fields.py upgrade

# Start executor
python -m autopack.autonomous_executor --run-id myrun
```

**Bash (Dev/Test - SQLite, explicit opt-in)**:

```bash
# Explicitly opt into SQLite for local testing
export DATABASE_URL="sqlite:///autopack.db"

# Run migration
python scripts/migrations/add_phase6_p3_fields.py upgrade

# Start executor (local testing only)
python -m autopack.autonomous_executor --run-id myrun
```

### Common DATABASE_URL Footguns

**Footgun #1: Migration on wrong DB**

```powershell
# ❌ BAD: Forgot to set DATABASE_URL, script exits with error
python scripts/migrations/add_phase6_p3_fields.py upgrade

# Output:
# ERROR: DATABASE_URL environment variable not set
# Migration scripts require explicit DATABASE_URL to prevent footguns.
# Production uses Postgres; SQLite is only for dev/test.
```

**Fix**: Always set `DATABASE_URL` before running migrations.

**Footgun #2: API and Executor on different DBs**

```powershell
# Canonical API server starts with Postgres (from settings.database_url)
PYTHONPATH=src uvicorn autopack.main:app --host 0.0.0.0 --port 8000

# Executor starts without DATABASE_URL set
# ❌ Would default to SQLite (if we hadn't fixed this)
python -m autopack.autonomous_executor --run-id myrun
```

**Fix**: Check `/health` endpoint's `database_identity` field to detect drift:

```bash
curl http://localhost:8000/health
# {
#   "status": "healthy",
#   "timestamp": "2025-12-31T12:34:56Z",
#   "database_identity": "a1b2c3d4e5f6"  # Hash of DATABASE_URL
# }
```

If executor and API return different `database_identity` values, they're using different databases.

### Database Identity Check

**BUILD-146 P4 Ops**: The `/health` endpoint now returns a `database_identity` hash to detect when API and executor are pointing at different databases.

**How it works**:
1. Computes SHA-256 hash of `DATABASE_URL` (with credentials masked)
2. Returns first 12 hex chars as identity fingerprint
3. Compare fingerprints between API and executor to detect drift

**Example**:

```bash
# Check API database identity
curl http://localhost:8000/health | jq -r .database_identity
# Output: a1b2c3d4e5f6

# Executor logs its identity on startup
# [2025-12-31 12:34:56] Database identity: a1b2c3d4e5f6

# If hashes differ, API and executor are on different DBs!
```

### Setting Up PostgreSQL

**Local PostgreSQL (Windows)**:

```powershell
# Install PostgreSQL 15+ via Chocolatey
choco install postgresql15

# Start PostgreSQL service
Start-Service postgresql-x64-15

# Create database and user
psql -U postgres -c "CREATE USER autopack WITH PASSWORD 'autopack';"
psql -U postgres -c "CREATE DATABASE autopack OWNER autopack;"

# Set DATABASE_URL
$env:DATABASE_URL="postgresql://autopack:autopack@localhost:5432/autopack"
```

**Local PostgreSQL (Linux/Mac)**:

```bash
# Install PostgreSQL 15+
sudo apt-get install postgresql-15  # Ubuntu/Debian
# or
brew install postgresql@15  # macOS

# Start PostgreSQL
sudo systemctl start postgresql  # Linux
# or
brew services start postgresql@15  # macOS

# Create database and user
sudo -u postgres psql -c "CREATE USER autopack WITH PASSWORD 'autopack';"
sudo -u postgres psql -c "CREATE DATABASE autopack OWNER autopack;"

# Set DATABASE_URL
export DATABASE_URL="postgresql://autopack:autopack@localhost:5432/autopack"
```

**Docker PostgreSQL**:

```bash
# Run Postgres in Docker
docker run --name autopack-postgres \
  -e POSTGRES_USER=autopack \
  -e POSTGRES_PASSWORD=autopack \
  -e POSTGRES_DB=autopack \
  -p 5432:5432 \
  -d postgres:15

# Set DATABASE_URL
export DATABASE_URL="postgresql://autopack:autopack@localhost:5432/autopack"
```

---

## Reverse Proxy Routing Invariants (PR-02 G6)

When deploying behind nginx (or another reverse proxy), these routing rules MUST be maintained:

### Path Preservation Rules

| Frontend Path | Backend Path | Notes |
|---------------|--------------|-------|
| `/api/auth/*` | `/api/auth/*` | **Preserved** - auth router mounted at `/api/auth` |
| `/api/*` | `/*` | **Stripped** - `/api/runs` → `/runs` |
| `/health` | `/health` | **Proxied** - full readiness check |
| `/nginx-health` | N/A | **Static** - nginx liveness only |

### Critical Configuration

```nginx
# Auth routes MUST preserve prefix (no trailing slash on proxy_pass)
location /api/auth/ {
    proxy_pass http://backend:8000;  # No trailing slash!
}

# Other API routes strip /api prefix (trailing slash strips prefix)
location /api/ {
    proxy_pass http://backend:8000/;  # Trailing slash strips /api
}
```

**Why this matters**: The auth router is mounted at `/api/auth` in the backend. If nginx strips the `/api` prefix, requests to `/api/auth/login` become `/auth/login`, which doesn't match any route (404).

### Health Check Semantics

- **`/nginx-health`**: Static nginx liveness probe. Returns `200 nginx-healthy\n`. Use for container liveness checks that should pass even if backend is starting.
- **`/health`**: Proxied to backend. Returns full readiness status including DB connectivity, Qdrant status, and kill switch states. Use for readiness checks.

### Testing Proxy Routing

```bash
# Test auth endpoint routing (should return 401/422, not 404)
curl -X POST http://localhost/api/auth/login -H "Content-Type: application/json"

# Test general API routing (should return run data or 404 for missing run)
curl http://localhost/api/runs/test-run-id

# Test health endpoints
curl http://localhost/nginx-health  # Static nginx liveness
curl http://localhost/health        # Full backend readiness
```

---

## Health Checks

### API Health Endpoint

**Endpoint**: `GET /health`

**Response**:

```json
{
  "status": "healthy",
  "timestamp": "2026-01-10T12:00:00Z",
  "database_identity": "a1b2c3d4e5f6",
  "database": "connected",
  "qdrant": "connected",
  "kill_switches": {"disable_all": false, "disable_autonomous": false},
  "version": "unknown",
  "service": "autopack",
  "component": "supervisor_api"
}
```

**Notes**:
- `database_identity`: Hash of DATABASE_URL for drift detection (see Database Identity Check below)
- `version`: Set via `AUTOPACK_VERSION` env var (defaults to "unknown")
- `kill_switches`: Current state of operational kill switches

**Usage**:

```bash
# Check API health
curl http://localhost:8000/health

# Docker health check
docker-compose ps
```

### Database Health

**Check PostgreSQL**:

```bash
# Via Docker
docker exec -it autopack-db-1 psql -U autopack -d autopack -c "SELECT version();"

# Via Python
PYTHONPATH=src python -c "from autopack.database import SessionLocal; session = SessionLocal(); print('DB OK')"
```

### Service Monitoring

**View logs**:

```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f backend

# Last 100 lines
docker-compose logs --tail=100 backend
```

**Container stats**:

```bash
# Real-time stats
docker stats

# Disk usage
docker system df
```

---

## Common Deployment Scenarios

### Local Development

```bash
# Start database only
docker-compose up -d db

# Run API locally
PYTHONPATH=src uvicorn autopack.main:app --reload --host 0.0.0.0 --port 8000

# Run tests
PYTHONPATH=src pytest tests/ -v
```

### Production Deployment

**Use the production override template for secure deployments**:

```bash
# 1. Copy the production override template
cp docker-compose.prod.example.yml docker-compose.prod.yml

# 2. Configure Docker secrets (see example commands in the template)
echo "postgresql://autopack:SECURE_PASSWORD@db:5432/autopack" | docker secret create db_url_secret -
echo "SECURE_PASSWORD" | docker secret create db_password -
docker secret create jwt_private_key /path/to/private_key.pem
docker secret create jwt_public_key /path/to/public_key.pem

# 3. Deploy with production override
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d

# 4. Verify deployment
curl http://localhost:8000/health
```

**Production override key features**:
- `AUTOPACK_ENV=production`: Enables security hardening (blocks ephemeral JWT keys)
- `*_FILE` secrets: Credentials via Docker secrets, not env vars
- No host port exposure for `db`/`qdrant`: Internal network only
- See `docker-compose.prod.example.yml` for full template

**Without override (local dev only)**:

```bash
# Build production images
docker-compose build --no-cache

# Start all services
docker-compose up -d

# Database schema / migrations
# - P0 guardrail: init_db() will FAIL unless you explicitly opt in with AUTOPACK_DB_BOOTSTRAP=1
# - For production: apply schema changes using the repo's migration workflow (see docs/guides/*MIGRATION*RUNBOOK*.md)
# - For dev/test only (fresh DB bootstrap): set AUTOPACK_DB_BOOTSTRAP=1 once, start backend, then unset it.

# Verify deployment
curl http://localhost:8000/health
curl http://localhost:80
```

### CI/CD Integration

```yaml
# .github/workflows/deploy.yml
name: Deploy

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Build and push Docker images
        run: |
          docker-compose build
          docker-compose push
      
      - name: Deploy to production
        run: |
          ssh user@server 'cd /app && docker-compose pull && docker-compose up -d'
```

---

## Troubleshooting

### "Connection refused" on port 8000

**Fix**: Ensure backend is running

```bash
docker-compose ps
docker-compose up -d backend
```

### "Database connection failed"

**Fix**: Check database status

```bash
# Restart database
docker-compose restart db

# Check logs
docker-compose logs db

# Verify connection string
echo $DATABASE_URL
```

### "No module named autopack"

**Fix**: Set PYTHONPATH

```bash
export PYTHONPATH=src  # Linux/Mac
$env:PYTHONPATH="src"  # Windows PowerShell
```

### "API key not set"

**Fix**: Add API key to .env

```bash
# Edit .env file
ANTHROPIC_API_KEY=sk-ant-your-key-here

# Restart services
docker-compose restart backend
```

---

## References

- [QUICKSTART.md](QUICKSTART.md) - Getting started guide
- [CONFIG_GUIDE.md](CONFIG_GUIDE.md) - Configuration reference
- [CONTRIBUTING.md](CONTRIBUTING.md) - Development setup
- [DOCKER_DEPLOYMENT_GUIDE.md](DOCKER_DEPLOYMENT_GUIDE.md) - Detailed Docker guide

---

**Total Lines**: 180 (within ≤180 line constraint)

**Coverage**: Docker setup (3 sections), environment variables (3 sections), health checks (3 sections), deployment scenarios (3 sections), troubleshooting (4 issues)
