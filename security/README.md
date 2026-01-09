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
- **CI artifacts are canonical** (not local runs) to avoid platform drift
- Only update on explicit PRs labeled `security-baseline-update` or dedicated baseline refresh PRs
- Run `scripts/security/update_baseline.py --write` after intentional baseline changes
- Document refresh in `docs/SECURITY_LOG.md` using the template format

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

### Baseline Refresh Procedure (Explicit Only)

**CRITICAL**: Baselines must be generated from **CI artifacts only** (same query suites + config as CI), never from local runs.

**When to Update**:
- After fixing a batch of vulnerabilities
- After upgrading dependencies that shift findings
- After accepting a documented exception (e.g., CVE-2024-23342)
- Never implicitly—only on explicit PRs labeled `security-baseline-update`

**Prerequisites**:
- ✅ CI must have run at least 1-2 times successfully on main with current scanner config
- ✅ SARIF artifacts available from `.github/workflows/security-artifacts.yml` run
- ✅ No outstanding security findings that should be fixed first

**Step-by-Step Procedure**:

```bash
# 1. Trigger the security-artifacts workflow (if not already run)
#    Go to: Actions → Security SARIF Artifacts → Run workflow (on main branch)

# 2. Download SARIF artifacts from the latest main branch run
#    Download "security-sarif-artifacts" from the workflow run
#    Extract to a temporary directory (e.g., /tmp/sarif-artifacts/)

# 3. Verify artifacts are from main branch and recent commit
ls -lh /tmp/sarif-artifacts/
# Should contain:
#   - trivy-results.sarif
#   - trivy-container.sarif
#   - codeql-results/python.sarif

# 4. Run baseline update tool (dry run first)
python scripts/security/update_baseline.py \
  --trivy-fs /tmp/sarif-artifacts/trivy-results.sarif \
  --trivy-image /tmp/sarif-artifacts/trivy-container.sarif \
  --codeql /tmp/sarif-artifacts/codeql-results/python.sarif

# Review the diff summary carefully
# Check: Added/Removed counts, total findings

# 5. Write baselines (if diff looks correct)
python scripts/security/update_baseline.py \
  --trivy-fs /tmp/sarif-artifacts/trivy-results.sarif \
  --trivy-image /tmp/sarif-artifacts/trivy-container.sarif \
  --codeql /tmp/sarif-artifacts/codeql-results/python.sarif \
  --write

# 6. Verify normalization is deterministic
#    Run update_baseline.py twice, output should be identical
git diff security/baselines/
# Should show changes only if findings actually changed

# 7. Create baseline refresh log entry
#    Edit docs/SECURITY_LOG.md and add a SECBASE-YYYYMMDD entry
#    Fill in: date, workflow run URL, commit SHA, delta summary
#    See template at bottom of docs/SECURITY_LOG.md

# 8. Commit to a baseline-refresh PR
git checkout -b security/baseline-refresh-$(date +%Y%m%d)
git add security/baselines/ docs/SECURITY_LOG.md
git commit -m "security: Baseline refresh from CI SARIF (SECBASE-$(date +%Y%m%d))

See docs/SECURITY_LOG.md for delta summary and source run URL."

# 9. Push and create PR
git push origin security/baseline-refresh-$(date +%Y%m%d)
# Create PR with label: security-baseline-update

# 10. After PR merge and 1-2 stable CI runs, flip enforcement
#     Edit .github/workflows/security.yml
#     Change: continue-on-error: true → false (for diff gates)
#     Log this policy change in docs/SECURITY_LOG.md
```

**Why CI Artifacts Only?**
- Ensures baselines match the exact scanner versions/config used in CI
- Avoids platform drift (Windows vs Linux path separators, etc.)
- Reproducible: anyone can download the same artifacts and verify

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

## Requirements Regeneration Policy (Linux/CI Canonical)

**Policy**: Committed `requirements*.txt` must be generated on **Linux (CI runner or WSL)** to ensure portability.

**Rationale**:
- Platform-specific dependencies (e.g., `pywin32`, `python-magic`) require environment markers
- Regenerating on Windows PowerShell/CMD drops non-Windows dependencies → breaks Linux/Docker
- WSL counts as "Linux" for this purpose (same dependency resolution behavior)

**Enforcement**:
- CI check via `scripts/check_requirements_portability.py` (runs on every PR)
- Fails CI if requirements are not portable (missing markers, unconditional platform deps)

**Regeneration Procedure**:

```bash
# REQUIRED: Run on Linux/WSL only
# If on Windows, use WSL: wsl bash

# From repo root:
bash scripts/regenerate_requirements.sh

# Or manually with pip-compile:
pip-compile --output-file=requirements.txt pyproject.toml
pip-compile --output-file=requirements-dev.txt --extra=dev pyproject.toml

# Verify portability:
python scripts/check_requirements_portability.py

# If check passes, commit:
git add requirements.txt requirements-dev.txt
git commit -m "deps: Regenerate requirements (Linux/WSL canonical)"
```

**Platform-Specific Markers**:
- `pywin32==... ; sys_platform == "win32"` (Windows-only)
- `python-magic==... ; sys_platform != "win32"` (Linux/macOS)
- `python-magic-bin==... ; sys_platform == "win32"` (Windows binary)

**CI Check**:
- Tool: `scripts/check_requirements_portability.py`
- Checks:
  - `pywin32` must have `sys_platform == "win32"` marker
  - `python-magic` must have `sys_platform != "win32"` marker
  - `python-magic-bin` must have `sys_platform == "win32"` marker
- Exit codes:
  - `0`: Portable (CI passes)
  - `1`: Violations detected (CI fails)
  - `2`: Runtime error (missing file, etc.)

**Troubleshooting**:

If CI fails with "requirements portability check failed":
1. **On Windows**: Do NOT regenerate requirements on Windows
2. **Use WSL**: `wsl bash scripts/regenerate_requirements.sh`
3. **Verify markers**: Check that platform-specific deps have environment markers
4. **Rerun check**: `python scripts/check_requirements_portability.py`

---

## References

- Policy log: [docs/SECURITY_LOG.md](../docs/SECURITY_LOG.md)
- Exceptions: [docs/SECURITY_EXCEPTIONS.md](../docs/SECURITY_EXCEPTIONS.md)
- Burndown: [docs/SECURITY_BURNDOWN.md](../docs/SECURITY_BURNDOWN.md)
- Implementation plan: [docs/IMPLEMENTATION_PLAN_INTENTION_FIRST_AUTONOMY_LOOP_REMAINING_IMPROVEMENTS.md](../docs/IMPLEMENTATION_PLAN_INTENTION_FIRST_AUTONOMY_LOOP_REMAINING_IMPROVEMENTS.md)

---

## Contract Tests

- Baseline format validation: `tests/security/test_update_baseline_determinism.py` ✅ (active)
- Normalization determinism: `tests/security/test_normalize_sarif_determinism.py` ✅ (active)
- SARIF schema validation: `tests/security/test_normalize_sarif_schema.py` ✅ (active)
- Diff gate logic: `tests/security/test_diff_gate_semantics.py` ✅ (active)
- Exemption classifier: `tests/security/test_exemption_classifier.py` ✅ (active)
- Requirements portability: `scripts/check_requirements_portability.py` ✅ (active)
