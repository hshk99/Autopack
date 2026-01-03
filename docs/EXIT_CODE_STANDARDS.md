# Exit Code Standards for Autopack Tools

**BUILD-167**: Standardized exit codes for CI integration and error handling

## Overview

This document defines the exit code conventions used across Autopack's core tools. Consistent exit codes enable reliable CI/CD pipelines, error handling, and automation.

## Standard Exit Codes

| Code | Meaning | Usage | CI Behavior |
|------|---------|-------|-------------|
| 0 | Success | Operation completed successfully with no errors | Pass |
| 1 | Failure | Operation failed due to validation errors or broken state | Fail |
| 2 | Partial Success / Warnings | Operation completed but with warnings or partial results | Depends on context* |
| 130 | User Interrupted | Operation cancelled by user (Ctrl+C, KeyboardInterrupt) | N/A |

*For exit code 2: CI behavior depends on the specific tool and context. See tool-specific sections below.

## Tool-Specific Exit Code Behavior

### check_doc_links.py

**Purpose**: Validates documentation links and prevents link drift

**Exit Codes**:
- **0 (Success)**: All links are valid
  - OR: Broken links found but only in informational categories (not in `fail_on`)
  - Example: Backticks in deep mode, `runtime_endpoint`, `historical_ref`
- **1 (Failure)**: Broken links found in CI-blocking categories
  - Default: `missing_file` in nav mode (README.md, INDEX.md, BUILD_HISTORY.md)
  - Configurable via `--fail-on` flag

**Nav Mode (Default)**:
```bash
python scripts/check_doc_links.py
# Exit 0: All markdown links valid (backticks ignored)
# Exit 1: Missing file referenced in markdown link
```

**Deep Mode**:
```bash
python scripts/check_doc_links.py --deep
# Exit 0: No missing_file violations OR only informational broken links
# Exit 1: missing_file violations found (CI-blocking)
```

**Key Principle**: Deep mode is report-only. Broken links in backticks or historical refs don't fail CI - only real broken markdown links in enforced categories fail.

### sot_db_sync.py

**Purpose**: Synchronizes SOT (Source of Truth) documentation with database state

**Exit Codes**:
- **0 (Success)**: Sync completed successfully
  - Documents were updated
  - OR: No entries found to sync *in a generic workspace context* (when using `--docs-only`)
  - Rationale: In an arbitrary folder, “no entries found” can be an idempotent no-op.
- **1 (Failure)**: Sync failed due to errors
  - Database errors
  - File write errors
  - Schema validation failures
- **2 (Partial Success)**: Some entries synced, some failed
  - At least one entry processed successfully
  - Some entries had validation or write errors
  - Warnings emitted but operation continued
- **130 (User Interrupted)**: User cancelled operation (Ctrl+C)

**Common Usage**:
```bash
# Sync all SOT documentation
python scripts/tidy/sot_db_sync.py
# Exit 0: All synced successfully
# Exit 1: Fatal error during sync
# Exit 2: Partial sync with warnings

# Docs-only mode (no database writes)
python scripts/tidy/sot_db_sync.py --docs-only
# Exit 0: Docs parsed successfully (and optionally indexed in dry-run)
# Exit 1: Doc write errors
```

**Repo-context invariant (IMPORTANT)**:
- In the **Autopack repo**, `--docs-only` is expected to find and parse SOT entries because the repository contains populated SOT ledgers.
- Therefore, in CI (repo context), “no entries found” should be treated as a **regression signal** (bad cwd, parse bug, missing ledgers), not a success case.
- CI smoke tests should require **exit code 0** for `python scripts/tidy/sot_db_sync.py --docs-only` in this repo.

**CI Integration**: Exit code 2 can be treated as success or warning depending on context:
- **Strict CI**: Fail on exit 2 (require all entries to sync cleanly)
- **Permissive CI**: Pass on exit 2 (allow partial syncs with warnings)

### tidy_up.py (Planned)

**Purpose**: Automated file organization and workspace tidying

**Exit Codes** (recommended for consistency):
- **0 (Success)**: Tidy operation completed successfully
  - Files organized as expected
  - OR: No files to tidy (workspace already clean)
- **1 (Failure)**: Tidy operation failed
  - File move errors
  - Lock acquisition failures
  - Validation errors
- **2 (Partial Success)**: Some files tidied, some skipped
  - Locked files skipped with warnings
  - Some paths inaccessible
  - Operation continued despite non-fatal errors
- **130 (User Interrupted)**: User cancelled operation

## Design Principles

### 1. Zero Means Success
Exit code 0 should always mean "operation succeeded according to its intent":
- For validators: All checks passed OR only informational warnings
- For sync tools: Sync completed OR no-op success (nothing to sync)
- For operations: Completed successfully OR idempotent no-op

### 2. One Means Failure
Exit code 1 should indicate a real failure that requires attention:
- Validation failures that break CI
- Fatal errors that prevent completion
- State that contradicts expectations

### 3. Two Means Partial Success
Exit code 2 indicates operation completed but with caveats:
- Some items succeeded, some failed
- Operation completed with non-fatal warnings
- Results may need manual review

**CI Decision**: Whether to treat exit 2 as pass or fail depends on the pipeline's risk tolerance and the specific tool's behavior.

### 4. Informational Never Fails
Informational categories should never cause CI failure:
- Backtick references in deep mode (code examples, not navigation)
- Historical references (intentional documentation of past state)
- Runtime endpoints (created dynamically, not static files)

**Rationale**: Failing CI on informational references creates false positives and discourages comprehensive documentation.

## Migration Notes

### check_doc_links.py Evolution
- **BUILD-158**: Nav mode created (README, INDEX, BUILD_HISTORY only)
- **BUILD-159**: Deep mode added (all docs/**/*.md)
- **BUILD-166**: Backtick filtering - nav ignores backticks, deep includes them
- **BUILD-167**: Exit code refinement - informational refs don't fail deep mode

### sot_db_sync.py Exit Code Clarification
User feedback (BUILD-167):
> "`sot_db_sync --docs-only` 'no entries found': Should be success (exit 0), not regression"

**Resolution**: Exit 0 when no entries found in docs-only mode. This is idempotent success, not failure.

## Testing Exit Codes

### Unit Tests
```python
def test_exit_code_on_broken_links():
    """Test that check_doc_links returns 1 on CI-blocking broken links."""
    result = subprocess.run(
        ["python", "scripts/check_doc_links.py"],
        capture_output=True
    )
    assert result.returncode == 1  # Failure

def test_exit_code_on_informational_only():
    """Test that deep mode returns 0 when only informational refs broken."""
    result = subprocess.run(
        ["python", "scripts/check_doc_links.py", "--deep"],
        capture_output=True
    )
    assert result.returncode == 0  # Success (informational only)
```

### CI Integration Example
```yaml
# GitHub Actions example
- name: Check doc links (nav mode)
  run: python scripts/check_doc_links.py
  # Fails if markdown links broken in README/INDEX/BUILD_HISTORY

- name: Check doc links (deep mode)
  run: python scripts/check_doc_links.py --deep
  continue-on-error: false
  # Fails only on missing_file violations, not backticks/historical

- name: SOT sync verification
  run: python scripts/tidy/sot_db_sync.py --docs-only
  # Exit 0: Synced or no entries (both ok)
  # Exit 1: Fatal error
  # Exit 2: Partial success (may want to fail-fast in CI)
```

## Future Enhancements

### Proposed: Exit Code 3 for Schema Validation
For tools that validate against schemas:
- **3 (Schema Error)**: Input/config fails schema validation
- Distinct from operational failures (exit 1)
- Helps debug configuration vs runtime errors

### Proposed: Verbose Error Codes (100+)
For detailed error reporting in automation:
- **100+**: Reserved for tool-specific detailed error codes
- Example: `101 = DB connection failed`, `102 = Lock timeout`
- Allows automation to take targeted remediation actions

## References

- Standard POSIX exit codes: 0 (success), 1-255 (failure)
- 130 = Interrupted (128 + SIGINT signal 2)
- Linux/Unix convention: Non-zero exit = failure
- CI/CD tools interpret non-zero as pipeline failure

## Related Documentation

- [BUILD-166 Completion Report](BUILD-166_COMPLETION_REPORT.md) - Backtick filtering implementation
- [BUILD-167 Burndown Plan](reports/BUILD-167_DOC_LINK_BURNDOWN_PLAN.md) - Missing file cleanup
- [Debug Log](DEBUG_LOG.md) - Historical context on exit code decisions

---

*Last updated: BUILD-167 (2026-01-03)*
