# BUILD-183: Workspace Structure Warnings Reduction

## Goal

Reduce noise from workspace structure verification warnings while maintaining enforcement integrity. BUILD-182 enabled workspace structure enforcement that exits non-zero on errors. This build reduces false-positive warnings from intentionally allowed patterns.

## Scope

This build addresses three warning categories:

1. **Root `security/` directory warning** - Allowlist by design
2. **`docs/` Non-SOT file warnings** - Pattern-based allowlist for known build/report docs
3. **Missing archive buckets** - Ensure required buckets exist

## Warning Categories Eliminated

### 1. Root `security/` Directory (Allowlisted)

**Warning:** `Unexpected directory at root: security`

**Reason for allowlisting:** The `security/` directory contains security baselines, threat models, and audit artifacts. It is intentionally at the repo root for visibility and is not subject to tidy operations.

### 2. `docs/` Non-SOT File Patterns (Allowlisted)

**Warnings:** Multiple `Non-SOT file in docs/: <filename>` warnings

**Patterns allowlisted:**

| Pattern | Reason |
|---------|--------|
| `BUILD-*.md` | Build documentation (per-task implementation docs) |
| `BUILD_*.md` | Alternate build doc naming convention |
| `*_COMPLETION*.md` | Task completion reports |
| `*_REPORT*.md` | Analysis and status reports |
| `*_OPERATIONS*.md` | Operations documentation |
| `*_PLAYBOOK*.md` | Operational playbooks |
| `*_HOWTO*.md` | How-to guides |
| `*_STATUS*.md` | Status tracking documents |
| `*_PLAN*.md` | Planning documents |
| `*_SUMMARY*.md` | Summary documents |
| `*_DECISIONS*.md` | Decision records |
| `*_POLICY*.md` | Policy documents |
| `*_LOG*.md` | Log files (security, debug, etc.) |
| `*_STANDARDS*.md` | Standards documentation |
| `PROMPT_*.md` | Prompt documentation |
| `P0_*.md` | Priority-0 documents |
| `PRE_*.md` | Pre-task analysis docs |
| `REMAINING_*.md` | Remaining work docs |
| `LEARNED_*.json` | Learned rules/mitigations |
| `CHAT_HISTORY_*.md` | Chat history extracts |
| `CHAT_HISTORY_*.json` | Chat history extracts |

**Important:** Unknown docs files still emit warnings (default-warn behavior preserved). SOT ledger rules remain unchanged.

### 3. Archive Buckets

The main `archive/` directory already contains all required buckets:
- `plans/`
- `prompts/`
- `scripts/`
- `unsorted/`
- `reports/`
- `research/`
- `diagnostics/`
- `superseded/`

No new buckets needed for the main archive.

## Acceptance Criteria

1. `verify_workspace_structure.py` does NOT warn on root `security/` directory
2. `verify_workspace_structure.py` does NOT warn on `docs/BUILD-*.md` and other allowlisted patterns
3. `verify_workspace_structure.py` DOES warn on unknown/unclassified docs files
4. Enforcement remains blocking: errors > 0 causes non-zero exit
5. All tests pass deterministically

## Files Changed

- `scripts/tidy/verify_workspace_structure.py` - Added allowlists
- `tests/tidy/test_verify_workspace_structure.py` - New test file for verifier behavior

## Non-Goals

- Converting docs files to SOT (they remain non-SOT, just allowlisted)
- Moving or reorganizing existing files
- Changing enforcement behavior (errors still fail CI)
