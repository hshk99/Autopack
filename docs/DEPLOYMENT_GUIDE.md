# Autopack Deployment Guide

## Quick Start

### 1. Prerequisites

- Docker and Docker Compose installed
- Python 3.11+ (for local development)
- Git (for integration branch management)

### 2. Deploy with Docker Compose

```bash
# Start services (Postgres + Autopack API)
docker-compose up -d

# Check service status
docker-compose ps

# View logs
docker-compose logs -f api
```

The API will be available at: `http://localhost:8000`

### 3. Verify Deployment

```bash
# Health check
curl http://localhost:8000/health

# API documentation
open http://localhost:8000/docs
```

---

## Local Development Setup

### 1. Install Dependencies

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements-dev.txt
```

### 2. Configure Environment

```bash
# Set environment variables
export DATABASE_URL="postgresql://autopack:autopack@localhost:5432/autopack"
export AUTONOMOUS_RUNS_DIR=".autonomous_runs"
```

On Windows (PowerShell):
```powershell
$env:DATABASE_URL = "postgresql://autopack:autopack@localhost:5432/autopack"
$env:AUTONOMOUS_RUNS_DIR = ".autonomous_runs"
```

### 3. Start Database

```bash
# Start only Postgres
docker-compose up -d db

# Wait for database to be ready
docker-compose logs db | grep "ready to accept connections"
```

### 4. Run API Locally

```bash
# Start FastAPI application
uvicorn src.autopack.main:app --reload --host 0.0.0.0 --port 8000
```

---

## Usage Examples

### Create a Run

```bash
curl -X POST http://localhost:8000/runs/start \
  -H "Content-Type: application/json" \
  -d '{
    "run": {
      "run_id": "run-001",
      "safety_profile": "normal",
      "run_scope": "incremental",
      "token_cap": 5000000,
      "max_phases": 25
    },
    "tiers": [
      {
        "tier_id": "T1",
        "tier_index": 0,
        "name": "Core Features",
        "description": "Tier 1: Core feature implementation"
      }
    ],
    "phases": [
      {
        "phase_id": "P1.1",
        "phase_index": 0,
        "tier_id": "T1",
        "name": "Implement user authentication",
        "description": "Add JWT-based authentication",
        "task_category": "feature_scaffolding",
        "complexity": "medium",
        "builder_mode": "compose"
      }
    ]
  }'
```

### Get Run Status

```bash
curl http://localhost:8000/runs/run-001
```

### Record an Issue

```bash
curl -X POST "http://localhost:8000/runs/run-001/phases/P1.1/record_issue" \
  -H "Content-Type: application/json" \
  -d '{
    "issue_key": "test_failure__auth_missing",
    "severity": "minor",
    "source": "test",
    "category": "test_failure",
    "task_category": "feature_scaffolding",
    "complexity": "medium",
    "evidence_refs": ["tests/test_auth.py::test_jwt_validation"]
  }'
```

### Submit Builder Result

```bash
curl -X POST "http://localhost:8000/runs/run-001/phases/P1.1/builder_result" \
  -H "Content-Type: application/json" \
  -d '{
    "phase_id": "P1.1",
    "run_id": "run-001",
    "patch_content": "diff --git a/src/auth.py ...",
    "files_changed": ["src/auth.py"],
    "lines_added": 45,
    "lines_removed": 12,
    "builder_attempts": 1,
    "tokens_used": 15000,
    "duration_minutes": 2.5,
    "status": "success",
    "notes": "Implemented JWT authentication with refresh tokens"
  }'
```

### Get Metrics

```bash
# All runs
curl http://localhost:8000/metrics/runs

# Runs by status
curl http://localhost:8000/metrics/runs?status=DONE_SUCCESS

# Tier metrics for a run
curl http://localhost:8000/metrics/tiers/run-001

# Issue backlog summary
curl http://localhost:8000/reports/issue_backlog_summary

# Budget analysis
curl http://localhost:8000/reports/budget_analysis

# Comprehensive run summary
curl http://localhost:8000/reports/run_summary/run-001
```

---

## Testing

### Run All Tests

```bash
# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ -v --cov=src/autopack --cov-report=html

# Run specific test suite
pytest tests/test_models.py -v
pytest tests/test_issue_tracker.py -v
```

### Run Validation Scripts

```bash
# Validate Chunk A (models)
bash scripts/autonomous_probe_run_state.sh

# Validate Chunk B (issues)
bash scripts/autonomous_probe_issues.sh

# Validate all chunks
bash scripts/autonomous_probe_complete.sh
```

### Run Preflight Gate

```bash
# Normal CI profile
CI_PROFILE=normal bash scripts/preflight_gate.sh

# Strict CI profile
CI_PROFILE=strict bash scripts/preflight_gate.sh
```

---

## GitHub Actions Workflows

### CI Workflow

Triggers on:
- Push to `main` branch
- Push to `autonomous/*` branches
- Pull requests to `main`

Jobs:
1. **lint** - Ruff linting and Black formatting checks
2. **test** - Run tests with Postgres service
3. **preflight-normal** - Run preflight gate with normal profile (autonomous/* branches only)
4. **preflight-strict** - Run preflight gate with strict profile (autonomous/* branches with `[strict]` in commit message)

### Promotion Workflow

Manual workflow to promote autonomous runs:

```bash
# Trigger via GitHub Actions UI
# Inputs:
#   - run_id: ID of the run to promote
#   - integration_branch: Branch to promote from (e.g., autonomous/run-001)

# Or via GitHub CLI
gh workflow run promotion.yml \
  -f run_id=run-001 \
  -f integration_branch=autonomous/run-001
```

The workflow:
1. Checks eligibility (run summary exists, tiers clean, no excess issues)
2. Creates PR to main if eligible
3. Blocks promotion if not eligible

---

## File Layout

Autopack creates the following file structure for each run:

```
.autonomous_runs/
└── {run_id}/
    ├── run_summary.md              # Run metadata and status
    ├── tiers/
    │   ├── tier_0_T1.md           # Tier summary
    │   └── tier_1_T2.md
    ├── phases/
    │   ├── phase_0_P1.1.md        # Phase summary
    │   └── phase_1_P1.2.md
    ├── issues/
    │   ├── phase_0_P1.1_issues.json    # Phase-level issues
    │   └── phase_1_P1.2_issues.json
    └── run_issue_index.json       # Run-level issue index
```

Project-level files:
```
.autonomous_runs/
├── project_issue_backlog.json           # Project backlog with aging
└── project_ruleset_Autopack.json        # Project ruleset (Chunk C)
```

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `postgresql://autopack:autopack@localhost:5432/autopack` | Postgres connection string |
| `AUTONOMOUS_RUNS_DIR` | `.autonomous_runs` | Base directory for run files |
| `TESTING` | Not set | Set to `"1"` to skip DB initialization (test mode) |
| `CI_PROFILE` | `normal` | CI profile for preflight gate (`normal` or `strict`) |
| `MAX_ATTEMPTS` | `3` | Max retry attempts for preflight gate |
| `BACKOFF_SECONDS` | `5` | Backoff seconds between retries |

---

## API Endpoints Reference

### Core Endpoints (Chunk A)
- `POST /runs/start` - Start new autonomous run
- `GET /runs/{run_id}` - Get run details with tiers and phases
- `POST /runs/{run_id}/phases/{phase_id}/update_status` - Update phase status

### Issue Endpoints (Chunk B)
- `POST /runs/{run_id}/phases/{phase_id}/record_issue` - Record issue at all three levels
- `GET /runs/{run_id}/issues/index` - Get run-level issue index
- `GET /project/issues/backlog` - Get project-level backlog with aging

### Builder/Auditor Endpoints (Chunk D)
- `POST /runs/{run_id}/phases/{phase_id}/builder_result` - Submit Builder result with patch
- `POST /runs/{run_id}/phases/{phase_id}/auditor_request` - Request Auditor review
- `POST /runs/{run_id}/phases/{phase_id}/auditor_result` - Submit Auditor result
- `GET /runs/{run_id}/integration_status` - Get integration branch status

### Metrics Endpoints (Chunk F)
- `GET /metrics/runs?status={state}` - Run metrics with optional filtering
- `GET /metrics/tiers/{run_id}` - Tier-level metrics for a run
- `GET /reports/issue_backlog_summary` - Issue backlog analysis
- `GET /reports/budget_analysis` - Budget failure analysis
- `GET /reports/run_summary/{run_id}` - Comprehensive run summary

### Utility Endpoints
- `GET /` - Root endpoint with service info
- `GET /health` - Health check endpoint
- `GET /docs` - Interactive API documentation (Swagger UI)
- `GET /redoc` - Alternative API documentation (ReDoc)

---

## Integration with Cursor and Codex

### Cursor (Builder) Integration

Cursor acts as the Builder agent. To integrate:

1. **Submit phase results** via `POST /runs/{run_id}/phases/{phase_id}/builder_result`
2. **Include**: diffs, probe outputs, suggested issues, token usage
3. **Patches** are automatically applied to `autonomous/{run_id}` integration branch

Example workflow:
```python
import requests

# After Cursor completes a phase
result = {
    "phase_id": "P1.1",
    "run_id": "run-001",
    "patch_content": diff_output,
    "files_changed": ["src/auth.py"],
    "builder_attempts": 1,
    "tokens_used": 15000,
    "status": "success"
}

response = requests.post(
    "http://localhost:8000/runs/run-001/phases/P1.1/builder_result",
    json=result
)
```

### Codex (Auditor) Integration

Codex acts as the Auditor for review. To integrate:

1. **Request review** via `POST /runs/{run_id}/phases/{phase_id}/auditor_request`
2. **Submit review** via `POST /runs/{run_id}/phases/{phase_id}/auditor_result`
3. **Auditor patches** also go through governed apply path

Example workflow:
```python
# Request Auditor review
request = {
    "phase_id": "P1.1",
    "run_id": "run-001",
    "tier_id": "T1",
    "review_focus": "security",
    "auditor_profile": "schema_review"
}

requests.post(
    "http://localhost:8000/runs/run-001/phases/P1.1/auditor_request",
    json=request
)

# Submit Auditor result
result = {
    "phase_id": "P1.1",
    "run_id": "run-001",
    "review_notes": "Security review complete",
    "recommendation": "approve",
    "confidence": "high"
}

requests.post(
    "http://localhost:8000/runs/run-001/phases/P1.1/auditor_result",
    json=result
)
```

---

## Troubleshooting

### Database Connection Issues

```bash
# Check if Postgres is running
docker-compose ps db

# View database logs
docker-compose logs db

# Restart database
docker-compose restart db
```

### API Not Starting

```bash
# Check API logs
docker-compose logs api

# Rebuild containers
docker-compose down
docker-compose up -d --build
```

### Test Failures

```bash
# Ensure TESTING environment variable is set
export TESTING=1
pytest tests/test_models.py -v

# For issue tracker tests, note that some tests have isolation issues
# This is expected and documented in IMPLEMENTATION_STATUS.md
```

### Integration Branch Issues

```bash
# Check integration branch status
curl http://localhost:8000/runs/run-001/integration_status

# Manually inspect branch
git branch -a | grep autonomous
git log autonomous/run-001
```

---

## Production Deployment

### Database Setup

1. Use managed Postgres service (AWS RDS, Google Cloud SQL, etc.)
2. Update `DATABASE_URL` environment variable
3. Run migrations: `python -c "from src.autopack.database import init_db; init_db()"`

### Security

1. **Never expose Postgres credentials** in version control
2. **Use secrets management** for DATABASE_URL (AWS Secrets Manager, etc.)
3. **Enable HTTPS** via reverse proxy (nginx, Traefik)
4. **Add authentication** to API endpoints (OAuth, API keys)

### Monitoring

1. **Metrics**: Use `/metrics/runs` and `/reports/*` endpoints
2. **Logs**: Configure structured logging (JSON format)
3. **Alerts**: Set up alerts for budget exhaustion and critical failures
4. **Prometheus**: Export metrics for Prometheus scraping (future enhancement)

---

## Next Steps

1. ✅ Deploy infrastructure: `docker-compose up -d`
2. ✅ Validate: `bash scripts/autonomous_probe_complete.sh`
3. ⏭️ Integrate with Cursor (Builder)
4. ⏭️ Integrate with Codex (Auditor)
5. ⏭️ Run first autonomous build
6. ⏭️ Monitor metrics and iterate

---

## References

- [IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md) - Complete implementation details
- [README.md](README.md) - Project overview and architecture
- [autonomous_build_playbook_v7_consolidated.md](autonomous_build_playbook_v7_consolidated.md) - V7 playbook specification
- [cursor_chunk_prompts_v7.md](cursor_chunk_prompts_v7.md) - Implementation chunk prompts

---

**Status:** Ready for deployment
**Last Updated:** 2025-11-23
