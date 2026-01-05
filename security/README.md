# Security Baseline + Diff Gate System

**Purpose**: Make security findings actionable by failing CI only on regressions (new findings), not on pre-existing debt.

**Principle**: Aligns with README directive — "safe, deterministic, mechanically enforceable via CI contracts."

---

## How It Works

### 1. Baselines (Committed Snapshots)

**Location**: `security/baselines/`

**Files**:
- `trivy-fs.high.json`: Trivy filesystem scan (CRITICAL/HIGH only)
- `trivy-image.high.json`: Trivy container scan (CRITICAL/HIGH only)
- `codeql.python.json`: CodeQL Python alerts

**Format**: Normalized JSON (deterministic finding keys), sorted alphabetically.

**Refresh Policy**:
- **Explicit only** (never automatic on PR)
- Run `scripts/security/update_baseline.py --write` after intentional baseline changes
- Document refresh in `docs/SECURITY_LOG.md`

**Why Committed?**
- Baselines are part of the CI contract (deterministic enforcement)
- Reviewable in PRs (visible when baseline shifts)
- No "moving target" problem (baselines don't auto-update)

---

### 2. Normalization (Deterministic Finding Keys)

**Tool**: `scripts/security/normalize_sarif.py`

**Purpose**: Convert SARIF → stable JSON keys for diff comparison.

**Key Components**:
- `tool` (trivy, codeql)
- `ruleId` (CVE-ID or CodeQL rule)
- `artifactUri` (normalized path: forward slashes, no leading `./`)
- `messageHash` (SHA256 first 16 chars)
- `startLine` / `startColumn` (if present; CodeQL precision)

**Tradeoffs**:
- **Line numbers included**: Precise but causes drift on refactors
- **Message hashing**: Compact but loses human readability (check SARIF for details)

**Path Normalization**:
- Windows: `src\autopack\main.py` → `src/autopack/main.py`
- Linux: Already `/` (no change)

---

### 3. Diff Gate (CI Enforcement)

**Tool**: `scripts/security/diff_gate.py`

**Logic**:
```
new_findings = current_findings - baseline_findings
if len(new_findings) > 0:
    exit 1  # Fail CI
else:
    exit 0  # Pass
```

**CI Integration**:
- Runs after SARIF upload in `.github/workflows/security.yml`
- Trivy + CodeQL each have separate diff gates
- Start non-blocking (`continue-on-error: true`), flip to blocking when stable

**Regression-Only Blocking**:
- Pre-existing findings: CI green (tracked in `SECURITY_BURNDOWN.md`)
- New findings: CI red (immediate blocker)

---

## Usage

### Normal Development (No Baseline Change)

```bash
# Push PR → CI runs security scans → diff gate compares to baseline
# If no new findings: CI green ✅
# If new findings: CI red ❌ (must fix or justify exception)
```

### Updating Baselines (Explicit)

**When to Update**:
- After fixing a batch of vulnerabilities
- After upgrading dependencies that shift findings
- After accepting a documented exception (e.g., CVE-2024-23342)

**How to Update**:

```bash
# 1. Generate current scans locally (or download CI artifacts)
docker build --target backend --tag autopack-backend:scan .
trivy fs --format sarif --severity CRITICAL,HIGH --output trivy-fs.sarif .
trivy image --format sarif --severity CRITICAL,HIGH --output trivy-image.sarif autopack-backend:scan

# 2. Normalize and update baselines
python scripts/security/update_baseline.py \
  --trivy-fs trivy-fs.sarif \
  --trivy-image trivy-image.sarif \
  --codeql codeql-results.sarif \
  --write

# 3. Review diff
git diff security/baselines/

# 4. Commit with log entry
# Add entry to docs/SECURITY_LOG.md explaining baseline change
git add security/baselines/ docs/SECURITY_LOG.md
git commit -m "security: Update baselines after [reason]"
```

**Why Manual?**
- Prevents "baseline drift" (CI silently accepting regressions)
- Forces explicit review and documentation
- Aligns with SOT ledger principle (intentional, append-only record)

---

## Finding Key Stability

### Stable Across (Should Not Cause Baseline Drift)

- Platform (Windows ↔ Linux)
- Scanner version updates (minor)
- SARIF format tweaks (schema compatible)

### Unstable Across (May Cause Drift)

- **Code refactors** (line numbers shift)
  - Mitigation: Review diff, update baseline if intended
- **Dependency major version bumps** (new CVEs surface)
  - Expected: Update baseline after review
- **CodeQL query suite changes** (new rules added)
  - Expected: Update baseline or suppress rule

### Future Improvements (Optional)

- **Shift-tolerant keys**: Exclude line numbers for files with low change frequency
- **Message text inclusion**: Store full message in baseline (more readable, larger files)
- **Severity filtering**: Per-tool severity thresholds (e.g., trivy CRITICAL-only on main branch)

---

## Troubleshooting

### CI Failing: "New findings detected"

**Steps**:
1. Check diff gate output (which findings are new?)
2. Review SARIF in GitHub Security tab
3. Options:
   - **Fix**: Upgrade dep, patch code, remove vulnerability
   - **Exception**: Document in `SECURITY_EXCEPTIONS.md` + add compensating control
   - **False positive**: Suppress via scanner config (trivy `.trivyignore`, CodeQL query filter)

### Baseline Out of Sync

**Symptom**: Local scans don't match CI baseline

**Causes**:
- Different scanner versions (use CI-pinned versions)
- Platform differences (normalize paths via script)
- Uncommitted baseline changes (check `git status`)

**Fix**:
```bash
# Regenerate baseline from current HEAD
python scripts/security/update_baseline.py --write
git diff security/baselines/  # Should be empty if in sync
```

### Too Many False Positives

**Options**:
1. **Scope reduction**: Update CodeQL config to exclude more paths
2. **Severity threshold**: Raise trivy threshold (e.g., CRITICAL-only)
3. **Suppress specific rules**: Add to scanner config (document in `SECURITY_LOG.md`)

---

## References

- Policy log: [docs/SECURITY_LOG.md](../docs/SECURITY_LOG.md)
- Exceptions: [docs/SECURITY_EXCEPTIONS.md](../docs/SECURITY_EXCEPTIONS.md)
- Burndown: [docs/SECURITY_BURNDOWN.md](../docs/SECURITY_BURNDOWN.md)
- Implementation plan: [docs/IMPLEMENTATION_PLAN_INTENTION_FIRST_AUTONOMY_LOOP_REMAINING_IMPROVEMENTS.md](../docs/IMPLEMENTATION_PLAN_INTENTION_FIRST_AUTONOMY_LOOP_REMAINING_IMPROVEMENTS.md)

---

## Contract Tests

- Baseline format validation: `tests/security/test_baseline_format.py` (planned)
- Normalization determinism: `tests/security/test_normalize_sarif.py` (planned)
- Diff gate logic: `tests/security/test_diff_gate.py` (planned)
