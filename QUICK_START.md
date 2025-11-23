# Autopack Quick Start Guide

⚡ **5-Minute Setup** - Get Autopack running in 5 minutes

---

## 1️⃣ Commit Your Work (1 minute)

```bash
git add .
git commit -m "Complete v7 autonomous build playbook implementation"
git push origin main
```

---

## 2️⃣ Start Services (1 minute)

```bash
docker-compose up -d
```

**Verify:** http://localhost:8000/health should return `{"status":"healthy"}`

---

## 3️⃣ View API Docs (30 seconds)

Open in browser: **http://localhost:8000/docs**

You'll see all 19 endpoints with interactive testing!

---

## 4️⃣ Create Your First Run (2 minutes)

```bash
curl -X POST http://localhost:8000/runs/start \
  -H "Content-Type: application/json" \
  -d '{
    "run": {
      "run_id": "my-first-run",
      "safety_profile": "normal",
      "run_scope": "incremental"
    },
    "tiers": [{
      "tier_id": "T1",
      "tier_index": 0,
      "name": "My First Tier",
      "description": "Testing Autopack"
    }],
    "phases": [{
      "phase_id": "P1",
      "phase_index": 0,
      "tier_id": "T1",
      "name": "My First Phase",
      "description": "Testing phase creation",
      "task_category": "feature_scaffolding",
      "complexity": "low",
      "builder_mode": "compose"
    }]
  }'
```

---

## 5️⃣ Check Results (30 seconds)

```bash
# Get run status
curl http://localhost:8000/runs/my-first-run | jq

# Check file structure
ls .autonomous_runs/my-first-run/
```

---

## ✅ You're Done!

**What You Have:**
- ✅ Autopack running on http://localhost:8000
- ✅ Postgres database with your first run
- ✅ File structure in `.autonomous_runs/`
- ✅ API documentation at http://localhost:8000/docs
- ✅ All 19 endpoints ready to use

---

## 🎯 Next Steps

**Play Around:**
```bash
# Record an issue
curl -X POST "http://localhost:8000/runs/my-first-run/phases/P1/record_issue?issue_key=my_issue&severity=minor&source=test&category=test_failure"

# Get metrics
curl http://localhost:8000/metrics/runs | jq

# Get comprehensive summary
curl http://localhost:8000/reports/run_summary/my-first-run | jq
```

**Read Documentation:**
- [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) - Full deployment guide
- [NEXT_STEPS.md](NEXT_STEPS.md) - Detailed next steps
- [COMPLETION_SUMMARY.md](COMPLETION_SUMMARY.md) - What was built

**Integrate:**
- Connect Cursor (Builder) to submit results
- Connect Codex (Auditor) for reviews
- Build Supervisor orchestration loop

---

## 🔧 Common Commands

```bash
# Start services
docker-compose up -d

# Stop services
docker-compose down

# View logs
docker-compose logs -f api

# Restart services
docker-compose restart

# Run validation
bash scripts/autonomous_probe_complete.sh

# Run tests
pytest tests/test_models.py -v
```

---

## 🆘 Troubleshooting

**API not responding?**
```bash
docker-compose ps        # Check if running
docker-compose logs api  # Check for errors
```

**Database issues?**
```bash
docker-compose logs db   # Check Postgres logs
docker-compose restart db
```

**Port already in use?**
Edit `docker-compose.yml` and change `8000:8000` to `8001:8000`

---

## 📚 Key Endpoints

| Endpoint | Purpose |
|----------|---------|
| `POST /runs/start` | Create new run |
| `GET /runs/{run_id}` | Get run status |
| `POST /runs/{run_id}/phases/{phase_id}/record_issue` | Record issue |
| `POST /runs/{run_id}/phases/{phase_id}/builder_result` | Submit Builder result |
| `GET /metrics/runs` | Get all run metrics |
| `GET /reports/run_summary/{run_id}` | Get comprehensive summary |

**Full API docs:** http://localhost:8000/docs

---

## 🎉 That's It!

Autopack is ready for autonomous builds. Connect it to Cursor and Codex to start building!

**Questions?** Check [NEXT_STEPS.md](NEXT_STEPS.md) for detailed instructions.
