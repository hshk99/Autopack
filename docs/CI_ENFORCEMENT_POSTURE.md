# CI Enforcement Posture

**Document Purpose**: Canonical reference for what CI checks block PRs vs what is informational.
**Contract**: CI behavior matches this document. Contributors can answer "will this fail CI?" by reading here.

---

## Quick Reference: What Blocks PRs?

| Check | Blocks PR? | Notes |
|-------|------------|-------|
| **Ruff lint** | ✅ Yes | All lint errors must be fixed |
| **Black formatting** | ✅ Yes | Code must be formatted |
| **Core tests** | ✅ Yes | Tests marked `not research and not aspirational` |
| **xfail budget** | ✅ Yes | Cannot add new xfail without approval |
| **Doc contract tests** | ✅ Yes | `tests/docs/` must pass |
| **Docs drift check** | ✅ Yes | SOT files must be current |
| **Doc links (nav-mode)** | ✅ Yes | README, INDEX links must work |
| **Security baseline log** | ✅ Yes | SECBASE entry required for baseline changes |
| **Production config guard** | ✅ Yes | DEBUG must not be enabled |
| **GitHub Actions pinning** | ✅ Yes | Actions must be pinned to SHA |
| **Frontend lint/typecheck/build** | ✅ Yes | Frontend must build |
| Mypy type check | ❌ No | `continue-on-error: true` - staged adoption |
| Aspirational tests | ❌ No | `continue-on-error: true` - roadmap features |
| Research tests | ❌ No | `continue-on-error: true` - quarantined subsystem |
| Deep doc link scan | ❌ No | Report-only workflow |

---

## Workflow Details

### ci.yml - Main CI Pipeline

**Lint Job** (BLOCKING)
- `ruff check` - Linting errors block
- `black --check` - Formatting errors block
- `mypy` - **Non-blocking** (`continue-on-error: true`)
  - Currently checking: `src/autopack/version.py`, `src/autopack/__version__.py`
  - Plan: Expand scope progressively as codebase matures

**Core Tests** (BLOCKING)
- Runs tests marked `not research and not aspirational and not legacy_contract`
- Uses PostgreSQL service container for realistic DB testing
- Coverage uploaded to Codecov
- xfail budget test must pass

**Aspirational Tests** (NON-BLOCKING)
- `continue-on-error: true`
- Tests extended/roadmap features
- Tracks progress but doesn't fail CI

**Research Tests** (NON-BLOCKING)
- `continue-on-error: true`
- Quarantined subsystem tests
- Informational only

**Docs/SOT Integrity** (BLOCKING)
- `pytest tests/docs/` - Doc contract tests
- `check_docs_drift.py` - SOT consistency
- `check_doc_links.py` - Navigation links
- OpenAPI export as artifact

**Frontend CI** (BLOCKING)
- `npm run lint`
- `npm run type-check`
- `npm run build`

### security.yml - Security Scanning

**Trivy/CodeQL Scans** (BLOCKING for regressions)
- Runs security scans
- Blocks on NEW HIGH/CRITICAL findings vs baseline
- Existing baseline items don't fail CI
- SARIF results uploaded

### security-artifacts.yml - Security Reporting

**Baseline Drift Report** (NON-BLOCKING)
- `continue-on-error: true`
- Exports SARIF artifacts
- Informational for tracking progress

### verify-workspace-structure.yml

**Structure Verification** (BLOCKING)
- Validates workspace organization
- **Root clutter check is NON-BLOCKING** (`continue-on-error: true`)

### doc-link-deep-scan.yml

**Deep Link Scan** (NON-BLOCKING)
- Report-only workflow
- Scans all documentation links
- Does not fail CI

---

## Coverage Policy

**Current State**: Coverage is collected and uploaded to Codecov but NOT enforced.

**Contract**:
- No coverage gate currently blocks PRs
- Codecov provides visibility but no enforcement
- Future: Consider non-regression gate (coverage cannot drop vs main)

**Rationale**:
- Avoid flaky global thresholds that punish refactors
- Coverage as visibility, not enforcement, during initial adoption

---

## Type Checking Staged Adoption

**Current Scope** (mypy, non-blocking):
- `src/autopack/version.py`
- `src/autopack/__version__.py`

**Expansion Plan**:
1. Add core modules progressively
2. Move to blocking once baseline is stable
3. Document which modules are "typed" vs "untyped"

---

## Test Categories

### Core Tests (must pass)
- Production-critical functionality
- No xfail markers allowed (tracked by xfail budget)
- Uses PostgreSQL for realistic testing

### Aspirational Tests (xfail allowed)
- Extended test suites
- Roadmap features
- xfail acceptable - tracks progress toward goals

### Research Tests (informational)
- Quarantined research subsystem
- Uses in-memory SQLite
- Expected to fail (subsystem has known API drift)

---

## How to Add New CI Checks

1. Determine if check should be **blocking** or **informational**
2. Add to appropriate workflow
3. If informational: add `continue-on-error: true`
4. Update this document with the new check
5. PR must include documentation update

---

## Security Baseline Process

When security baselines change:
1. `security.yml` runs Trivy/CodeQL scans
2. New HIGH/CRITICAL findings vs baseline BLOCK the PR
3. If baseline legitimately changes, add SECBASE entry
4. `check_security_baseline_log_entry.py` enforces SECBASE requirement

---

*Last updated: 2026-01-08*
