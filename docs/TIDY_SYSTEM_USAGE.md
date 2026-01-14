# Tidy System Usage Guide

**Version**: 2.0 (BUILD-147 Phase A P11+)
**Date**: 2026-01-01

## Quick Start

The tidy system now has a **unified entrypoint** that matches README expectations:

```bash
# Preview what would be cleaned (dry-run, safe)
python scripts/tidy/tidy_up.py

# Apply changes
python scripts/tidy/tidy_up.py --execute

# Aggressive cleanup - reduce docs/ to SOT-only
python scripts/tidy/tidy_up.py --execute --docs-reduce-to-sot
```

## Repair Mode (create missing structure safely)

If you have a project workspace under `.autonomous_runs/<project>/` that is missing the required 6-file SOT ledgers or archive buckets, you can repair it safely:

```bash
# Preview what would be created (no routing/consolidation)
python scripts/tidy/tidy_up.py --repair --repair-only

# Repair a specific project (dry-run)
python scripts/tidy/tidy_up.py --repair --repair-only --repair-projects file-organizer-app-v1

# Apply the repairs
python scripts/tidy/tidy_up.py --repair --repair-only --repair-projects file-organizer-app-v1 --execute
```

Notes:
- Repair mode is conservative: it only creates missing directories/files; it does not move or delete content.
- `.autonomous_runs/autopack` is a runtime workspace and is excluded from project-SOT repair.

## Root SOT Duplicate Report (helps unblock tidy execution)

If `tidy_up.py --execute` aborts because a canonical SOT file exists at **repo root** and also in `docs/` with different content (e.g., `BUILD_HISTORY.md`), generate a merge report:

```bash
# Preview report paths (no files written)
python scripts/tidy/tidy_up.py --report-root-sot-duplicates --report-root-sot-duplicates-only

# Write the report to archive/diagnostics/
python scripts/tidy/tidy_up.py --report-root-sot-duplicates --report-root-sot-duplicates-only --execute
```

The report includes SHA-256 hashes and a truncated diff to make manual merging faster.

## ⚠️ Important: Resolve Root SOT Duplicates First

**Before running tidy in execute mode**, ensure there are no divergent SOT files at repo root:

If you have copies of SOT files (like `BUILD_HISTORY.md`, `DEBUG_LOG.md`) at both **repo root** and **docs/**, tidy will:
- **Block execution** if the files differ (to prevent data loss)
- **Auto-move to archive** if the files are identical duplicates

### Resolution Steps (if blocked):
1. **Compare files**: `diff BUILD_HISTORY.md docs/BUILD_HISTORY.md`
2. **Merge unique content** from root version into `docs/` version
3. **Delete root version**: `rm BUILD_HISTORY.md`
4. **Commit**: `git add -A && git commit -m 'fix: merge duplicate SOT files'`
5. **Re-run tidy**: `python scripts/tidy/tidy_up.py --execute`

Tidy will never silently overwrite divergent SOT files - it will exit with a clear error message listing blocked files.

## What Tidy Up Does

The unified `tidy_up.py` script performs **5 phases** of workspace organization:

### Phase 1: Root Routing
Routes stray files from repo root to proper locations:
- Log files (`*.log`) → `archive/diagnostics/logs/`
- Markdown docs → `archive/{reports|plans|prompts|research}/`
- Python scripts → `scripts/{backend|test|utility}/`
- JSON phase files → `archive/plans/`
- Config files → `archive/plans/`

### Phase 2: Docs Hygiene
Enforces that `docs/` contains only **truth sources**, not an inbox:
- **Conservative mode** (default): Reports violations, doesn't move files
- **Reduction mode** (`--docs-reduce-to-sot`): Moves non-SOT files to archive

**Allowed in docs/**:
- 6-file SOT structure (PROJECT_INDEX.json, BUILD_HISTORY.md, DEBUG_LOG.md, ARCHITECTURE_DECISIONS.md, FUTURE_PLAN.md, LEARNED_RULES.json)
- Additional truth files (INDEX.md, CHANGELOG.md, WORKSPACE_ORGANIZATION_SPEC.md, CURSOR_PROMPT_*.md, etc.)
- Allowed subdirectories: guides/, cli/, cursor/, examples/, api/, autopack/, research/, reports/

### Phase 3: Archive Consolidation
Consolidates archive markdown into SOT ledgers:
- Uses semantic classification (GLM-4.7 LLM by default)
- Appends summaries to BUILD_HISTORY.md, DEBUG_LOG.md, ARCHITECTURE_DECISIONS.md
- Moves consolidated files to `archive/superseded/`

### Phase 4: Verification
Validates workspace structure matches [WORKSPACE_ORGANIZATION_SPEC.md](WORKSPACE_ORGANIZATION_SPEC.md):
- Checks SOT files exist
- Ensures required archive buckets exist
- Reports violations

### Phase 5: SOT Re-index Handoff (Dirty Marker System)

Tidy uses a "dirty marker" to trigger SOT re-indexing when needed:

**How it works**:
1. **Tidy creates marker** when SOT files are modified:
   - Marker location: `.autonomous_runs/sot_index_dirty_autopack.json`
   - Marker content: `{"dirty": true, "timestamp": "...", "reason": "tidy modified SOT"}`
   - **Only created when SOT actually changed** (not just when Phase 3 runs)

2. **Executor detects marker** on next startup:
   - If `AUTOPACK_ENABLE_SOT_MEMORY_INDEXING=true`, executor checks for marker
   - If marker exists, executor re-indexes SOT documents into semantic memory
   - After successful re-indexing, executor deletes marker

3. **Result**: Semantic retrieval always uses latest consolidated docs

**When marker is created**:
- ✅ SOT file moved from root to docs/
- ✅ Non-SOT file moved into docs/ (docs hygiene violation)
- ✅ Archive consolidation actually modified BUILD_HISTORY.md or other SOT files
- ❌ Archive consolidation ran but made no SOT changes (optimized)

**Marker location by project**:
- Autopack: `.autonomous_runs/sot_index_dirty_autopack.json`
- Sub-project: `.autonomous_runs/<project>/.autonomous_runs/sot_index_dirty.json`

**Manual cleanup** (if needed):
```bash
# Remove marker manually (forces re-index on next run)
rm .autonomous_runs/sot_index_dirty_autopack.json
```

## Command Reference

### Basic Usage

```bash
# Dry-run (default) - preview changes
python scripts/tidy/tidy_up.py

# Execute changes
python scripts/tidy/tidy_up.py --execute

# Reduce docs/ to SOT-only (aggressive)
python scripts/tidy/tidy_up.py --execute --docs-reduce-to-sot

# Skip archive consolidation (faster)
python scripts/tidy/tidy_up.py --execute --skip-archive-consolidation

# Verbose output
python scripts/tidy/tidy_up.py --execute --verbose
```

### Project Scope

```bash
# Tidy specific project
python scripts/tidy/tidy_up.py --execute --project file-organizer-app-v1

# Custom roots (overrides tidy_scope.yaml)
python scripts/tidy/tidy_up.py --execute --scope archive .autonomous_runs
```

### Checkpoints

```bash
# Skip checkpoint creation (not recommended)
python scripts/tidy/tidy_up.py --execute --no-checkpoint

# Create git commits before/after
python scripts/tidy/tidy_up.py --execute --git-checkpoint
```

## Verification Tool

Verify workspace structure independently:

```bash
# Verify Autopack project structure
python scripts/tidy/verify_workspace_structure.py

# Verify specific project
python scripts/tidy/verify_workspace_structure.py --project file-organizer-app-v1

# Generate JSON report
python scripts/tidy/verify_workspace_structure.py --json-output verify_report.json

# Generate markdown report
python scripts/tidy/verify_workspace_structure.py --markdown-output verify_report.md
```

**Exit codes**:
- `0` - Structure is valid
- `1` - Structure has violations

## Workspace Organization Rules

See [WORKSPACE_ORGANIZATION_SPEC.md](WORKSPACE_ORGANIZATION_SPEC.md) for complete specification.

### Repository Root

**Allowed**:
- Essential config files (.gitignore, .env, README.md, pyproject.toml, package.json, etc.)
- Database files (*.db - development only)
- Allowed directories (.git, src/, tests/, scripts/, docs/, archive/, etc.)

**Disallowed** (will be routed by tidy):
- Markdown files (except README.md)
- Log files
- Python scripts (except build tools)
- JSON files (except configs)

### Docs Directory

**Purpose**: Single Source of Truth (SOT) for project knowledge

**Core SOT** (6 files):
1. PROJECT_INDEX.json
2. BUILD_HISTORY.md
3. DEBUG_LOG.md
4. ARCHITECTURE_DECISIONS.md
5. FUTURE_PLAN.md
6. LEARNED_RULES.json

**Additional allowed**:
- INDEX.md, CHANGELOG.md, WORKSPACE_ORGANIZATION_SPEC.md
- CURSOR_PROMPT_*.md, IMPLEMENTATION_PLAN_*.md, SOT_*.md
- Subdirectories: guides/, cli/, cursor/, examples/, api/, autopack/, research/, reports/

### Archive Directory

**Purpose**: Inbox + history for processed artifacts

**Required buckets**:
- plans/ - Implementation plans, phase definitions
- reports/ - Build reports, analysis summaries
- research/ - Research notes, investigations
- prompts/ - Prompt templates
- diagnostics/ - Debug logs, error reports
  - diagnostics/logs/ - Log files
- scripts/ - Archived scripts
- superseded/ - Consolidated files (won't be reprocessed)
- unsorted/ - Temporary inbox

## Preventing Root Clutter

### Centralized Logging Configuration

To prevent log files from accumulating in the repository root, use the centralized logging configuration:

```python
from autopack.logging_config import setup_logging

# Quick setup
logger = setup_logging(run_id="build-147", project_id="autopack")
logger.info("Starting execution...")
logger.error("Error occurred: %s", error_message)

# Advanced setup
from autopack.logging_config import configure_logging

logger = configure_logging(
    run_id="batch-drain",
    project_id="autopack",
    log_level="DEBUG",
    log_to_console=True,
    log_to_file=True,
)
```

**Default log locations**:
- Main project: `archive/diagnostics/logs/`
- Sub-projects: `.autonomous_runs/{project}/archive/diagnostics/logs/`

**Environment variables**:
- `AUTOPACK_LOG_DIR` - Override default log directory
- `AUTOPACK_LOG_LEVEL` - Set log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)

**For scripts that write logs directly** (not using Python logging):

```python
from autopack.logging_config import get_safe_log_path

# Get safe path in archive/diagnostics/logs/
log_path = get_safe_log_path("batch_drain.log")

with open(log_path, "w", encoding="utf-8") as f:
    f.write("Log content here...\n")
```

### Script Best Practices

When writing new scripts:

1. ✅ **DO**: Use centralized logging (`setup_logging()`)
2. ✅ **DO**: Write logs to `archive/diagnostics/logs/`
3. ✅ **DO**: Use UTF-8 encoding for file operations
4. ❌ **DON'T**: Write logs to current working directory (CWD)
5. ❌ **DON'T**: Create `.log`, `.txt`, or output files at repo root

**Example - Before and After**:

```python
# ❌ BAD - Creates root clutter
with open("batch_drain.log", "w") as f:
    f.write("Starting batch drain...\n")

# ✅ GOOD - Uses centralized logging
from autopack.logging_config import get_safe_log_path

log_path = get_safe_log_path("batch_drain.log")
with open(log_path, "w", encoding="utf-8") as f:
    f.write("Starting batch drain...\n")
```

## Configuration

### Tidy Scope (tidy_scope.yaml)

Override default roots to tidy:

```yaml
# tidy_scope.yaml
roots:
  - .autonomous_runs/file-organizer-app-v1
  - .autonomous_runs
  - archive

db_overrides:
  archive: "sqlite:///custom.db"

purge: false  # true to delete aged artifacts instead of archiving
```

### Semantic Model (config/models.yaml)

Configure LLM for semantic classification:

```yaml
# config/models.yaml
tool_models:
  tidy_semantic: glm-4.7  # or claude-sonnet-4-5, gpt-4o, etc.
```

## Comparison: Old vs New

### Old Tidy System (`run_tidy_all.py`)

- Only tidied `.autonomous_runs` and `archive`
- Did **not** clean repo root or `docs/`
- Required manual intervention for root clutter
- No docs hygiene enforcement

### New Tidy System (`tidy_up.py`)

- ✅ Cleans repo root (Phase 1)
- ✅ Enforces docs/ hygiene (Phase 2)
- ✅ Consolidates archive (Phase 3)
- ✅ Verifies structure (Phase 4)
- ✅ SOT re-index handoff (Phase 5)
- ✅ Matches README expectations
- ✅ Single unified command

## Safety Guarantees

1. **Dry-run by default** - No changes without `--execute`
2. **Checkpoint creation** - Zip backup before moves (unless `--no-checkpoint`)
3. **Git checkpoints** - Optional pre/post commits (`--git-checkpoint`)
4. **Validation** - Blocks invalid operations, reports clearly
5. **Idempotency** - Repeated runs don't cause churn
6. **Reversible** - All changes tracked in git, checkpoints available

## Troubleshooting

### "Disallowed file at root" errors

**Cause**: Files in repo root that don't match allowed list

**Fix**: Run `python scripts/tidy/tidy_up.py --execute` to route them to proper locations

### "Missing SOT files" errors

**Cause**: Required SOT files don't exist in docs/

**Fix**: Create missing files or check project structure

### "Disallowed subdirectory in docs/" errors

**Cause**: Unexpected subdirectory in docs/

**Fix**:
- If legitimate, add to DOCS_ALLOWED_SUBDIRS in verify_workspace_structure.py
- If not, run tidy with `--docs-reduce-to-sot` to move to archive

### Archive consolidation fails

**Cause**: Semantic model unavailable or API key missing

**Fix**:
1. Set API key: `export GLM_API_KEY=your-key` (or ANTHROPIC_API_KEY, OPENAI_API_KEY)
2. Check config/models.yaml for correct model
3. Use `--skip-archive-consolidation` to bypass

### Structure validation fails after tidy

**Cause**: Manual files created after tidy run

**Fix**: Run tidy again or manually route files

## Integration with Autopack

### SOT Retrieval (Phase 1.5)

After tidy consolidates docs, the executor can retrieve them:

```python
from autopack.memory_service import MemoryService

# Executor startup checks for dirty flag
if Path(".autonomous_runs/sot_index_dirty_autopack.json").exists():
    memory = MemoryService(...)
    memory.index_sot_docs("autopack", workspace_root, docs_dir)
    # Clear dirty flag
    Path(".autonomous_runs/sot_index_dirty_autopack.json").unlink()

# During execution, retrieve SOT context
context = retrieve_context(
    ...,
    include_sot=True  # Enabled by AUTOPACK_SOT_RETRIEVAL_ENABLED env var
)
```

### Autonomous Workflow

1. Cursor creates files at repo root
2. User runs `python scripts/tidy/tidy_up.py --execute`
3. Tidy routes root files → archive/
4. Tidy consolidates archive → SOT ledgers
5. Tidy marks SOT as dirty
6. Executor startup re-indexes SOT
7. Executor retrieves SOT during `retrieve_context(..., include_sot=True)`

## CI Integration and Enforcement

### GitHub Actions Workflow

Autopack includes a CI workflow (`.github/workflows/verify-workspace-structure.yml`) that automatically verifies workspace organization on every push and pull request.

**Features**:
- Runs workspace structure verification automatically
- Uploads JSON and Markdown reports as artifacts
- Displays verification summary in GitHub Actions UI
- Initially **non-blocking** (continues even with violations)
- Can be promoted to **blocking** once workspace is clean

**Activation**:
The workflow is automatically active for pushes and PRs to `main` and `develop` branches.

**Making it blocking** (after workspace is clean):
Edit `.github/workflows/verify-workspace-structure.yml` and uncomment the `exit 1` line:

```yaml
if [ "$violations" -gt 0 ]; then
  echo "::warning::Found $violations workspace structure violations."
  exit 1  # Uncomment this line to make it blocking
fi
```

### Pre-Commit Hook (Optional)

Prevent committing root clutter in the first place with an optional pre-commit hook:

**Activate the hook**:
```bash
# One-time setup
git config core.hooksPath .githooks
```

**What it does**:
- Blocks commits of disallowed root files (*.log, BUILD-*.md, etc.)
- Warns about SOT file duplicates (BUILD_HISTORY.md at root vs. docs/)
- Suggests running tidy to fix violations
- Can be bypassed with `git commit --no-verify` if needed

**Deactivate the hook**:
```bash
git config --unset core.hooksPath
```

### Integration with Storage Policy

Tidy works in coordination with the Storage Optimizer according to `config/protection_and_retention_policy.yaml`:

**Recommended Order**:
1. **Tidy runs first** - consolidates docs, routes files, marks SOT dirty
2. **Executor re-indexes SOT** - updates semantic memory with consolidated docs
3. **Storage Optimizer runs** - reclaims disk space (respects retention policies)

**Protection Guarantees**:
- **Tidy never deletes protected paths** (src/, tests/, .git/, docs/ SOT, archive/superseded/)
- **Storage Optimizer respects tidy's audit trail** (archive/superseded/ within retention)
- **Both tools consult the unified policy** before any destructive actions

**Absolute Protections** (defined in `config/protection_and_retention_policy.yaml`):
```yaml
protected_globs:
  - "src/**"                    # Source code
  - "tests/**"                  # Test suite
  - ".git/**"                   # Git history
  - "docs/PROJECT_INDEX.json"   # SOT files
  - "docs/BUILD_HISTORY.md"
  - "docs/DEBUG_LOG.md"
  - "docs/ARCHITECTURE_DECISIONS.md"
  - "docs/FUTURE_PLAN.md"
  - "docs/LEARNED_RULES.json"
  - "archive/superseded/**"     # Audit trail
  - "*.db"                      # Databases
```

See [DATA_RETENTION_AND_STORAGE_POLICY.md](archive/superseded/reports/unsorted/DATA_RETENTION_AND_STORAGE_POLICY.md) for complete policy details.

## Migration from Old Tidy

If you were using `run_tidy_all.py`:

1. **Switch to tidy_up.py**: `python scripts/tidy/tidy_up.py --execute`
2. **First run**: Expect many root files to be routed
3. **Docs cleanup**: Use `--docs-reduce-to-sot` if you want aggressive docs/ cleanup
4. **Verify**: Run `python scripts/tidy/verify_workspace_structure.py` after

**Legacy script still available**: `run_tidy_all.py` remains for backward compatibility, but `tidy_up.py` is recommended.

## FAQs

### Q: Will tidy delete my files?

A: No. Tidy **moves** files, it doesn't delete them (unless `--purge` is used with `--prune` for aged artifacts). All moves are reversible via git.

### Q: Can I run tidy multiple times?

A: Yes. Tidy is idempotent - repeated runs won't cause churn. Files already in correct locations won't be moved again.

### Q: What if tidy moves a file I need?

A: Check git history or checkpoints. Restore with `git checkout <file>` or extract from checkpoint zip.

### Q: Do I need to run tidy after every build?

A: No. Run tidy periodically (e.g., weekly, or when root/docs get cluttered). Autopack doesn't create root clutter during normal operation.

### Q: Will tidy modify my source code?

A: No. Tidy only organizes documentation, logs, scripts, and artifacts. It never modifies files in `src/`, `tests/`, or other code directories.

---

**Document Version**: BUILD-147 Phase A P11+ (2026-01-01)
**Related Docs**: [WORKSPACE_ORGANIZATION_SPEC.md](WORKSPACE_ORGANIZATION_SPEC.md), [CURSOR_PROMPT_TIDY.md](CURSOR_PROMPT_TIDY.md)
