# Intention System Migration Guide (IMP-INTENT-003)

## Overview

Autopack has two intention systems:
- **v1 (Old)**: `ProjectIntentionManager` in `project_intention.py`
- **v2 (New)**: `IntentionAnchorV2` in `intention_anchor/v2.py`

**Status**: v1 is deprecated as of IMP-INTENT-003 and will be removed in a future release.

This guide helps you migrate from v1 to v2.

---

## Why Migrate?

**v2 advantages over v1**:
- ✅ **Universal pivot intentions**: Works for any project type
- ✅ **Explicit safety/risk sections**: `never_allow`, `requires_approval`, `risk_tolerance`
- ✅ **Evidence/verification gates**: `hard_blocks`, `required_proofs`, `verification_gates`
- ✅ **Governance/review policies**: Auto-approval rules, escalation paths
- ✅ **Schema-validated**: Validates against `docs/schemas/intention_anchor_v2.schema.json`
- ✅ **Better structured**: Pydantic models with type safety

**v1 limitations**:
- ❌ No safety/risk modeling
- ❌ No verification gates
- ❌ No governance policies
- ❌ Unstructured `intent_facts` and `constraints` fields

---

## Quick Migration

### Before (v1)

```python
from autopack.project_intention import ProjectIntentionManager

manager = ProjectIntentionManager(run_id=run_id, project_id=project_id)

intention = manager.create_intention(
    raw_input="Build a web scraper that extracts product prices",
    intent_facts=[
        "Must respect robots.txt",
        "Should cache results to minimize requests",
    ],
    non_goals=[
        "No distributed scraping",
        "No captcha solving",
    ],
    acceptance_criteria=[
        "Scraper extracts price within 5% accuracy",
        "Respects rate limits (1 req/sec)",
    ],
)

# Store in memory
manager.store_intention(intention)

# Retrieve for context injection
anchor_text = intention.intent_anchor
```

### After (v2)

```python
from autopack.intention_anchor.v2 import (
    IntentionAnchorV2,
    NorthStarIntention,
    SafetyRiskIntention,
    EvidenceVerificationIntention,
    ScopeBoundariesIntention,
)

intention = IntentionAnchorV2(
    project_id=project_id,

    # Desired outcomes and non-goals
    north_star=NorthStarIntention(
        desired_outcomes=[
            "Extract product prices with ≥95% accuracy",
            "Cache results to minimize HTTP requests",
        ],
        non_goals=[
            "Distributed scraping across multiple IPs",
            "CAPTCHA solving or evasion",
        ],
    ),

    # Safety constraints
    safety_risk=SafetyRiskIntention(
        never_allow=[
            "Ignore robots.txt directives",
            "Exceed site rate limits",
        ],
        requires_approval=[
            "Scraping sites without explicit robots.txt",
        ],
        risk_tolerance="low",
    ),

    # Verification gates
    evidence_verification=EvidenceVerificationIntention(
        hard_blocks=[
            "robots.txt compliance check",
            "Rate limit enforcement (≤1 req/sec)",
        ],
        required_proofs=[
            "Price accuracy test suite passing",
            "Rate limiter unit tests",
        ],
    ),

    # Scope boundaries
    scope_boundaries=ScopeBoundariesIntention(
        allowed_write_roots=["src/scraper", "tests/scraper"],
        protected_paths=["src/autopack/core"],
        network_allowlist=["api.example.com"],
    ),
)

# Store and render
from autopack.intention_anchor.storage import IntentionStorage
from autopack.intention_anchor.render import render_for_prompt

storage = IntentionStorage(workspace_root="/path/to/workspace")
storage.save(intention)

# Retrieve for context injection
anchor_text = render_for_prompt(intention, max_chars=2048)
```

---

## Field Mapping

| v1 Field | v2 Equivalent | Notes |
|----------|---------------|-------|
| `intent_anchor` | `north_star.desired_outcomes` | v2 uses structured outcomes instead of free text |
| `intent_facts` | `north_star.desired_outcomes` | Migrate facts to desired outcomes |
| `non_goals` | `north_star.non_goals` | Direct mapping |
| `acceptance_criteria` | `evidence_verification.verification_gates` | v2 adds hard_blocks and required_proofs |
| `constraints` | `scope_boundaries.*` or `safety_risk.*` | Split by type: scope vs safety |
| `toolchain_hypotheses` | _(removed)_ | Not used in v2; consider storing elsewhere |
| `open_questions` | _(removed)_ | Track in planning artifacts instead |

---

## Migration Steps

### 1. Detect Current Usage

Run the migration detector to find files using v1:

```python
from autopack.intention_anchor.migration import detect_intention_system_usage

usage = detect_intention_system_usage("/path/to/workspace")

print(f"Files using v1: {len(usage['old_system'])}")
print(f"Files using v2: {len(usage['new_system'])}")
print(f"Files using both (critical): {len(usage['both_systems'])}")
```

### 2. Generate Migration Report

```python
from autopack.intention_anchor.migration import generate_migration_report

report = generate_migration_report(
    workspace_root="/path/to/workspace",
    output_file="migration_report.md"
)
```

This creates a detailed report with:
- Files needing migration (sorted by priority)
- Code examples for each file
- Migration recommendations

### 3. Migrate Priority Files

**Priority order**:
1. **CRITICAL**: Files using both v1 and v2 (conflicts possible)
2. **HIGH**: Files using only v1 (deprecated)
3. **LOW**: Files already using v2 (no action)

### 4. Update Imports

**Before**:
```python
from autopack.project_intention import ProjectIntentionManager, ProjectIntention
```

**After**:
```python
from autopack.intention_anchor.v2 import IntentionAnchorV2, NorthStarIntention
from autopack.intention_anchor.storage import IntentionStorage
from autopack.intention_anchor.render import render_for_prompt
```

### 5. Update Data Structures

**v1 dict structure**:
```python
{
    "project_id": "web-scraper",
    "intent_anchor": "Build scraper with rate limiting",
    "intent_facts": ["Respect robots.txt", "Cache results"],
    "non_goals": ["No CAPTCHA solving"],
    "acceptance_criteria": ["95% accuracy", "1 req/sec limit"],
    "constraints": {"rate_limit": "1/sec"},
}
```

**v2 structure**:
```python
{
    "project_id": "web-scraper",
    "north_star": {
        "desired_outcomes": ["Build scraper with rate limiting", "Cache results"],
        "non_goals": ["CAPTCHA solving"],
    },
    "safety_risk": {
        "never_allow": ["Ignore robots.txt"],
        "risk_tolerance": "low",
    },
    "evidence_verification": {
        "hard_blocks": ["Rate limit: 1 req/sec"],
        "required_proofs": ["95% accuracy test suite"],
    },
}
```

### 6. Update Storage/Retrieval

**v1**:
```python
manager = ProjectIntentionManager(run_id=run_id)
manager.store_intention(intention)
retrieved = manager.retrieve_intention()
```

**v2**:
```python
storage = IntentionStorage(workspace_root=workspace_root)
storage.save(intention)
retrieved = storage.load(project_id=project_id)
```

### 7. Update Context Injection

**v1**:
```python
anchor_text = intention.intent_anchor
prompt = f"Project intention: {anchor_text}\n\n{task_description}"
```

**v2**:
```python
from autopack.intention_anchor.render import render_for_prompt

anchor_text = render_for_prompt(intention, max_chars=2048)
prompt = f"{anchor_text}\n\n{task_description}"
```

---

## Common Patterns

### Pattern 1: Simple Intent Facts → Desired Outcomes

**v1**:
```python
intention = manager.create_intention(
    raw_input="Build API client",
    intent_facts=[
        "Use requests library",
        "Support rate limiting",
        "Include retry logic",
    ],
)
```

**v2**:
```python
intention = IntentionAnchorV2(
    project_id=project_id,
    north_star=NorthStarIntention(
        desired_outcomes=[
            "Build API client using requests library",
            "Support configurable rate limiting",
            "Include exponential backoff retry logic",
        ],
    ),
)
```

### Pattern 2: Constraints → Scope Boundaries

**v1**:
```python
intention = manager.create_intention(
    raw_input="Refactor database layer",
    constraints={
        "allowed_paths": ["src/db"],
        "protected_paths": ["src/db/migrations"],
    },
)
```

**v2**:
```python
intention = IntentionAnchorV2(
    project_id=project_id,
    north_star=NorthStarIntention(
        desired_outcomes=["Refactor database layer for better testability"],
    ),
    scope_boundaries=ScopeBoundariesIntention(
        allowed_write_roots=["src/db"],
        protected_paths=["src/db/migrations"],
    ),
)
```

### Pattern 3: Acceptance Criteria → Verification Gates

**v1**:
```python
intention = manager.create_intention(
    raw_input="Add caching layer",
    acceptance_criteria=[
        "Cache hit rate > 80%",
        "Cache invalidation works correctly",
        "All tests pass",
    ],
)
```

**v2**:
```python
intention = IntentionAnchorV2(
    project_id=project_id,
    north_star=NorthStarIntention(
        desired_outcomes=["Add Redis-based caching layer"],
        success_signals=["Cache hit rate ≥80% in production"],
    ),
    evidence_verification=EvidenceVerificationIntention(
        verification_gates=[
            "Cache invalidation integration tests passing",
            "All unit and integration tests passing",
        ],
        required_proofs=[
            "Cache hit rate benchmark results",
        ],
    ),
)
```

---

## Testing After Migration

### 1. Validate Schema

```python
from autopack.schema_validation import validate_intention_anchor_v2

is_valid = validate_intention_anchor_v2(intention.model_dump())
assert is_valid, "Intention failed v2 schema validation"
```

### 2. Compare Rendered Output

```python
from autopack.intention_anchor.render import render_for_prompt

v2_anchor = render_for_prompt(intention, max_chars=2048)
assert len(v2_anchor) <= 2048, "Anchor exceeds size limit"
```

### 3. Test Storage Round-Trip

```python
from autopack.intention_anchor.storage import IntentionStorage

storage = IntentionStorage(workspace_root="/tmp/test")
storage.save(intention)
loaded = storage.load(project_id=intention.project_id)

assert loaded.model_dump() == intention.model_dump()
```

---

## Deprecation Timeline

| Phase | Timeline | Action |
|-------|----------|--------|
| **Phase 1** (Current) | IMP-INTENT-003 | Deprecation warnings added, migration guide published |
| **Phase 2** | Next release | v1 marked deprecated in docs, automated migration tools |
| **Phase 3** | 2-3 releases later | v1 removed after all internal usage migrated |

---

## FAQ

### Q: Can I use both v1 and v2 in the same codebase?

**A**: Yes, but it's **not recommended**. If the migration detector finds files using both systems (`both_systems` list), migrate those files immediately to avoid conflicts.

### Q: What if I have custom fields in v1?

**A**: v2 uses Pydantic models with `extra="forbid"`, so custom fields will cause validation errors. Options:
1. Map custom fields to existing v2 sections
2. Store custom data in `metadata` dict (if using IntentionStorage)
3. Keep custom data in separate artifacts

### Q: How do I migrate `toolchain_hypotheses` and `open_questions`?

**A**: These fields don't exist in v2:
- `toolchain_hypotheses`: Store in planning artifacts or comments
- `open_questions`: Track in issue tracker or planning collection

### Q: Will v1 intentions still work during migration?

**A**: Yes. The system will show deprecation warnings but remain functional during the migration period (Phase 1-2). However, migrate as soon as possible to avoid breaking changes in Phase 3.

---

## Getting Help

- **Migration detector**: `python -m autopack.intention_anchor.migration`
- **Schema reference**: `docs/schemas/intention_anchor_v2.schema.json`
- **Code examples**: `tests/intention_anchor/test_v2.py`
- **Issues**: Report migration issues with tag `IMP-INTENT-003`

---

*Generated as part of IMP-INTENT-003: Intention System Consolidation*
