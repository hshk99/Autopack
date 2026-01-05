# Security Burndown (Living Document)

**Purpose**: Current open vulnerabilities and security debt with owners and ETAs.
**Format**: Living (updated as findings resolved/escalated).
**Review Cadence**: Weekly during active remediation; monthly otherwise.

---

## Summary Dashboard

| Category | Critical | High | Medium | Low | Total |
|----------|----------|------|--------|-----|-------|
| **Trivy (filesystem)** | 0 | 0 | - | - | 0 |
| **Trivy (container)** | 0 | 0 | - | - | 0 |
| **CodeQL** | 0 | ~140 | - | - | ~140 |
| **Total** | **0** | **~140** | **-** | **-** | **~140** |

_Last Updated: 2026-01-05 (SECBASE-20260105 baseline refresh)_

**Notes**:
- Trivy scans show 0 CRITICAL/HIGH findings (clean state ✅)
- CodeQL ~140 findings are pre-existing technical debt (empty-except, unused-local-variable, cyclic-import, etc.)
- CodeQL findings classified as HIGH by CodeQL severity but not all represent exploitable vulnerabilities
- Medium/Low counts not tracked (focus on CRITICAL/HIGH regression prevention only)

---

## Critical Findings (Block Deployment)

_(None currently)_

---

## High Findings (Target: 30-day remediation)

### CodeQL Findings (Pre-existing Technical Debt)

**Baseline**: SECBASE-20260105 captured ~140 pre-existing CodeQL findings (see )

**Inventory Status**: Full inventory deferred (not blocking - regression prevention is primary goal)

**Common patterns**:
- : Empty except blocks without error handling
- : Unused variables in scope
- : Circular import dependencies
- : Dead code after returns

**Remediation approach**:
- Priority: Prevent new findings (diff gate blocks PRs with regressions)
- Burndown: Opportunistic cleanup during related refactoring (not time-boxed)
- Exceptions: None required (findings are code quality issues, not security vulnerabilities)

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

1. **After security scans**: Run `scripts/security/summarize.py` (when implemented) to generate markdown table updates
2. **On finding resolution**: Move entry from active section to "Resolved This Quarter"
3. **On new exception**: Add to Watchlist + link to `SECURITY_EXCEPTIONS.md`
4. **Weekly triage**: Review dashboard, update owners/ETAs, escalate stalled items

### Automation Status

- [ ] Automated dashboard generation from baselines (planned: Phase 5)
- [ ] PR comment summaries (planned: Phase 5)
- [ ] Weekly Slack/email digest (future work)

---

## References

- Enforcement baselines: [security/baselines/](../security/baselines/)
- Exception policies: [SECURITY_EXCEPTIONS.md](SECURITY_EXCEPTIONS.md)
- Change log: [SECURITY_LOG.md](SECURITY_LOG.md)
- Diff gate implementation: [scripts/security/diff_gate.py](../scripts/security/diff_gate.py)
