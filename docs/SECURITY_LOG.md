# Security Log (Append-Only)

**Purpose**: Durable record of security policy changes, baseline events, and verification milestones.
**Format**: Append-only (newest entries at top).
**Audience**: Future maintainers, auditors, incident responders.

---

## 2026-01-05: Documentation Drift Detection (Signal Only, Non-Blocking)

**Event**: Doc update hook (`scripts/update_docs.py --check`) reports dashboard-related drift.

**Hook Findings**:
- Dashboard section missing from README
- Architecture diagram needs LlmService mention
- README should mention dashboard in status

**Decision**: Treat as **signal only** (not enforced via CI contracts).

**Rationale**:
- README is intentionally slim (principle: avoid doc bloat)
- Dashboard is working code but not yet production-critical
- Doc contracts already exist for critical invariants (see `tests/docs/`)
- Adding new doc contracts would create ongoing maintenance burden

**Status**: Acknowledged but not acted upon.
- If dashboard becomes production-critical, revisit README mention
- If drift causes user confusion, add minimal mention (not full section)
- Architecture diagram updates are aspirational (not enforced)

**Follow-up Trigger**: User feedback about missing dashboard documentation or production promotion of dashboard

**Owner**: Documentation team
**Next Review**: Q2 2026 or on user feedback

---

## 2026-01-05: Requirements Regeneration Policy (Linux/CI Canonical)

**Event**: Established policy that committed requirements must be generated on Linux/WSL only.

**Policy Decisions**:
- **Canonical platform**: Linux (CI runner) or WSL (treated as Linux for dependency resolution)
- **Forbidden**: Regenerating requirements on Windows PowerShell/CMD (drops non-Windows deps)
- **Platform-specific markers**: Required for `pywin32`, `python-magic`, `python-magic-bin`
- **CI enforcement**: Mechanical check via `scripts/check_requirements_portability.py`

**Enforcement Mechanism**:
- Tool: `scripts/check_requirements_portability.py`
- Runs in: `.github/workflows/ci.yml` lint job (every PR)
- Checks:
  - `pywin32==...` must have `; sys_platform == "win32"` marker
  - `python-magic==...` must have `; sys_platform != "win32"` marker
  - `python-magic-bin==...` must have `; sys_platform == "win32"` marker
- Exit codes: 0 = portable, 1 = violations, 2 = runtime error

**Verification**:
- Current requirements.txt and requirements-dev.txt: ✅ Portable (markers present)
- CI check passes on current main branch

**Rationale**:
- Prevents platform drift: regenerating on Windows drops Linux-only dependencies
- Docker/CI uses Linux → must match Linux dependency resolution
- WSL acceptable: same pip resolution behavior as Linux
- Aligns with README principle: "mechanically enforceable via CI contracts"

**Documentation**:
- Policy: `security/README.md` (Requirements Regeneration Policy section)
- Tool: `scripts/check_requirements_portability.py` (executable documentation)
- Remediation: Tool prints guidance if check fails

**Owner**: Infrastructure team
**Next Review**: After first requirements regeneration incident or Q2 2026

---

## 2026-01-05: Security Baseline Refresh Framework (CI SARIF Artifacts Canonical)

**Event**: Established baseline refresh procedure with CI artifacts as single source of truth.

**Policy Decisions**:
- **Baseline source**: CI SARIF artifacts only (not local runs) → prevents platform drift
- **Refresh trigger**: Explicit PRs labeled `security-baseline-update` only (never automatic)
- **Procedure**: Download CI artifacts → run `update_baseline.py --write` → log in SECURITY_LOG.md
- **Enforcement flip**: After 1-2 stable baseline updates, change `continue-on-error: true` → `false`

**New Artifacts Workflow**:
- File: `.github/workflows/security-artifacts.yml`
- Purpose: Export SARIF files as downloadable artifacts for baseline refresh
- Triggers: `workflow_dispatch` (manual), push/PR to main
- Artifacts: `trivy-results.sarif`, `trivy-container.sarif`, `codeql-results/python.sarif`
- Retention: 90 days

**Baseline Refresh Procedure**:
1. Trigger security-artifacts workflow on main branch
2. Download SARIF artifacts from successful run
3. Run `scripts/security/update_baseline.py --trivy-fs ... --trivy-image ... --codeql ... --write`
4. Verify normalization determinism (run twice, identical output)
5. Create SECBASE-YYYYMMDD entry in SECURITY_LOG.md (template provided)
6. Commit to `security/baseline-refresh-YYYYMMDD` PR with label `security-baseline-update`

**Why CI Artifacts Only?**:
- Reproducible: exact scanner versions/config as CI
- Platform-consistent: avoids Windows/Linux path separator drift
- Auditable: workflow run URL + commit SHA in log entry

**Documentation**:
- Procedure: `security/README.md` (Baseline Refresh Procedure section)
- Log template: `docs/SECURITY_LOG.md` (SECBASE-YYYYMMDD template at bottom)

**Verification**:
- Baselines directory exists: `security/baselines/` (empty baselines committed)
- Tools ready: `scripts/security/update_baseline.py`, `scripts/security/normalize_sarif.py`
- Workflow ready: `.github/workflows/security-artifacts.yml`

**Rationale**:
- Baselines are derived truth → must come from canonical CI environment
- Explicit procedure → prevents silent acceptance of regressions
- Append-only log → audit trail for baseline changes
- Aligns with README principle: "mechanically enforceable via CI contracts"

**Owner**: Security team
**Next Review**: After first baseline refresh or Q2 2026

---

## 2026-01-05: Initial Security Gate Policy Established

**Event**: Security baseline enforcement framework initialized.

**Policy Decisions**:
- **Trivy (filesystem + container)**: Block only on new `CRITICAL,HIGH` findings
- **CodeQL**: Block only on new alerts (default Python query suite)
- **Baseline refresh**: Explicit only (never automatic on PR)
- **Exceptions**: Require documented entry in `SECURITY_EXCEPTIONS.md` + compensating control

**Enforcement Mechanism**:
- Baselines committed to `security/baselines/`
- Diff gate in CI via `scripts/security/diff_gate.py`
- SARIF normalization ensures deterministic finding keys

**Verification**:
- Initial baselines captured from current scan state
- CI configured to fail only on regressions (new findings)

**Rationale**:
- Aligns with README principle: "mechanically enforceable via CI contracts"
- Prevents noisy red builds from pre-existing debt
- Makes security signals actionable: new findings = immediate blocker
- Security debt tracked separately in `SECURITY_BURNDOWN.md`

**Owner**: Implementation team
**Next Review**: After first production security incident or Q2 2026 (whichever comes first)

---

## 2026-01-05: Docker Compose Image Pinning (Supply-Chain Determinism)

**Event**: Pinned moving image tags in docker-compose.yml to specific versions.

**Changes**:
- `postgres:15` → `postgres:15.10-alpine` (pinned patch version)
- `qdrant/qdrant:latest` → `qdrant/qdrant:v1.12.5` (pinned release version)

**Rationale**:
- Prevents supply-chain drift (images changing under same tag)
- Deterministic builds (same compose file → same images)
- Reduces risk of breaking changes from upstream image updates
- Aligns with README principle: "safe, deterministic, mechanically enforceable"

**Maintenance**:
- Review pinned versions quarterly or on major upstream releases
- Test upgrades in dev environment before updating compose file
- Document upgrades in this log

**Owner**: Infrastructure team
**Next Review**: Q2 2026 or on upstream security advisories

---

## Template for Future Entries

```
## YYYY-MM-DD: [Event Title]

**Event**: [What changed]

**Policy/Baseline Changes**: [Specific modifications]

**Verification**: [How change was validated]

**Rationale**: [Why this change was made]

**Owner**: [Team/person responsible]
**Next Review**: [Date or trigger condition]
```

---

## Baseline Refresh Log Entry Template (SECBASE-YYYYMMDD)

Use this template when updating security baselines from CI SARIF artifacts.
Add new entries at the TOP of the file (after the header, before older entries).

```markdown
## SECBASE-YYYYMMDD: Security Baseline Refresh (Trivy + CodeQL)

**Date (UTC)**: [YYYY-MM-DD]
**Author**: [name/handle]
**Branch/PR**: [branch name] / [PR #]
**Trigger**: Baseline refresh from CI SARIF (explicit update; no auto-update)

### Source (canonical inputs)
- **Workflow run**: [GitHub Actions run URL]
- **Commit SHA (main)**: `[abcdef1234567890]`
- **Artifacts used**:
  - `trivy-results.sarif` (filesystem scan)
  - `trivy-container.sarif` (container scan)
  - `codeql-results/python.sarif` (CodeQL Python)

### Policy snapshot (what is enforced)
- **Trivy threshold**: `CRITICAL,HIGH` (regression-only)
- **CodeQL threshold**: new alerts only (regression-only)
- **CI mode**: `continue-on-error=[true|false]` for diff gates

### Baseline outputs (derived state committed)
| Baseline file | Generator | Notes |
| --- | --- | --- |
| `security/baselines/trivy-fs.high.json` | `scripts/security/update_baseline.py --trivy-fs ... --write` | [e.g., "updated from run artifacts"] |
| `security/baselines/trivy-image.high.json` | `scripts/security/update_baseline.py --trivy-image ... --write` | [notes] |
| `security/baselines/codeql.python.json` | `scripts/security/update_baseline.py --codeql ... --write` | [notes] |

### Delta summary (from previous baseline → new baseline)
| Scanner | Previous count | New count | Net | Comment |
| --- | ---:| ---:| ---:| --- |
| Trivy FS (HIGH/CRITICAL) | [N] | [N] | [+/-N] | [why changed] |
| Trivy Image (HIGH/CRITICAL) | [N] | [N] | [+/-N] | [why changed] |
| CodeQL Python | [N] | [N] | [+/-N] | [why changed] |

### Verification
- **Normalized outputs deterministic**: [YES/NO] (ran normalization twice, identical output)
- **Diff gate behavior**:
  - main with refreshed baseline: expected pass ✅
  - canary regression PR (optional): expected fail ✅ / not run

### Notes / Follow-ups
- [Link to `docs/SECURITY_BURNDOWN.md` items created/updated]
- [Any exceptions added/updated in `docs/SECURITY_EXCEPTIONS.md`]
```

(Keep the `SECBASE-YYYYMMDD` prefix consistent so you can reference it later.)
