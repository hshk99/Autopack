# Implementation Revision: Tidy Storage (Correcting Misalignments)

## Purpose
This document identifies what was implemented incorrectly or incompletely by the previous cursor session and provides concrete fixes to align with the user's TRUE intentions.

---

## ❌ Critical Misunderstandings in Previous Implementation

### 1. **Cursor File Creation - Fundamentally Misunderstood**

**What was implemented:**
- CLI helpers (`run_output_paths.py`, `create_run_with_routing.py`) that suggest where files should go
- Assumption that Cursor can somehow use these helpers at creation time

**Why this is WRONG:**
- **Cursor cannot execute Python helpers during file creation** - when Cursor creates `IMPLEMENTATION_PLAN_TIDY_STORAGE.md`, it just creates it in the workspace root
- The helpers are useless for Cursor-created files because Cursor has no mechanism to call them
- The user's intention was NOT to add helpers for Cursor - it was to handle the **reality that Cursor creates files in the wrong place**

**What the user ACTUALLY wants:**
1. **Accept the limitation**: Cursor will create files in the workspace root (we can't change this)
2. **Post-creation cleanup**: Add logic to `tidy_workspace.py` to detect Cursor-created files in the root and route them based on:
   - File name analysis (e.g., `IMPLEMENTATION_PLAN_*` → plans folder)
   - Content analysis (read first few lines to determine purpose)
   - Date/time proximity to known run IDs
3. **User education**: A README section telling the user where to manually move files after Cursor creates them

**Fix Required:**
- Remove or repurpose the CLI helpers (they're only useful for Autopack's own run creation)
- Add a `detect_and_route_cursor_files()` function in `tidy_workspace.py` that:
  - Scans workspace root for recently created MD files
  - Analyzes names/content to determine project and purpose
  - Moves them to the correct location
- Add README guidance for manual file placement

---

### 2. **Autopack Run Creation - Not Actually Fixed**

**What was implemented:**
- `route_run_output()` helper function
- Wrapper script that "suggests" where runs should go

**Why this is WRONG:**
- The helpers don't actually CHANGE where Autopack creates run folders
- Autopack's actual run-creation code (in `autonomous_executor.py` or similar) was never modified
- This means Autopack will continue creating runs in the wrong locations

**What the user ACTUALLY wants:**
- **Modify Autopack's run creation code directly** so it creates folders in the right place from the start
- Example: If the run ID is `fileorg-country-uk-20251205-132826`, Autopack should create:
  ```
  .autonomous_runs/file-organizer-app-v1/runs/fileorg-country-uk/fileorg-country-uk-20251205-132826/
  ```
  NOT:
  ```
  .autonomous_runs/fileorg-country-uk-20251205-132826/
  ```

**Fix Required:**
- Find Autopack's run creation code (likely in `src/autopack/` or similar)
- Modify it to:
  1. Extract project ID from run context
  2. Extract family name from run ID (prefix before timestamp)
  3. Create directory: `.autonomous_runs/{project}/runs/{family}/{run_id}/`
  4. Place all run outputs (logs, errors, results) inside this directory

---

### 3. **Run Log Location - Never Investigated**

**What was implemented:**
- Assumption that logs should be in run folders (correct)
- No investigation of where logs currently ARE

**Why this is WRONG:**
- The user explicitly asked: "where did Autopack put the run log files?"
- This question was never answered
- Without knowing where logs currently go, we can't fix the problem

**What the user ACTUALLY wants:**
1. **Investigation**: Find where Autopack currently creates run logs
2. **Fix the source**: Modify Autopack's logging setup to write logs inside the run folder
3. **Verify**: After changes, confirm logs appear in the correct location

**Fix Required:**
- Search Autopack codebase for logging configuration
- Find where run logs are written (likely a `logs/` directory or similar)
- Change log file path to: `{run_output_dir}/run.log`
- Ensure error logs also go to: `{run_output_dir}/errors/`

---

### 4. **Truth Source Files - Location Not Clarified**

**What was implemented:**
- Plan says "move truth files to `C:\dev\Autopack\docs`"
- No distinction between Autopack truth sources vs project truth sources

**Why this is WRONG:**
- The user has TWO different types of truth sources:
  1. **Autopack project truth** (README, tidy docs, etc.) → should be in `C:\dev\Autopack\docs\`
  2. **File Organizer project truth** (WHATS_LEFT_TO_BUILD, etc.) → should be in `.autonomous_runs/file-organizer-app-v1/docs/`
- Current files are scattered:
  - `README.md` in both locations
  - `WHATS_LEFT_TO_BUILD.md` in multiple locations
  - Duplicates everywhere

**What the user ACTUALLY wants:**
- **One canonical location per file**:
  - Autopack's README → `C:\dev\Autopack\README.md` (already correct)
  - File Organizer's WHATS_LEFT_TO_BUILD → `.autonomous_runs/file-organizer-app-v1/docs/WHATS_LEFT_TO_BUILD.md`
  - Consolidated docs → `.autonomous_runs/file-organizer-app-v1/docs/CONSOLIDATED_*.md`
- **Update scripts that read/write these files** to use the canonical locations
- **Merge duplicates carefully** during tidy, preserving the most recent content

**Fix Required:**
- Identify all truth source files and their canonical locations
- Add logic to `tidy_workspace.py` to detect duplicates and merge them
- Update any scripts that read/write truth sources to use canonical paths
- Add protection so tidy never moves truth sources

---

### 5. **Runs Folder Structure - Half-Implemented**

**What was implemented:**
- Tidy script can move runs to `archive/superseded/runs/{family}/{run_id}/`
- Family extraction logic exists

**Why this is INCOMPLETE:**
- This only handles **moving existing runs** after they're created wrong
- Doesn't fix the root cause (Autopack creating runs in the wrong place)
- Doesn't handle **active runs** (only archived ones)

**What the user ACTUALLY wants:**
- **Active runs**: `.autonomous_runs/file-organizer-app-v1/runs/{family}/{run_id}/`
- **Archived runs**: `.autonomous_runs/file-organizer-app-v1/archive/superseded/runs/{family}/{run_id}/`
- **No cleanup needed** - runs created in the right place from the start

**Fix Required:**
- Step 1: Fix Autopack to create active runs in the right location (see #2 above)
- Step 2: Add an archival mechanism:
  - After a run completes, move it from `runs/{family}/{run_id}/` to `archive/superseded/runs/{family}/{run_id}/`
  - Or: leave recent runs in `runs/` and only move old ones during tidy

---

## ✅ What Was Done Correctly

1. **Family grouping logic** - Extracting family name from run ID works correctly
2. **Bucket definitions** - Plans, analysis, logs, scripts, etc. are well-defined
3. **Protection for critical files** - DBs, rules, and protected files are excluded from moves
4. **Normalization logic** - Removing duplicate `archive/superseded` segments is correct
5. **Logging** - SHA256 tracking and activity logging is good

---

## 🎯 Concrete Action Plan to Fix Everything

### Phase 1: Investigation (DO FIRST)
1. **Find Autopack's run creation code**
   - Search for: `autonomous_executor`, `create_run`, `setup_run_directory`
   - Identify: Where run output directories are created
   - Document: Current behavior

2. **Find Autopack's logging setup**
   - Search for: logging configuration, `getLogger`, log file paths
   - Identify: Where run logs are written
   - Document: Current log locations

3. **Audit truth source files**
   - List all instances of: `README.md`, `WHATS_LEFT_TO_BUILD*.md`, `CONSOLIDATED_*.md`
   - Identify: Which are duplicates vs. legitimate separate files
   - Document: Canonical location for each

### Phase 2: Fix Autopack's Behavior (CORE FIX)
1. **Modify run creation to use correct paths**
   ```python
   # Pseudocode for autonomous_executor.py or similar
   def create_run_directory(run_id: str, project_id: str) -> Path:
       family = extract_family(run_id)  # e.g., "fileorg-country-uk"
       base = Path(f".autonomous_runs/{project_id}/runs/{family}/{run_id}")
       base.mkdir(parents=True, exist_ok=True)
       return base
   ```

2. **Fix logging to write inside run directory**
   ```python
   # Set up logging to go to run directory
   log_file = run_dir / "run.log"
   error_dir = run_dir / "errors"
   error_dir.mkdir(exist_ok=True)
   ```

3. **Update project context detection**
   - Ensure Autopack knows which project it's working on
   - Pass project_id through the execution pipeline
   - Default to "file-organizer-app-v1" for file organizer runs

### Phase 3: Cursor File Routing (PRACTICAL FIX)
1. **Add cursor file detection to tidy_workspace.py**
   ```python
   def detect_and_route_cursor_files(root: Path, project_id: str) -> List[Action]:
       """Detect files created by Cursor in workspace root and route them."""
       actions = []
       # Look for MD files in root that were created recently
       for file in root.glob("*.md"):
           # Skip protected files
           if is_protected(file):
               continue

           # Determine destination based on name/content
           dest = classify_cursor_file(file, project_id)
           if dest:
               actions.append(Action("move", file, dest, "cursor file routing"))

       return actions

   def classify_cursor_file(file: Path, project_id: str) -> Path | None:
       """Classify a Cursor-created file based on name and content."""
       name = file.name.lower()

       # Read first few lines for context
       try:
           content = file.read_text(encoding="utf-8")[:500].lower()
       except:
           content = ""

       # Determine bucket
       if "implementation_plan" in name or "plan" in name:
           bucket = "plans"
       elif "analysis" in name or "review" in name:
           bucket = "analysis"
       elif "prompt" in name or "delegation" in name:
           bucket = "prompts"
       elif "log" in name or "diagnostic" in name:
           bucket = "diagnostics"
       else:
           # Check content
           if any(word in content for word in ["plan:", "implementation", "design"]):
               bucket = "plans"
           elif any(word in content for word in ["analysis", "findings", "review"]):
               bucket = "analysis"
           else:
               # Fallback to unsorted
               return REPO_ROOT / "archive" / "unsorted" / file.name

       # Determine project
       if project_id == "autopack" or "autopack" in name or "tidy" in name:
           return REPO_ROOT / "archive" / bucket / file.name
       else:
           project_root = REPO_ROOT / ".autonomous_runs" / project_id
           return project_root / "archive" / bucket / file.name
   ```

2. **Call this in tidy main loop**
   ```python
   # In main(), before other tidy operations
   if root == REPO_ROOT:
       cursor_actions = detect_and_route_cursor_files(root, "file-organizer-app-v1")
       execute_actions(cursor_actions, dry_run, checkpoint_dir, logger, run_id)
   ```

### Phase 4: Truth Source Consolidation
1. **Define canonical locations**
   ```python
   TRUTH_SOURCES = {
       "autopack": {
           "README.md": REPO_ROOT / "README.md",
           "consolidated_docs.md": REPO_ROOT / "docs" / "consolidated_docs.md",
       },
       "file-organizer-app-v1": {
           "README.md": REPO_ROOT / ".autonomous_runs" / "file-organizer-app-v1" / "README.md",
           "WHATS_LEFT_TO_BUILD.md": REPO_ROOT / ".autonomous_runs" / "file-organizer-app-v1" / "docs" / "WHATS_LEFT_TO_BUILD.md",
           "WHATS_LEFT_TO_BUILD_MAINTENANCE.md": REPO_ROOT / ".autonomous_runs" / "file-organizer-app-v1" / "docs" / "WHATS_LEFT_TO_BUILD_MAINTENANCE.md",
           "CONSOLIDATED_BUILD.md": REPO_ROOT / ".autonomous_runs" / "file-organizer-app-v1" / "docs" / "CONSOLIDATED_BUILD.md",
           "CONSOLIDATED_STRATEGY.md": REPO_ROOT / ".autonomous_runs" / "file-organizer-app-v1" / "docs" / "CONSOLIDATED_STRATEGY.md",
       }
   }
   ```

2. **Merge duplicates during tidy**
   - Find all instances of each truth source file
   - Compare by last modified time
   - Move newer content to canonical location
   - Archive old copies to `archive/superseded/refs/`

3. **Update scripts that reference truth sources**
   - Search codebase for hardcoded paths to these files
   - Replace with references to TRUTH_SOURCES dictionary
   - Ensure all readers/writers use canonical paths

### Phase 5: User Documentation
1. **Add to README.md (Autopack root)**
   ```markdown
   ## File Organization Guidelines

   ### Cursor-Created Files
   When Cursor creates files like `IMPLEMENTATION_PLAN_*.md`, they will appear in the workspace root.

   **For Autopack project files:**
   - Plans/designs → Move to `archive/plans/`
   - Analysis/reviews → Move to `archive/analysis/`
   - If unsure → Leave in `archive/unsorted/` and run tidy

   **For File Organizer project files:**
   - Plans → Move to `.autonomous_runs/file-organizer-app-v1/archive/plans/`
   - Analysis → Move to `.autonomous_runs/file-organizer-app-v1/archive/analysis/`
   - If unsure → Leave in `archive/unsorted/` and run tidy

   ### Running Tidy
   ```bash
   # Dry run to see what would be moved
   python scripts/tidy_workspace.py --root . --dry-run --verbose

   # Execute (creates checkpoint first)
   python scripts/tidy_workspace.py --root . --execute
   ```

   ### Truth Source Locations
   - Autopack README: `C:\dev\Autopack\README.md`
   - File Organizer docs: `.autonomous_runs/file-organizer-app-v1/docs/`
   - Never manually edit files in `archive/` - these are archived versions
   ```

2. **Add to File Organizer README**
   ```markdown
   ## Project Structure

   ```
   .autonomous_runs/file-organizer-app-v1/
   ├── docs/                    # Truth sources (WHATS_LEFT_TO_BUILD, etc.)
   ├── runs/                    # Active runs
   │   ├── fileorg-country-uk/  # Family: UK country pack runs
   │   ├── fileorg-docker/      # Family: Docker-related runs
   │   └── ...
   ├── archive/
   │   ├── plans/               # Archived plans
   │   ├── analysis/            # Archived analysis docs
   │   └── superseded/
   │       └── runs/            # Old run outputs
   │           ├── fileorg-country-uk/
   │           └── ...
   ```
   ```

---

## 🔍 Validation Checklist

After implementing fixes, verify:

- [ ] New Autopack runs create folders in: `.autonomous_runs/{project}/runs/{family}/{run_id}/`
- [ ] Run logs appear inside run folders, not scattered elsewhere
- [ ] Cursor-created files in root get detected and routed by tidy
- [ ] Truth source files have one canonical location each
- [ ] No more nested `archive/superseded/archive/superseded/...` after tidy
- [ ] Family grouping works for all run types (fileorg-country-uk, fileorg-docker, etc.)
- [ ] README clearly explains where to put files manually
- [ ] `archive/unsorted/` only contains genuinely unclassifiable files

---

## 📊 Summary: What Needs to Change

| Component | Current State | Required Action |
|-----------|--------------|-----------------|
| Autopack run creation | Creates in `.autonomous_runs/{run_id}/` | Modify to create in `.autonomous_runs/{project}/runs/{family}/{run_id}/` |
| Run logging | Unknown location | Investigate, then fix to write inside run folders |
| Cursor file routing | CLI helpers (useless) | Replace with auto-detection in tidy_workspace.py |
| Truth sources | Scattered, duplicated | Define canonical locations, merge duplicates |
| User guidance | Missing | Add comprehensive README sections |
| Active vs archived runs | No distinction | Active in `runs/`, archived in `archive/superseded/runs/` |

---

## 🚀 Recommended Implementation Order

1. **First**: Investigation phase - understand current behavior
2. **Second**: Fix Autopack run creation - stop the mess at the source
3. **Third**: Add Cursor file detection - handle the reality of Cursor's behavior
4. **Fourth**: Truth source consolidation - eliminate duplicates
5. **Fifth**: Documentation - empower the user to maintain organization
6. **Last**: Clean up existing mess with tidy (only after source is fixed)

---

## 💡 Key Insights

1. **CLI helpers for Cursor = Wrong approach** - Cursor can't use Python helpers during file creation
2. **Suggestions != Fixes** - The route helpers only suggest paths; they don't change actual behavior
3. **Fix the source, not just the symptoms** - Modifying Autopack's run creation is more important than building sophisticated tidy logic
4. **User can help** - Clear documentation enables the user to manually place files correctly when Cursor creates them in the wrong spot
5. **One canonical location per file** - Truth sources should never be duplicated

---

---

## 🔧 Assessment: Backend Run Creation vs Client-Side Wrappers

### Context from Previous Implementation

The previous cursor mentioned:
> "Outstanding/code not touched: backend run creation still uses the API; the new wrapper is the client-side path setter (no backend change). If you want, I can also wire any specific run-creator scripts to call this helper or set the output dirs explicitly."

### Architecture Understanding

After investigation, here's how Autopack actually works:

1. **Run Creation Scripts** (e.g., `create_fileorg_country_runs.py`):
   - Python scripts that call the Autopack API (`POST /runs/start`)
   - They only create the run **record** in the database
   - They do NOT create local directories

2. **Autonomous Executor** (`autonomous_executor.py`):
   - Polls the API for QUEUED runs
   - Uses `RunFileLayout` class to create local directories
   - `RunFileLayout` gets base directory from `settings.autonomous_runs_dir = ".autonomous_runs"`
   - Creates structure: `.autonomous_runs/{run_id}/` (WRONG - missing project and family!)

3. **Current Wrapper** (`create_run_with_routing.py`):
   - Calls API to create run
   - Prints "suggested" output directory
   - **Does nothing** - the executor still creates directories in the wrong place

### Should the "Outstanding" Note Be Incorporated?

**Answer: PARTIALLY - But Misunderstood**

The previous cursor was on the right track but missed the real fix:

#### ❌ What They Suggested (Wrong Approach):
- "Wire specific run-creator scripts to call this helper"
- This is **useless** because run-creator scripts don't create local directories at all
- They only create database records via API

#### ✅ What Actually Needs to Happen:

**The fix must be in `autonomous_executor.py` and `RunFileLayout` class**, not in the run-creator scripts.

Here's what needs to change:

```python
# FILE: src/autopack/file_layout.py
# CURRENT (WRONG):
class RunFileLayout:
    def __init__(self, run_id: str, base_dir: Optional[Path] = None):
        self.run_id = run_id
        if base_dir is not None:
            self.base_dir = base_dir / run_id
        else:
            self.base_dir = Path(settings.autonomous_runs_dir) / run_id  # ❌ Missing project/family

# NEEDED (CORRECT):
class RunFileLayout:
    def __init__(self, run_id: str, project_id: str = None, base_dir: Optional[Path] = None):
        self.run_id = run_id
        self.project_id = project_id or self._detect_project(run_id)
        self.family = self._extract_family(run_id)

        if base_dir is not None:
            self.base_dir = base_dir / self.project_id / "runs" / self.family / run_id
        else:
            # New structure: .autonomous_runs/{project}/runs/{family}/{run_id}/
            base = Path(settings.autonomous_runs_dir)
            self.base_dir = base / self.project_id / "runs" / self.family / run_id

    def _detect_project(self, run_id: str) -> str:
        """Detect project from run_id prefix"""
        if run_id.startswith("fileorg-"):
            return "file-organizer-app-v1"
        elif run_id.startswith("backlog-"):
            return "file-organizer-app-v1"
        else:
            return "autopack"

    def _extract_family(self, run_id: str) -> str:
        """Extract family name from run_id (prefix before timestamp)"""
        import re
        # Match pattern: prefix-YYYYMMDD-HHMMSS or prefix-timestamp
        match = re.match(r"(.+?)-(?:\d{8}-\d{6}|\d{10,})", run_id)
        if match:
            return match.group(1)
        return run_id  # Fallback to full run_id as family
```

Then in `autonomous_executor.py`:
```python
# Pass project context when creating RunFileLayout
self.run_layout = RunFileLayout(
    run_id=self.run_id,
    project_id=self.project_id  # Must be determined from run context
)
```

### Specific Code Changes Needed

**Phase 2 of the action plan should be updated to include:**

1. **Modify `src/autopack/file_layout.py`:**
   - Add `project_id` parameter to `__init__`
   - Add `family` extraction logic
   - Change `base_dir` construction to include project and family

2. **Modify `src/autopack/autonomous_executor.py`:**
   - Detect `project_id` from run context (scope paths, description, run_id prefix)
   - Pass `project_id` when instantiating `RunFileLayout`
   - Update any hardcoded `.autonomous_runs/{run_id}` references

3. **Update `src/autopack/config.py` (optional):**
   - Could add `project_detection_rules` if needed for complex cases

4. **DO NOT modify run-creator scripts:**
   - They only call the API
   - They don't create local directories
   - The wrapper `create_run_with_routing.py` is **cosmetic only** - it prints suggestions but doesn't enforce them

### Verdict on "Outstanding" Note

**Should be REPLACED with this guidance:**

```markdown
## Backend Run Directory Creation - Critical Fix Required

**Previous Approach (Incomplete):**
- Created CLI wrappers that "suggest" paths ❌
- Assumed run-creator scripts control directory creation ❌
- Did not modify the actual code that creates directories ❌

**Correct Approach:**
1. Modify `RunFileLayout` class in `src/autopack/file_layout.py` to:
   - Accept `project_id` parameter
   - Extract `family` from `run_id`
   - Create path: `.autonomous_runs/{project}/runs/{family}/{run_id}/`

2. Modify `autonomous_executor.py` to:
   - Detect project from run context
   - Pass project_id to RunFileLayout

3. Delete or repurpose cosmetic wrappers:
   - `create_run_with_routing.py` - doesn't actually fix anything
   - `run_output_paths.py` - only useful for manual reference

**Why This Matters:**
- Run-creator scripts (e.g., `create_fileorg_country_runs.py`) only call the API
- The API creates database records, not local directories
- `autonomous_executor.py` creates the actual local directories using `RunFileLayout`
- **Fix must be in `RunFileLayout`, not in API client scripts**

**Priority:** HIGH - This is the root cause of the directory mess
```

### Summary

| Component | Previous Understanding | Actual Reality | What Needs to Change |
|-----------|----------------------|----------------|---------------------|
| Run-creator scripts | "Wire them to use helpers" ❌ | Only call API, don't create directories | **Nothing** - they're fine as-is |
| `create_run_with_routing.py` | "Wrapper that helps" ❌ | Prints suggestions, doesn't enforce | **Delete or document as reference only** |
| `autonomous_executor.py` | Not mentioned ❌ | **Actually creates directories** | **Add project detection and pass to RunFileLayout** |
| `RunFileLayout` class | Not mentioned ❌ | **Constructs directory paths** | **Add project_id/family to path construction** |

**Conclusion:** The "Outstanding" note identifies the right symptom (backend not fixed) but prescribes the wrong solution (wire run-creator scripts). The real fix is in `RunFileLayout` and `autonomous_executor.py`.

---

## End of Revision Document
