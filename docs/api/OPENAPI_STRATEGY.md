# OpenAPI Strategy (BUILD-191)

**Status**: Canonical
**Decision Date**: 2026-01-08
**Decision Source**: IMPROVEMENTS_GAP_ANALYSIS.md section 0.3

## Strategy

**OpenAPI is runtime-canonical**: The OpenAPI specification is generated at runtime by FastAPI and served at `/openapi.json`. It is NOT checked into git.

## Rationale

1. **Single source of truth**: FastAPI automatically generates OpenAPI from endpoint decorators. Checking in a separate `openapi.json` would create "two truths" that can drift.

2. **Determinism**: The runtime OpenAPI always reflects the actual deployed API. A checked-in spec could be stale.

3. **CI verification**: CI exports OpenAPI as a build artifact (not committed) for external consumers who need a static copy.

## Access Points

### Runtime (Canonical)

| Endpoint | Description |
|----------|-------------|
| `GET /openapi.json` | Full OpenAPI 3.0 specification |
| `GET /docs` | Swagger UI interactive documentation |
| `GET /redoc` | ReDoc documentation |

### CI Artifacts

OpenAPI is exported as a CI artifact during the `docs-sot-integrity` job. This artifact:
- Is NOT checked into git
- Is regenerated on every CI run
- Can be downloaded from GitHub Actions for external tooling

## Contract Tests

The following contract tests verify OpenAPI generation:

1. **`tests/docs/test_openapi_strategy.py`**: Verifies:
   - Runtime OpenAPI is accessible at `/openapi.json`
   - Schema includes required metadata (title, version, paths)
   - No checked-in `docs/api/openapi.json` exists

## What NOT to Do

- Do NOT check in `openapi.json` to git
- Do NOT create `docs/api/openapi.json` as a committed file
- Do NOT use checked-in OpenAPI as the source of truth

## Related Files

- `src/autopack/main.py`: FastAPI app with OpenAPI generation
- `.github/workflows/ci.yml`: CI job that exports OpenAPI artifact
- `tests/docs/test_openapi_strategy.py`: Contract tests
