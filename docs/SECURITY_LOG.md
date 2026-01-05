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
