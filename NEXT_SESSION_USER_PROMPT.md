# User Prompt for Next Cursor Chat Session

## Quick Start

Copy and paste this into your next cursor chat:

---

**Task**: Implement BUILD-146 P12 Production Hardening (5 tasks)

**Context**: You just completed BUILD-146 P11 (API split-brain fix). The project has reached the README "ideal state" for True Autonomy with observability. What remains is staging validation and production hardening - NOT new features.

**Technical Context**: Read the comprehensive technical prompt in `NEXT_SESSION_TECHNICAL_PROMPT.md` for complete architecture details, code patterns, and constraints.

## Your 5 Tasks

Implement ALL 5 tasks below. Do not skip any. Each task is documented in detail in the technical prompt.

### 1. Rollout Playbook + Safety Rails
- Create `docs/STAGING_ROLLOUT.md` with production readiness checklist
- Add kill switches: `AUTOPACK_ENABLE_PHASE6_METRICS` and `AUTOPACK_ENABLE_CONSOLIDATED_METRICS` (default OFF)
- Create health check endpoint `src/backend/api/health.py`
- Write tests verifying kill switches default to OFF

### 2. Pattern Expansion → PR Automation
- Extend `scripts/pattern_expansion.py` to auto-generate:
  - Python detector/mitigation stubs in `src/autopack/patterns/pattern_*.py`
  - Pytest skeletons in `tests/patterns/test_pattern_*.py`
  - Backlog entries in `docs/backlog/PATTERN_*.md`
- Create pattern registry `src/autopack/patterns/__init__.py`
- Generate code for top 3-5 patterns from real data

### 3. Data Quality + Performance Hardening
- Add database indexes with migration script `scripts/migrations/add_performance_indexes.py`
- Add pagination to consolidated metrics endpoint (limit 10000 max)
- Add kill switch check to consolidated metrics
- Optional: Create retention script `scripts/metrics_retention.py`
- Document query plan verification in STAGING_ROLLOUT.md

### 4. A/B Results Persistence
- Create `ABTestResult` model in `src/autopack/models.py`
- Create migration `scripts/migrations/add_ab_test_results.py`
- Create `scripts/ab_analysis.py` to persist A/B results to DB
- Add `/ab-results` endpoint to `src/backend/api/dashboard.py`
- **CRITICAL**: Enforce strict validity (same commit SHA, same model hash - not warnings!)

### 5. Replay Campaign
- Create `scripts/replay_campaign.py` to replay failed runs
- Support filters: `--run-id`, `--from-date`, `--to-date`, `--state`, `--dry-run`
- Clone failed runs with new IDs and Phase 6 features enabled
- Use `scripts/run_parallel.py --executor api` for async execution
- Generate comparison reports in `archive/replay_results/`
- Integrate with pattern expansion for post-replay analysis

## Critical Constraints

**MUST FOLLOW**:
- ✅ Windows compatibility (Path objects, CRLF, sys.executable)
- ✅ PostgreSQL + SQLite support (test migrations on both)
- ✅ No double-counting tokens (4 categories: retrieval, second_opinion, evidence_request, base)
- ✅ No new LLM calls (operational improvements only)
- ✅ Opt-in by default (kill switches OFF)
- ✅ Test coverage for all new endpoints and migrations
- ✅ Minimal refactor (add new code, don't reorganize existing)

## Success Criteria

You're done when:
1. ✅ All 5 tasks completed (no skipping!)
2. ✅ `docs/STAGING_ROLLOUT.md` exists with complete checklist
3. ✅ All kill switches default to OFF
4. ✅ Pattern expansion generates code + tests + backlog
5. ✅ Database indexes added with migration script
6. ✅ A/B results persist to database with strict validation
7. ✅ Replay script can replay failed runs with comparison reports
8. ✅ All tests pass: `PYTHONUTF8=1 PYTHONPATH=src pytest tests/ -v`
9. ✅ BUILD_HISTORY.md updated with P12 entry
10. ✅ DEBUG_LOG.md updated with session notes
11. ✅ Changes committed and pushed to `phase-a-p11-observability` branch

## Testing Commands

```bash
# Run all tests
PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="sqlite:///:memory:" pytest tests/ -v

# Test migrations on both databases
PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="sqlite:///test.db" python scripts/migrations/add_performance_indexes.py
PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="postgresql://autopack:autopack@localhost:5432/autopack" python scripts/migrations/add_performance_indexes.py

# Generate pattern stubs
PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="sqlite:///autopack.db" python scripts/pattern_expansion.py --run-id telemetry-collection-v7 --generate-code

# Run A/B analysis
PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="sqlite:///autopack.db" python scripts/ab_analysis.py --control-run v5 --treatment-run v6 --test-id v5-vs-v6

# Replay failed runs (dry run first!)
PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="sqlite:///autopack.db" python scripts/replay_campaign.py --state FAILED --dry-run
```

## Git Workflow

```bash
# You should already be on this branch
git checkout phase-a-p11-observability

# After completing all tasks
git add .
git commit -m "feat: BUILD-146 P12 Production Hardening - Rollout+Patterns+Performance+AB+Replay"
git push origin phase-a-p11-observability
```

## Important Notes

- Read `NEXT_SESSION_TECHNICAL_PROMPT.md` for complete technical details
- This is **production hardening**, not new features
- Focus on **operational maturity** (reliability, performance, observability)
- All new features must be **OFF by default** (kill switches)
- Test on **both SQLite and PostgreSQL**
- **Windows compatibility** is critical

---

**Ready?** Start by reading `NEXT_SESSION_TECHNICAL_PROMPT.md`, then implement all 5 tasks systematically. Good luck! 🚀
