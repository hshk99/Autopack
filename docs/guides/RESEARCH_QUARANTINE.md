# Research API Quarantine Guide

## Overview

The Research API provides programmatic access to Autopack's research capabilities. Due to the sensitive nature of research operations (external API calls, data processing, resource consumption), the API implements a tri-state mode system with safety gates.

## API Mode System

### Mode Types

| Mode | Description | Use Case |
|------|-------------|----------|
| `DISABLED` | All endpoints return 503 | Production default |
| `BOOTSTRAP_ONLY` | Only bootstrap endpoints accessible | Limited production use |
| `FULL` | All endpoints accessible with safety gates | Development / authorized use |

### Configuration

The API mode is determined by environment variables in this priority order:

1. **`RESEARCH_API_MODE`** (explicit mode selection)
   - Values: `disabled`, `bootstrap_only`, `full`
   - Example: `RESEARCH_API_MODE=full`

2. **`RESEARCH_API_ENABLED`** (legacy boolean)
   - `true`/`1`/`yes` maps to `FULL`
   - `false`/`0`/`no` maps to `DISABLED`

3. **Environment-based defaults**
   - Production (`AUTOPACK_ENV=production`): `DISABLED`
   - Development (`AUTOPACK_ENV=development`): `FULL`

## Endpoint Groups

### Bootstrap Endpoints (BOOTSTRAP_ONLY or FULL mode)

These endpoints are designed for production use with limited scope:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/research/bootstrap` | POST | Start a bootstrap research session |
| `/research/bootstrap/{id}/status` | GET | Get session status |
| `/research/bootstrap/{id}/draft_anchor` | GET | Get draft anchor from completed session |

### Full Mode Endpoints (FULL mode only)

These endpoints provide full research capabilities with safety gates:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/research/full/session` | POST | Start a full research session |
| `/research/full/session/{id}/validate` | POST | Validate a session |
| `/research/full/session/{id}/publish` | POST | Publish research findings |
| `/research/full/cache/status` | GET | Get cache statistics |
| `/research/full/cache` | DELETE | Clear research cache |
| `/research/full/invalidate` | POST | Invalidate cached session |

### Legacy Endpoints (FULL mode only)

These endpoints are maintained for backward compatibility:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/research/sessions` | GET | List all sessions |
| `/research/sessions` | POST | Create a session |
| `/research/sessions/{id}` | GET | Get session by ID |

### Utility Endpoints (Always accessible)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/research/mode` | GET | Get current mode and configuration |

## Safety Gates

Full mode endpoints are protected by safety gates to prevent abuse:

### Rate Limiting

- **Default**: 30 requests per minute per endpoint
- **Configuration**: `RESEARCH_API_RATE_LIMIT` environment variable
- **Response**: HTTP 429 when exceeded

### Audit Logging

- **Default**: Enabled
- **Configuration**: `RESEARCH_API_AUDIT_LOGGING` environment variable
- **Log format**: JSON entries in application log with `[RESEARCH_API_AUDIT]` prefix

### Request Validation

- **Default**: 10KB maximum request size
- **Configuration**: `RESEARCH_API_MAX_REQUEST_SIZE` environment variable
- Field validation via Pydantic models

## Enabling Full Mode

### Development

Full mode is enabled by default in development:

```bash
# Explicitly set development environment
export AUTOPACK_ENV=development
```

### Production (Not Recommended)

To enable full mode in production:

```bash
# Option 1: Explicit mode
export RESEARCH_API_MODE=full

# Option 2: Legacy flag
export RESEARCH_API_ENABLED=true
```

**Warning**: Enabling full mode in production exposes all research endpoints. Ensure proper authentication and network controls are in place.

## Safety Gate Configuration

```bash
# Rate limiting (requests per minute)
export RESEARCH_API_RATE_LIMIT=30

# Maximum request body size (bytes)
export RESEARCH_API_MAX_REQUEST_SIZE=10240

# Audit logging
export RESEARCH_API_AUDIT_LOGGING=true
```

## Checking Current Mode

Query the `/research/mode` endpoint:

```bash
curl http://localhost:8000/api/research/mode
```

Response example:

```json
{
  "mode": "full",
  "bootstrap_endpoints_enabled": true,
  "full_endpoints_enabled": true,
  "bootstrap_available": true,
  "safety_gates": {
    "rate_limit_requests_per_minute": 30,
    "max_request_size_bytes": 10240,
    "audit_logging_enabled": true
  }
}
```

## Resolution Path

The quarantine system was implemented to address:

1. **IMP-RES-006**: Initial bootstrap mode implementation
2. **IMP-RES-010**: Full mode enablement with safety gates

### Future Considerations

- Add authentication/authorization for full mode endpoints
- Implement per-user rate limiting
- Add request tracing for debugging
- Consider Redis-based rate limiting for multi-instance deployments

## Related Documentation

- [Research System Architecture](../architecture/RESEARCH_SYSTEM.md)
- [API Reference](../api/RESEARCH_API.md)
- [Security Guidelines](../security/API_SECURITY.md)
