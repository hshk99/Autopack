# Security Burndown (Living Document)

**Purpose**: Current open vulnerabilities and security debt with owners and ETAs.
**Format**: Living (updated as findings resolved/escalated).
**Review Cadence**: Weekly during active remediation; monthly otherwise.

---

## Summary Dashboard

| Category | Critical | High | Medium | Low | Total |
|----------|----------|------|--------|-----|-------|
| **Trivy (filesystem)** | 0 | TBD | TBD | TBD | TBD |
| **Trivy (container)** | 0 | TBD | TBD | TBD | TBD |
| **CodeQL** | 0 | TBD | TBD | TBD | TBD |
| **Total** | **0** | **TBD** | **TBD** | **TBD** | **TBD** |

_Last Updated: 2026-01-05_

---

## Critical Findings (Block Deployment)

_(None currently)_

---

## High Findings (Target: 30-day remediation)

### Baseline Findings (Pre-Gate Implementation)

_To be populated after initial baseline scan. High-severity findings from baseline will be inventoried here with:_
- Finding ID / CVE
- Affected package/path
- Attack vector summary
- Owner
- Target resolution date
- Mitigation status

**Placeholder**: Will be populated in Phase 4 (baseline generation).

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
