# Security Infrastructure Restoration Guide

**Date Archived**: 2026-01-15  
**Reason**: Simplification for private/internal use

## What Was Stashed

This directory contains the SARIF baseline and diff-gate enforcement infrastructure that was previously active in Autopack's CI pipeline:

### Baselines
- `baselines/security/baselines/` - SARIF baseline files for CodeQL, Trivy filesystem, and Trivy container scans
- `baselines/security/README.md` - Documentation for the baseline system

### Scripts
- `scripts/security/diff_gate.py` - Baseline regression enforcement (blocks CI on new findings)
- `scripts/security/normalize_sarif.py` - SARIF normalization for deterministic comparison
- `scripts/security/update_baseline.py` - Baseline update automation
- `scripts/security/update_baseline_for_refactor.py` - Baseline updates during refactoring
- `scripts/security/exemption_classifier.py` - Exemption classification logic
- `scripts/security/generate_security_burndown_counts.py` - Security burndown metrics

### Documentation
- `docs/SECURITY_LOG.md` - Security baseline change log
- `docs/SECURITY_EXCEPTIONS.md` - Documented security exceptions
- `docs/SECURITY_BURNDOWN.md` - Security burndown tracking
- `docs/SECURITY_INVARIANTS.md` - Security invariants documentation
- `docs/SECURITY_BASELINE_AUTOMATION_STATUS.md` - Baseline automation status

### Tests
- `tests/security/` - Unit tests for baseline scripts
- `tests/test_security_baseline_refresh_workflow_contract.py` - Workflow contract tests
- `tests/test_security_invariants.py` - Security invariants tests

### Workflows
- `workflows/security-baseline-refresh.yml` - Automated baseline refresh workflow
- `workflows/security-artifacts.yml` - Security artifact management workflow

## Why It Was Stashed

Autopack is a **private/internal tool** for personal use. The baseline/diff-gate system was designed for:
- Multi-contributor open-source projects
- Distributed deployments requiring regression enforcement
- Enterprise compliance requirements

For private/internal use:
- **Visibility scans remain active** (weekly CVE scans, CodeQL, Trivy) in the GitHub Security tab
- **Baseline regression enforcement removed** to reduce CI complexity
- **Security responsibility clarified**: Downstream projects built with Autopack must implement their own security posture

## Current Security Posture

After simplification, Autopack maintains:
1. **Visibility Scans**: Weekly CVE scans, CodeQL, Trivy (informational, non-blocking)
2. **Secrets Hygiene**: Gitleaks secret scanning
3. **External API Hygiene**: Circuit breakers, rate limiting, timeouts
4. **Multi-Device Auth**: API key authentication for non-local access (Phase 4)
5. **Egress Controls** (Optional Phase 5): Outbound host allowlist

## How to Restore

If you need to restore the baseline infrastructure (e.g., for distributed deployment or open-source release):

### 1. Move Files Back

```bash
# Restore baselines
git mv archive/security-infrastructure/baselines/security/ security/

# Restore scripts
git mv archive/security-infrastructure/scripts/security/ scripts/security/

# Restore docs
git mv archive/security-infrastructure/docs/SECURITY_*.md docs/

# Restore tests
git mv archive/security-infrastructure/tests/security/ tests/security/
git mv archive/security-infrastructure/tests/test_security_baseline_refresh_workflow_contract.py tests/ci/
git mv archive/security-infrastructure/tests/test_security_invariants.py tests/unit/

# Restore workflows
git mv archive/security-infrastructure/workflows/security-baseline-refresh.yml .github/workflows/
git mv archive/security-infrastructure/workflows/security-artifacts.yml .github/workflows/
```

### 2. Update Workflows

Edit `.github/workflows/security.yml` and `.github/workflows/ci.yml` to re-enable:
- Baseline normalization steps
- Diff-gate enforcement steps
- Baseline logging enforcement

### 3. Update archive/.gitignore

Remove `security-infrastructure/` from the allowlist in `archive/.gitignore`.

### 4. Validate

```bash
# Run baseline-dependent tests
pytest tests/security/ tests/ci/test_security_baseline_refresh_workflow_contract.py tests/unit/test_security_invariants.py -v

# Verify workflows reference correct paths
grep -r "scripts/security" .github/workflows/
grep -r "security/baselines" .github/workflows/
```

### 5. Commit

```bash
git add .
git commit -m "feat(security): restore baseline/diff-gate infrastructure

Restore SARIF baseline tooling and diff-gate enforcement for [reason]."
git push
```

## When to Redesign vs. Restore

### Restore As-Is If:
- You need immediate baseline regression enforcement
- The existing system meets your needs
- You're preparing for open-source release or distributed deployment

### Redesign If:
- Autopack becomes a distributed service (consider runtime security posture, not just CI)
- You need different threat models (e.g., multi-tenant, public API)
- You want to integrate with external security platforms (e.g., Snyk, Dependabot)

## Downstream Project Security

If you build projects with Autopack that will be published/monetized:
1. **Threat Model**: Define your specific threats (public API, multi-tenant, data sensitivity)
2. **Secure Hosting**: Use secure infrastructure (HTTPS, firewalls, secrets management)
3. **Release Pipeline**: Implement your own security scanning and approval workflow
4. **Monitoring**: Add runtime security monitoring (intrusion detection, anomaly detection)
5. **Incident Response**: Define incident response procedures

Autopack's internal baseline system is **not** a substitute for downstream project security posture.

## Questions?

If you have questions about restoring or redesigning the security infrastructure, refer to:
- Original implementation: Git history before 2026-01-15
- Security simplification proposal: `docs/reports/SECURITY_SIMPLIFICATION_PROPOSAL.md`
