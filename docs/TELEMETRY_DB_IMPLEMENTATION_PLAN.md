# Telemetry DB Persistence Implementation Plan

## Status: Ready for Implementation

**Priority**: P0 - Required for real validation

---

## Implementation Summary

Add database persistence for TokenEstimationV2 telemetry events to enable real validation with actual deliverable paths.

---

## Changes Required

### 1. Add Helper Function to anthropic_clients.py

**Location**: After imports, around line 50

```python
def _write_token_estimation_v2_telemetry(
    run_id: str,
    phase_id: str,
    category: str,
    complexity: str,
    deliverables: List[str],
    predicted_output_tokens: int,
    actual_output_tokens: int,
    selected_budget: int,
    success: bool,
    truncated: bool,
    stop_reason: Optional[str],
    model: str,
) -> None:
    """Write TokenEstimationV2 event to database for validation.

    Feature flag: TELEMETRY_DB_ENABLED (default: false for backwards compat)
    """
    import os
    import json
    from autopack.database import SessionLocal
    from autopack.models import TokenEstimationV2Event

    # Feature flag check
    if not os.environ.get("TELEMETRY_DB_ENABLED", "").lower() in ["1", "true", "yes"]:
        return

    try:
        # Calculate metrics
        if actual_output_tokens > 0 and predicted_output_tokens > 0:
            denom = (abs(actual_output_tokens) + abs(predicted_output_tokens)) / 2
            smape = abs(actual_output_tokens - predicted_output_tokens) / max(1, denom) * 100
            waste_ratio = predicted_output_tokens / actual_output_tokens
            underestimated = actual_output_tokens > predicted_output_tokens
        else:
            smape = None
            waste_ratio = None
            underestimated = None

        # Sanitize deliverables (max 20, truncate long paths)
        deliverables_clean = []
        for d in deliverables[:20]:  # Cap at 20
            if len(str(d)) > 200:
                deliverables_clean.append(str(d)[:197] + "...")
            else:
                deliverables_clean.append(str(d))

        deliverables_json = json.dumps(deliverables_clean)

        # Write to DB
        session = SessionLocal()
        try:
            event = TokenEstimationV2Event(
                run_id=run_id,
                phase_id=phase_id,
                category=category,
                complexity=complexity,
                deliverable_count=len(deliverables),
                deliverables_json=deliverables_json,
                predicted_output_tokens=predicted_output_tokens,
                actual_output_tokens=actual_output_tokens,
                selected_budget=selected_budget,
                success=success,
                truncated=truncated,
                stop_reason=stop_reason,
                model=model,
                smape_percent=int(smape) if smape is not None else None,
                waste_ratio=int(waste_ratio * 100) if waste_ratio is not None else None,  # Store as percentage
                underestimated=underestimated,
            )
            session.add(event)
            session.commit()
        finally:
            session.close()
    except Exception as e:
        # Don't fail the build on telemetry errors
        logger.warning(f"[TokenEstimationV2] Failed to write DB telemetry: {e}")
```

### 2. Call Helper from Logging Sites

**Location**: Lines 682-697 (after `logger.info` call)

```python
# Existing logger.info call stays
logger.info(
    "[TokenEstimationV2] predicted_output=%s actual_output=%s smape=%.1f%% ...",
    ...
)

# ADD THIS: Write to DB for validation
_write_token_estimation_v2_telemetry(
    run_id=phase_spec.get("run_id", "unknown"),
    phase_id=phase_spec.get("phase_id", "unknown"),
    category=task_category or "implementation",
    complexity=complexity,
    deliverables=deliverables if isinstance(deliverables, list) else [],
    predicted_output_tokens=predicted_output_tokens,
    actual_output_tokens=actual_out,
    selected_budget=token_selected_budget or phase_spec.get("metadata", {}).get("token_prediction", {}).get("selected_budget", 0),
    success=getattr(result, "success", False),
    truncated=was_truncated_local,
    stop_reason=stop_reason_local,
    model=model,
)
```

**Location**: Lines 698-711 (fallback path)

```python
# Existing logger.info call stays
logger.info(
    "[TokenEstimationV2] predicted_output=%s actual_total=%s ...",
    ...
)

# ADD THIS: Write to DB (fallback case)
_write_token_estimation_v2_telemetry(
    run_id=phase_spec.get("run_id", "unknown"),
    phase_id=phase_spec.get("phase_id", "unknown"),
    category=task_category or "implementation",
    complexity=complexity,
    deliverables=deliverables if isinstance(deliverables, list) else [],
    predicted_output_tokens=predicted_output_tokens,
    actual_output_tokens=result.tokens_used,  # Using total tokens as fallback
    selected_budget=token_selected_budget or phase_spec.get("metadata", {}).get("token_prediction", {}).get("selected_budget", 0),
    success=getattr(result, "success", False),
    truncated=False,  # Unknown in fallback
    stop_reason=None,
    model=model,
)
```

---

## Validation Script

Create `scripts/export_token_estimation_telemetry.py`:

```python
"""
Export TokenEstimationV2 telemetry from database to NDJSON for analysis.
"""
import json
from autopack.database import SessionLocal
from autopack.models import TokenEstimationV2Event

def main():
    session = SessionLocal()
    try:
        events = session.query(TokenEstimationV2Event).order_by(TokenEstimationV2Event.timestamp.desc()).all()

        print(f"# TokenEstimationV2 Telemetry Export")
        print(f"# Total events: {len(events)}")
        print()

        for event in events:
            deliverables = json.loads(event.deliverables_json)
            record = {
                "run_id": event.run_id,
                "phase_id": event.phase_id,
                "timestamp": event.timestamp.isoformat(),
                "category": event.category,
                "complexity": event.complexity,
                "deliverable_count": event.deliverable_count,
                "deliverables": deliverables,
                "predicted_output_tokens": event.predicted_output_tokens,
                "actual_output_tokens": event.actual_output_tokens,
                "selected_budget": event.selected_budget,
                "success": event.success,
                "truncated": event.truncated,
                "stop_reason": event.stop_reason,
                "model": event.model,
                "smape_percent": event.smape_percent,
                "waste_ratio": event.waste_ratio / 100.0 if event.waste_ratio else None,
                "underestimated": event.underestimated,
            }
            print(json.dumps(record))
    finally:
        session.close()

if __name__ == "__main__":
    main()
```

---

## Update replay_telemetry.py

Replace synthetic deliverables generation:

```python
# OLD (line 66):
deliverables = [f"src/file{j}.py" for j in range(sample['deliverable_count'])]

# NEW:
# Load real deliverables from DB
session = SessionLocal()
try:
    event = session.query(TokenEstimationV2Event).filter(
        TokenEstimationV2Event.phase_id == sample['phase_id']
    ).first()

    if event and event.deliverables_json:
        deliverables = json.loads(event.deliverables_json)
    else:
        # Fallback to synthetic if not found
        deliverables = [f"src/file{j}.py" for j in range(sample['deliverable_count'])]
        print(f"WARNING: No deliverables found for {sample['phase_id']}, using synthetic")
finally:
    session.close()
```

---

## Testing

### 1. Enable telemetry DB

```bash
export TELEMETRY_DB_ENABLED=1
```

### 2. Run a test phase

```bash
PYTHONUTF8=1 PYTHONPATH=src TELEMETRY_DB_ENABLED=1 python -m autopack.autonomous_executor --run-id test-run
```

### 3. Verify data written

```bash
PYTHONUTF8=1 PYTHONPATH=src python -c "
from autopack.database import SessionLocal
from autopack.models import TokenEstimationV2Event
session = SessionLocal()
count = session.query(TokenEstimationV2Event).count()
print(f'TokenEstimationV2 events in DB: {count}')
if count > 0:
    latest = session.query(TokenEstimationV2Event).order_by(TokenEstimationV2Event.timestamp.desc()).first()
    print(f'Latest event: {latest.phase_id}, {latest.category}/{latest.complexity}, {latest.deliverable_count} deliverables')
session.close()
"
```

### 4. Export telemetry

```bash
PYTHONUTF8=1 PYTHONPATH=src python scripts/export_token_estimation_telemetry.py > telemetry_export.ndjson
```

### 5. Re-run validation with real deliverables

```bash
PYTHONUTF8=1 PYTHONPATH=src python scripts/replay_telemetry.py --source db
```

---

## Success Criteria

- ✅ TokenEstimationV2 events written to DB with deliverables
- ✅ Feature flag works (disabled by default)
- ✅ Export script produces NDJSON with real deliverable paths
- ✅ Replay validation uses real deliverables instead of synthetic
- ✅ No build failures due to telemetry errors (try/except wrapper)

---

## Next Steps After Implementation

1. Enable telemetry DB for production runs
2. Collect 30-50 stratified samples organically
3. Re-run validation with real deliverables
4. Update BUILD-129 Phase 3 status from "validation incomplete" to "validated on real data"

---

**Status**: Implementation plan ready. Requires manual code changes to `src/autopack/anthropic_clients.py` due to file size (2980 lines).
