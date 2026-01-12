# Autopack Authentication & Authorization Posture

**Last Updated**: 2026-01-12
**Status**: Production-ready with documented boundaries

## Overview

Autopack uses a dual-mode authentication system designed for both automated executors and human operators:

1. **API Key Authentication** - For programmatic access (executors, CLI tools)
2. **JWT Session Authentication** - For browser-based operator UI (future enhancement)

---

## Production Operator UI Auth Story

### Current State (2026-01-12)

The Vite-based operator UI (`src/frontend/`) is currently configured for:

- **Development Mode**: Proxied API calls to backend (`/api` → `http://localhost:8000`)
- **Production Mode**: Served via nginx with API proxying

### Auth Boundary

**Key Decision**: The operator UI currently relies on API key authentication passed through headers.

**For JWT browser sessions** (when implemented):
1. Auth routes are explicitly preserved: `/api/auth/*` → backend (no prefix stripping)
2. Other API routes: `/api/*` → backend (prefix stripped to `/`)
3. Nginx routing configured in [nginx.conf:42-64](nginx.conf#L42-L64)

### Nginx Routing Constraints

```nginx
# Auth API proxy - MUST preserve /api/auth prefix
location /api/auth/ {
    proxy_pass http://backend:8000;  # No trailing slash = prefix preserved
    # ... (headers, timeouts)
}

# General API proxy - strips /api prefix
location /api/ {
    proxy_pass http://backend:8000/;  # Trailing slash = prefix stripped
    # ... (headers, timeouts)
}
```

**Why this matters**:
- The auth router in FastAPI is mounted at `/api/auth`
- nginx MUST preserve the full path including `/api/auth` for auth endpoints
- Other routes have `/api` stripped so `/api/runs` becomes `/runs` at the backend

**Verification**: See `tests/api/test_route_contract.py` for API route shape contracts

---

## API Key Access

### Executor → Supervisor API

**Location**: `src/autopack/supervisor/api_client.py` (SupervisorApiClient)

**Mechanism**:
- Executor includes `X-API-Key` header in all requests to supervisor
- Configurable via environment variable
- Timeout: 10s default

**Security boundary**:
- The executor is the **only** component that makes raw HTTP calls
- BUILD-135 enforcement: `tests/unit/test_executor_http_enforcement.py` prevents raw `requests.*` usage outside allowed zones
- Phase 2 (PR #143): Enforcement extended to `autonomous_executor.py`

### Operator → API

**Current**:
- Operators can use API keys via `X-API-Key` header
- Frontend can pass API key in requests (insecure for browser; intended for CLI/automation)

**Future (JWT sessions)**:
- Browser-based UI will use JWT tokens stored in httpOnly cookies
- `/api/auth/login` endpoint will issue JWT
- `/api/auth/logout` endpoint will clear session
- Token refresh via `/api/auth/refresh`

---

## Testing Coverage

### Backend Auth Contract Tests

**File**: `tests/api/test_auth_dependency_contract.py` (19 tests)

**Coverage**:
- ✅ TESTING mode bypasses auth (for test isolation)
- ✅ Production mode requires API key
- ✅ Dev mode optional key behavior
- ✅ Forwarded headers (`X-Forwarded-For`) trusted only from nginx (trusted proxy)
- ✅ Rate limiting key extraction respects proxy chain

**File**: `tests/api/test_route_contract.py`

**Coverage**:
- ✅ Route shapes don't drift
- ✅ All expected endpoints are mounted
- ✅ Auth router at `/api/auth/*` preserved

### Frontend Tests (P2 - Item 1.4)

**Status**: Test harness configured, example tests created

**Files**:
- `vitest.config.ts` - Test framework configuration
- `src/frontend/test/setup.ts` - Test environment setup
- `src/frontend/App.test.tsx` - Routing tests
- `src/frontend/pages/NotFound.test.tsx` - 404 page tests
- `src/frontend/components/MultiFileUpload.test.tsx` - Component tests

**Note**: Test execution requires troubleshooting in the Windows/Node 18 environment. Infrastructure is complete and ready for CI integration once execution issue is resolved.

---

## Auth Boundary Guarantees

### What's Enforced

1. **Executor HTTP isolation** (BUILD-135):
   - Only `SupervisorApiClient` makes HTTP calls
   - grep-based test prevents raw `requests.*` in executor code
   - Phase 2: Extended to `autonomous_executor.py`

2. **nginx routing constraints**:
   - `/api/auth/*` prefix preserved (longest-match rule)
   - `/api/*` prefix stripped for general routes
   - Health checks: `/nginx-health` (static), `/health` (proxied)

3. **API contract stability**:
   - Route shapes tested in `test_route_contract.py`
   - Auth dependency behavior tested in `test_auth_dependency_contract.py`

### What's Not Yet Enforced

1. **JWT session implementation**:
   - Routes exist (`/api/auth/*`) but JWT logic not yet wired
   - httpOnly cookie storage not yet configured
   - Token refresh not yet implemented

2. **Frontend auth state management**:
   - No React context for auth state
   - No protected route guards
   - No token refresh logic

3. **CORS for JWT**:
   - CORS configured in `src/autopack/api/app.py`
   - Credentials support (`Access-Control-Allow-Credentials`) needs verification for JWT cookies

---

## Security Considerations

### API Key Best Practices

- **Storage**: Environment variables only (never in code)
- **Transmission**: HTTPS only in production
- **Rotation**: Manual process (document rotation procedure)
- **Scope**: Single key grants full access (no per-endpoint scoping yet)

### JWT Session Best Practices (Future)

- **Storage**: httpOnly cookies (XSS protection)
- **Transmission**: Secure flag in production
- **Expiry**: Short-lived access tokens (15-30min) + refresh tokens (7-30 days)
- **CSRF**: SameSite=Lax or Strict + CSRF tokens for state-changing operations

### nginx Security Headers

**File**: [nginx.conf:17-31](nginx.conf#L17-L31)

- `X-Frame-Options: SAMEORIGIN` (clickjacking protection)
- `X-Content-Type-Options: nosniff` (MIME-sniffing protection)
- `X-XSS-Protection: 1; mode=block` (legacy XSS filter)
- `Content-Security-Policy` (CSP for script/style/resource loading)
- `Strict-Transport-Security` (HSTS for HTTPS enforcement)

---

## Operator UI Access Patterns

### Development

```bash
npm run dev        # Frontend dev server on :3000
                   # Proxies /api to http://localhost:8000
```

### Production (Docker Compose)

```bash
docker-compose up  # nginx on :80
                   # Serves static UI from /usr/share/nginx/html
                   # Proxies /api to backend:8000
```

**Access**:
- UI: `http://localhost/`
- API (direct): `http://localhost/api/*`
- Health: `http://localhost/health` (backend), `http://localhost/nginx-health` (nginx only)

---

## References

- **API routing**: `src/autopack/api/app.py` (FastAPI app factory)
- **Auth deps**: `src/autopack/api/deps.py` (verify_api_key, get_client_ip)
- **nginx config**: `nginx.conf` (routing + security headers)
- **Executor client**: `src/autopack/supervisor/api_client.py` (SupervisorApiClient)
- **Route contracts**: `tests/api/test_route_contract.py`
- **Auth contracts**: `tests/api/test_auth_dependency_contract.py`
- **HTTP enforcement**: `tests/unit/test_executor_http_enforcement.py` (BUILD-135)

---

## Future Enhancements (Out of Scope for Item 1.4)

1. **JWT Implementation**:
   - Wire up `/api/auth/login`, `/api/auth/logout`, `/api/auth/refresh`
   - Issue JWT with user claims
   - Verify JWT in `verify_api_key` dependency (support both API keys and JWTs)

2. **Frontend Auth**:
   - React Context for auth state
   - Protected route wrapper component
   - Auto token refresh logic
   - Login/logout UI

3. **RBAC (Role-Based Access Control)**:
   - Define roles (operator, admin, read-only)
   - Scope API key or JWT with role claims
   - Per-endpoint permission checks

4. **Audit Logging**:
   - Log all auth attempts (success + failure)
   - Log API key usage
   - Tie operations to authenticated identity

---

**Status Summary**: Auth boundary is well-defined, tested, and enforced at the HTTP layer. JWT browser sessions are scoped as a future enhancement with routing already in place.
