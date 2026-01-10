# Canonical API Contract

**Canonical Server**: `PYTHONPATH=src uvicorn autopack.main:app --host 0.0.0.0 --port 8000`

This document defines the **required endpoints** that must be served by the canonical Autopack server (`autopack.main:app`). All first-party scripts, the autonomous executor, dashboards, and observability tooling must target only these endpoints.

Last updated: 2026-01-10 (GAP-8.10 Operator Surface Endpoints)

---

## Authentication

**Canonical header**: `X-API-Key`
**Compatibility**: `Bearer` tokens supported for auth endpoints
**Configuration**: `AUTOPACK_API_KEY` environment variable

---

## Required Endpoints

### 1. Run Lifecycle (Required by Executor)

#### `POST /runs/start`
- **Purpose**: Create and initialize a new autonomous build run
- **Auth**: Requires `X-API-Key`
- **Rate limit**: 10/minute per IP
- **Request**: `RunStartRequest` (includes run, tiers, phases)
- **Response**: `RunResponse` (201)

#### `GET /runs/{run_id}`
- **Purpose**: Get run details with all tiers and phases
- **Auth**: None (public read)
- **Response**: `RunResponse` (200)

#### `POST /runs/{run_id}/phases/{phase_id}/update_status`
- **Purpose**: Update phase status and metrics
- **Auth**: None (executor trust boundary)
- **Request**: `PhaseStatusUpdate`
- **Response**: Status update confirmation

#### `POST /runs/{run_id}/phases/{phase_id}/builder_result`
- **Purpose**: Submit Builder results and apply patches
- **Auth**: None (executor trust boundary)
- **Request**: `BuilderResult`
- **Response**: Builder result confirmation

#### `POST /runs/{run_id}/phases/{phase_id}/auditor_result`
- **Purpose**: Submit Auditor results
- **Auth**: None (executor trust boundary)
- **Request**: `AuditorResult`
- **Response**: Auditor result confirmation

#### `POST /runs/{run_id}/phases/{phase_id}/record_issue`
- **Purpose**: Record an issue for a phase
- **Auth**: None
- **Response**: Issue tracking confirmation

---

### 2. Health & Observability

#### `GET /health`
- **Purpose**: Health check with DB connectivity, dependency checks, kill switch states
- **Auth**: None (public)
- **Response**: Enhanced health response with:
  - `status`: "healthy" | "degraded" | "unhealthy"
  - `database_identity`: Hash of DB URL for drift detection
  - `database`: Connection status
  - `qdrant`: Optional Qdrant connection status
  - `kill_switches`: State of all kill switches
  - `version`: API version
- **Status codes**: 200 (healthy), 503 (unhealthy)

---

### 3. Dashboard Endpoints

#### `GET /dashboard/runs/{run_id}/status`
- **Purpose**: Get run status for dashboard display
- **Auth**: None
- **Response**: `DashboardRunStatus`

#### `GET /dashboard/usage`
- **Purpose**: Get token usage statistics
- **Auth**: None
- **Query params**: `period` (day/week/month)
- **Response**: `UsageResponse` (providers, models)

#### `GET /dashboard/models`
- **Purpose**: Get current model mappings
- **Auth**: None
- **Response**: List of `ModelMapping`

#### `GET /dashboard/runs/{run_id}/token-efficiency`
- **Purpose**: Get token efficiency metrics (BUILD-145)
- **Auth**: Requires `X-API-Key`
- **Response**: `TokenEfficiencyStats`
- **Status**: Legacy - prefer `/consolidated-metrics`

#### `GET /dashboard/runs/{run_id}/phase6-stats`
- **Purpose**: Get Phase 6 True Autonomy metrics (BUILD-146)
- **Auth**: Requires `X-API-Key`
- **Response**: `Phase6Stats`
- **Status**: Legacy - prefer `/consolidated-metrics`

#### `GET /dashboard/runs/{run_id}/consolidated-metrics`
- **Purpose**: **PRIMARY** - Get consolidated token metrics (no double-counting)
- **Auth**: None
- **Kill switch**: `AUTOPACK_ENABLE_CONSOLIDATED_METRICS=1` (default: OFF)
- **Query params**: `limit` (max: 10000, default: 1000), `offset` (default: 0)
- **Response**: `ConsolidatedTokenMetrics` with 4 independent categories:
  1. `total_tokens_spent`: Actual LLM spend
  2. `artifact_tokens_avoided`: Efficiency savings
  3. `doctor_tokens_avoided_estimate`: Counterfactual estimate
  4. `ab_delta_tokens_saved`: Measured A/B delta
- **Status codes**: 200 (success), 503 (kill switch disabled), 404 (run not found), 400 (bad pagination)

#### `GET /dashboard/ab-results`
- **Purpose**: Get A/B test results
- **Auth**: None
- **Query params**: `test_id`, `valid_only` (default: true), `limit` (max: 1000, default: 100)
- **Response**: List of A/B test comparison results

#### `POST /dashboard/human-notes`
- **Purpose**: Add human notes to notes file
- **Auth**: None
- **Request**: `HumanNoteRequest`
- **Response**: Confirmation with timestamp

#### `POST /dashboard/models/override`
- **Purpose**: Add model override (global or per-run)
- **Auth**: None
- **Request**: `ModelOverrideRequest`
- **Response**: Override confirmation

---

### 4. Issue Tracking

#### `GET /runs/{run_id}/issues/index`
- **Purpose**: Get run-level issue index
- **Auth**: None
- **Response**: Run issue index

#### `GET /project/issues/backlog`
- **Purpose**: Get project-level issue backlog
- **Auth**: None
- **Response**: Project backlog

---

### 5. Error Reporting

#### `GET /runs/{run_id}/errors`
- **Purpose**: Get all error reports for a run
- **Auth**: None
- **Response**: Error report list

#### `GET /runs/{run_id}/errors/summary`
- **Purpose**: Get error summary for a run
- **Auth**: None
- **Response**: Error summary

---

### 6. Approval Workflows (BUILD-117)

#### `POST /approval/request`
- **Purpose**: Request human approval for risky decisions
- **Auth**: None
- **Request**: Approval context (phase_id, run_id, decision_info, deletion_info)
- **Response**: Approval status (approved/rejected/pending)
- **Features**: Telegram notifications, timeout handling, audit trail

#### `GET /approval/status/{approval_id}`
- **Purpose**: Check approval request status (for executor polling)
- **Auth**: None
- **Response**: Approval status details

#### `GET /approval/pending`
- **Purpose**: Get all pending approvals (for dashboard)
- **Auth**: None
- **Response**: List of pending approval requests

#### `POST /telegram/webhook`
- **Purpose**: Handle Telegram webhook callbacks for approval buttons
- **Auth**: None (validates webhook signature internally)
- **Request**: Telegram callback query
- **Response**: Acknowledgment

---

### 7. Governance Requests (BUILD-127)

#### `GET /governance/pending`
- **Purpose**: Get all pending governance requests
- **Auth**: None
- **Response**: List of pending governance requests

#### `POST /governance/approve/{request_id}`
- **Purpose**: Approve or deny a governance request
- **Auth**: None
- **Query params**: `approved` (bool), `user_id` (string)
- **Response**: Approval status

---

### 8. Authentication Endpoints (Canonical Auth Router)

These endpoints are served by `src/autopack/auth/router.py` and are mounted under `/api/auth/*`.

#### `POST /api/auth/register`
- **Purpose**: Register new user
- **Auth**: None
- **Request**: Username, email, password
- **Response**: User created confirmation

#### `POST /api/auth/login`
- **Purpose**: Login and get JWT token
- **Auth**: None (credentials in request)
- **Request**: Username, password
- **Response**: JWT access token

#### `GET /api/auth/me`
- **Purpose**: Get current user info
- **Auth**: Requires `Bearer` token
- **Response**: User profile

#### `GET /api/auth/.well-known/jwks.json`
- **Purpose**: Get JSON Web Key Set for JWT validation
- **Auth**: None (public)
- **Response**: JWKS

---

### 9. OAuth Credential Health (BUILD-189)

These endpoints are served by `src/autopack/auth/oauth_router.py` for OAuth credential lifecycle management.

#### `GET /api/auth/oauth/health`
- **Purpose**: Get comprehensive credential health report for dashboard
- **Auth**: Requires `Bearer` token
- **Response**: Health report with summary and per-credential status

#### `GET /api/auth/oauth/health/{provider}`
- **Purpose**: Get health status for a specific OAuth provider
- **Auth**: Requires `Bearer` token
- **Response**: CredentialHealth (status, expiry, failure counts)

#### `POST /api/auth/oauth/refresh/{provider}`
- **Purpose**: Manually trigger credential refresh
- **Auth**: Requires `Bearer` token + **Admin only** (`is_superuser=true`)
- **Response**: Refresh queued confirmation or 403 if not admin

#### `POST /api/auth/oauth/reset/{provider}`
- **Purpose**: Reset failure count for a credential
- **Auth**: Requires `Bearer` token + **Admin only** (`is_superuser=true`)
- **Response**: Reset confirmation or 403 if not admin

#### `GET /api/auth/oauth/events`
- **Purpose**: Get recent credential lifecycle events (for audit)
- **Auth**: Requires `Bearer` token
- **Query params**: `provider` (optional), `limit` (default: 100)
- **Response**: List of credential events (refresh attempts, failures, etc.)

---

### 10. Operator Surface - Runs Inbox & Artifacts (GAP-8.10)

These endpoints provide the operator UI with run browsing, artifact viewing, and progress monitoring capabilities.

**Auth Policy** (P0.4 Security Hardening):
- **Production** (`AUTOPACK_ENV=production`): Requires `X-API-Key` header
- **Development**: Public by default, or opt-in to require auth by NOT setting `AUTOPACK_PUBLIC_READ=1`
- **Dev with public read** (`AUTOPACK_PUBLIC_READ=1`): No auth required (for local dashboards)

#### `GET /runs`
- **Purpose**: List all runs with pagination and summary info
- **Auth**: Required in production; dev opt-in via `AUTOPACK_PUBLIC_READ=1`
- **Query params**: `limit` (1-100, default: 20), `offset` (default: 0)
- **Response**: `{ runs: [...], total, limit, offset }`
- **Notes**: Returns phase counts per run; known N+1 query (tracked in GAP-8.11.1)

#### `GET /runs/{run_id}/progress`
- **Purpose**: Get phase-by-phase progress details for a run
- **Auth**: Required in production; dev opt-in via `AUTOPACK_PUBLIC_READ=1`
- **Response**: `{ run_id, state, phases_total, phases_completed, phases_in_progress, phases_pending, phases: [...], tokens_used, token_cap, started_at, elapsed_seconds }`

#### `GET /runs/{run_id}/artifacts/index`
- **Purpose**: List all artifact files for a run
- **Auth**: Required in production; dev opt-in via `AUTOPACK_PUBLIC_READ=1`
- **Response**: `{ run_id, artifacts: [{ path, size_bytes, modified_at }], total_size_bytes }`
- **Notes**: Returns empty list if run directory doesn't exist

#### `GET /runs/{run_id}/artifacts/file`
- **Purpose**: Get content of a specific artifact file
- **Auth**: Required in production; dev opt-in via `AUTOPACK_PUBLIC_READ=1`
- **Query params**: `path` (required, relative path within run directory)
- **Response**: Plain text file content
- **Security**: Path traversal protection (blocks `..`, absolute paths, Windows drive letters, URL-encoded bypass attempts)

#### `GET /runs/{run_id}/browser/artifacts`
- **Purpose**: List browser-specific artifacts (screenshots, HTML files)
- **Auth**: Required in production; dev opt-in via `AUTOPACK_PUBLIC_READ=1`
- **Response**: `{ run_id, screenshots: [{ path, timestamp, size_bytes }], html_files: [...], total_size_bytes }`

---

### 11. Storage Management

#### `GET /storage/scans`
- **Purpose**: List storage scans
- **Auth**: Requires `X-API-Key`
- **Response**: List of `StorageScanResponse`

#### `GET /storage/scans/{scan_id}`
- **Purpose**: Get storage scan details
- **Auth**: Requires `X-API-Key`
- **Response**: `StorageScanDetailResponse`

#### `POST /storage/scans/{scan_id}/approve`
- **Purpose**: Approve a storage scan
- **Auth**: Requires `X-API-Key`
- **Response**: Approval confirmation

#### `GET /storage/steam/games`
- **Purpose**: List Steam games (storage analysis)
- **Auth**: None
- **Response**: `SteamGamesListResponse`

#### `POST /storage/patterns/analyze`
- **Purpose**: Analyze file patterns
- **Auth**: None
- **Response**: List of `PatternResponse`

#### `GET /storage/learned-rules`
- **Purpose**: Get learned file organization rules
- **Auth**: None
- **Response**: List of `LearnedRuleResponse`

#### `POST /storage/learned-rules/{rule_id}/approve`
- **Purpose**: Approve a learned rule
- **Auth**: None
- **Response**: `LearnedRuleResponse`

#### `GET /storage/recommendations`
- **Purpose**: Get file organization recommendations
- **Auth**: None
- **Response**: `RecommendationsListResponse`

---

### 12. File Upload

#### `POST /files/upload`
- **Purpose**: Upload files for processing
- **Auth**: Requires `X-API-Key`
- **Response**: Upload confirmation with file metadata

---

### 13. Research API (Experimental)

#### `POST /research/*`
- **Purpose**: Research API endpoints (BUILD-113+)
- **Auth**: Varies by endpoint
- **Status**: Experimental - see `/research` prefix endpoints

---

## Kill Switches (All Default OFF)

| Switch | Environment Variable | Default | Purpose |
|--------|---------------------|---------|---------|
| Phase 6 Metrics | `AUTOPACK_ENABLE_PHASE6_METRICS` | `0` | Enable Phase 6 telemetry collection |
| Consolidated Metrics | `AUTOPACK_ENABLE_CONSOLIDATED_METRICS` | `0` | Enable consolidated metrics endpoint |
| Auto-Approve | `AUTO_APPROVE_BUILD113` | `true` | Auto-approve risky decisions (disable for human-in-loop) |

**Important**: All observability kill switches default to **OFF** to prevent accidental LLM calls or performance overhead in production.

---

## Deprecated Endpoints (Legacy Support)

These endpoints exist for backward compatibility but should not be used by new code:

- `/dashboard/runs/{run_id}/token-efficiency` → Use `/dashboard/runs/{run_id}/consolidated-metrics`
- `/dashboard/runs/{run_id}/phase6-stats` → Use `/dashboard/runs/{run_id}/consolidated-metrics`

---

## Migration Notes (See Consolidation Plan)

This canonical contract intentionally avoids documenting deprecated entrypoints or legacy paths.
For historical context and migration notes, see `docs/CANONICAL_API_CONSOLIDATION_PLAN.md`.

---

## Testing the Canonical Server

```bash
# Start canonical server
PYTHONPATH=src uvicorn autopack.main:app --host 0.0.0.0 --port 8000

# Health check with DB identity
curl http://localhost:8000/health

# With debug identity info
DEBUG_DB_IDENTITY=1 PYTHONPATH=src uvicorn autopack.main:app
```

---

## Contract Guarantees

1. **Single control plane**: Only `autopack.main:app` serves production traffic
2. **No dual runtime**: Backend server is deprecated
3. **Kill switches OFF by default**: Explicit opt-in required for observability features
4. **No new LLM calls**: API/telemetry never triggers additional AI costs
5. **Windows + Postgres first-class**: All endpoints tested on both platforms
6. **Backward compatibility**: Legacy endpoints maintained where feasible

---

## Related Documentation

- [Canonical API Consolidation Plan](CANONICAL_API_CONSOLIDATION_PLAN.md) - Implementation roadmap
- [BUILD-146 P12 Production Hardening](../BUILD-146-P12-PRODUCTION-HARDENING.md) - Kill switches and safety
- [BUILD-146 P11 Observability](../BUILD-146-P11-OBSERVABILITY.md) - Consolidated metrics design
