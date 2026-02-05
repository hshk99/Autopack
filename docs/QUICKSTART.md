# Developer Quickstart Guide

**Get Autopack running locally in <15 minutes. Perfect for new developers.**

---

## Prerequisites (Verify)

- Python 3.11+
- pip / venv
- Git
- A text editor (VSCode, Cursor, etc.)

**Time: 2 minutes**

---

## Step 1: Clone and Setup Environment (3 min)

**Terminal:**

```bash
# Clone repository
git clone https://github.com/hshk99/Autopack.git
cd Autopack

# Create virtual environment
python -m venv venv

# Activate virtual environment
# Linux/Mac:
source venv/bin/activate
# Windows PowerShell:
./venv/Scripts/Activate.ps1

# Install dependencies
pip install -r requirements.txt -r requirements-dev.txt
```

---

## Step 2: Configure Local Environment (2 min)

```bash
# Set PYTHONPATH (required for all commands)
# Linux/Mac:
export PYTHONPATH=src

# Windows PowerShell:
$env:PYTHONPATH="src"

# Set API key (optional but recommended)
# Get your key from https://console.anthropic.com/
export ANTHROPIC_API_KEY="sk-ant-..."  # Linux/Mac
$env:ANTHROPIC_API_KEY="sk-ant-..."    # Windows PowerShell
```

---

## Step 3: Initialize Database (2 min)

```bash
# Enable database bootstrap (dev-only, one-time)
export AUTOPACK_DB_BOOTSTRAP=1  # Linux/Mac
$env:AUTOPACK_DB_BOOTSTRAP="1"  # Windows PowerShell

# Verify PYTHONPATH is set
echo $PYTHONPATH  # Linux/Mac
Write-Output $env:PYTHONPATH  # Windows PowerShell
# Should print: src
```

---

## Step 4: Start API Server (2 min)

**Terminal 1:**

```bash
# Ensure PYTHONPATH=src is still set
PYTHONPATH=src python -m uvicorn autopack.main:app --reload --host 127.0.0.1 --port 8000
```

**Expected output:**
```
INFO:     Uvicorn running on http://127.0.0.1:8000
INFO:     Application startup complete
```

**Verify** (in another terminal):
```bash
curl http://localhost:8000/health
# Expected: {"status": "healthy", "database": "connected", ...}
```

---

## Step 5: Disable Bootstrap (After API Starts)

```bash
# Once API is running, disable bootstrap in original terminal
unset AUTOPACK_DB_BOOTSTRAP  # Linux/Mac
Remove-Item Env:AUTOPACK_DB_BOOTSTRAP  # Windows PowerShell
```

---

## Step 6: Run Tests (3 min)

**Terminal 2:**

```bash
# Ensure PYTHONPATH=src is set
PYTHONPATH=src pytest tests/ -v --tb=short

# Run a specific test file (faster):
PYTHONPATH=src pytest tests/test_api.py -v
```

**Expected:** Most tests pass (some marked `aspirational` may be skipped).

---

## Step 7: Verify Everything Works (1 min)

```bash
# Check API health endpoint
curl http://localhost:8000/health

# View API documentation
# Open browser to: http://127.0.0.1:8000/docs
```

---

## Next Steps: Development Workflow

### Option A: Run Autonomous Executor

```bash
# Terminal 3 (with PYTHONPATH=src set):
PYTHONPATH=src python -m autopack.autonomous_executor --run-id telemetry-collection-v4
```

### Option B: Explore the Codebase

- **Architecture Overview:** See [docs/ARCHITECTURE.md](ARCHITECTURE.md)
- **Build History:** See [docs/BUILD_HISTORY.md](BUILD_HISTORY.md)
- **Development Guide:** See [docs/CONTRIBUTING.md](CONTRIBUTING.md)

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| "No module named autopack" | Verify `PYTHONPATH=src` is set: `echo $PYTHONPATH` |
| "Connection refused" (port 8000) | API not running. Start it in Terminal 1. |
| "Database locked" | Close other executors. Only one can run at a time. |
| "ModuleNotFoundError" | Run `pip install -r requirements-dev.txt` again. |
| Tests take too long | Run a single file: `pytest tests/test_api.py -v` |

---

## Windows-Specific Guidance

**PowerShell Equivalents:**

```powershell
# Set PYTHONPATH
$env:PYTHONPATH="src"

# Activate venv
./venv/Scripts/Activate.ps1

# Set API key
$env:ANTHROPIC_API_KEY="sk-ant-..."

# Run tests with parallel execution
$env:PYTHONPATH="src"
pytest tests/ -v -n auto
```

---

## Common Commands Reference

```bash
# Health check
curl http://localhost:8000/health

# Run all tests
PYTHONPATH=src pytest tests/ -v

# Run with coverage
PYTHONPATH=src pytest tests/ --cov=src/autopack

# Format code (before commit)
pre-commit run --all-files

# List available runs
PYTHONPATH=src python scripts/list_run_counts.py
```

---

## Advanced Features

For advanced usage including batch draining, telemetry collection, and other features:

- **Batch Draining:** [scripts/batch_drain_controller.py](../scripts/batch_drain_controller.py)
- **Telemetry Collection:** [DB_HYGIENE_AND_TELEMETRY_SEEDING.md](guides/DB_HYGIENE_AND_TELEMETRY_SEEDING.md)
- **Quality Gates:** [BUILD-126_QUALITY_GATE.md](BUILD-126_QUALITY_GATE.md)

---

## Getting Help

- **Documentation:** Start at [docs/INDEX.md](INDEX.md)
- **Debug Issues:** Check [docs/DEBUG_LOG.md](DEBUG_LOG.md)
- **Architecture Questions:** See [docs/ARCHITECTURE_DECISIONS.md](ARCHITECTURE_DECISIONS.md)
