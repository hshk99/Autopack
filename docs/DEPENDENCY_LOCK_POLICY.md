# Dependency Lock Policy

**Last Updated**: 2026-01-09

This document defines the canonical dependency lock strategy for Autopack, ensuring reproducible builds across development and production environments.

## 1. Canonical Lock Strategy

### 1.1 Python Dependencies

**Canonical Platform**: Linux (CI/Production)

All production container builds use Linux as the canonical platform. The `requirements.txt` file is generated via `pip-compile` on Linux (or in CI) to ensure deterministic hashes.

**Lock File Hierarchy**:
1. `requirements.txt` - Production dependencies (canonical, pip-compile generated)
2. `requirements-dev.txt` - Development/test dependencies (extends requirements.txt)

**Platform-Specific Packages**:
- Platform markers (e.g., `; sys_platform == "win32"`) are used for OS-specific dependencies
- `python-magic` (Linux) vs `python-magic-bin` (Windows)
- `pywin32` (Windows only)

### 1.2 Node.js Dependencies

**Canonical Lock File**: `package-lock.json` at repo root

The root `package-lock.json` is canonical for the frontend build. All CI and production Docker builds use this lock file.

## 2. Supported Development Platforms

### 2.1 Linux (Canonical)

Linux is the canonical development and production platform. All lock files are generated and tested on Linux first.

```bash
# Generate canonical requirements.txt
pip-compile --output-file=requirements.txt pyproject.toml

# Generate dev requirements
pip-compile --extra=dev --output-file=requirements-dev.txt pyproject.toml
```

### 2.2 Windows (Best-Effort)

Windows development is supported on a best-effort basis. The lock files work on Windows with platform markers, but Windows should not redefine canonical locks.

**Windows-Specific Notes**:
- Use `python-magic-bin` instead of `python-magic` (handled via platform markers)
- `pywin32` is automatically included via platform markers
- If you encounter hash mismatches, verify against Linux-generated locks

**Windows Setup**:
```powershell
# Install from canonical requirements (platform markers handle Windows specifics)
pip install -r requirements.txt

# For development
pip install -r requirements-dev.txt
```

### 2.3 macOS (Best-Effort)

macOS development is also supported on a best-effort basis with the same lock files.

## 3. Lock File Generation Rules

### 3.1 When to Regenerate

Lock files should be regenerated when:
1. Adding new dependencies to `pyproject.toml`
2. Updating dependency version constraints
3. Security updates require newer versions
4. CI detects lock drift

### 3.2 How to Regenerate

**IMPORTANT**: Always regenerate locks on Linux (or in CI) to maintain canonical hashes.

```bash
# Option 1: Local Linux/WSL
pip-compile --upgrade --output-file=requirements.txt pyproject.toml
pip-compile --extra=dev --upgrade --output-file=requirements-dev.txt pyproject.toml

# Option 2: Via CI workflow (recommended)
# Use the `regenerate-locks` workflow dispatch
```

### 3.3 Lock File Verification

The CI pipeline verifies:
1. Lock files are present and valid
2. No unexpected changes from pip-compile
3. Production builds are deterministic

## 4. Production Build Determinism

### 4.1 Container Builds

Production containers are built deterministically:

```dockerfile
# From Dockerfile
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
```

Key guarantees:
- Same `requirements.txt` = same installed packages
- No floating versions (all pinned)
- Hash verification via pip

### 4.2 Verification Script

Use the verification script to check lock determinism:

```bash
# Check if current environment matches lock files
python scripts/ci/check_dependency_locks.py
```

## 5. Cross-Platform Compatibility

### 5.1 Platform Markers

Platform-specific dependencies use environment markers:

```
python-magic==0.4.27 ; sys_platform != "win32"
python-magic-bin==0.4.14 ; sys_platform == "win32"
pywin32==311 ; sys_platform == "win32"
```

### 5.2 Known Platform Differences

| Package | Linux | Windows | macOS | Notes |
|---------|-------|---------|-------|-------|
| python-magic | ✅ | ❌ | ✅ | Requires libmagic |
| python-magic-bin | ❌ | ✅ | ❌ | Bundled libmagic |
| pywin32 | ❌ | ✅ | ❌ | Windows-only |
| portalocker | ✅ | ✅ (pywin32) | ✅ | Uses pywin32 on Windows |

### 5.3 Handling Hash Mismatches

If you encounter hash mismatches:

1. **Do not regenerate locks locally on non-Linux** - this can introduce platform-specific hashes
2. **Check if the package has platform-specific wheels** - some packages have different wheels per platform
3. **Use `--no-verify-hashes` only for local development** (never in CI/prod)
4. **Report the issue** - platform markers may need to be added

## 6. Node.js Lock Determinism

### 6.1 Lock File Strategy

The root `package-lock.json` is canonical:

```bash
# Install with exact versions
npm ci

# DO NOT use npm install in CI (can modify lock file)
```

### 6.2 Regenerating Node Locks

```bash
# Update all packages
npm update

# Regenerate lock file
rm -rf node_modules package-lock.json
npm install
```

## 7. CI Enforcement

### 7.1 Lock Drift Detection

CI checks for lock drift:
- `pip-compile --dry-run` to verify no changes needed
- `npm ci` strict mode (fails if lock file would change)

### 7.2 Blocking on Lock Issues

Lock issues block PRs:
- Missing lock files
- Stale lock files (dependencies changed but lock not updated)
- Invalid lock file format

## 8. Troubleshooting

### 8.1 "Hash mismatch" Error

**Cause**: Package has different content per platform or version mismatch.

**Solution**:
1. Verify you're using the canonical lock file
2. Check platform markers
3. Regenerate on Linux if needed

### 8.2 "Package not found" Error

**Cause**: Platform-specific package missing marker.

**Solution**:
1. Add platform marker to `pyproject.toml`
2. Regenerate locks
3. Test on affected platform

### 8.3 "Lock file out of date" Error

**Cause**: `pyproject.toml` changed but locks not regenerated.

**Solution**:
```bash
pip-compile --output-file=requirements.txt pyproject.toml
```
