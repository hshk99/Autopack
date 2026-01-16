# Phase Naming Convention

## Historical Naming Collision: "Phase 6"

Two distinct systems were both called "Phase 6" in BUILD_HISTORY.md, creating confusion about which work belongs to which system.

| System | BUILD Entry | Location | Purpose |
|--------|-------------|----------|---------|
| Intentions Framework v2 | BUILD-178 | src/autopack/intention_anchor/ | Pivot intentions, anchors, autonomy loop |
| Execution Hardening | BUILD-146 | src/autopack/executor/ | Failure recovery, retries, plan normalization |

### Details

#### Intentions Framework v2 (BUILD-178)
- **Schema**: IntentionAnchorV2 with 8 universal pivot intention types
- **Components**:
  - Gap taxonomy with 10 gap types
  - Plan proposer with governance classification
  - AutopilotController for autonomous execution
  - ParallelismPolicyGate for safe parallelism
- **Artifacts**: 4 JSON schemas in docs/schemas/
- **Status**: 100% complete as of 2026-01-06

#### Execution Hardening (BUILD-146)
- **Scope**: Production polish for DB-level idempotency enforcement
- **Features**:
  - Partial unique index on token_efficiency_metrics
  - Smoke test enhancements
  - Rollout checklist clarifications
- **Status**: 100% complete as of 2026-01-01

## Resolution

As of IMP-PHASE6-001, we use explicit names to avoid confusion:
- **Intentions Framework v2** (not "Phase 6 Intentions") - BUILD-178
- **Execution Hardening** (not "Phase 6 Hardening") - BUILD-146

## Going Forward

Recommendations:
1. Avoid using "Phase N" as system names. Use descriptive names instead.
2. When referring to these systems, use full names:
   - "Intentions Framework v2" instead of "Phase 6"
   - "Execution Hardening" instead of "Phase 6"
3. Reference docs/BUILD_HISTORY.md for historical context
4. Reference module docstrings for clarification (see intention_anchor/__init__.py, executor/__init__.py)

## References
- [BUILD_HISTORY.md](BUILD_HISTORY.md) - Contains detailed entries for BUILD-146 and BUILD-178
- [src/autopack/intention_anchor/__init__.py](../src/autopack/intention_anchor/__init__.py) - Intentions Framework v2 module
- [src/autopack/executor/__init__.py](../src/autopack/executor/__init__.py) - Execution Hardening module
