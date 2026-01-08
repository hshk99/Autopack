# Feature Flags Registry

> **Single Source of Truth**: All feature flags are defined in `src/autopack/feature_flags.py`
>
> **Contract**: P1-FLAGS-001 - No "mystery flags"; all AUTOPACK_ENABLE_* must be registered

## Quick Reference

| Flag | Default | Risk | Scope | Description |
|------|---------|------|-------|-------------|
| `AUTOPACK_ENABLE_PHASE6_METRICS` | `false` | SAFE | METRICS | Enable Phase 6 metrics collection and reporting |
| `AUTOPACK_ENABLE_CONSOLIDATED_METRICS` | `false` | SAFE | API | Enable consolidated metrics endpoint (/consolidated-metrics) |
| `AUTOPACK_ENABLE_FAILURE_HARDENING` | `false` | CAUTION | RUNTIME | Enable failure hardening logic in autonomous executor |
| `AUTOPACK_ENABLE_INTENTION_CONTEXT` | `false` | CAUTION | RUNTIME | Enable intention context in prompts for better coherence |
| `AUTOPACK_ENABLE_PLAN_NORMALIZATION` | `false` | CAUTION | RUNTIME | Enable plan normalization for consistent execution |
| `AUTOPACK_ENABLE_MEMORY` | `false` | EXTERNAL | RUNTIME | Enable vector memory service (requires Qdrant) |
| `AUTOPACK_ENABLE_SOT_MEMORY_INDEXING` | `false` | EXTERNAL | RUNTIME | Enable SOT document memory indexing |
| `AUTOPACK_ENABLE_RESEARCH_API` | `false` | CAUTION | API | Enable /research/* API endpoints (uses mock in-memory state) |
| `AUTOPACK_ENABLE_PR_APPROVAL` | `false` | EXTERNAL | RUNTIME | Enable PR approval pipeline for Telegram-based reviews |

## Risk Levels

- **SAFE**: No external side effects, safe to enable in any environment
- **CAUTION**: May affect runtime behavior, review before enabling
- **EXTERNAL**: Has external side effects (API calls, DB writes, etc.)

## Scopes

- **RUNTIME**: Affects runtime execution behavior
- **API**: Affects API endpoint availability or behavior
- **TOOLING**: Affects tooling/scripts only
- **METRICS**: Affects metrics collection

## Production Posture

**Default posture for production**: All flags are OFF by default.

The `get_production_posture()` function returns the recommended production configuration:
- EXTERNAL risk flags: Always OFF
- API scope flags: Always OFF (explicit opt-in required)
- Other flags: Use registered defaults

## Usage

### Checking if a flag is enabled

```python
from autopack.feature_flags import is_enabled

if is_enabled("AUTOPACK_ENABLE_PHASE6_METRICS"):
    collect_phase6_metrics()
```

### Getting flag metadata

```python
from autopack.feature_flags import get_flag

flag = get_flag("AUTOPACK_ENABLE_MEMORY")
if flag:
    print(f"Risk: {flag.risk}, Scope: {flag.scope}")
```

### Environment Override

Flags can be overridden via environment variables:

```bash
# Enable a flag
export AUTOPACK_ENABLE_PHASE6_METRICS=true

# Disable a flag (even if default is true)
export AUTOPACK_ENABLE_MEMORY=false
```

Valid true values: `true`, `1`, `yes` (case-insensitive)
Valid false values: `false`, `0`, `no` (case-insensitive)

## Adding New Flags

1. Add the flag to `FEATURE_FLAGS` in `src/autopack/feature_flags.py`:

```python
"AUTOPACK_ENABLE_NEW_FEATURE": FeatureFlag(
    name="AUTOPACK_ENABLE_NEW_FEATURE",
    default=False,
    description="Brief description of what this flag enables",
    risk=RiskLevel.CAUTION,  # Choose appropriate risk level
    scope=Scope.RUNTIME,     # Choose appropriate scope
    doc_url="docs/RELEVANT_DOC.md",  # Optional
    owner="your-team",       # Optional, defaults to autopack-core
),
```

2. Use `is_enabled()` in code:

```python
from autopack.feature_flags import is_enabled

if is_enabled("AUTOPACK_ENABLE_NEW_FEATURE"):
    # Feature-gated code
```

3. Update this document (or run script to regenerate)

## CI Enforcement

Contract tests in `tests/ci/test_feature_flags_registry.py` ensure:
- All `AUTOPACK_ENABLE_*` in code are registered
- All flags have required metadata (name, default, description, risk, scope)
- EXTERNAL risk flags default to False
- Production posture is conservative

---

*This document is the canonical reference for feature flags. The source of truth is `src/autopack/feature_flags.py`.*
