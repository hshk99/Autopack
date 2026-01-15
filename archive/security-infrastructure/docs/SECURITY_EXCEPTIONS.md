# Security Exceptions (Append-Only)

**Purpose**: Documented accepted risks with rationale and compensating controls.
**Format**: Append-only (active exceptions at top, expired/resolved at bottom).
**Review Cadence**: Quarterly or on dependency major version updates.

---

## Active Exceptions

### CVE-2024-23342: ECDSA Signature Malleability in python-jose (via ecdsa)

**Vulnerability Details**:
- **Package**: `ecdsa` (transitive via `python-jose[cryptography]`)
- **CVE**: CVE-2024-23342
- **Severity**: HIGH
- **CVSS**: 7.5 (NIST), 5.3 (GitHub Advisory)
- **Attack Vector**: Signature malleability in ECDSA implementation

**Why Not Exploitable in Autopack**:
1. **Algorithm Enforcement**: Autopack exclusively uses `RS256` (RSA-based) for JWT signing/verification
2. **No ECDSA Usage**: ECDSA algorithms (`ES256`, `ES384`, `ES512`) are never used in production
3. **Configuration**: JWT algorithm is hardcoded to `RS256` in [src/autopack/auth/security.py](../src/autopack/auth/security.py)

**Compensating Controls**:
1. **Allowlist Enforcement**: Config validator (`src/autopack/config.py`) enforces `jwt_algorithm == "RS256"` at startup and fails fast on any other algorithm
2. **Contract Test**: `tests/autopack/test_auth_algorithm_guardrail.py` (3 tests, 100% pass) validates:
   - Default RS256 enforcement
   - Environment variable override rejection
   - Error message references this security exception doc
3. **Code Review**: Any changes to JWT configuration require security review

**Remediation Options Considered**:
- **Upgrade python-jose**: No fixed version available yet; upstream issue tracked
- **Replace python-jose**: Would require significant refactor of auth layer (deferred until upstream fix or major breaking change)
- **Remove ecdsa**: Not feasible; required by python-jose

**Decision**: Accept risk with documented guardrails (lowest churn, preserves determinism).

**Owner**: @autopack/security-team
**Review Date**: 2026-04-05 or upon python-jose upstream fix (whichever comes first)
**Tracked In**: `SECURITY_BURNDOWN.md` (watchlist section)

---

## Expired/Resolved Exceptions

_(None yet)_

---

## Template for Future Exceptions

```
### [CVE ID or Finding Title]

**Vulnerability Details**:
- **Package**: [package name + version]
- **CVE/CWE**: [identifier]
- **Severity**: [CRITICAL/HIGH/MEDIUM/LOW]
- **Attack Vector**: [brief description]

**Why Not Exploitable in Autopack**:
[Detailed technical explanation]

**Compensating Controls**:
1. [Control 1: technical mitigation]
2. [Control 2: process/monitoring]
3. [Control 3: testing/validation]

**Remediation Options Considered**:
- [Option 1: why rejected/deferred]
- [Option 2: why rejected/deferred]

**Decision**: [Accept/defer/mitigate + rationale]

**Owner**: [Team/person]
**Review Date**: [Date or trigger]
**Tracked In**: [Link to burndown/issue]
```
