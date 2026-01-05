# Security Log (Append-Only)

**Purpose**: Durable record of security policy changes, baseline events, and verification milestones.
**Format**: Append-only (newest entries at top).
**Audience**: Future maintainers, auditors, incident responders.

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
