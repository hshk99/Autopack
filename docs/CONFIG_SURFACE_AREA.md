# Config Surface Area Index

**Last Updated**: 2026-01-09
**Purpose**: Document which config files are consumed at runtime vs CI-only vs future/unused.

---

## Overview

All config files live under `config/`. This document tracks their usage status to prevent "two truths" drift (agents asking "is this canonical?").

---

## Config File Inventory

### Runtime-Critical (consumed by `src/autopack/`)

| File | Subsystem | Description |
|------|-----------|-------------|
| `models.yaml` | Model routing, LLM service, cost estimation | Primary model catalog; defines aliases, routing rules, token caps, tool models |
| `pricing.yaml` | Model catalog, cost estimation | Per-model token pricing; used for budget tracking |
| `memory.yaml` | Memory service, goal drift, Qdrant | Vector store config; Qdrant connection; goal drift thresholds |
| `baseline_policy.yaml` | Gap scanner, risk scorer | Baseline security/governance policy; gap detection signals |
| `protection_and_retention_policy.yaml` | Storage optimizer, risk scorer | Data retention rules; protected path patterns |
| `feature_flags.yaml` | Feature flag registry | Runtime feature toggles; single source of truth for flags |
| `diagnostics.yaml` | Diagnostics agent | Diagnostic collection settings; thresholds |

### CI/Scripts-Only (consumed by `scripts/` or `tests/`)

| File | Consumer | Description |
|------|----------|-------------|
| `doc_link_check_ignore.yaml` | `scripts/check_doc_links.py` | Allowlist for doc link checker; ignores known-broken links |
| `doc_link_triage_overrides.yaml` | `scripts/doc_links/apply_triage.py` | Triage decisions for doc links; remediation overrides |
| `sot_registry.json` | SOT drift tests, CI | Source-of-truth file registry; enforced by doc contract tests |
| `todo_policy.yaml` | `tests/ci/test_todo_quarantine_policy.py` | TODO quarantine policy; defines allowed TODO locations |
| `tidy_scope.yaml` | Tidy system scripts | Tidy workspace scope config; directories to include/exclude |

### Hybrid (Runtime + Scripts)

| File | Consumers | Description |
|------|-----------|-------------|
| `project_types.yaml` | `scripts/launch_claude_agents.py` | Project type definitions; used for agent spawning |
| `storage_policy.yaml` | `src/autopack/storage_optimizer/policy.py` | Storage optimization rules |
| `project_ruleset_Autopack.json` | Strategy engine | Project-specific rules; used by tidy and strategy subsystems |

### Templates (Not Loaded at Runtime)

| File | Purpose |
|------|---------|
| `templates/` | Template files for new configs; not directly consumed |

---

## Usage Notes

### Adding a New Config File

1. **Decide the scope**: Runtime, CI-only, or hybrid?
2. **Add to this index** before merging
3. **Add CI validation** if runtime-critical (see `tests/ci/` for examples)
4. **Document the schema** in the config file itself (YAML comments)

### Removing/Archiving a Config File

1. **Search for references**: `grep -r "filename" src/ scripts/ tests/`
2. **Remove references** before archiving
3. **Move to `archive/config/`** (not delete) for audit trail
4. **Update this index**

### Previously Removed (for reference)

The following configs were mentioned in historical gap analysis but no longer exist:

- `feature_catalog.yaml` - archived/removed
- `stack_profiles.yaml` - archived/removed
- `tools.yaml` - archived/removed

---

## Enforcement

- `tests/ci/test_docker_bootability.py` validates runtime-critical configs exist
- `tests/ci/test_feature_flags_registry.py` enforces feature flag consistency
- `tests/ci/test_sot_registry_consistency.py` enforces SOT registry integrity
- `tests/ci/test_todo_quarantine_policy.py` enforces TODO policy existence
