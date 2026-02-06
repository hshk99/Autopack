---
name: cleanup
description: Cleanup - remove old worktree directories from C:\dev that were locked
---

# Cleanup Old Worktree Directories

Remove old Autopack worktree directories from `C:\dev\` that couldn't be removed previously due to file locks.

## Your Task

1. **Check Archive for reference**: Read `C:\Users\hshk9\OneDrive\Backup\Desktop\Archive\` to see which projects have been archived
2. **Check failed_removals.txt**: Read `C:\dev\streamdeck_auto_build\failed_removals.txt` for specific directories that failed to remove
3. **Find old worktrees**: List directories in `C:\dev\` matching pattern `Autopack_w*` (e.g., Autopack_w1_loop002, Autopack_w2_fix-lint)
4. **Remove directories**: For each old worktree directory found:
   - First try: `Remove-Item -Path "C:\dev\Autopack_w*" -Recurse -Force`
   - If that fails, try removing `.git` lock first: `Remove-Item -Path "C:\dev\Autopack_w*\.git\*.lock" -Force`
   - Then retry removal
5. **Clean git worktree list**: Run `git worktree prune` in `C:\dev\Autopack` to clean stale entries

## Commands to Run

```powershell
# List what will be removed
Get-ChildItem -Path "C:\dev" -Directory -Filter "Autopack_w*" | Select-Object FullName

# Remove all Autopack worktree directories
Get-ChildItem -Path "C:\dev" -Directory -Filter "Autopack_w*" | ForEach-Object {
    Write-Host "Removing: $($_.FullName)"
    Remove-Item -Path $_.FullName -Recurse -Force -ErrorAction SilentlyContinue
}

# Prune git worktree references
Set-Location "C:\dev\Autopack"
git worktree prune

# Clear failed_removals.txt
Set-Content -Path "C:\dev\streamdeck_auto_build\failed_removals.txt" -Value ""
```

## Important Notes
- Make sure no Cursor windows are open in these directories before cleanup
- The OCR handler should be stopped during cleanup
- After cleanup, the directories can be recreated fresh by the automation
