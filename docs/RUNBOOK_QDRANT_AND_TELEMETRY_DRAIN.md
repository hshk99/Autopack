## Qdrant: make Autopack “work as intended” (no recurring connection errors)

Autopack’s vector memory can use **Qdrant** (preferred) but should **continue operating** without it (FAISS fallback).

### Recommended (most reliable): run Qdrant via Docker Compose

- Ensure `docker-compose.yml` contains a `qdrant` service (it does as of this change).
- Autopack can now auto-start Qdrant when configured (see “Autostart” below), but you can also start it manually:

```bash
docker compose up -d qdrant
```

Autopack will connect to:
- **Outside docker**: `localhost:6333`
- **Inside docker compose network**: `qdrant:6333` (set in compose env)

### If you don’t want Qdrant (offline/dev)

Disable Qdrant explicitly:
- **Env**: `AUTOPACK_USE_QDRANT=0`
- Or set `use_qdrant: false` in `config/memory.yaml`

### Autostart (no human intervention)

If Qdrant is configured and the host is `localhost`, Autopack will attempt to:
- start Qdrant via `docker compose up -d qdrant` (preferred), else
- start a standalone container named `autopack-qdrant`
- wait briefly for port readiness before continuing

Controls:
- `config/memory.yaml` → `qdrant.autostart: true`
- Env override: `AUTOPACK_QDRANT_AUTOSTART=0|1`
- Wait time: `qdrant.autostart_timeout_seconds` or env `AUTOPACK_QDRANT_AUTOSTART_TIMEOUT`

### If you require Qdrant (hard fail)

Set:
- `config/memory.yaml` → `qdrant.require: true`
- Optionally `qdrant.fallback_to_faiss: false`

## Draining 160 queued phases safely (telemetry collection)

### Goals
- Keep success rate high (avoid timeouts/truncation)
- Avoid wasting tokens on known-bad infra
- Make progress resumable

### Strategy

- **Batch execution**: run in chunks (e.g., 10–25 phases per batch) using `--max-iterations`.
- **Stop early on systemic failures**: use `--stop-on-first-failure` for the first small batch, then relax once stable.
- **Prefer longer timeouts** on CI/test-heavy phases (your earlier analysis suggests 900–1200s when optimizing for quality).

### Suggested command patterns

First “stability” batch (fast feedback):

```bash
python -m autopack.autonomous_executor --run-id <RUN_ID> --max-iterations 5 --stop-on-first-failure
```

Then “throughput” batches:

```bash
python -m autopack.autonomous_executor --run-id <RUN_ID> --max-iterations 25
```

### What to tell the other Cursor (operator checklist)

- Pull latest main.
- Run a quick preflight:
  - Confirm Qdrant intent:
    - If using Qdrant: start `qdrant` (`docker compose up -d qdrant`)
    - If not: set `AUTOPACK_USE_QDRANT=0`
- Run batches, not all 160 at once.
- If phases commonly exit with timeout (code 143), increase timeout strategy and/or focus on success=True & truncated=False samples for telemetry validation.
