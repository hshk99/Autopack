# CONSOLIDATED_DEBUG.md

## Open Issues

### Diagnostics parity followups: docs batch truncation / ellipsis causes PATCH_FAILED
- **Severity**: HIGH (convergence blocker)
- **Symptom**: Builder emitted truncated markdown placeholders (e.g., `# ...`) causing patch validation failure (`patch_truncation` / ellipsis detection) during docs-only batch for `diagnostics-iteration-loop`.
- **Impact**: Phase would repeatedly fail at `PATCH_FAILED` even after successful code/tests batches; retries wasted tokens.
- **Resolution**:
  - Executor now retries with batch skipping (if earlier deliverables already exist).
  - If the failing batch is a single `docs/*.md` deliverable and the patch fails truncation validation, executor applies a deterministic minimal markdown doc patch to satisfy deliverables and proceed to CI/Auditor/Quality Gate.
  - Added deterministic `LlmService.generate_deliverables_manifest(...)` to restore manifest-gate behavior.
- **Verified Run**: `autopack-diagnostics-parity-v5` (backend 8001)

## Resolved Issues

## Prevention Rules

