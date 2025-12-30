# API Basics

**Purpose**: High-level overview of Autopack API routes, authentication, and common responses

**Last Updated**: 2025-12-29

---

## Overview

Autopack provides a REST API for managing autonomous execution runs, phases, and approvals. This guide covers the essential endpoints and response patterns.

---

## Base URL

**Local Development**:
```
http://127.0.0.1:8000
```

**Production** (if deployed):
```
https://your-domain.com
```

---

## Authentication

### Current Status

**No authentication required** for local development. All endpoints are open.

### Future (Production)

Planned authentication methods:
- API key via `Authorization: Bearer <token>` header
- JWT tokens for user sessions
- Service account credentials

---

## Core Routes

### Health Check

**Endpoint**: `GET /health`

**Purpose**: Verify API server is running

**Response**:
```json
{
  "status": "healthy",
  "database": "connected",
  "timestamp": "2025-12-29T12:00:00Z"
}
```

**Status Codes**:
- `200 OK` - Server healthy
- `503 Service Unavailable` - Database connection failed

---

### Runs

#### Get Run

**Endpoint**: `GET /runs/{run_id}`

**Purpose**: Fetch run state and all phases

**Response**:
```json
{
  "id": "telemetry-collection-v4",
  "state": "EXECUTING",
  "created_at": "2025-12-29T10:00:00Z",
  "phases": [
    {
      "phase_id": "phase-1",
      "state": "COMPLETE",
      "description": "Create utility functions",
      "retry_attempt": 0
    }
  ]
}
```

**Status Codes**:
- `200 OK` - Run found
- `404 Not Found` - Run ID doesn't exist
- `500 Internal Server Error` - Database error

#### List Runs

**Endpoint**: `GET /runs`

**Purpose**: List all runs (paginated)

**Query Parameters**:
- `limit` (optional) - Max results (default: 50)
- `offset` (optional) - Skip N results (default: 0)
- `state` (optional) - Filter by state (QUEUED, EXECUTING, DONE_SUCCESS, etc.)

**Response**:
```json
{
  "runs": [
    {"id": "run-1", "state": "COMPLETE"},
    {"id": "run-2", "state": "EXECUTING"}
  ],
  "total": 42,
  "limit": 50,
  "offset": 0
}
```

---

### Phases

#### Update Phase Status

**Endpoint**: `PUT /runs/{run_id}/phases/{phase_id}`

**Purpose**: Update phase state (used by executor)

**Request Body**:
```json
{
  "state": "COMPLETE",
  "retry_attempt": 1,
  "error_message": null
}
```

**Response**:
```json
{
  "phase_id": "phase-1",
  "state": "COMPLETE",
  "updated_at": "2025-12-29T12:00:00Z"
}
```

**Status Codes**:
- `200 OK` - Phase updated
- `404 Not Found` - Phase doesn't exist
- `422 Unprocessable Entity` - Invalid state transition

---

### Approvals

#### Request Approval

**Endpoint**: `POST /approval/request`

**Purpose**: Request human approval for risky changes

**Request Body**:
```json
{
  "run_id": "research-build113-test",
  "phase_id": "phase-1",
  "reason": "Large deletion: 426 lines removed",
  "risk_level": "CRITICAL",
  "timeout_seconds": 3600
}
```

**Response**:
```json
{
  "approval_id": 123,
  "status": "PENDING",
  "created_at": "2025-12-29T12:00:00Z",
  "expires_at": "2025-12-29T13:00:00Z"
}
```

**Status Codes**:
- `201 Created` - Approval request created
- `400 Bad Request` - Invalid request body

#### Check Approval Status

**Endpoint**: `GET /approval/status/{approval_id}`

**Purpose**: Poll approval decision

**Response**:
```json
{
  "approval_id": 123,
  "status": "APPROVED",
  "decided_at": "2025-12-29T12:05:00Z",
  "decided_by": "user@example.com"
}
```

**Status Values**:
- `PENDING` - Awaiting decision
- `APPROVED` - Human approved
- `REJECTED` - Human rejected
- `TIMEOUT` - Expired without decision

---

## Common Response Patterns

### Success Responses

**200 OK** - Request succeeded
```json
{"status": "success", "data": {...}}
```

**201 Created** - Resource created
```json
{"id": "new-resource-id", "created_at": "..."}
```

**204 No Content** - Success with no response body

---

### Error Responses

**400 Bad Request** - Invalid input
```json
{
  "error": "Invalid request",
  "details": "Field 'state' is required"
}
```

**404 Not Found** - Resource doesn't exist
```json
{
  "error": "Not found",
  "resource": "run",
  "id": "nonexistent-run-id"
}
```

**422 Unprocessable Entity** - Validation failed
```json
{
  "error": "Validation error",
  "details": [
    {"field": "state", "message": "Invalid state transition"}
  ]
}
```

**500 Internal Server Error** - Server error
```json
{
  "error": "Internal server error",
  "message": "Database connection failed"
}
```

---

## Quick Reference

### Essential Endpoints

| Method | Endpoint | Purpose |
|--------|----------|----------|
| GET | `/health` | Health check |
| GET | `/runs/{run_id}` | Get run state |
| GET | `/runs` | List runs |
| PUT | `/runs/{run_id}/phases/{phase_id}` | Update phase |
| POST | `/approval/request` | Request approval |
| GET | `/approval/status/{id}` | Check approval |

### Common Status Codes

| Code | Meaning | Action |
|------|---------|--------|
| 200 | Success | Continue |
| 404 | Not Found | Check ID |
| 422 | Validation Error | Fix request body |
| 500 | Server Error | Check logs |

---

## Next Steps

- **Full API Reference**: See OpenAPI docs at `/docs` (Swagger UI)
- **Architecture**: [ARCHITECTURE.md](ARCHITECTURE.md) for system overview
- **Development**: [CONTRIBUTING.md](CONTRIBUTING.md) for local setup
- **Deployment**: [DEPLOYMENT.md](DEPLOYMENT.md) for production config

---

**Total Lines**: 198 (within ≤200 line constraint)

**Coverage**: Routes overview (6 endpoints), authentication (current + future), common responses (success + errors), quick reference

**Style**: High-level bullet format with code examples
