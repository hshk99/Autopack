## Multi-Agent Planning Kickoff (Hardening/QA/Deploy)

Use this prompt to launch parallel agents (research, analysis, question-collection) for any new project. The agents should propose relevant phases from `templates/hardening_phases.json` and gather answers to the checklist below.

### Roles
- Research agent: Gather domain-specific constraints (auth provider, storage choice, compliance, perf targets).
- Analysis agent: Map constraints to hardening phases; flag risks (security/perf/data).
- Question agent: Ask missing-info questions to unblock planning (infra, data volume, SLAs).
- Scribe: Consolidate outputs into a phase shortlist with rationale.

### Inputs
- Project slug and feature set (e.g., auth, search, batch/upload, frontend, deploy).
- Existing phase plan (if any) and WHATS_LEFT_TO_BUILD (if any).
- Template phases: `templates/hardening_phases.json`
- Defaults: `templates/phase_defaults.json`

### Checklist (agents should answer)
- Auth: provider, RBAC needs, reset/verification, protected routes, token/secret handling.
- Storage: local/S3, presigned URLs, retention, backup/restore.
- Upload/Batch: file types/size limits, safety scanning, job queue needs, observability (status/cancel/retry).
- Search: relevance tuning, filters/facets, pagination, export needs, perf targets.
- Security: rate limits, CORS/headers, secret/config audit.
- Perf: latency targets for search/batch, load expectations, indexing/caching needs.
- Deploy: docker/deploy/sh smoke, target env(s), health/smoke requirements.
- Testing: E2E scope (auth/upload/search/batch/export/logout), logging/metrics expectations.
- Docs: what must be documented (flows, deploy steps, diagrams).

### Output (for review)
- Recommended phases (ids from template) with rationale and any blockers/questions.
- Missing inputs (with owner/questions) to finalize scope.
- Any phase-specific scopes or safety flags to set (e.g., structured_edit, log_on_success).

