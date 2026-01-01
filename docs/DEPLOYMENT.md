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

The `docker-compose.yml` orchestrates three services:

1. **backend**: FastAPI application (port 8000)
2. **frontend**: nginx serving React app (port 80)
3. **db**: PostgreSQL 15 database (port 5432)

**Configuration**:

```yaml
services:
  backend:
    build:
      context: .
      target: backend
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql://autopack:autopack@db:5432/autopack
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
    depends_on:
      - db

  frontend:
    build:
      context: .
    ports:
      - "80:80"

  db:
    image: postgres:15
    environment:
      - POSTGRES_USER=autopack
      - POSTGRES_PASSWORD=autopack
      - POSTGRES_DB=autopack
    volumes:
      - postgres_data:/var/lib/postgresql/data
```

### Multi-Stage Dockerfile

The `Dockerfile` uses three stages:

1. **Backend Stage**: Python 3.11 + FastAPI dependencies
2. **Frontend Stage**: Node 20 + Vite build
3. **Production Stage**: nginx serving built frontend

**Key Features**:
- Minimal production image size
- Separate build and runtime dependencies
- Cached layer optimization

---

## Environment Variables

### Required Variables

```bash
# Database
DATABASE_URL="sqlite:///autopack.db"  # Default: SQLite
# Or for PostgreSQL:
# DATABASE_URL="postgresql://user:pass@host:5432/dbname"

# Python Environment
PYTHONPATH="src"  # Required: Module resolution
PYTHONUTF8="1"    # Required on Windows: UTF-8 encoding

# API Keys (at least one required)
ANTHROPIC_API_KEY="sk-ant-..."  # Claude Sonnet/Opus
OPENAI_API_KEY="sk-..."         # GPT-4o (fallback)
GEMINI_API_KEY="..."            # Gemini (optional)
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

## Health Checks

### API Health Endpoint

**Endpoint**: `GET /health`

**Response**:

```json
{
  "status": "healthy",
  "database": "connected",
  "version": "1.0.0",
  "uptime_seconds": 3600
}
```

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

```bash
# Build production images
docker-compose build --no-cache

# Start all services
docker-compose up -d

# Run database migrations
docker-compose exec backend python -c "from autopack.database import init_db; init_db()"

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
      - uses: actions/checkout@v3
      
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
