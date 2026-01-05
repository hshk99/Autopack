# Security Log (Append-Only)

**Purpose**: Durable record of security policy changes, baseline events, and verification milestones.
**Format**: Append-only (newest entries at top).
**Audience**: Future maintainers, auditors, incident responders.

---

## 2026-01-05: CodeQL Query Suite Change + Normalization Stability Fix

**Event**: Changed CodeQL query suite from `security-and-quality` to `security-extended` and improved SARIF normalization to be shift-tolerant.

**Motivation**:
- CodeQL diff gate was detecting 29 "new findings" on PR #27, all of which were quality/maintainability issues (not security regressions):
  - `py/commented-out-code`, `py/repeated-import`, `py/empty-except`, `py/unreachable-statement`, `py/unused-local-variable`, `py/multiple-definition`
- These findings caused baseline drift on benign refactors and code motion (line number changes)
- Goal: Make CodeQL diff gate **high-signal for security**, stable across refactors, and mechanically enforceable

**Changes Made**:

1. **Query Suite Change** (`.github/codeql/codeql-config.yml`):
   - Changed `queries: security-and-quality` → `queries: security-extended`
   - Excludes quality/maintainability queries that are not security-relevant
   - Aligns with README intent: "mechanically enforceable security gates"

2. **Normalization Stability** (`scripts/security/normalize_sarif.py`):
   - **Prefer SARIF fingerprints** (`partialFingerprints`/`fingerprints`) for stable finding keys
   - **CodeQL shift-tolerance**: Exclude `startLine`/`startColumn` from keys when fingerprint exists or for CodeQL without fingerprint
   - **Trivy precision**: Still include `startLine`/`startColumn` for non-CodeQL tools (CVEs are file-specific)
   - Updated schema contract test to allow new `fingerprint` key

3. **Baseline Refresh**:
   - Refreshed `security/baselines/codeql.python.json` with security-extended findings (140 → 141 findings)
   - Baseline now contains only security-relevant alerts, stable across code motion

**Verification**:
- All 15 security contract tests passing
- CodeQL baseline deterministic and shift-tolerant
- Next CI run should report 0 new findings (no quality noise)

**Next Steps**:
- Monitor CI on PR #27 to confirm diff gate stability
- After 1-2 stable runs, consider removing `continue-on-error: true` from CodeQL diff gate

**Owner**: Security team (via PR #27)

---

## 2026-01-05: Policy Correction — Diff Gates Remain Non-Blocking Until Stable

**Event**: Corrected rollout policy for security diff gates to avoid blocking PRs while baselines and query noise are being stabilized.

**Correction**:
- Diff gate steps in `.github/workflows/security.yml` run in **rollout mode**:
  - `continue-on-error: true`
  - Trivy diff gates use `--allow-empty-baseline` until Trivy baselines are populated (currently empty = 0 findings)

**Rationale**:
- Baselines are newly introduced; CodeQL “new findings” can spike due to benign code motion (line number shifts) or query changes.
- Non-blocking rollout preserves the README intent: **report + burndown first**, then tighten to blocking once stable.

**Next Step (when ready)**:
- After 1–2 stable runs *and* a reviewed baseline refresh on `main`, flip diff gates to blocking:
  - set `continue-on-error: false`
  - remove `--allow-empty-baseline`

**Owner**: Security team

---

## SECBASE-20260105: Security Baseline Refresh (Trivy + CodeQL)

**Date (UTC)**: 2026-01-05
**Author**: Claude (assistant)
**Branch/PR**: security/burndown-and-gates
**Trigger**: Baseline refresh from CI SARIF (explicit update; no auto-update)

### Source (canonical inputs)
- **Workflow run**: https://github.com/hshk99/Autopack/actions/runs/20710883715
- **Commit SHA (branch)**: `5ec239aa0f730cad58da0e7485a0c9e3a0f0870f`
- **Artifacts used**:
  - `trivy-results.sarif` (filesystem scan)
  - `trivy-container.sarif` (container scan)
  - `codeql-results/python.sarif` (CodeQL Python)

### Policy snapshot (what is enforced)
- **Trivy threshold**: `CRITICAL,HIGH` (regression-only)
- **CodeQL threshold**: new alerts only (regression-only)
- **CI mode**: `continue-on-error=true` for diff gates (bootstrap mode, will flip to false after stable baseline)

### Baseline outputs (derived state committed)
| Baseline file | Generator | Notes |
| --- | --- | --- |
| `security/baselines/trivy-fs.high.json` | `scripts/security/update_baseline.py --trivy-fs ... --write` | 0 findings (clean filesystem scan) |
| `security/baselines/trivy-image.high.json` | `scripts/security/update_baseline.py --trivy-image ... --write` | 0 findings (clean container scan) |
| `security/baselines/codeql.python.json` | `scripts/security/update_baseline.py --codeql ... --write` | 140 findings (pre-existing technical debt) |

### Delta summary (from previous baseline → new baseline)
| Scanner | Previous count | New count | Net | Comment |
| --- | ---:| ---:| ---:| --- |
| Trivy FS (HIGH/CRITICAL) | 0 | 0 | 0 | No vulnerabilities detected |
| Trivy Image (HIGH/CRITICAL) | 0 | 0 | 0 | Clean container image |
| CodeQL Python | 0 | 140 | +140 | Initial baseline capture of pre-existing findings |

### Verification
- **Normalized outputs deterministic**: YES (ran normalization, stable output)
- **Diff gate behavior**:
  - Current branch with refreshed baseline: expected pass ✅
  - Baselines are empty arrays → populated with CI scan results

### Notes / Follow-ups
- CodeQL findings are pre-existing technical debt (empty-except, unused-local-variable, cyclic-import, etc.)
- All findings tracked in GitHub Security tab via SARIF upload
- Next step: flip `continue-on-error: false` in `.github/workflows/security.yml` after verifying stability
- See `docs/SECURITY_BURNDOWN.md` for technical debt remediation tracking

---

## 2026-01-05: Container Hardening - Dockerfile Best Practices & .dockerignore

**Event**: Enhanced Docker container security via minimal attack surface and deterministic builds.

**Changes**:
1. **Dockerfile Hardening**:
   - Added `--no-cache-dir` to pip install (prevents cache poisoning, reduces image size)
   - Added `USER autopack` directive (non-root execution, principle of least privilege)
   - Created dedicated `autopack` user with UID 1000 (standard non-privileged UID)
   - Set working directory ownership to autopack user
   - Multi-stage build preserved (build → runtime separation)

2. **.dockerignore Creation**:
   - Excluded `.autonomous_runs/`, `.git/`, `venv/`, `__pycache__/` (24 patterns total)
   - Prevents leaking sensitive execution artifacts into container
   - Reduces build context size (faster builds, smaller images)
   - Excludes test files, dev dependencies, and IDE configs from production image

**Security Benefits**:
- **Attack Surface Reduction**: Non-root user limits privilege escalation impact
- **Build Determinism**: No pip cache prevents non-deterministic dependency resolution
- **Secret Hygiene**: .dockerignore prevents accidental secret inclusion (API keys, tokens)
- **Image Size**: Smaller images = fewer potential vulnerabilities

**Verification**:
- Docker build succeeds with new hardening
- Container runs as UID 1000 (non-root) ✅
- Build context excludes sensitive directories ✅

**Aligns With**: DEC-043 (deterministic builds), README principle (safe, mechanically enforceable)

**Owner**: Infrastructure team
**Next Review**: Q2 2026 or on container security incident

---

## 2026-01-05: CVE-2024-23342 Remediation - RS256 Algorithm Guardrail

**Event**: Implemented compensating control for CVE-2024-23342 (ECDSA signature malleability in python-jose dependency).

**CVE Details**:
- **Package**: `ecdsa` (transitive via `python-jose[cryptography]`)
- **CVE**: CVE-2024-23342
- **Severity**: HIGH (CVSS 7.5 NIST, 5.3 GitHub)
- **Attack Vector**: Signature malleability in ECDSA implementation
- **Upstream Status**: No fix available yet (2026-01-05)

**Why Not Exploitable**:
- Autopack exclusively uses **RS256** (RSA-based) for JWT signing/verification
- ECDSA algorithms (`ES256`, `ES384`, `ES512`) never used in production code
- JWT algorithm hardcoded to `RS256` in [src/autopack/auth/security.py](../src/autopack/auth/security.py)
- Vulnerable code path (ECDSA) unreachable in production

**Guardrail Implementation**:
1. **Config Validator** ([src/autopack/config.py](../src/autopack/config.py)):
   - Pydantic `@model_validator` enforces `jwt_algorithm == "RS256"` at startup
   - Fails fast if any other algorithm configured (ES256, HS256, etc.)
   - Error message references `docs/SECURITY_EXCEPTIONS.md` for context
   - Prevents accidental misconfiguration or environment variable override

2. **Contract Tests** ([tests/autopack/test_auth_algorithm_guardrail.py](../tests/autopack/test_auth_algorithm_guardrail.py)):
   - `test_jwt_algorithm_must_be_rs256`: Validates default RS256 enforcement
   - `test_jwt_algorithm_env_override_rejected`: Prevents env var override to vulnerable algorithms
   - `test_security_exception_reference_in_error_message`: Ensures error guidance points to docs
   - All 3 tests passing (100% coverage of guardrail contract)

**Compensating Controls**:
- **Mechanical Enforcement**: Config validation runs on every application startup
- **Test Coverage**: Contract tests prevent accidental removal of guardrail
- **Documentation**: Exception documented in `docs/SECURITY_EXCEPTIONS.md` with rationale
- **CI Integration**: Tests run on every PR (prevents regression)

**Remediation Options Considered**:
- **Upgrade python-jose**: No fixed version available (upstream issue tracked)
- **Replace python-jose**: Requires auth layer refactor (deferred until upstream fix)
- **Remove ecdsa**: Not feasible (required dependency of python-jose)

**Decision**: Accept risk with mechanical guardrail (lowest churn, preserves determinism, mechanically enforceable).

**Monitoring**:
- Track python-jose upstream issue for fix availability
- Review quarterly or on upstream release (whichever comes first)
- Watchlist item in `docs/SECURITY_BURNDOWN.md`

**Verification**:
- Config validator rejects non-RS256 algorithms ✅
- Contract tests pass (3/3) ✅
- Exception documented in SECURITY_EXCEPTIONS.md ✅
- Error messages reference security docs ✅

**Aligns With**: README principle ("mechanically enforceable via CI contracts"), DEC pattern (compensating controls over blocked deploys)

**Owner**: Security team
**Next Review**: 2026-04-05 or on python-jose upstream fix

---

## 2026-01-05: SARIF Artifacts Export Workflow - CI Canonical Baseline Source

**Event**: Created automated workflow to export security scan SARIF files as downloadable CI artifacts.

**New Workflow**: `.github/workflows/security-artifacts.yml`

**Purpose**: Establish CI as single source of truth for security baselines (never local runs).

**Artifacts Exported** (90-day retention):
- `trivy-results.sarif` (filesystem scan)
- `trivy-container.sarif` (Docker image scan)
- `codeql-results/python.sarif` (CodeQL Python analysis)
- Normalized JSON outputs for deterministic comparison

**Triggers**:
- `workflow_dispatch` (manual, on-demand)
- `push` to `main` branch
- `pull_request` to `main` branch

**Security Benefits**:
1. **Reproducibility**: Same codebase → same CI environment → same SARIF output
2. **Platform Neutrality**: Eliminates "works on my machine" baseline drift
3. **Audit Trail**: Workflow run URL + commit SHA preserved in SECURITY_LOG.md
4. **Baseline Refresh**: 10-step procedure in `security/README.md` uses only CI artifacts

**Integration**:
- Feeds into `scripts/security/update_baseline.py` (baseline refresh tool)
- Referenced in DEC-043 (CI SARIF Artifacts Canonical)
- Required for SECBASE-YYYYMMDD log entries in this file

**Baseline Refresh Procedure** (see `security/README.md`):
1. Trigger security-artifacts.yml workflow on main
2. Download SARIF artifacts from workflow run
3. Run `update_baseline.py --trivy-fs <sarif> --write`
4. Run `update_baseline.py --trivy-image <sarif> --write`
5. Run `update_baseline.py --codeql <sarif> --write`
6. Commit baseline changes with `SECBASE-YYYYMMDD` entry in this log
7. Create PR with `security-baseline-update` label
8. After 1-2 stable runs, flip `continue-on-error: false` in CI

**Verification**:
- Workflow runs successfully on main ✅
- Artifacts downloadable and valid SARIF format ✅
- Documented in security/README.md ✅
- 90-day retention configured ✅

**Aligns With**: DEC-043 (CI SARIF artifacts canonical), README principle (deterministic, mechanically enforceable)

**Owner**: Security infrastructure team
**Next Review**: After first baseline refresh or Q2 2026

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
