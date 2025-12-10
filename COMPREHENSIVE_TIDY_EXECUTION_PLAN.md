# Comprehensive Workspace Tidy - Execution Plan
**Date**: 2025-12-11
**Goal**: Organize scattered files across workspace root, docs/, prompts/, logs/, and nested subdirectories
**Safety**: Git commits (pre/post) + checkpoint archives + dry-run validation

---

## Context

### Current Situation
Scattered files and folders across multiple locations created by Cursor and Autopack:
- **Root**: `C:\dev\Autopack\` (workspace root files)
- **Docs**: `C:\dev\Autopack\docs\`
- **Prompts**: `C:\dev\Autopack\prompts\claude\`
- **Logs**: `C:\dev\Autopack\logs\` (with nested subdirs like `logs/autopack/`, `logs/archived_runs/`)
- **Autonomous Runs**: `C:\dev\Autopack\.autonomous_runs\` (already in default scope)
- **Nested Folders**: Multiple layers of subdirectories (e.g., `.autopack/config/`, `scripts/backend/`, etc.)

### Default Scope
The tidy system defaults to:
- `.autonomous_runs/file-organizer-app-v1`
- `.autonomous_runs`
- `archive`

### Key Capabilities
✅ **Recursive Directory Traversal**: `os.walk()` at line 1225 handles nested folders automatically
✅ **Cursor File Detection**: Scans workspace root for files created in last 7 days (line 753-802)
⚠️ **Limitation**: Cursor detection only scans immediate root directory, not nested subdirs

### Safety Mechanisms
1. **Git Pre-Commit** (line 1071-1072): Captures state before any changes
2. **Git Post-Commit**: Captures state after all operations
3. **Checkpoint ZIP Archives** (line 691-693): SHA256-verified backups of moved files
4. **Dry-Run Mode**: Preview all actions before execution

### Recovery Options
1. **Git Reset**: `git reset --hard <tag_name>` to manual checkpoint
2. **Checkpoint Restore**: Extract files from ZIP archives in `.autonomous_runs/<run_id>/checkpoint/`
3. **Interactive Correction**: `python scripts/correction/interactive_correction.py --flagged`

---

## Assessment

### Can We Tidy All at Once?
**YES** - The tidy system can handle multiple directories in one run via `tidy_scope.yaml`

### Should We Run One by One?
**RECOMMENDED FOR FIRST TIME** - Phased approach allows validation at each step

### Are Git Commits Sufficient Failsafe?
**YES** - Three-layer protection:
1. Manual checkpoint tag (before everything)
2. Git pre-commit (automatic)
3. Checkpoint ZIP archives (file-level recovery)

### Should We Expand Default Scope?
**NO** - This is a **one-time cleanup**. After tidying:
- Cursor file detection (last 7 days) handles new files in root automatically
- Future files will be created in organized locations
- Scope expansion would be permanent and unnecessary

### Nested Folder Handling
**AUTOMATIC** - When you add directories like `docs/`, `prompts/claude/`, `logs/` to the scope:
- `os.walk()` automatically traverses all subdirectories recursively
- Files in `docs/plans/drafts/` or `logs/autopack/old/` will be found and classified
- No additional configuration needed

---

## Recommended Approach: Option A (Conservative Phased)

### Phase 1: Safety Preparation (5 minutes)

#### 1.1 Manual Checkpoint
```bash
cd /c/dev/Autopack

# Create manual safety tag
git add -A
git commit -m "Pre-tidy checkpoint: Manual safety commit before comprehensive workspace tidy"
git tag -a tidy-checkpoint-2025-12-11 -m "Manual checkpoint before comprehensive tidy - safe rollback point"

# Verify tag created
git tag -l tidy-*
git log -1 --oneline
```

#### 1.2 Verify Git Status
```bash
# Ensure clean state
git status

# Should show: "nothing to commit, working tree clean"
# If not clean, commit or stash changes first
```

#### 1.3 Identify Nested Folders
```bash
# List all directories that will be tidied (including nested)
find . -maxdepth 4 -type d ! -path "./.git/*" ! -path "./node_modules/*" ! -path "./.venv/*" ! -path "./venv/*" ! -path "./src/*" ! -path "./tests/*" | head -50

# This shows the nested structure that os.walk() will traverse
```

**Expected Output**: Directories like:
- `./.autopack/config/`
- `./.claude/commands/`
- `./prompts/claude/`
- `./logs/autopack/`
- `./logs/archived_runs/`
- `./scripts/backend/`
- etc.

---

### Phase 2: Dry-Run Assessment (15 minutes)

Test each directory individually to preview actions **including nested folder contents**.

#### 2.1 Test Workspace Root
```bash
cd /c/dev/Autopack

# Dry-run on workspace root (will find files in nested subdirs too)
PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="postgresql://autopack:autopack@localhost:5432/autopack" QDRANT_HOST="http://localhost:6333" python scripts/tidy_workspace.py --root . --dry-run --verbose 2>&1 | tee dry-run-root.log

# Review output
tail -50 dry-run-root.log
```

**What to Check**:
- ✅ Files from nested folders are detected (e.g., `.autopack/config/settings.json`, `prompts/claude/system.md`)
- ✅ Cursor files (last 7 days) identified correctly
- ✅ Classification confidence scores (should be >0.60)
- ⚠️ Any unusual paths (like `C:Usershshk9.claudeplans` - investigate if found)
- ❌ No errors or exceptions

#### 2.2 Test Docs Directory
```bash
# Dry-run on docs/ (including nested subdirs)
PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="postgresql://autopack:autopack@localhost:5432/autopack" QDRANT_HOST="http://localhost:6333" python scripts/tidy_workspace.py --root docs --dry-run --verbose 2>&1 | tee dry-run-docs.log

# Count files to be moved
grep -c "Would move" dry-run-docs.log
```

**What to Check**:
- ✅ Documentation files classified as `report` or `plan`
- ✅ Files in nested subdirs (if any) are found
- ✅ Destinations look correct (e.g., `.autonomous_runs/autopack/reports/`)

#### 2.3 Test Prompts Directory
```bash
# Dry-run on prompts/claude/ (nested folder)
PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="postgresql://autopack:autopack@localhost:5432/autopack" QDRANT_HOST="http://localhost:6333" python scripts/tidy_workspace.py --root prompts/claude --dry-run --verbose 2>&1 | tee dry-run-prompts.log

grep -c "Would move" dry-run-prompts.log
```

**What to Check**:
- ✅ Prompt files classified as `prompt` or `plan`
- ✅ Nested structure preserved in destination paths

#### 2.4 Test Logs Directory
```bash
# Dry-run on logs/ (including logs/autopack/, logs/archived_runs/, etc.)
PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="postgresql://autopack:autopack@localhost:5432/autopack" QDRANT_HOST="http://localhost:6333" python scripts/tidy_workspace.py --root logs --dry-run --verbose 2>&1 | tee dry-run-logs.log

grep -c "Would move" dry-run-logs.log
```

**What to Check**:
- ✅ Log files classified as `log`
- ✅ Files in nested subdirs (`logs/autopack/`, `logs/archived_runs/`) are found
- ✅ API logs, test logs, run logs classified correctly

#### 2.5 Unusual Paths Check
```bash
# Check if unusual paths exist (like C:Usershshk9.claudeplans)
find . -name "*Users*" -o -name "*C:*" 2>/dev/null

# If found, investigate what these are
ls -la ./C:Usershshk9.claudeplans 2>/dev/null || echo "Path not found (good)"
```

**Action if Found**:
- Investigate what these paths are
- May need to manually delete or move before tidy
- Could be malformed paths from Cursor/Windows issues

---

### Phase 3: Execution (30-45 minutes)

#### Option A: Conservative (Step-by-Step) - **RECOMMENDED**

Execute one directory at a time with validation between steps.

##### Step 3.1: Tidy Workspace Root
```bash
cd /c/dev/Autopack

# Execute tidy on workspace root (includes nested folders)
PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="postgresql://autopack:autopack@localhost:5432/autopack" QDRANT_HOST="http://localhost:6333" python scripts/tidy_workspace.py --root . --execute --verbose 2>&1 | tee tidy-root-execution.log

# Verify git commit was created
git log -2 --oneline
# Should show: "tidy auto checkpoint (post)" and "tidy auto checkpoint (pre)"

# Check moved files
grep "Moved:" tidy-root-execution.log | head -20
```

**Validation**:
```bash
# Verify files were moved correctly
ls -la .autonomous_runs/autopack/ | head -20
ls -la .autonomous_runs/file-organizer-app-v1/ | head -20

# Check workspace root is cleaner
ls -la . | grep -E "\.md|\.py|\.log" | wc -l
# Should be significantly fewer files
```

##### Step 3.2: Tidy Docs Directory
```bash
# Execute tidy on docs/ (includes nested subdirs)
PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="postgresql://autopack:autopack@localhost:5432/autopack" QDRANT_HOST="http://localhost:6333" python scripts/tidy_workspace.py --root docs --execute --verbose 2>&1 | tee tidy-docs-execution.log

# Verify git commit
git log -1 --oneline
```

**Validation**:
```bash
# Check docs/ is cleaner
ls -la docs/ | wc -l

# Verify moved files
grep "Moved:" tidy-docs-execution.log | head -10
```

##### Step 3.3: Tidy Prompts Directory
```bash
# Execute tidy on prompts/claude/
PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="postgresql://autopack:autopack@localhost:5432/autopack" QDRANT_HOST="http://localhost:6333" python scripts/tidy_workspace.py --root prompts/claude --execute --verbose 2>&1 | tee tidy-prompts-execution.log

git log -1 --oneline
```

##### Step 3.4: Tidy Logs Directory
```bash
# Execute tidy on logs/ (includes logs/autopack/, logs/archived_runs/, etc.)
PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="postgresql://autopack:autopack@localhost:5432/autopack" QDRANT_HOST="http://localhost:6333" python scripts/tidy_workspace.py --root logs --execute --verbose 2>&1 | tee tidy-logs-execution.log

git log -1 --oneline
```

##### Step 3.5: Review After Each Step
```bash
# After EACH step above, review:

# 1. Check for errors
grep -i "error\|exception\|failed" tidy-<directory>-execution.log

# 2. Check files were moved correctly
grep "Moved:" tidy-<directory>-execution.log | head -10

# 3. Verify git commits
git log -3 --oneline

# 4. If issues found, STOP and investigate before proceeding
```

---

#### Option B: All-at-Once (Faster) - Use After Testing Option A Once

Create temporary scope file and execute all directories in one run.

##### Step 3B.1: Create Comprehensive Scope
```bash
cd /c/dev/Autopack

# Create temporary tidy scope for comprehensive cleanup
cat > tidy_scope_comprehensive.yaml << 'EOF'
# Comprehensive one-time tidy scope (includes nested folders automatically)
roots:
  - "."
  - "docs"
  - "prompts/claude"
  - "logs"
  - ".autonomous_runs/file-organizer-app-v1"
  - ".autonomous_runs"
  - "archive"

# Database overrides (optional - use default if not specified)
db_overrides: {}

# Purge mode (false = move to archive; true = delete - DO NOT USE)
purge: false
EOF

# Verify file created
cat tidy_scope_comprehensive.yaml
```

##### Step 3B.2: Execute All-at-Once
```bash
# Run tidy for all scopes (recursive traversal automatic)
python scripts/run_tidy_all.py 2>&1 | tee tidy-all-execution.log

# This will:
# 1. Create git pre-commit for workspace root "."
# 2. Process all files in "." including nested subdirs (os.walk)
# 3. Create git post-commit
# 4. Repeat for docs/, prompts/claude/, logs/, etc.
# 5. Create checkpoint ZIPs for each root
```

**Validation**:
```bash
# Check all git commits created
git log -10 --oneline
# Should see pairs of "tidy auto checkpoint (pre)" and "(post)"

# Count total files moved
grep -c "Moved:" tidy-all-execution.log

# Check for errors
grep -i "error\|exception\|failed" tidy-all-execution.log
```

---

### Phase 4: Post-Tidy Verification (15 minutes)

#### 4.1 Verify Workspace is Organized
```bash
cd /c/dev/Autopack

# Check workspace root is clean
ls -la . | grep -E "\.md|\.py|\.log|\.json" | wc -l
# Should be minimal (only protected files like README.md, package.json, etc.)

# Check nested folders are cleaner
ls -la docs/ | wc -l
ls -la prompts/claude/ | wc -l
ls -la logs/ | wc -l

# Check organized storage
ls -la .autonomous_runs/autopack/
ls -la .autonomous_runs/file-organizer-app-v1/
```

#### 4.2 Verify Classification Accuracy
```bash
# Check classification accuracy from logs
grep "confidence:" tidy-all-execution.log | head -20

# Look for low-confidence classifications
grep "confidence:" tidy-all-execution.log | awk '{print $NF}' | sort -n | head -10
# If many files have confidence <0.60, investigate
```

#### 4.3 Review Potential Misclassifications
```bash
# Use interactive correction tool to review flagged files
PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="postgresql://autopack:autopack@localhost:5432/autopack" QDRANT_HOST="http://localhost:6333" python scripts/correction/interactive_correction.py --flagged

# This will show files with:
# - Confidence <0.60
# - PostgreSQL/Qdrant disagreements
# - Generic/unknown classifications
```

#### 4.4 Manual Spot Checks
```bash
# Spot check a few files to verify correct destinations

# Check autopack scripts
ls -la .autonomous_runs/autopack/scripts/ | head -10

# Check file organizer plans
ls -la .autonomous_runs/file-organizer-app-v1/plans/ | head -10

# Check logs
ls -la .autonomous_runs/autopack/logs/ | head -10

# Check reports
ls -la .autonomous_runs/autopack/reports/ | head -10
```

#### 4.5 Make Corrections if Needed
```bash
# If misclassifications found, use batch correction
PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="postgresql://autopack:autopack@localhost:5432/autopack" QDRANT_HOST="http://localhost:6333" python scripts/correction/batch_correction.py --pattern "WRONG_*.md" --project autopack --type script --execute

# Or use interactive correction
PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="postgresql://autopack:autopack@localhost:5432/autopack" QDRANT_HOST="http://localhost:6333" python scripts/correction/interactive_correction.py --interactive
```

---

### Phase 5: Cleanup (5 minutes)

#### 5.1 Remove Temporary Scope File (if used Option B)
```bash
cd /c/dev/Autopack

# Remove temporary comprehensive scope
rm tidy_scope_comprehensive.yaml

# Verify default scope still works
python scripts/run_tidy_all.py --help
```

#### 5.2 Create Final Commit
```bash
# Commit any corrections made
git add -A
git commit -m "Post-tidy corrections and cleanup"

# View final state
git log -5 --oneline
```

#### 5.3 Create Success Tag
```bash
# Tag successful tidy completion
git tag -a tidy-complete-2025-12-11 -m "Comprehensive workspace tidy completed successfully"

# List all tidy tags
git tag -l tidy-*
```

---

## Recovery Procedures (If Things Go South)

### Option 1: Full Git Reset (Nuclear Option)
```bash
cd /c/dev/Autopack

# Reset to manual checkpoint tag
git reset --hard tidy-checkpoint-2025-12-11

# Verify state
git log -1 --oneline
git status
```

### Option 2: Restore from Checkpoint ZIP
```bash
# Find checkpoint archives
find .autonomous_runs -name "checkpoint_*.zip" -mtime -1

# Example restore (replace <run_id> with actual run ID)
cd .autonomous_runs/<run_id>/checkpoint/
unzip checkpoint_<timestamp>.zip -d /c/dev/Autopack/

# Verify restored files
ls -la /c/dev/Autopack/
```

### Option 3: Selective File Restoration
```bash
# Extract specific file from checkpoint
unzip -l checkpoint_<timestamp>.zip | grep "filename.md"
unzip checkpoint_<timestamp>.zip "path/to/filename.md" -d /c/dev/Autopack/
```

---

## Nested Folder Handling - Technical Details

### How `os.walk()` Handles Nested Folders

The tidy system uses **recursive directory traversal** at [tidy_workspace.py:1225](scripts/tidy_workspace.py#L1225):

```python
for dirpath, dirnames, filenames in os.walk(root):
    dirnames[:] = [d for d in dirnames if d not in {".git", "node_modules", ".pytest_cache", "__pycache__", ".venv", "venv"}]
    for fname in filenames:
        src = Path(dirpath) / fname
        # Process file...
```

**What This Means**:
- ✅ **Automatic Recursion**: When you specify `--root docs`, it processes:
  - `docs/file1.md`
  - `docs/plans/file2.md`
  - `docs/plans/drafts/file3.md` (any depth)

- ✅ **Nested Structure Preserved**: If a file is at `logs/autopack/api_test.log`, the classification system preserves context from the nested path

- ✅ **Protected Directories Skipped**: `.git`, `node_modules`, `.venv`, etc. are automatically excluded

### Example: Logs Directory with Nested Folders

If you have:
```
logs/
  api_test.log
  autopack/
    run_20251211.log
    old/
      run_20251210.log
  archived_runs/
    archive_20251209.log
```

When you run `--root logs`, **all 4 files** will be found and classified, regardless of nesting level.

### Unusual Paths Warning

If `find` command found paths like `./C:Usershshk9.claudeplans`:
- This is likely a malformed Windows path created by Cursor
- **Action**: Investigate before tidy:
  ```bash
  ls -la "./C:Usershshk9.claudeplans"
  file "./C:Usershshk9.claudeplans"/*
  ```
- If it's junk, manually delete:
  ```bash
  rm -rf "./C:Usershshk9.claudeplans"
  ```

---

## Summary

### Key Decisions
1. ✅ **Phased Approach (Option A)** - Recommended for first-time comprehensive tidy
2. ✅ **Nested Folders Handled Automatically** - No special configuration needed
3. ✅ **Git Commits as Failsafe** - Pre/post commits + manual checkpoint tag
4. ❌ **No Scope Expansion** - This is one-time cleanup only

### Timeline Estimate (Option A)
- **Phase 1**: 5 minutes (safety preparation)
- **Phase 2**: 15 minutes (dry-run assessment)
- **Phase 3**: 30-45 minutes (step-by-step execution)
- **Phase 4**: 15 minutes (verification + corrections)
- **Phase 5**: 5 minutes (cleanup)
- **Total**: ~70-85 minutes

### Timeline Estimate (Option B)
- **Phase 1**: 5 minutes
- **Phase 2**: 10 minutes (condensed dry-run)
- **Phase 3B**: 10-15 minutes (all-at-once execution)
- **Phase 4**: 15 minutes
- **Phase 5**: 5 minutes
- **Total**: ~45-50 minutes

### Success Criteria
✅ Workspace root cleaned (only protected files remain)
✅ Nested folders organized (docs/, prompts/, logs/ subdirs tidied)
✅ Files classified to correct projects (autopack vs file-organizer-app-v1)
✅ Classification confidence >0.60 for >98% of files
✅ Git commits show clean history (pre/post pairs)
✅ No errors or exceptions in execution logs
✅ Manual spot checks confirm correct destinations

### Next Steps
**User Decision Required**:
1. Choose **Option A (Conservative)** or **Option B (All-at-Once)**
2. Approve execution of Phase 1 (Safety Preparation)
3. Proceed with dry-run assessment (Phase 2)

---

**Status**: READY FOR APPROVAL
**Recommended**: Start with **Phase 1** → **Phase 2** (dry-run) → Review results → Decide on Phase 3 approach
**Safety**: 3-layer protection (manual checkpoint tag + automatic git commits + checkpoint ZIPs)
**Reversibility**: Full rollback available at any point
