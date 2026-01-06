# Security Baseline Automation - Implementation Status

**Last Updated**: 2026-01-06
**Status**: Phase B operational, monitoring Phase A for schedule stability

---

## Implementation Phases

### Phase A: Weekly Security Artifacts (SARIF Generation)
**Status**: ✅ Operational (scheduled)

**Schedule**: Weekly Monday 06:00 UTC (`.github/workflows/security-artifacts.yml`)

**What It Does**:
- Runs CodeQL, Trivy filesystem, and Trivy container scans
- Normalizes SARIF outputs to canonical format
- Uploads artifacts for Phase B consumption
- Uploads SARIF to GitHub Security tab

**Monitoring Checklist** (before enabling Phase B schedule):
- [ ] Scheduled run 1: Monday 2026-01-13 06:00 UTC (next)
- [ ] Scheduled run 2: Monday 2026-01-20 06:00 UTC
- [ ] Scheduled run 3: Monday 2026-01-27 06:00 UTC

**Success Criteria** (before enabling Phase B schedule):
- All 3 scheduled runs complete successfully (100% success rate)
- Artifacts uploaded consistently and immediately available
- No workflow failures or timeouts
- Verify Phase B can download artifacts from completed Phase A runs

**Recent Runs** (all push-triggered, not scheduled yet):
- 2026-01-05 23:51 UTC: ✅ success (run 20732879384)
- 2026-01-05 23:44 UTC: ✅ success (run 20732754849)
- 2026-01-05 14:43 UTC: ✅ success (run 20718916336)

---

### Phase B: Automated Baseline Refresh (PR Creation)
**Status**: ✅ Operational (manual trigger only, schedule disabled)

**Trigger**: `workflow_dispatch` only (`.github/workflows/security-baseline-refresh.yml` line 4)

**What It Does**:
- Downloads latest SARIF artifacts from Phase A
- Updates baseline JSON files if drift detected
- Creates PR with stub SECBASE entry for human completion
- Skips PR creation if no changes

**Validation Status**:
- ✅ No-change path validated (run 20732762649, no PR created)
- ✅ Change path validated (PR #31, SECBASE-20260106 completed)
- ✅ CI blocks incomplete SECBASE entries
- ✅ Timestamp stability confirmed (SECBASE-anchored)

**Hardening Completed**:
- ✅ SECBASE-anchored timestamps (PR #34)
- ✅ Exit code hardening (PR #34)
- ✅ Windows UTF-8 console support (PR #34)
- ✅ Run ID in branch names (commit 53460677)
- ✅ Operational checklist added (docs/SECURITY_LOG.md)

**Schedule** (currently disabled, ready to enable after Phase A monitoring):
```yaml
# Uncomment after 2-3 successful Phase A scheduled runs
# schedule:
#   - cron: "0 7 * * 1"   # Weekly Monday 07:00 UTC (1 hour after Phase A)
```

**Enabling Schedule** (after Phase A proves stable):
1. Verify all success criteria met (3/3 Phase A runs successful, artifacts available)
2. Create PR to uncomment schedule in `.github/workflows/security-baseline-refresh.yml` lines 5-6
3. PR title: `feat: Enable Phase B scheduled baseline refresh (weekly Monday 07:00 UTC)`
4. Wait for CI to pass, merge PR (preserves mechanically enforceable intent)
5. Monitor first scheduled Phase B run (Monday 07:00 UTC after Phase A completes)

---

### Phase C: Auto-Merge Exempted Changes (Future)
**Status**: ⏳ Not yet implemented

**Goal**: Auto-merge PRs when only exempted patterns change (e.g., Trivy DB metadata updates that don't affect actual vulnerabilities)

**Why Deferred**:
- Need to observe real baseline drift patterns from Phase A/B
- Must identify safe exemption patterns empirically
- Requires additional safety gates (e.g., "no new CVE IDs", "only informational severity changes")

**Potential Exemption Patterns** (to be validated):
- Trivy database updates that only change metadata (not vulnerability counts)
- CodeQL query description updates (same finding IDs, updated help text)
- Dependency version bumps with no new findings

**Design Considerations** (when implementing):
- Must still create SECBASE entry (even if auto-merged)
- Should notify security team (Slack/email) on auto-merge
- Should have emergency disable mechanism (env var: `DISABLE_PHASE_C_AUTOMERGE=1`)
- Must fail-safe: if uncertainty → require human review

**Next Steps**:
1. Monitor Phase B PRs for 3-6 months
2. Identify recurring "safe" patterns
3. Document exemption criteria in ADR
4. Implement Phase C with conservative exemptions
5. Validate with dry-run mode before enabling auto-merge

---

## Operational Procedures

### Monitoring Phase A Scheduled Runs

```bash
# Check upcoming scheduled runs
gh workflow view security-artifacts.yml

# List recent runs
gh run list --workflow=security-artifacts.yml --limit 10

# Watch specific run
gh run watch <run-id>

# Download artifacts from completed run
gh run download <run-id> --name security-sarif-artifacts
```

### Manually Triggering Phase B

```bash
# Trigger baseline refresh
gh workflow run security-baseline-refresh.yml --ref main

# Monitor progress
gh run list --workflow=security-baseline-refresh.yml --limit 1
gh run watch <run-id>

# Check if PR was created
gh pr list --label security-baseline-update --state open
```

### Completing SECBASE Entries

See: [docs/SECURITY_LOG.md - Phase B Operational Checklist](SECURITY_LOG.md#phase-b-automation-operational-checklist)

---

## Success Metrics

### Phase A Stability
- **Target**: 100% success rate for scheduled runs (3/3 consecutive)
- **Current**: N/A (no scheduled runs yet, monitoring starts 2026-01-13)

### Phase B Accuracy
- **No-change path**: Should create 0 PRs when baselines unchanged
  - ✅ Validated: Run 20732762649 (no PR created)
- **Change path**: Should create exactly 1 PR when baselines drift
  - ✅ Validated: PR #31 (first automated baseline refresh)

### Overall Automation Health
- **Manual baseline updates eliminated**: Target 90%+ automated via Phase B
- **False positive rate**: Target <5% (PRs created with no real changes)
- **Time to merge baseline PRs**: Target <1 business day (SECBASE entry completion)

---

## Troubleshooting

### Phase A Failures
- **Trivy timeout**: Increase timeout in workflow (currently default)
- **CodeQL query errors**: Check `.github/codeql/codeql-config.yml` syntax
- **Artifact upload failures**: Check GitHub storage quota

### Phase B Failures
- **Artifacts not found**: Phase A must run successfully first
- **Timestamp drift**: Should be fixed (SECBASE-anchored), report if recurs
- **CI blocks merge despite complete SECBASE**: Check for `TODO` markers via `grep -A20 "## SECBASE-YYYYMMDD" docs/SECURITY_LOG.md`

### Emergency Procedures
- **Disable Phase B schedule**: Create PR to comment out schedule in workflow (preserves CI enforcement)
- **Rollback baselines**: Revert baseline PR, create new SECBASE entry documenting rollback
- **Skip CI enforcement**: Add `SKIP_BASELINE_CHECK=1` env var (use only in emergency)

---

## References

- **Implementation Plan**: `docs/IMPLEMENTATION_PLAN_BASELINE_REFRESH.md`
- **Operational Checklist**: `docs/SECURITY_LOG.md` (Phase B section)
- **Baseline Policy**: `docs/SECURITY_LOG.md` (2026-01-05 governance policy)
- **Validation PRs**:
  - PR #30: Three-phase automation implementation
  - PR #31: First automated baseline refresh (change path)
  - PR #34: Timestamp stability + hardening
  - Commit 53460677: Branch naming + operational checklist

---

## Decision Log

### 2026-01-06: Phase B Schedule Remains Disabled
**Decision**: Keep Phase B on manual trigger until 2-3 successful Phase A scheduled runs observed.

**Rationale**: Phase A schedule hasn't been validated yet (all recent runs are push-triggered). Need to confirm weekly schedule reliability before adding dependent automation.

**Next Review**: After Monday 2026-01-27 06:00 UTC (3rd scheduled run)

### 2026-01-06: Phase C Deferred
**Decision**: Defer Phase C implementation until Phase A/B patterns observed.

**Rationale**: Cannot design safe exemption criteria without empirical data from real baseline drift events.

**Next Review**: Q1 2026 (after 3 months of Phase B operation)
