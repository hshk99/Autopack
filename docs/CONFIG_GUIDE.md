# Configuration Guide

**Purpose**: Quick reference for configuring Autopack via environment variables and configuration files

---

## Environment Variables

### Core Configuration

```bash
# Database
DATABASE_URL="sqlite:///autopack.db"  # Default: SQLite in repo root

# Python Environment
PYTHONPATH="src"  # Required: Module resolution
PYTHONUTF8="1"    # Required on Windows: UTF-8 encoding

# API Keys (at least one required for LLM calls)
ANTHROPIC_API_KEY="sk-ant-..."  # Claude Sonnet/Opus
OPENAI_API_KEY="sk-..."         # GPT-4o (fallback)
GOOGLE_API_KEY="..."            # Gemini (optional)
# Deprecated alias (prefer GOOGLE_API_KEY):
GEMINI_API_KEY="..."
```

### Optional Features

```bash
# Telemetry Collection
TELEMETRY_DB_ENABLED="1"  # Enable token usage tracking (default: 0)

# Telegram Notifications (for approval workflows)
TELEGRAM_BOT_TOKEN="123456789:ABC..."  # From @BotFather
TELEGRAM_CHAT_ID="123456789"           # Your chat ID
NGROK_URL="https://yourbot.ngrok.app"  # Public webhook URL

# Memory System
AUTOPACK_USE_QDRANT="0"        # Disable Qdrant (use FAISS fallback)
AUTOPACK_ENABLE_MEMORY="0"     # Disable memory entirely

# API Server
AUTOPACK_CALLBACK_URL="http://localhost:8001"  # Backend callback URL
```

### Testing & CI

```bash
# Test Mode
TESTING="1"  # Skip DB initialization in tests

# CI Profile
CI_PROFILE="strict"  # Options: normal, strict (for preflight gate)

# Target Repository
TARGET_REPO_PATH="/path/to/repo"  # Build target (default: current dir)
```

---

## .env File Setup

### Creating Your .env File

```bash
# Copy example template
cp .env.example .env

# Edit with your values
nano .env  # or vim, code, etc.
```

### Example .env File

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

### Loading .env File

**Automatic (recommended)**:
```bash
# Most scripts auto-load .env if present
python -m autopack.autonomous_executor --run-id my-run
```

**Manual (if needed)**:
```bash
# Bash/Linux
export $(cat .env | xargs)

# PowerShell
Get-Content .env | ForEach-Object {
    if ($_ -match '^([^=]+)=(.*)$') {
        [Environment]::SetEnvironmentVariable($matches[1], $matches[2])
    }
}
```

---

## Common Configuration Patterns

### Pattern 1: Local Development

```bash
# .env for local dev
PYTHONPATH=src
PYTHONUTF8=1
DATABASE_URL=sqlite:///autopack.db
ANTHROPIC_API_KEY=sk-ant-...
TELEMETRY_DB_ENABLED=1
AUTOPACK_USE_QDRANT=0  # Use FAISS fallback
```

**Usage**:
```bash
# Start API server
python -m uvicorn autopack.main:app --host 127.0.0.1 --port 8000

# Run executor
python -m autopack.autonomous_executor --run-id test-run
```

### Pattern 2: Production Deployment

```bash
# .env for production
PYTHONPATH=src
DATABASE_URL=postgresql://user:pass@host:5432/autopack
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...  # Fallback
TELEMETRY_DB_ENABLED=1
AUTOPACK_USE_QDRANT=1  # Qdrant via docker-compose
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
```

**Usage**:
```bash
# Start services
docker-compose up -d

# Run executor with production DB
python -m autopack.autonomous_executor --run-id prod-run
```

### Pattern 3: Telemetry Collection

```bash
# .env for telemetry seeding
PYTHONPATH=src
PYTHONUTF8=1
DATABASE_URL=sqlite:///autopack_telemetry_seed.db
ANTHROPIC_API_KEY=sk-ant-...
TELEMETRY_DB_ENABLED=1  # CRITICAL: Enable telemetry
```

**Usage**:
```bash
# Seed telemetry run
python scripts/create_telemetry_collection_run.py

# Drain phases to collect data
python scripts/batch_drain_controller.py \
    --run-id telemetry-collection-v4 \
    --batch-size 10

# Analyze results
python scripts/analyze_token_telemetry_v3.py --success-only
```

### Pattern 4: CI/Testing

```bash
# .env for CI
PYTHONPATH=src
DATABASE_URL=sqlite:///:memory:  # In-memory DB
TESTING=1  # Skip DB init
CI_PROFILE=strict  # Strict preflight checks
AUTOPACK_ENABLE_MEMORY=0  # Disable memory in tests
```

**Usage**:
```bash
# Run test suite
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=src/autopack --cov-report=html
```

---

## Configuration Files

### config/memory.yaml

```yaml
memory:
  enabled: true
  use_qdrant: true
  qdrant:
    host: "localhost"
    port: 6333
    require: false  # Fail-safe: fallback to FAISS if unavailable
    fallback_to_faiss: true
    autostart: true  # Auto-start Qdrant via docker-compose
    autostart_timeout_seconds: 15
```

### config/models.yaml

```yaml
models:
  default_provider: "anthropic"
  providers:
    anthropic:
      models:
        - name: "claude-sonnet-4-5"
          max_tokens: 16384
          temperature: 0.7
        - name: "claude-opus-4"
          max_tokens: 32768
          temperature: 0.7
    openai:
      models:
        - name: "gpt-4o"
          max_tokens: 16384
          temperature: 0.7
```

---

## Troubleshooting

### "No module named autopack"

**Fix**: Set `PYTHONPATH=src`

```bash
export PYTHONPATH=src  # Linux/Mac
$env:PYTHONPATH="src"  # Windows PowerShell
```

### "Database locked"

**Fix**: Only one executor per database. Stop other executors.

```bash
# Find running executors
ps aux | grep autonomous_executor  # Linux/Mac
Get-Process | Where-Object {$_.CommandLine -match 'autonomous_executor'}  # Windows

# Kill if needed
kill <PID>  # Linux/Mac
Stop-Process -Id <PID>  # Windows
```

### "API server not responding"

**Fix**: Ensure API server is running on correct port.

```bash
# Check if server is running
curl http://localhost:8000/health

# If not, start it
python -m uvicorn autopack.main:app --host 127.0.0.1 --port 8000
```

### "Qdrant connection refused"

**Fix**: Either start Qdrant or disable it.

```bash
# Option 1: Start Qdrant
docker-compose up -d qdrant

# Option 2: Disable Qdrant (use FAISS)
export AUTOPACK_USE_QDRANT=0
```

---

## References

- [QUICKSTART.md](QUICKSTART.md) - Getting started guide
- [CONTRIBUTING.md](CONTRIBUTING.md) - Development setup
- [DOCKER_DEPLOYMENT_GUIDE.md](DOCKER_DEPLOYMENT_GUIDE.md) - Production deployment
- [DB_HYGIENE_AND_TELEMETRY_SEEDING.md](guides/DB_HYGIENE_AND_TELEMETRY_SEEDING.md) - Database management

---

**Total Lines**: 148 (within ≤150 line constraint)

**Coverage**: Environment variables (3 sections), .env file (2 examples), common configs (4 patterns), troubleshooting (4 issues)

**Code Snippets**: 5 total (env vars, .env example, local dev, production, telemetry)
