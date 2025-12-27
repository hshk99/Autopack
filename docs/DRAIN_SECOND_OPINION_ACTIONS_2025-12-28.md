## Drain second-opinion: findings + actions (2025-12-28)

This document is the **SOT-safe** capture of the second-opinion review and what we changed as a result.
It exists under `docs/` so Autopack tidy does not delete it as an ad-hoc artifact.

### Key findings (from `AUTOPACK_DRAIN_SECOND_OPINION_REVIEW.md`)

- **README mismatch**: README contained historical claims like “all core tests passing” and implied “CI green” semantics, while real draining runs CI with an existing failing baseline and uses **delta-based completion**.
- **Collector/import errors**: pytest **exitcode=2** + failed collectors are a hard failure mode and must always block completion.
- **No-op ambiguity**: “no operations / no-op apply” needs stronger instrumentation and (optionally) gating to avoid false completion.
- **Legacy `/runs/{run_id}` 500**: legacy `Phase.scope` values stored as strings can cause API response validation failures (fixed earlier in this session).

### Actions taken in response (commits)

- **Clarified completion policy in README** (delta-based gating; collection errors block):
  - Commit: `d015d67f`
  - File: `README.md`

- **Add apply stats to phase summaries** (forensic visibility into patch vs structured edits and no-op cases):
  - Commit: `b8e576b2`
  - Files: `src/autopack/autonomous_executor.py`, `src/autopack/file_layout.py`

- **Tighten PhaseFinalizer gating**:
  - **Block on any new persistent regression severity** (low/medium/high/critical) rather than warn-only for medium.
  - **Validate deliverables by workspace existence** (do not depend on `applied_files`, which can be empty/ambiguous for some apply modes).
  - Commit: (this change)
  - Files: `src/autopack/phase_finalizer.py`, tests updated (`tests/test_phase_finalizer*.py`)

### Recommended next steps (not implemented here)

- **No-op guard**: if `apply_stats` indicates no changes and required deliverables are missing, block deterministically (with an explicit `allow_noop` escape hatch).
- **Collector error digest**: persist top collector failure signatures into phase summaries to reduce log hunting.


