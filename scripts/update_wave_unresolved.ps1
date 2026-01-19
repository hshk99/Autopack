# Update Wave1_All_Phases.md with proper actionable prompt format for unresolved issues

# Read the file
$content = Get-Content 'C:\Users\hshk9\OneDrive\Backup\Desktop\Wave1_All_Phases.md' -Raw

# Find and remove everything from the old Unresolved Issues section onwards
$pattern = '(?s)---\s*\r?\n\s*## Unresolved Issues.*$'
$content = $content -replace $pattern, ''

# Also clean up excessive trailing blank lines
$content = $content.TrimEnd()

# Ensure it ends with the last phase separator
if (-not $content.EndsWith('---')) {
    $content += "`n`n---"
}

# Add the new unresolved issues section with actionable prompt format
$newSection = @"


---

## Unresolved Issues (Wave 1)

**Summary**: The following phases have CI failures that need to be fixed. Each phase below is formatted as an actionable prompt.

---

## Phase: feat003 [UNRESOLVED]

**Title**: Fix CI Failure for feat003
**PR**: #331
**Issue**: CI failed: verify-structure, lint, Core Tests (Must Pass)
**Recorded**: 2026-01-19 22:21:31

I'm working in git worktree: C:\dev\Autopack_w1_feat003
Branch: wave1/feat-003-nullstore-logging

Task: Fix the CI failure for PR #331

The CI run has failed with: CI failed: verify-structure, lint, Core Tests (Must Pass)

Please investigate and fix the issue:

1. Check the CI logs for PR #331 to identify the specific failure
2. Since "Core Tests (Must Pass)" failed:
   - Review the test output to find which tests failed
   - Fix the code to make tests pass
   - Run tests locally before pushing: pytest tests/ -v
3. Push the fix and verify CI passes
4. Once CI passes, the PR can be merged

**Last Updated**: 2026-01-19 22:45:00
"@

$content += $newSection

# Write back
Set-Content 'C:\Users\hshk9\OneDrive\Backup\Desktop\Wave1_All_Phases.md' -Value $content -Encoding UTF8
Write-Host 'Updated Wave1_All_Phases.md with actionable prompt format for unresolved issues'
