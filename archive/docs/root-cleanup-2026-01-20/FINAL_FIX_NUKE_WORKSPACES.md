# FINAL FIX: Nuke All Extra Workspaces

## The Real Problem (Found!)

Cursor stores **122 workspaces** in its configuration. Each workspace is a separate window/project. When you reopen Cursor, it tries to restore ALL of them.

That's why the invisible windows keep reappearing - **Cursor was designed to remember all opened projects**.

## The Solution

**Delete all workspaces except the main one.** This forces Cursor to start fresh with just your current project.

## DO THIS NOW

### Step 1: Close Cursor Completely

⚠️ **CRITICAL: Close ALL Cursor windows!**
- Close your main window
- Verify Cursor is gone from Task Manager
- Don't open it again until step 3

### Step 2: Run the Workspace Nuker

Open PowerShell and run:

```powershell
cd C:\dev\Autopack
.\scripts\nuke_cursor_workspaces.ps1
```

What it does:
1. Verifies Cursor is closed
2. Finds your main workspace (the one with your current project)
3. **DELETES all other 121 workspaces**
4. Keeps only the main one
5. Tells you when done

**IMPORTANT**: When it asks to confirm, type exactly: `DELETE ALL`

### Step 3: Reopen Cursor

After the script completes:
- Open Cursor normally
- **It will open with ONLY your main project**
- **No invisible windows will appear**

### Step 4: Test Auto-Fill

Once Cursor opens with just the main window:

```batch
cd C:\dev\Autopack
auto_fill_empty_slots.bat
```

New Cursor windows should appear in the grid slots!

## What Gets Deleted

- 121 workspace directories
- Each contains old project/window state
- Safe to delete - just clears old sessions

**Kept**: 1 workspace (your current main project)

## Why This Works

When Cursor starts:
1. It checks `workspaceStorage` folder
2. Finds all stored workspaces
3. Tries to restore them all as windows
4. This is why invisible windows appeared

By deleting 121 of them:
- Cursor finds only 1 workspace to restore
- Opens just that one
- No invisible windows
- Problem solved!

## Quick Reference

```powershell
# Step 1: Close Cursor (all windows!)

# Step 2: Run the nuker (confirm with 'DELETE ALL')
cd C:\dev\Autopack
.\scripts\nuke_cursor_workspaces.ps1

# Step 3: Reopen Cursor (should be clean)

# Step 4: Test auto-fill
auto_fill_empty_slots.bat
```

## If Something Goes Wrong

If you accidentally delete the wrong workspace:
- The git backups are fine (no code lost)
- Just reopen Cursor and reconfigure your workspace
- Session state is not critical data

## Important Notes

✅ This is **permanent** - those 121 workspaces won't come back
✅ Your code/projects are **safe** - this only deletes session state
✅ Settings/extensions are **preserved** - stored elsewhere
✅ Git history is **fine** - no repo changes

---

**Ready?** Follow the 4 steps above, then report results!
