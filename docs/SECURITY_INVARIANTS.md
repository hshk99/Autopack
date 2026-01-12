# Security Invariants - Proved Safe Patterns

**Purpose**: Document security findings that are accepted as safe with proven invariants and compensating controls.

**Status**: All 31 CodeQL findings assessed and categorized (SECBASE-20260112)

**Review Cadence**: Quarterly or when findings categories change

---

## Overview

This document catalogs security patterns detected by automated scanners (CodeQL, Trivy) that are **intentionally accepted** because they are:
1. **Proved safe** through compensating controls or architectural constraints
2. **False positives** where the scanner lacks context
3. **Acceptable trade-offs** with documented rationale

Each invariant includes:
- **Finding category** (CWE number)
- **Acceptance rationale** (why it's safe)
- **Proof mechanism** (tests, runtime gates, or architectural constraints)
- **Watchlist triggers** (when to re-evaluate)

---

## Active Invariants

### INV-001: Log Injection (CWE-117) - String Interpolation in Logging

**Current Findings**: ~26 findings across codebase
**Status**: ✅ ACCEPTED (Proved Safe)

**Pattern**:
```python
logger.info(f"Request {request_id} started")
logger.error(f"Phase {phase_id} failed: {error}")
```

**Why Safe**:
1. **No User-Controlled Data**: All logged values are internal identifiers from database:
   - `run_id`, `phase_id`, `request_id`: Database UUIDs (validated format)
   - `user_id`: Internal database foreign key
   - No HTTP request parameters logged directly

2. **Structured Logging Format**: All logs use prefixes that make injection attempts visible:
   ```
   [2026-01-12 10:30:45] INFO Request a1b2c3d4-... started
   ```

3. **No Log Aggregation Pipeline**: No SIEM or log aggregation that could be manipulated

**Proof Mechanism**:
- **Architectural constraint**: Database IDs are validated at insertion (UUID format, integer IDs)
- **Code review**: Manual audit confirms no HTTP parameters in log statements
- **Test coverage**: Unit tests verify log output format

**Watchlist Trigger**:
- Adding SIEM/log aggregation → migrate to structured logging library with separate fields
- Logging HTTP request parameters → add explicit redaction

**References**:
- [SECURITY_BURNDOWN.md:49-56](docs/SECURITY_BURNDOWN.md#49-56)
- CodeQL rule: `py/log-injection`

---

### INV-002: Stack Trace Exposure (CWE-209) - Debug Mode Stack Traces

**Current Findings**: ~3 findings in error handling
**Status**: ⚠️ ACCEPTED WITH GUARDRAIL

**Pattern**:
```python
if os.getenv("DEBUG") == "1":
    response_data["traceback"] = format_exc()
```

**Why Safe** (with guardrail):
1. **Runtime Gate**: Stack traces only exposed when `DEBUG=1` environment variable is set
2. **Deployment Contract**: Production deployments MUST NOT set `DEBUG=1`
3. **Development Utility**: Tracebacks are valuable for development/staging environments

**Proof Mechanism**:
- ✅ **CI Enforcement**: `scripts/ci/check_production_config.py` blocks PRs with `DEBUG=1` in production configs
- ✅ **Test Coverage**: `tests/ci/test_ci_enforcement_ladder.py` validates config check
- ✅ **Documentation**: [SECURITY_EXCEPTIONS.md](docs/SECURITY_EXCEPTIONS.md) documents policy

**CI Check**:
```bash
# Runs on every PR
python scripts/ci/check_production_config.py
# Exit code 1 if DEBUG=1 found in .env.production, production.yml, etc.
```

**Compensating Controls**:
- **Required**: Production config MUST NOT contain `DEBUG=1`
- **Validation**: CI check added (see [scripts/ci/check_production_config.py](scripts/ci/check_production_config.py))
- **Runtime**: No additional runtime enforcement needed (environment variable check is sufficient)

**Watchlist Trigger**:
- Any change to DEBUG flag logic or error response formatting
- Production incident involving stack trace exposure

**References**:
- [SECURITY_BURNDOWN.md:69-83](docs/SECURITY_BURNDOWN.md#69-83)
- [scripts/ci/check_production_config.py](scripts/ci/check_production_config.py)
- CodeQL rule: `py/stack-trace-exposure`

---

### INV-003: Path Injection (CWE-73) - Settings-Based Path Construction

**Current Findings**: ~1 finding
**Status**: ✅ ACCEPTED (False Positive)

**Pattern**:
```python
artifacts_dir = Path(settings.autonomous_runs_dir) / run_id / "artifacts"
```

**Why Safe**:
1. **Controlled Sources Only**: Paths constructed from:
   - `settings.autonomous_runs_dir`: Deployment config (not user input)
   - `run_id`: Database UUID with validated format (`^[a-f0-9-]{36}$`)
   - No HTTP parameters used in path construction

2. **Scoped Operations**: All file operations scoped to `.autonomous_runs/` directory

**Proof Mechanism**:
- **Architectural constraint**: Settings loaded from config files, not user input
- **Database validation**: UUIDs validated at insertion (see `src/autopack/schemas.py`)
- **Path traversal protection**: Artifact endpoints reject `..` and absolute paths (see [src/autopack/api/routes/artifacts.py](src/autopack/api/routes/artifacts.py))

**Test Coverage**:
```python
# tests/api/test_artifacts_router_contract.py
def test_artifact_file_rejects_path_traversal()
def test_artifact_file_rejects_absolute_paths()
def test_artifact_file_rejects_windows_drive_letters()
```

**Watchlist Trigger**:
- Using HTTP request parameters in path construction
- Adding user-controlled directory names

**References**:
- [SECURITY_BURNDOWN.md:58-67](docs/SECURITY_BURNDOWN.md#58-67)
- CodeQL rule: `py/path-injection`

---

### INV-004: Bad Tag Filter / XSS - Quarantined Research Module

**Current Findings**: 1 finding
**Status**: ✅ NOT USED (Quarantined Code)

**Location**: `src/research/discovery/web_discovery.py`

**Why Safe**:
1. **Not Imported**: Module not imported by any production code
2. **Research Code**: Experimental research module with API drift
3. **Quarantined**: Module tagged for removal (BUILD-146)

**Proof Mechanism**:
- **Code grep**: No imports of `web_discovery` in production codebase
- **Dead code analysis**: Module not executed in any workflow

**Watchlist Trigger**:
- If research module is re-activated, add XSS protection or remove module

**References**:
- [SECURITY_BURNDOWN.md:95-103](docs/SECURITY_BURNDOWN.md#95-103)
- CodeQL rule: `py/bad-tag-filter`

---

### INV-005: Artifact Exposure - Redaction Infrastructure

**Current Findings**: N/A (preventive control)
**Status**: ✅ PROTECTED

**Risk**: Artifacts (logs, HAR files, browser recordings) could expose sensitive data

**Protection Mechanism**:
1. **Redaction Module**: `src/autopack/artifacts/redaction.py` provides pattern-based redaction
2. **Default Patterns**: Credentials, PII, financial data, session tokens, IP addresses
3. **HAR-Specific Redaction**: Special handling for HTTP archives (headers, cookies, POST data)

**Redaction Categories**:
- **CREDENTIAL**: API keys, tokens, passwords, bearer tokens, OAuth tokens
- **PII**: Email addresses, phone numbers, SSNs
- **FINANCIAL**: Credit card numbers, bank accounts
- **SESSION**: Cookies, session IDs
- **NETWORK**: IP addresses, URLs with auth

**Usage Pattern**:
```python
from autopack.artifacts.redaction import ArtifactRedactor

redactor = ArtifactRedactor()
clean_text, count = redactor.redact_text(sensitive_log)
clean_har = redactor.redact_har(har_data)
redactor.redact_file(Path("logs/api_response.json"))
```

**Proof Mechanism**:
- **Infrastructure exists**: Redaction module implemented with comprehensive patterns
- **Default patterns**: 15+ patterns covering common sensitive data
- **Test coverage**: Module includes pattern validation

**Gap**: Redaction not automatically applied to all artifacts (manual opt-in)

**Watchlist Trigger**:
- Artifact exposure incident
- Adding new artifact types (e.g., video recordings, network traces)

**Future Enhancement** (P3):
- Auto-redact all artifacts before storage
- Add artifact scanning to CI

**References**:
- [src/autopack/artifacts/redaction.py](src/autopack/artifacts/redaction.py)

---

## Dependency Vulnerabilities

### CVE-2024-23342: ECDSA Signature Malleability in python-jose

**Status**: ✅ ACCEPTED WITH MECHANICAL GUARDRAIL

**Details**: See [SECURITY_EXCEPTIONS.md](docs/SECURITY_EXCEPTIONS.md)

**Why Not Exploitable**:
- Autopack exclusively uses **RS256** (RSA-based) for JWT signing
- ECDSA algorithms never used in production
- Vulnerable code path unreachable

**Proof Mechanism**:
- ✅ **Config Validator**: Pydantic validator enforces `jwt_algorithm == "RS256"` at startup
- ✅ **Contract Tests**: 3 tests validate algorithm guardrail (see `tests/autopack/test_auth_algorithm_guardrail.py`)
- ✅ **Error Guidance**: Validation error references security docs

**Compensating Controls**:
- **Mechanical enforcement**: Config validation runs on every startup
- **Test coverage**: Contract tests prevent accidental removal
- **Documentation**: Exception documented with rationale

**References**:
- [SECURITY_EXCEPTIONS.md:11-43](docs/SECURITY_EXCEPTIONS.md#11-43)
- [SECURITY_LOG.md:416-474](docs/SECURITY_LOG.md#416-474)

---

## Maintenance

### How to Update This Document

1. **On new finding acceptance**: Add new invariant section with:
   - Finding category (CWE number)
   - Acceptance rationale
   - Proof mechanism (tests, gates, or constraints)
   - Watchlist triggers

2. **On invariant invalidation**: Move to "Expired Invariants" section and link to remediation PR

3. **Quarterly review**: Re-validate all invariants still hold:
   - Run CodeQL scan to verify finding count matches expectations
   - Review test coverage for proof mechanisms
   - Check if any watchlist triggers have occurred

### Proof Mechanism Types

1. **Architectural Constraint**: Design prevents the vulnerability (e.g., no user input in logs)
2. **Runtime Gate**: Environment variable or config check at startup (e.g., DEBUG mode)
3. **CI Enforcement**: Automated check blocks unsafe patterns in PRs (e.g., production config check)
4. **Test Coverage**: Contract tests validate safe behavior (e.g., path traversal rejection)

### Relationship to Other Security Docs

- **SECURITY_EXCEPTIONS.md**: Formal exceptions for dependency CVEs with acceptance rationale
- **SECURITY_BURNDOWN.md**: Current vulnerability counts and remediation status
- **SECURITY_LOG.md**: Append-only audit log of security policy changes
- **This doc (SECURITY_INVARIANTS.md)**: Proved-safe patterns and architectural safety contracts

---

## Expired Invariants

_(None yet - section reserved for invalidated invariants)_

---

## Template for Future Invariants

```markdown
### INV-XXX: [Finding Category] - [Brief Description]

**Current Findings**: N findings
**Status**: ✅ ACCEPTED / ⚠️ ACCEPTED WITH GUARDRAIL / ❌ REMEDIATION REQUIRED

**Pattern**:
```python
# Code example showing the pattern
```

**Why Safe**:
1. [Reason 1: architectural constraint, controlled inputs, etc.]
2. [Reason 2: compensating control, runtime gate, etc.]

**Proof Mechanism**:
- **Type**: Architectural / Runtime Gate / CI Enforcement / Test Coverage
- **Implementation**: [Description or link to code]
- **Test Coverage**: [Test file paths or test names]

**Watchlist Trigger**:
- [Condition that would invalidate this invariant]

**References**:
- [Link to baseline entry, tests, or related docs]
```
