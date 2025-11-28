# Auto-Documentation System

**Zero-token documentation updates using Python AST + git diff analysis**

## Overview

Autopack automatically keeps documentation in sync with code changes without using LLMs. The system has two modes:

1. **Quick Mode** (default): Fast endpoint count updates for git pre-commit hook
2. **Full Analysis Mode** (`--analyze`): Deep structural change detection for CI flow

## What Gets Detected

### Structural Changes (Full Analysis Only)

- **New Modules**: Python files added to `src/autopack/`
- **New Classes**: Classes defined in new modules (via AST parsing)
- **API Changes**: New endpoint groups (e.g., `/dashboard/*`)
- **Dependencies**: Changes to `requirements.txt` or `package.json`

### Statistics (Both Modes)

- API endpoint count in `main.py`
- Dashboard build status
- Documentation file count

## Usage

### Quick Mode (Pre-Commit Hook)

```bash
# Fast update (< 0.5 seconds)
python scripts/update_docs.py

# Preview changes
python scripts/update_docs.py --dry-run

# Check if updates needed
python scripts/update_docs.py --check
```

This runs automatically on every commit via `.git/hooks/pre-commit`.

### Full Analysis Mode (CI Flow)

```bash
# Full structural analysis (1-2 seconds)
python scripts/update_docs.py --analyze

# Preview what would be documented
python scripts/update_docs.py --analyze --dry-run

# Run via CI script
bash scripts/ci_update_docs.sh
```

Use this during CI flow to detect and document major structural changes.

## What Gets Updated

### README.md

- API endpoint count in technology stack section
- Validates dashboard section exists
- Validates architecture diagram includes new components

### CHANGELOG.md

When `--analyze` detects structural changes, creates a new entry:

```markdown
## [2025-11-25] - Structural Updates

### New Modules
- New module: llm_service (`src/autopack/llm_service.py`)
- New module: model_router (`src/autopack/model_router.py`)

### New Classes
- New classes: LlmService (`src/autopack/llm_service.py`)
- New classes: ModelRouter (`src/autopack/model_router.py`)

### API Changes
- Dashboard API endpoints added (`main.py::/dashboard/*`)
```

## Integration Points

### Git Pre-Commit Hook

Location: `.git/hooks/pre-commit`

```bash
if [ -f "scripts/update_docs.py" ]; then
    python scripts/update_docs.py --check

    if [ $? -ne 0 ]; then
        echo "⚠️  Documentation may need updating. Run: python scripts/update_docs.py"
        echo "Continuing with commit..."
    fi
fi
```

**Non-blocking**: Prints warning but allows commit to proceed.

### CI Flow Integration

Add to your CI probe script:

```bash
# After tests pass, update documentation
if [ $all_tests_passed ]; then
    bash scripts/ci_update_docs.sh

    # Commit documentation updates
    git add CHANGELOG.md README.md
    git commit -m "docs: auto-update from CI flow"
fi
```

## Technical Details

### AST Parsing

Uses Python's `ast` module to parse source code and extract:
- Class definitions (`ast.ClassDef`)
- Function definitions (`ast.FunctionDef`)
- Module-level constants

### Git Diff Analysis

Uses `git diff --name-status` to detect:
- New files (`A` status)
- Modified files (`M` status)
- Deleted files (`D` status)

Looks back 5 commits by default:
```python
git diff --name-status HEAD~5 HEAD
```

### Pattern Matching

Uses regex to detect:
- FastAPI endpoint decorators: `@app.(get|post|put|delete|patch)`
- Dependency declarations: Package names in `requirements.txt`

## Cost Analysis

- **Token usage**: 0 (uses only Python stdlib + git)
- **Execution time**:
  - Quick mode: < 0.5 seconds
  - Full analysis: 1-2 seconds
- **Dependencies**: None (uses `ast`, `re`, `subprocess`, `pathlib`)

## Examples

### Example 1: Quick Update

```bash
$ python scripts/update_docs.py
[*] Scanning codebase for documentation updates...
[Mode] Quick update (endpoint counts only)

[OK] Documentation is up to date!
```

### Example 2: Full Analysis with Changes

```bash
$ python scripts/update_docs.py --analyze
[*] Scanning codebase for documentation updates...
[Mode] Full structural analysis (detecting major changes)

[Status] Current State:
  API Endpoints: 22
  New Modules: 7
  Dashboard Built: YES
  Doc Files: 4

[*] Analyzing structural changes (AST + git diff)...

[Detected] 8 major structural changes:
  [MODULE] New module: llm_service
      Location: src/autopack/llm_service.py
  [CLASS] New classes: LlmService
      Location: src/autopack/llm_service.py
  [API] Dashboard API endpoints added
      Location: main.py::/dashboard/*

[OK] Updated CHANGELOG.md with 8 structural changes
[OK] All updates applied
```

### Example 3: Preview Mode

```bash
$ python scripts/update_docs.py --analyze --dry-run
[*] Scanning codebase for documentation updates...
[Mode] Full structural analysis (detecting major changes)

[Detected] 3 major structural changes:
  [MODULE] New module: feature_x
  [CLASS] New classes: FeatureX, FeatureXService
  [API] New /features/* endpoints

[DRY RUN] Would add to CHANGELOG.md:

## [2025-11-25] - Structural Updates

### New Modules
- New module: feature_x (`src/autopack/feature_x.py`)

[DRY RUN] No files modified
```

## Troubleshooting

### "Documentation may need updating" warning

**Cause**: Structural changes detected but not yet documented.

**Solution**: Run `python scripts/update_docs.py` to apply updates.

### No structural changes detected

**Cause**:
- Changes are within existing files (not new modules)
- Changes are in last 5 commits already documented
- Changes are in non-tracked directories

**Solution**: This is expected for minor updates. Only major structural changes trigger updates.

### Git command fails

**Cause**: Not in a git repository or git not installed.

**Solution**: Ensure you're in the Autopack root directory with `.git/` folder present.

## Future Enhancements

Potential additions (still token-free):

1. **Diff-based detection**: Detect significant function signature changes
2. **Import analysis**: Track new external library imports
3. **Test coverage**: Count test files per module
4. **Architecture validation**: Ensure layer boundaries are maintained
5. **Breaking change detection**: Detect removed public APIs

## Configuration

### Adjust lookback range

In `scripts/update_docs.py`:

```python
def detect_new_modules_since_commit(self, since_commit: str = "HEAD~5"):
    # Change HEAD~5 to HEAD~10 to look back 10 commits
```

### Customize module detection

In `scripts/update_docs.py`:

```python
if "src/autopack/" in file_path and not file_path.endswith("__init__.py"):
    # Add additional filters here
```

### Add new detection categories

Extend `StructuralChange` categories:

```python
class StructuralChange:
    def __init__(self, category: str, description: str, location: str):
        # Valid categories: "module", "class", "api", "dependency", "config", "test", "breaking"
        self.category = category
```

## Comparison to LLM-Based Approach

| Feature | Auto-Documentation | LLM Approach |
|---------|-------------------|--------------|
| Token cost | $0 | $0.01-0.10 per run |
| Speed | < 2 seconds | 5-30 seconds |
| Accuracy | Deterministic | 95%+ |
| Semantic understanding | No | Yes |
| Offline capable | Yes | No |
| False positives | Low | Medium |

**When to use each**:
- **Auto-Documentation**: Structural changes, statistics, CI flow
- **LLM Approach**: Semantic summaries, release notes, user-facing docs
