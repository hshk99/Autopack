# Security Burndown (Living Document)

**Purpose**: Current open vulnerabilities and security debt with owners and ETAs.
**Format**: Living (updated as findings resolved/escalated).
**Review Cadence**: Weekly during active remediation; monthly otherwise.

---

## Summary Dashboard

<!-- AUTO_COUNTS_START -->
| Category | Critical | High | Medium | Low | Total |
|----------|----------|------|--------|-----|-------|
| **Trivy (filesystem)** | 0 | 0 | - | - | 0 |
| **Trivy (container)** | 0 | 0 | - | - | 0 |
| **CodeQL** | 0 | 57 | - | - | 57 |
| **Total** | **0** | **57** | **-** | **-** | **57** |

_Last Updated: 2026-01-06 (auto-generated from security/baselines/)_
<!-- AUTO_COUNTS_END -->

**Notes**:
- Trivy scans show 0 CRITICAL/HIGH findings (clean state ✅)
- CodeQL 57 findings are security patterns detected by `security-extended` query suite (CWE-117, CWE-73, CWE-209, CWE-1333)
- CodeQL switched from default (code quality) to security-extended suite per SECBASE-20260105
- All 57 findings reviewed - no exploitable vulnerabilities (see assessment below)
- Medium/Low counts not tracked (focus on CRITICAL/HIGH regression prevention only)

---

## Critical Findings (Block Deployment)

_(None currently)_

---

## High Findings (Target: 30-day remediation)

### CodeQL Security Findings (Accepted - Non-Exploitable)

**Baseline**: SECBASE-20260105 captured 57 security patterns after CodeQL suite change (default → security-extended)

**Security Assessment Completed**: All 57 findings reviewed and categorized as non-exploitable:

#### 1. Log Injection (CWE-117) - 42 findings ✅ ACCEPTED
**Pattern**: String interpolation in logging statements (e.g., `logger.info(f"Request {request_id}")`)

**Risk**: Low - No user-controlled data in logs
- All logged values are internal identifiers (request_id, phase_id, run_id) from database
- No HTTP request parameters logged directly
- Structured logging format with prefixes makes injection attempts visible
- No log aggregation pipeline that could be manipulated

**Compensating Controls**: None required (not exploitable in current architecture)

**Watchlist Trigger**: If adding SIEM/log aggregation → use structured logging library with separate fields

#### 2. Path Injection (CWE-73) - 7 findings ✅ ACCEPTED (False Positives)
**Pattern**: Path construction from config/settings (e.g., `Path(settings.autonomous_runs_dir) / run_id`)

**Risk**: None - Paths constructed from controlled sources only
- `settings.autonomous_runs_dir`: Deployment config (not user input)
- `run_id`: Database UUID (validated format)
- No HTTP parameters used in path construction
- All file operations scoped to `.autonomous_runs/` directory

**Compensating Controls**: None required (false positive)

#### 3. Stack Trace Exposure (CWE-209) - 6 findings ⚠️ ACCEPTED WITH EXCEPTION
**Pattern**: HTTP responses include tracebacks when `DEBUG=1` (e.g., `"traceback": tb if os.getenv("DEBUG") == "1"`)

**Risk**: Medium (if DEBUG=1 in production) - Currently mitigated by runtime gate

**Exception Rationale**:
- Debug mode explicitly gated by environment variable
- Production deployments MUST NOT set DEBUG=1 (deployment contract)
- Useful for development/staging environments

**Compensating Controls**:
- **Required**: Production config MUST NOT contain `DEBUG=1`
- **Validation**: CI check added to block PRs setting DEBUG in production configs (implemented: `scripts/ci/check_production_config.py`, executed in `.github/workflows/ci.yml`)

**Watchlist Trigger**: Any change to DEBUG flag logic or error response formatting

#### 4. Polynomial ReDoS (CWE-1333) - 1 finding ✅ ACCEPTED
**Pattern**: Regex with potential exponential backtracking in `governed_apply.py` patch validation

**Risk**: Low - Bounded input size, internal operation only
- Used only for patch validation (LLM-generated patches, not arbitrary user input)
- No HTTP endpoint accepts raw regex patterns
- Performance impact minimal (runs once per phase)

**Compensating Controls**: None required (acceptable for validation use case)

#### 5. Bad Tag Filter (XSS) - 1 finding ✅ NOT USED
**Location**: `src/research/discovery/web_discovery.py` (quarantined research module)

**Risk**: None - Module not imported by production code
- Research module has API drift (quarantined per BUILD-146)
- WebDiscovery class not used anywhere in codebase
- CodeQL scans `src/research/` but code is inactive

**Compensating Controls**: None required (code not executed)

---

**Remediation Strategy**: Diff gate prevents new security findings. No time-boxed remediation required for baselined findings (all assessed as non-exploitable or properly mitigated).

---

## Medium Findings (Target: 90-day remediation)

_To be populated after baseline analysis._

---

## Watchlist (Accepted Risks / Long-term Debt)

### CVE-2024-23342: ecdsa via python-jose

**Status**: Exception granted (see `SECURITY_EXCEPTIONS.md`)
**Compensating Controls**: RS256 algorithm enforcement + contract test
**Owner**: @autopack/security-team
**Next Review**: 2026-04-05

**Trigger for Re-evaluation**:
- python-jose releases fixed version
- Upstream ecdsa patches CVE-2024-23342
- Any change to JWT signing/verification logic
- Major authentication layer refactor

---

## Resolved This Quarter

_(None yet)_

---

## Maintenance Notes

### How to Update This Document

1. **Summary Dashboard**: Auto-generated from `security/baselines/` (run `python scripts/security/generate_security_burndown_counts.py` after baseline updates)
2. **On finding resolution**: Move entry from active section to "Resolved This Quarter"
3. **On new exception**: Add to Watchlist + link to `SECURITY_EXCEPTIONS.md`
4. **Weekly triage**: Review dashboard, update owners/ETAs, escalate stalled items

### Automation Status

- [x] Automated dashboard generation from baselines (✓ CI-enforced)
- [x] Automated baseline refresh PR workflow (Phase B - validated)
- [ ] PR comment summaries (planned: Phase 5)
- [ ] Weekly Slack/email digest (future work)

### Phase B Test Procedure

The automated baseline refresh workflow (`.github/workflows/security-baseline-refresh.yml`) has two paths:

#### Change Path (Validated ✓)
**Trigger**: Baselines differ from latest security artifacts
**Expected behavior**:
1. Downloads latest SARIF artifacts from Phase A (security-artifacts workflow)
2. Updates `security/baselines/*.json` files
3. Regenerates `docs/SECURITY_BURNDOWN.md` counts
4. Creates stub SECBASE entry in `docs/SECURITY_LOG.md` with TODO markers
5. Creates PR branch `security/baseline-refresh-YYYYMMDD`
6. Creates PR with detailed description
7. CI blocks merge until SECBASE entry TODO markers are removed

**Validation**: PR #31 (2026-01-05) - First automated baseline refresh

#### No-Change Path (To Be Validated)
**Trigger**: Baselines match latest security artifacts
**Expected behavior**:
1. Downloads artifacts and compares with current baselines
2. Detects no changes
3. Skips PR creation
4. Workflow completes successfully with log: "✅ No baseline changes detected"

**Test procedure**:
```bash
# After merging a baseline refresh PR, immediately run Phase B again
gh workflow run security-baseline-refresh.yml --ref main

# Verify workflow completes with "Skip PR creation (no changes)" step
gh run list --workflow=security-baseline-refresh.yml --limit 1
```

**Deterministic testing** (future enhancement):
Add `artifacts_run_id` input parameter to Phase B workflow to enable testing with specific artifact versions instead of always using "latest".

---

## References

- Enforcement baselines: [security/baselines/](../security/baselines/)
- Exception policies: [SECURITY_EXCEPTIONS.md](SECURITY_EXCEPTIONS.md)
- Change log: [SECURITY_LOG.md](SECURITY_LOG.md)
- Diff gate implementation: [scripts/security/diff_gate.py](../scripts/security/diff_gate.py)
