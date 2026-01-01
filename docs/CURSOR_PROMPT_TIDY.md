# Cursor Prompt: Run Autopack Tidy

**Purpose**: Simple guide for running Autopack's workspace organization (tidy) system.

**Preferred Entrypoint**: Use `scripts/tidy/tidy_up.py` - the unified entrypoint that matches README expectations.

For complete documentation, see [TIDY_SYSTEM_USAGE.md](TIDY_SYSTEM_USAGE.md).

---

## What Tidy Does

The unified tidy system performs **5 phases** of workspace organization:

1. **Root Routing**: Moves stray files from repo root to proper locations
2. **Docs Hygiene**: Enforces docs/ as truth source only (not inbox)
3. **Archive Consolidation**: Consolidates archive markdown into SOT ledgers
4. **Verification**: Validates workspace structure
5. **SOT Re-index Handoff**: Marks SOT dirty for executor re-indexing

**Consolidates into SOT**:
- `docs/BUILD_HISTORY.md` - Build completion ledger
- `docs/DEBUG_LOG.md` - Problem-solving history
- `docs/ARCHITECTURE_DECISIONS.md` - Design decisions

**Safety**: Tidy uses append-only approach for SOT files and blocks on divergent duplicates.

---

## Quick Run Command

```bash
# Preview changes (dry-run, safe)
python scripts/tidy/tidy_up.py

# Execute changes
python scripts/tidy/tidy_up.py --execute

# Skip archive consolidation (faster, for quick cleanup)
python scripts/tidy/tidy_up.py --execute --skip-archive-consolidation
```

**What happens** (full run with consolidation):
1. Routes stray root files to archive/
2. Validates docs/ structure
3. Consolidates archive markdown into SOT (using glm-4.7 LLM)
4. Creates dirty marker for executor re-indexing
5. Generates verification report

**Time**: 5-15 minutes for full consolidation, <1 minute without

---

## Pre-Tidy Checklist

Before running tidy, verify:

- [ ] **Working Directory**: At repo root (`c:\dev\Autopack`)
- [ ] **No Divergent SOT Duplicates**: No copies of SOT files at both root and docs/ with different content (tidy will block if found)
- [ ] **SOT Files Exist**: `docs/BUILD_HISTORY.md`, `docs/DEBUG_LOG.md`, `docs/ARCHITECTURE_DECISIONS.md`
- [ ] **API Key** (if using consolidation): `GLM_API_KEY` environment variable set (for glm-4.7)
- [ ] **No Uncommitted Changes**: Commit or stash changes before running (or use `--git-checkpoint`)

---

## Environment Setup

```bash
# Windows (PowerShell)
$env:PYTHONUTF8 = "1"
$env:GLM_API_KEY = "your-api-key-here"

# Windows (CMD)
set PYTHONUTF8=1
set GLM_API_KEY=your-api-key-here

# Linux/Mac
export PYTHONUTF8=1
export GLM_API_KEY=your-api-key-here
```

---

## Command Options

### Basic Run (Lexical Mode - No LLM)
```bash
PYTHONUTF8=1 python scripts/tidy/run_tidy_all.py --project autopack-framework
```
- Uses keyword matching only (fast, free)
- Less accurate classification
- Good for quick reorganization

### Semantic Mode (Recommended)
```bash
PYTHONUTF8=1 python scripts/tidy/run_tidy_all.py --semantic --project autopack-framework
```
- Uses `glm-4.7` LLM for intelligent classification
- Better accuracy (understands context)
- Requires API key and consumes tokens (~100k-200k tokens typical)

### Custom Semantic Model
```bash
PYTHONUTF8=1 python scripts/tidy/run_tidy_all.py --semantic --semantic-model claude-sonnet-4-5 --project autopack-framework
```
- Override default `glm-4.7` with another model
- Requires appropriate API key (`ANTHROPIC_API_KEY` for Claude)

### Limit Files Processed
```bash
PYTHONUTF8=1 python scripts/tidy/run_tidy_all.py --semantic --semantic-max-files 20 --project autopack-framework
```
- Only process first 20 files (good for testing)

---

## What Gets Tidied

### Included Files
- All `.md` files in `archive/` (recursive)
- Files matching patterns:
  - Build logs (`BUILD-*.md`, `GPT_*.md`)
  - Debug logs (`DBG-*.md`, `DEBUG_*.md`)
  - Architecture docs (`ARCH-*.md`, `ADR-*.md`)
  - Research notes, planning docs, etc.

### Excluded Files/Directories
- `archive/prompts/` - Prompt templates (preserved as-is)
- `archive/research/active/` - Active research (work in progress)
- `archive/ARCHIVE_INDEX.md` - Archive navigation (metadata)
- `README.md` files - Project entry points

---

## After Tidy Completes

### 1. Review Changes
```bash
# See what was added to SOT files
git diff docs/BUILD_HISTORY.md
git diff docs/DEBUG_LOG.md
git diff docs/ARCHITECTURE_DECISIONS.md
```

### 2. Check Tidy Report
```bash
# Find latest report
ls -ltr archive/reports/
# or on Windows
dir /O:D archive\reports\

# Open report (example path)
cat archive/reports/tidy_v7/tidy_summary.md
```

The report shows:
- Files processed
- Classification decisions
- Merge suggestions
- Skipped files

### 3. Commit Results
```bash
git add docs/BUILD_HISTORY.md docs/DEBUG_LOG.md docs/ARCHITECTURE_DECISIONS.md
git commit -m "docs: consolidate archive to SOT via tidy

Processed XX files from archive/ and consolidated to canonical SOT docs.

🤖 Generated with [Claude Code](https://claude.com/claude-code)"
```

---

## Troubleshooting

### Error: "No module named 'autopack'"
**Fix**: Set `PYTHONPATH=src`
```bash
PYTHONUTF8=1 PYTHONPATH=src python scripts/tidy/run_tidy_all.py --semantic --project autopack-framework
```

### Error: "API key not found" or "Invalid API key"
**Fix**: Ensure `GLM_API_KEY` is set in environment
```bash
# Check if set (Windows PowerShell)
$env:GLM_API_KEY

# Check if set (Linux/Mac)
echo $GLM_API_KEY
```

### Error: "UnicodeEncodeError" (Windows)
**Fix**: Set `PYTHONUTF8=1` before running
```bash
set PYTHONUTF8=1
python scripts/tidy/run_tidy_all.py --semantic --project autopack-framework
```

### Tidy Output Looks Wrong
**Check**:
1. Is the correct model configured? See `config/models.yaml:154` (`tool_models.tidy_semantic`)
2. Verify model config:
   ```bash
   PYTHONUTF8=1 python -c "from autopack.model_registry import get_tool_model; print(f'Tidy model: {get_tool_model(\"tidy_semantic\", default=\"glm-4.6\")}')"
   ```
   Expected: `Tidy model: glm-4.7`

### Tidy Crashes or Hangs
**Possible causes**:
- API rate limit hit (wait and retry)
- Network timeout (LLM provider unreachable)
- Out of memory (too many large files)

**Debug**:
1. Check tidy logs in `archive/reports/tidy_v*/tidy.log`
2. Try limiting files: `--semantic-max-files 10`
3. Use lexical mode (no LLM): remove `--semantic` flag

---

## Advanced Usage

### Dry Run (Preview Only)
```bash
# See what would be tidied without modifying files
PYTHONUTF8=1 python scripts/tidy/tidy_workspace.py archive/ --semantic --dry-run
```

### Tidy Specific Directory
```bash
# Tidy only a subdirectory
PYTHONUTF8=1 python scripts/tidy/tidy_workspace.py archive/builds/ --semantic
```

### Custom Truth Files
```bash
# Use different SOT file locations
PYTHONUTF8=1 python scripts/tidy/tidy_workspace.py archive/ \
  --semantic \
  --truth-files docs/BUILD_HISTORY.md,docs/DEBUG_LOG.md,docs/CUSTOM.md
```

### Enable Merge Suggestions
```bash
# Get LLM suggestions for merging duplicates
PYTHONUTF8=1 python scripts/tidy/run_tidy_all.py \
  --semantic \
  --enable-merge-suggestions \
  --project autopack-framework
```

---

## Model Configuration

Tidy semantic model is configured centrally in `config/models.yaml`:

```yaml
# config/models.yaml line 154
tool_models:
  tidy_semantic: glm-4.7
```

**To change the model**:
1. Edit `config/models.yaml:154`
2. Change `glm-4.7` to your preferred model (e.g., `claude-sonnet-4-5`, `gpt-4o`)
3. Set appropriate API key environment variable
4. Run tidy (no code changes needed)

**Model aliases** (config/models.yaml line 148):
- `glm-tidy` → `glm-4.7` (semantic reference)
- `glm-legacy` → `glm-4.6` (old version)

---

## Tidy System Architecture

### How It Works
1. **Scan**: Find all `.md` files in target directory (default: `archive/`)
2. **Filter**: Exclude patterns (prompts, active research, indexes)
3. **Classify**: For each file:
   - Lexical mode: keyword pattern matching
   - Semantic mode: LLM reads file and classifies (build/debug/arch/other)
4. **Summarize**: LLM generates 2-3 sentence summary
5. **Consolidate**: Append summary to appropriate SOT file with metadata
6. **Report**: Generate consolidation report

### Files Modified
- `docs/BUILD_HISTORY.md` - Gets build-related summaries appended
- `docs/DEBUG_LOG.md` - Gets debug/incident summaries appended
- `docs/ARCHITECTURE_DECISIONS.md` - Gets design decision summaries appended

### Files Created
- `archive/reports/tidy_v{N}/` - New report directory with:
  - `tidy_summary.md` - Human-readable summary
  - `tidy_decisions.json` - Machine-readable classification data
  - `tidy.log` - Detailed execution log

---

## Quick Reference

| What | Command |
|------|---------|
| **Standard tidy (semantic)** | `PYTHONUTF8=1 python scripts/tidy/run_tidy_all.py --semantic --project autopack-framework` |
| **Fast tidy (lexical)** | `PYTHONUTF8=1 python scripts/tidy/run_tidy_all.py --project autopack-framework` |
| **Dry run (preview)** | Add `--dry-run` to any command |
| **Limit files** | Add `--semantic-max-files 20` |
| **Custom model** | Add `--semantic-model claude-sonnet-4-5` |
| **Check tidy model** | `python -c "from autopack.model_registry import get_tool_model; print(get_tool_model('tidy_semantic'))"` |
| **Review changes** | `git diff docs/BUILD_HISTORY.md docs/DEBUG_LOG.md docs/ARCHITECTURE_DECISIONS.md` |

---

## Safety Guarantees

✅ **Append-only**: Never deletes SOT files, only adds to them
✅ **Idempotent**: Safe to run multiple times (won't create duplicates if re-run)
✅ **Reversible**: All changes are git-tracked, easy to revert
✅ **Bounded**: Respects file size limits, won't process huge files
✅ **Excludes critical files**: Won't touch active research, prompts, indexes

---

## For Full Details

See [CURSOR_PROMPT_RUN_AUTOPACK.md](CURSOR_PROMPT_RUN_AUTOPACK.md) for:
- Complete environment variable reference
- Database integration (if using DB-backed tidy)
- Token usage tracking
- Advanced troubleshooting
- Tidy system internals

---

**Document Version**: BUILD-147 Phase A P11 (2026-01-01)
**Model Confirmed**: `glm-4.7` (configured in `config/models.yaml:154`)
**Safe to Run**: Yes (append-only, reversible, excludes critical files)
