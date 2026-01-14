# CI-Efficient Workflows - Quick Reference

**Choose the right workflow based on what you're doing:**

---

## 🎯 Workflow Decision Tree

```
What are you doing?
│
├─ Making a small fix/change to known files
│  └─> Use: STANDARD WORKFLOW (below)
│
├─ Adding a new experimental feature
│  └─> Use: ASPIRATIONAL WORKFLOW (below)
│
├─ Running comprehensive improvement scan
│  └─> Use: COMPREHENSIVE SCAN WORKFLOW (below)
│
├─ Refactoring a large file (5000+ lines)
│  └─> Use: REFACTORING WORKFLOW (below)
│
└─ Updating docs or frontend only
   └─> Use: FAST-TRACK WORKFLOW (below)
```

---

## 0. PRE-FLIGHT CHECKLIST (Before Every Commit)

**CRITICAL**: Follow these steps BEFORE every `git commit` to prevent CI failures and save 45-70 minutes per PR in debugging cycles.

### Quick Checklist:

```bash
# 1. Clean git state (remove temp files)
git status
rm -f tmpclaude-*-cwd 2>/dev/null || true
git status  # Verify no temp files remain

# 2. Run formatting (MANDATORY)
pre-commit run --all-files
# If pre-commit modifies files, stage them:
git add .

# 3. Verify clean state
git status
# Should show only your intended changes

# 4. Run local tests (optional but recommended)
pytest tests/path/to/your_tests.py -v

# 5. Commit and push
git commit -m "your commit message"
git push
```

### Why This Matters:

**Time Savings**: Following this checklist prevents:
- ✅ Formatting CI failures (saves 25+ min per PR)
- ✅ Temp file rebase conflicts (saves 10-15 min per PR)
- ✅ Multiple CI feedback loops (saves 45-70 min per cursor)

**Evidence**: Cursor sessions (ref3.md) showed 45-70 minutes wasted per cursor from:
- Not running pre-commit before pushing (formatting failures)
- Committing temp files (rebase conflicts)
- Reactive CI debugging vs proactive local checks

### Common Mistakes (DO NOT DO THIS):
- ❌ Committing without running `pre-commit run --all-files`
- ❌ Leaving temp files (tmpclaude-*-cwd) in commits
- ❌ Skipping `git status` verification before commit
- ❌ Pushing without running local tests on critical changes

**See Also**:
- [Complete PRE-FLIGHT CHECKLIST](C:\dev\Autopack\docs\WORKTREE_PARALLEL_WORKFLOW.md#-pre-flight-checklist-run-before-every-commit) with detailed explanations
- [REBASE RECOVERY GUIDE](C:\dev\Autopack\docs\WORKTREE_PARALLEL_WORKFLOW.md#-rebase-recovery-guide-when-git-state-goes-wrong) for when things go wrong
- [KNOWN PITFALLS](C:\Users\hshk9\OneDrive\Backup\Desktop\comprehensive_scan_prompt_v2.md#-known-pitfalls-learn-from-past-failures) documenting common failure patterns

---

## 1. STANDARD WORKFLOW
**When**: Small fixes, known changes, normal development
**CI Time**: Depends on files changed (5-45 min)

### Steps:
```bash
# 1. Make changes to files

# 2. Follow PRE-FLIGHT CHECKLIST (Section 0 above) BEFORE committing:
#    - Clean git state (remove temp files)
#    - Run pre-commit formatting
#    - Verify clean state
#    - Run local tests (optional)
#    - Commit and push

# 3. Wait for CI (time varies by path filter)
```

### CI Time by File Type:
- Docs only (`docs/**`, `*.md`): **~5-10 min**
- Frontend only (`*.tsx`, `*.css`): **~10-15 min**
- Backend non-critical (`research/**`): **~15-25 min**
- Backend core (`autonomous_executor.py`): **~30-45 min**

---

## 2. ASPIRATIONAL WORKFLOW
**When**: Experimental features, roadmap items, uncertain implementations
**CI Time**: ~15-20 min (only 110 aspirational tests run)

### Steps:
```bash
# 1. Mark new tests as aspirational
# In your test file:
import pytest

@pytest.mark.aspirational
def test_new_experimental_feature():
    # Your test here
    pass

# 2. Implement feature with aspirational tests
# 3. Push - CI runs only 110 aspirational tests (fast!)

# 4. Once stable, promote to core tests
python scripts/ci/aspirational_test_promotion.py \
  --test tests/path/to/test.py::test_new_experimental_feature
```

### Benefits:
- ✅ Fast iteration during development (110 tests vs 4,901)
- ✅ Non-blocking CI (can merge even if tests fail)
- ✅ Easy to promote to core tests when ready

### When to Use:
- New features not fully spec'd out
- Experimental implementations
- Roadmap items (marked in README as "Planned")
- Prototypes and POCs

---

## 3. COMPREHENSIVE SCAN WORKFLOW
**When**: Running the full "comprehensive improvement scan" prompt
**CI Time**: ~60-125 min total (vs 450+ min without strategy)

### Prompt to Use:
```
[Use the comprehensive_scan_prompt.md from Desktop]
```

### Steps:
```bash
# 1. Run comprehensive scan (copy-paste prompt from comprehensive_scan_prompt.md)
# Claude will output categorized JSON with A/B/C/D/E categories

# 2. Create Wave 1 PRs in parallel (Docs + Frontend + Infra)
git checkout -b docs/scan-wave1-docs
# Make docs improvements
git commit -am "docs: Wave 1 improvements"
git push

git checkout main
git checkout -b frontend/scan-wave1-ui
# Make frontend improvements
git commit -am "feat(ui): Wave 1 improvements"
git push

git checkout main
git checkout -b infra/scan-wave1-tooling
# Make infrastructure improvements
git commit -am "chore: Wave 1 infrastructure improvements"
git push

# All 3 PRs run in parallel - wait ~15 min total (not 45 min!)

# 3. Create Wave 2 PRs in parallel (Backend Non-Critical)
# Same process, ~25 min total

# 4. Create Wave 3 PRs sequentially (Backend Core, batched)
# Batch multiple improvements into one PR
# ~45 min per batch
```

### Time Savings:
- Without strategy: **10 PRs × 45 min = 450 min**
- With Wave strategy: **Wave1 (15 min) + Wave2 (25 min) + Wave3 (90 min) = 130 min**
- **Savings: 71% reduction**

---

## 4. REFACTORING WORKFLOW
**When**: Breaking down large god files (5000+ lines)
**CI Time**: ~45 min per PR (but batched extractions save time)

### Strategy:
```bash
# Example: Refactoring 9,626-line autonomous_executor.py

# Bad approach: 14 separate PRs × 45 min = 630 min
# Good approach: 7 batched PRs × 45 min = 315 min (2 extractions per PR)

# 1. Identify extraction targets (e.g., PR-EXE-8 through PR-EXE-14)
# 2. Batch related extractions together
# 3. Run each batch as a single PR

git checkout -b refactor/executor-batch-1-builders
# Extract 2 related modules
git commit -am "refactor(executor): extract Builder orchestration (PR-EXE-8 + PR-EXE-9)"
git push

# Repeat for other batches
```

### Benefits:
- ✅ Amortizes CI cost (2 extractions for price of 1 CI run)
- ✅ Related changes stay together
- ✅ Easier to review (clear extraction scope)

### When to Batch:
- Related functionality (e.g., all Builder-related extractions)
- Sequential dependencies (extraction B needs extraction A)
- Same subsystem (all executor modules, all LLM modules)

---

## 5. FAST-TRACK WORKFLOW
**When**: Docs or frontend-only changes
**CI Time**: ~5-15 min (backend tests skipped!)

### Steps:
```bash
# 1. Make ONLY docs or frontend changes
# Don't touch: src/autopack/**/*.py (backend)

# 2. Verify path filter will work
git status
# Should show only:
# - docs/**
# - README.md
# - *.tsx, *.css (frontend)
# - NOT: src/autopack/**/*.py

# 3. Push - backend tests automatically skipped
git commit -am "docs: update architecture guide"
git push

# CI runs only docs-sot-integrity job (~5-10 min)
```

### Path Filter Magic:
The `.github/workflows/ci.yml` automatically skips jobs based on changed files:
```yaml
backend:
  - 'src/**'        # If these don't change...
  - 'tests/**'
  - 'pyproject.toml'

docs:
  - 'docs/**'       # ...and these do change...
  - 'README.md'

# ...then backend tests are skipped! ✅
```

### Perfect for:
- Documentation updates
- SOT file corrections
- Architecture decision records
- README improvements
- Frontend UI tweaks
- CSS styling changes

---

## 🚀 Advanced: Parallel Test Execution (Future)

**After PR-INFRA-1 merges** (pytest-xdist setup):

### Setup:
```bash
# This will be added to CI automatically
pytest tests/ -n auto  # Auto-detect CPU count and parallelize
```

### Expected Improvement:
- Current: 4,901 tests × ~0.5s = **~45 min**
- With xdist: 4,901 tests ÷ 4 workers = **~15 min** (67% reduction)

### Local Usage:
```bash
# Run tests in parallel locally
pytest tests/ -n 4 -v

# Smart mode (auto-detect CPUs)
pytest tests/ -n auto -v
```

---

## 📊 CI Time Comparison Table

| Workflow | Files Changed | CI Time | Tests Run | Blocking |
|----------|---------------|---------|-----------|----------|
| Docs only | `docs/**`, `*.md` | ~5-10 min | Doc tests only | ✅ Yes |
| Frontend only | `*.tsx`, `*.css` | ~10-15 min | Frontend tests | ✅ Yes |
| Backend (research) | `research/**` | ~15-25 min | 549 research tests | ⚠️ No (continue-on-error) |
| Backend (core) | `autonomous_executor.py` | ~30-45 min | 4,901 core tests | ✅ Yes |
| Aspirational | `src/**` + `@pytest.mark.aspirational` | ~15-20 min | 110 aspirational tests | ⚠️ No (continue-on-error) |
| Infrastructure | `scripts/**`, `.github/**` | ~15-45 min | Variable | ✅ Yes |

---

## 🎓 Pro Tips

### Tip 1: Check Path Filter Before Pushing
```bash
# See which CI jobs will trigger
git diff main --name-only

# Only docs? → Fast track! (~5 min)
# Backend files? → Full suite (~45 min)
```

### Tip 2: Use Local Pre-flight for Fast Feedback
```bash
# Instead of waiting 45 min for CI feedback:
pytest tests/executor/ -v  # Run just executor tests locally

# Or run specific test file:
pytest tests/executor/test_batched_deliverables_executor.py -v
```

### Tip 3: Batch Related Changes
```bash
# Bad: 10 separate PRs × 45 min = 450 min
# Good: 1 batched PR × 45 min = 45 min

# Batch improvements into logical groups:
git commit -am "refactor: extract 5 executor helpers (batched)"
```

### Tip 4: Use Aspirational for Uncertain Code
```python
# During development - mark as aspirational
@pytest.mark.aspirational
def test_new_experimental_feature():
    pass

# Once stable - remove marker and let it become core test
def test_new_experimental_feature():
    pass
```

### Tip 5: Parallel PRs for Independent Changes
```bash
# Create 3 PRs simultaneously:
# PR-1: Docs improvements (5 min CI)
# PR-2: Frontend improvements (10 min CI)
# PR-3: Research module (20 min CI)

# Total wall-clock: 20 min (not 35 min!)
# All can merge independently
```

---

## 🔗 Related Files

- **Full Strategy**: `C:\Users\hshk9\OneDrive\Backup\Desktop\COMPREHENSIVE_SCAN_STRATEGY.md`
- **Scan Prompt**: `C:\Users\hshk9\OneDrive\Backup\Desktop\comprehensive_scan_prompt.md`
- **CI Config**: `.github/workflows/ci.yml`
- **Test Markers**: Search codebase for `@pytest.mark.aspirational`, `@pytest.mark.research`
- **Path Filters**: Lines 25-47 in `.github/workflows/ci.yml`

---

## 📝 TL;DR - Choose Your Workflow

1. **Small change to known files** → Standard workflow (5-45 min depending on files)
2. **Experimental feature** → Aspirational workflow (~15 min)
3. **Comprehensive scan** → Use comprehensive_scan_prompt.md (60-125 min batched)
4. **Large refactoring** → Batch extractions (save 50% CI time)
5. **Docs/Frontend only** → Fast-track (~5-15 min, backend skipped)

**Key principle**: Match your workflow to the CI impact of your changes!
