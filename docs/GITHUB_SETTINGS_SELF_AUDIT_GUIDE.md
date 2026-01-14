# GitHub Settings Self-Audit Guide

**Purpose**: Make “beyond-repo” GitHub settings (branch protections, required checks) auditable and drift-detectable.

This repo’s “ideal state” depends on GitHub settings that are **not stored in git**. This guide documents:
- the **recommended** protection policy for `main`
- how to run a **self-audit** against live GitHub settings
- how to treat drift (fix settings vs update policy expectations)

---

## 1) Repo slug

Autodetected from `git remote origin` when run in a clone. For this repo:

- `hshk99/Autopack`

You can also provide it explicitly via `--repo owner/repo` or `GITHUB_REPO`.

---

## 2) Auth (recommended)

Create a GitHub token and export it:

- **Env var**: `GITHUB_TOKEN` (or `GH_TOKEN`)

Note: GitHub’s branch protection endpoints commonly return **401** without a token (even for public repos).

Minimum permissions to *read* branch protection vary based on repo settings, but in general:
- public repos: read-only may work
- private repos / fine-grained restrictions: token must have repo read access

---

## 3) Run the audit

### Default (Markdown to stdout)

```bash
python scripts/ci/github_settings_self_audit.py
```

PowerShell:

```powershell
python scripts/ci/github_settings_self_audit.py
```

### Explicit repo + branch

```bash
python scripts/ci/github_settings_self_audit.py --repo hshk99/Autopack --branch main
```

PowerShell:

```powershell
python scripts/ci/github_settings_self_audit.py --repo hshk99/Autopack --branch main
```

### Save a report file

```bash
python scripts/ci/github_settings_self_audit.py --out archive/diagnostics/github_settings_audit.md
```

### JSON output

```bash
python scripts/ci/github_settings_self_audit.py --format json --out archive/diagnostics/github_settings_audit.json
```

### Fail on drift (exit code 1)

```bash
python scripts/ci/github_settings_self_audit.py --check
```

---

## 4) Policy expectations (default)

The script’s default expectations are intentionally conservative and map to Autopack’s “mechanical enforcement” goals:

- **Required checks**: `lint`, `docs-sot-integrity`, `test-core`
- **Require PR reviews**: enabled
- **Require conversation resolution**: enabled
- **Force-pushes**: disallowed
- **Branch deletions**: disallowed
- **Linear history**: not required by default (optional hardening)

Note: GitHub check names may appear with workflow prefixes (e.g., `Autopack CI / lint`). The audit matches required checks by **suffix** to avoid false failures.

---

## 5) Custom policy file (optional)

If you want to override defaults, pass a JSON file:

```bash
python scripts/ci/github_settings_self_audit.py --policy config/github_settings_audit_policy.json
```

Example policy file:

```json
{
  "required_checks": ["lint", "docs-sot-integrity", "test-core"],
  "require_prs": true,
  "require_conversation_resolution": true,
  "require_linear_history": false,
  "disallow_force_pushes": true,
  "disallow_deletions": true
}
```

---

## 6) What to do when the audit fails

- **If protections are missing/loose**: update GitHub branch protection settings to match policy.
- **If policy is too strict**: update the policy (and document rationale in `docs/IMPROVEMENTS_GAP_ANALYSIS.md` / governance docs).
- **If check names don’t match**: adjust `required_checks` to the actual check-run names you want enforced (prefer stable job names).
