# Compose Stack Smoke Tests (Item 1.7)

This directory contains smoke tests that validate the docker-compose topology for Autopack.

## Purpose

These tests catch "integration drift" issues where:
- Services work in isolation but fail when composed together
- nginx routing configuration breaks
- API prefix preservation fails
- Database/Qdrant connectivity issues arise

## What's Tested

1. **Nginx Routing**
   - Static nginx health endpoint (`/nginx-health`)
   - Proxied backend health endpoint (`/health`)

2. **Auth Route Preservation**
   - Validates `/api/auth/*` prefix is preserved (not stripped)
   - Ensures nginx routes to backend's `/api/auth` router correctly

3. **Backend Readiness**
   - Backend API responds
   - Backend can connect to PostgreSQL
   - Backend can connect to Qdrant (or reports it as disabled)

4. **Database Connectivity**
   - PostgreSQL container is healthy
   - `pg_isready` check passes

5. **Qdrant Connectivity**
   - Qdrant container is running
   - Qdrant HTTP API is reachable

## Running Smoke Tests

### Option 1: Shell Script (Recommended for Manual Testing)

The shell script manages the complete lifecycle:

```bash
# Run smoke tests (starts compose, tests, then cleans up)
./scripts/smoke_test_compose.sh

# Keep compose stack running after tests (for debugging)
./scripts/smoke_test_compose.sh --no-cleanup
```

### Option 2: Python Script (Standalone)

```bash
# Start compose stack manually
docker compose up -d --wait

# Run Python smoke test
python scripts/smoke_test_compose.py

# Cleanup
docker compose down -v
```

### Option 3: Pytest Integration Tests

```bash
# Start compose stack
docker compose up -d --wait

# Run pytest smoke tests
pytest tests/integration/test_compose_smoke.py -v

# Or run specific test class
pytest tests/integration/test_compose_smoke.py::TestNginxRouting -v

# Cleanup
docker compose down -v
```

## CI Integration

Smoke tests run automatically:
- **Weekly**: Sunday at 06:00 UTC (scheduled)
- **Manual**: Via GitHub Actions workflow_dispatch

See [.github/workflows/compose-smoke.yml](../../.github/workflows/compose-smoke.yml)

## Troubleshooting

### Tests fail with "connection refused"

The compose stack may not be running:
```bash
docker compose ps  # Check service status
docker compose logs backend  # Check backend logs
```

### Tests fail with timeout

Services may be slow to start:
```bash
# Wait longer for services
docker compose up -d --wait --wait-timeout 180

# Check service health
docker compose ps
```

### Database connectivity fails

Check database container:
```bash
docker compose logs db
docker compose exec db pg_isready -U autopack
```

### Qdrant connectivity fails

Qdrant is optional - failures are warnings not errors. Check:
```bash
docker compose logs qdrant
curl http://localhost:6333/  # Should return 200
```

## Adding New Smoke Tests

When adding smoke tests:

1. **Keep tests lightweight** - Smoke tests should run in < 2 minutes
2. **Test integration points** - Focus on service boundaries, not unit logic
3. **Use appropriate assertions** - Distinguish hard failures from warnings
4. **Document expectations** - Add comments explaining what "healthy" means

Example:
```python
def test_new_service_integration(self, compose_stack):
    """Test that new service X can reach service Y."""
    response = requests.get("http://localhost:8000/service-x/ping-y", timeout=10)

    assert response.status_code == 200, "Service X cannot reach Y"
    data = response.json()
    assert data.get("status") == "connected"
```

## Related Documentation

- [docker-compose.yml](../../docker-compose.yml) - Compose configuration
- [nginx.conf](../../nginx.conf) - Nginx routing rules
- [IMPROVEMENT_GAPS_CURRENT_2026-01-12.md](../../docs/reports/IMPROVEMENT_GAPS_CURRENT_2026-01-12.md) - Item 1.7
