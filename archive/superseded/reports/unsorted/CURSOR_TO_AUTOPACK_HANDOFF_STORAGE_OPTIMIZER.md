# Cursor → Autopack Handoff: Storage Optimizer

**Date**: 2026-01-01
**Status**: Ready for Autopack Execution
**Cursor Phases**: Completed
**Autopack Phases**: Ready to Start

---

## ✅ Cursor Phases Complete

### Phase 1: Research & Prototyping ✅

**Status**: **COMPLETE**

**Deliverables Created**:
1. ✅ [WIZTREE_CLI_INTEGRATION_RESEARCH.md](research/WIZTREE_CLI_INTEGRATION_RESEARCH.md)
   - WizTree CLI command reference
   - CSV schema documentation
   - Performance benchmarks
   - Edge cases and limitations

2. ✅ [STORAGE_SCANNER_COMPARISON.md](research/STORAGE_SCANNER_COMPARISON.md)
   - Detailed comparison of 4 scanning options
   - Recommendation: WizTree (primary) + Python fallback
   - Distribution strategy
   - Licensing analysis

3. ✅ [WINDOWS_CLEANUP_APIS.md](research/WINDOWS_CLEANUP_APIS.md)
   - Safe deletion methods (send2trash vs permanent)
   - Windows Storage Sense integration
   - DISM cleanup commands
   - Safety checklists

4. ✅ [prototype_scanner.py](../scripts/storage/prototype_scanner.py)
   - Working WizTree CLI wrapper
   - Python fallback scanner
   - Basic classification logic
   - Ready to test on real system

**Key Findings**:
- ✅ WizTree can scan 1 TB in ~20 seconds (vs 10-20 minutes for Python)
- ✅ CSV export format is well-structured and parseable
- ✅ send2trash library provides safe deletion (Recycle Bin)
- ✅ Fallback scanner works but is 30-50x slower

**Test Results**: Prototype validated (see prototype_scanner.py)

---

## 🎯 Autopack Phases Ready to Execute

Autopack can now autonomously implement **Phases 2-7, 9 (partial), and 10**:

### Phase 2: Core Module Structure (AUTOPACK)

**Duration**: 1-2 hours
**Complexity**: Low
**Dependencies**: None

**Objectives**:
1. Create `src/autopack/storage_optimizer/` module directory
2. Create all subdirectories and `__init__.py` files
3. Implement data models (`models.py`)
4. Implement configuration schema (`config.py`)
5. Create `scripts/storage/` directory
6. Create `tests/autopack/storage_optimizer/` directory

**Detailed Tasks**:

```bash
# Directory structure to create:
src/autopack/storage_optimizer/
├── __init__.py
├── scanner.py          # (Cursor will complete in Phase 3)
├── classifier.py       # ← Autopack implements
├── cleanup_rules.py    # ← Autopack implements
├── cleanup_executor.py # ← Autopack implements
├── scheduler.py        # ← Autopack implements
├── reporter.py         # ← Autopack implements
├── config.py           # ← Autopack implements
└── models.py           # ← Autopack implements

scripts/storage/
├── scan_disk.py        # ← Autopack implements
├── cleanup_storage.py  # ← Autopack implements
├── storage_report.py   # ← Autopack implements
└── prototype_scanner.py # ✅ Already created

tests/autopack/storage_optimizer/
├── test_classifier.py        # ← Autopack implements
├── test_cleanup_rules.py     # ← Autopack implements
├── test_cleanup_executor.py  # ← Autopack implements
└── fixtures/
    └── sample_scan_results.csv
```

**Files to Create** (see IMPLEMENTATION_PLAN_STORAGE_OPTIMIZER.md for full code):

1. **models.py** - Data classes:
   - `CleanupCategory` enum
   - `SafetyLevel` enum
   - `ScanResult` dataclass
   - `CleanupCandidate` dataclass
   - `CleanupPlan` dataclass
   - `CleanupResult` dataclass
   - `StorageReport` dataclass

2. **config.py** - Configuration:
   - `StorageOptimizerConfig` dataclass
   - `DEFAULT_CONFIG` instance

3. **__init__.py** - Module exports:
   - Export all models
   - Export all core classes
   - Define `__version__`
   - Define `__all__`

**Acceptance Criteria**:
- [ ] All directories created
- [ ] All `__init__.py` files created
- [ ] `models.py` has all 7 classes defined
- [ ] `config.py` has configuration with sensible defaults
- [ ] Module can be imported: `from autopack.storage_optimizer import CleanupCategory`

---

### Phase 4: Classification Engine (AUTOPACK)

**Duration**: 2-3 hours
**Complexity**: Medium
**Dependencies**: Phase 2 (models)

**Objectives**:
1. Implement `FileClassifier` class in `classifier.py`
2. Create 9+ classification rules
3. Implement confidence scoring
4. Add safety level assignment
5. Write unit tests

**Classification Rules to Implement**:

1. **Temp files** (`_classify_temp_files`):
   - Pattern: `\temp\`, `\tmp\`, `appdata\local\temp`
   - Age threshold: 7+ days
   - Safety: SAFE
   - Confidence: 0.9

2. **Browser cache** (`_classify_browser_cache`):
   - Pattern: `chrome.*\cache`, `edge.*\cache`, `firefox.*\cache`
   - Safety: SAFE
   - Confidence: 0.95

3. **Developer artifacts** (`_classify_dev_artifacts`):
   - Patterns: `node_modules`, `venv`, `.venv`, `virtualenv`
   - Age threshold: 60+ days (configurable)
   - Safety: REVIEW (requires approval)
   - Confidence: 0.8

4. **Windows Update** (`_classify_windows_update`):
   - Pattern: `softwaredistribution\download`
   - Safety: SAFE
   - Confidence: 0.9

5. **Windows.old** (`_classify_windows_old`):
   - Pattern: `c:\windows.old`
   - Safety: REVIEW
   - Confidence: 1.0

6. **Docker/WSL** (`_classify_docker_wsl`):
   - Patterns: `docker\wsl\data`, `appdata\local\docker`
   - Safety: REVIEW
   - Confidence: 0.7

7. **Build artifacts** (`_classify_build_artifacts`):
   - Patterns: `dist`, `build`, `target`, `out`, `.next`, `__pycache__`
   - Age threshold: 7+ days
   - Safety: REVIEW
   - Confidence: 0.6

8. **Old downloads** (`_classify_old_downloads`):
   - Pattern: `\downloads\`
   - Age threshold: 30+ days (configurable)
   - Safety: REVIEW
   - Confidence: 0.5

9. **Recycle Bin** (`_classify_recycle_bin`):
   - Pattern: `$recycle.bin`
   - Safety: SAFE
   - Confidence: 1.0

**Code Template** (see IMPLEMENTATION_PLAN_STORAGE_OPTIMIZER.md Phase 4 for full implementation)

**Unit Tests to Create**:
```python
# tests/autopack/storage_optimizer/test_classifier.py
def test_classify_temp_files()
def test_classify_node_modules()
def test_classify_browser_cache()
def test_classify_windows_old()
# ... etc
```

**Acceptance Criteria**:
- [ ] `FileClassifier` class implemented
- [ ] All 9 classification rules working
- [ ] `classify()` method returns `CleanupCandidate` or `None`
- [ ] `classify_batch()` method works with list of results
- [ ] Unit tests pass with >80% coverage
- [ ] Can classify prototype_scanner.py results

---

### Phase 5: Cleanup Executor (AUTOPACK)

**Duration**: 2-3 hours
**Complexity**: Medium
**Dependencies**: Phase 2 (models), Phase 4 (classifier)

**Objectives**:
1. Implement `CleanupExecutor` class in `cleanup_executor.py`
2. Implement safe deletion with `send2trash`
3. Add approval workflow logic
4. Add protected path checking
5. Implement rollback/undo capability
6. Write unit tests

**Key Methods to Implement**:

1. **create_plan()**:
   - Input: List of `CleanupCandidate`
   - Output: `CleanupPlan`
   - Logic: Separate auto-deletable from requires-approval

2. **execute_plan()**:
   - Input: `CleanupPlan`, approved paths, dry_run flag
   - Output: List of `CleanupResult`
   - Logic: Delete safe items, skip unapproved items

3. **_delete_item()**:
   - Input: `CleanupCandidate`
   - Output: `CleanupResult`
   - Logic: Use send2trash or permanent deletion

4. **_is_protected_path()**:
   - Input: path string
   - Output: boolean
   - Logic: Check against protected paths list

**Safety Features Required**:
- ✅ Protected path checking (`C:\Windows`, `C:\Program Files`)
- ✅ Size threshold (auto-delete only < 100 MB by default)
- ✅ Total deletion limit (max 10 GB per run by default)
- ✅ Dry-run mode (preview without deleting)
- ✅ Recycle Bin by default (recoverable)
- ✅ Comprehensive error handling

**Dependencies**:
```python
pip install send2trash
```

**Code Template** (see IMPLEMENTATION_PLAN_STORAGE_OPTIMIZER.md Phase 5)

**Unit Tests**:
```python
# tests/autopack/storage_optimizer/test_cleanup_executor.py
def test_create_plan()
def test_execute_plan_dry_run()
def test_execute_plan_real()
def test_protected_path_blocking()
def test_size_threshold()
# ... etc
```

**Acceptance Criteria**:
- [ ] `CleanupExecutor` class implemented
- [ ] send2trash integration working
- [ ] Protected path checking prevents dangerous deletions
- [ ] Dry-run mode works correctly
- [ ] Approval workflow works
- [ ] Unit tests pass
- [ ] Can execute cleanup plans from Phase 4

---

### Phase 6: Scheduler Integration (AUTOPACK)

**Duration**: 1-2 hours
**Complexity**: Low
**Dependencies**: None

**Objectives**:
1. Implement `StorageScheduler` class in `scheduler.py`
2. Create Windows Task Scheduler integration
3. Add schedule creation/deletion methods
4. Add schedule status checking

**Key Methods to Implement**:

1. **create_schedule()**:
   - Uses `schtasks /create` to create Windows task
   - Schedule: Every 14 days
   - Time: 2:00 AM (configurable)
   - Command: `python scripts/storage/cleanup_storage.py --auto`

2. **delete_schedule()**:
   - Uses `schtasks /delete` to remove task

3. **check_schedule_status()**:
   - Uses `schtasks /query` to check if task exists

**Code Template** (see IMPLEMENTATION_PLAN_STORAGE_OPTIMIZER.md Phase 6)

**Acceptance Criteria**:
- [ ] `StorageScheduler` class implemented
- [ ] Can create Windows Task Scheduler task
- [ ] Can delete scheduled task
- [ ] Can check task status
- [ ] Task runs Python script correctly
- [ ] Fortnightly schedule works

---

### Phase 7: Reporting System (AUTOPACK)

**Duration**: 2-3 hours
**Complexity**: Medium
**Dependencies**: Phase 2 (models)

**Objectives**:
1. Implement `StorageReporter` class in `reporter.py`
2. Create storage usage reports
3. Track historical trends
4. Generate human-readable summaries
5. Save reports to disk

**Key Methods to Implement**:

1. **create_report()**:
   - Input: scan data, disk usage, cleanup candidates
   - Output: `StorageReport`
   - Logic: Aggregate data, load historical trend

2. **generate_summary()**:
   - Input: `StorageReport`, optional `CleanupResult` list
   - Output: Formatted string
   - Logic: Human-readable summary with disk usage, top consumers, cleanup results

3. **_save_report()**:
   - Saves report to `~/.autopack/storage_reports/` as JSON

4. **_load_historical_trend()**:
   - Loads last 12 reports for trend analysis

**Report Format** (example):
```
======================================================================
STORAGE OPTIMIZATION REPORT
======================================================================
Date: 2026-01-01 14:30:00

DISK USAGE:
  Total Space: 1000.00 GB
  Used Space:  750.00 GB (75.0%)
  Free Space:  250.00 GB (25.0%)

TOP 10 SPACE CONSUMERS:
  1. 52.00 GB - C:\Program Files (x86)\Steam\steamapps\common\Monster Hunter World
  2. 20.00 GB - C:\dev\old_project\node_modules
  ...

CLEANUP OPPORTUNITIES:
  Total Potential Savings: 85.00 GB
  Candidates: 25

  By Category:
    dev_artifacts: 45.00 GB (8 items)
    temp_files: 20.00 GB (12 items)
    browser_cache: 15.00 GB (3 items)
    windows_update: 5.00 GB (2 items)

CLEANUP RESULTS:
  Total Space Freed: 25.00 GB
  Successful: 18
  Failed: 2

  Failed Deletions:
    - C:\locked_file.tmp: Permission denied
======================================================================
```

**Code Template** (see IMPLEMENTATION_PLAN_STORAGE_OPTIMIZER.md Phase 7)

**Acceptance Criteria**:
- [ ] `StorageReporter` class implemented
- [ ] Can create storage reports
- [ ] Can generate human-readable summaries
- [ ] Reports saved to disk as JSON
- [ ] Historical trend tracking works
- [ ] Reports can be loaded and displayed

---

### Phase 9 (Partial): Unit Testing (AUTOPACK)

**Duration**: 1-2 hours
**Complexity**: Medium
**Dependencies**: Phases 4, 5, 7

**Objectives**:
1. Write unit tests for classifier
2. Write unit tests for cleanup executor
3. Write unit tests for reporter
4. Create test fixtures
5. Achieve >80% code coverage

**Test Files to Create**:

1. **test_classifier.py**:
   - Test each classification rule
   - Test batch classification
   - Test edge cases (Unicode, long paths, special chars)

2. **test_cleanup_executor.py**:
   - Test plan creation
   - Test dry-run mode
   - Test protected path blocking
   - Test approval workflow
   - Test send2trash integration (mock)

3. **test_reporter.py**:
   - Test report creation
   - Test summary generation
   - Test report saving/loading
   - Test historical trend

4. **Test Fixtures**:
   - `sample_scan_results.csv` - Sample WizTree output
   - `sample_cleanup_candidates.json` - Sample classification results

**Testing Strategy**:
```python
# Use pytest
import pytest
from autopack.storage_optimizer import FileClassifier, ScanResult
from datetime import datetime, timedelta

def test_classify_old_temp_file():
    """Test that old temp files are classified correctly."""
    classifier = FileClassifier(DEFAULT_CONFIG)

    old_temp = ScanResult(
        path="C:\\Users\\test\\AppData\\Local\\Temp\\oldfile.txt",
        size_bytes=1024 * 1024,  # 1 MB
        modified=datetime.now() - timedelta(days=30),
        is_folder=False,
        attributes='-'
    )

    candidate = classifier.classify(old_temp)

    assert candidate is not None
    assert candidate.category == CleanupCategory.TEMP_FILES
    assert candidate.safety_level == SafetyLevel.SAFE
    assert candidate.confidence >= 0.8
```

**Acceptance Criteria**:
- [ ] All test files created
- [ ] Tests pass with pytest
- [ ] Code coverage >80%
- [ ] Test fixtures created
- [ ] Edge cases tested

---

### Phase 10: Documentation (AUTOPACK)

**Duration**: 1-2 hours
**Complexity**: Low
**Dependencies**: All other phases

**Objectives**:
1. Create user guide
2. Create API documentation
3. Create configuration reference
4. Create troubleshooting guide

**Documents to Create**:

1. **docs/guides/STORAGE_OPTIMIZER_USER_GUIDE.md**:
   - Installation instructions
   - Quick start guide
   - Command reference
   - Configuration options
   - Scheduling setup
   - Understanding reports
   - FAQ

2. **docs/api/STORAGE_OPTIMIZER_API.md**:
   - Module structure
   - Class reference
   - Method signatures
   - Usage examples
   - Integration guide

3. **README_STORAGE_OPTIMIZER.md** (root):
   - Overview
   - Features
   - Quick start
   - Links to detailed docs

**Acceptance Criteria**:
- [ ] User guide created
- [ ] API documentation created
- [ ] README created
- [ ] All examples are working code
- [ ] Documentation is clear and comprehensive

---

## 🔄 Remaining Cursor Phases (After Autopack Completes)

Once Autopack finishes Phases 2-7, 9-10, Cursor will complete:

### Phase 3: Scanner Wrapper (CURSOR)

**Status**: Pending Autopack completion
**Duration**: 2-3 hours

**Tasks**:
1. Complete `scanner.py` implementation
2. Integrate WizTree CLI wrapper from prototype
3. Add robust error handling
4. Implement caching
5. Add fallback scanner
6. Write integration tests

**Why Cursor**: External process management, CSV parsing edge cases

---

### Phase 8: Autopack Executor Integration (CURSOR)

**Status**: Pending Autopack completion
**Duration**: 2-3 hours

**Tasks**:
1. Add `PhaseType.STORAGE_OPTIMIZATION` to models
2. Create `StorageOptimizationPhase` handler
3. Integrate with `autonomous_executor.py`
4. Add database schema updates
5. Test full integration

**Why Cursor**: Requires modifying existing Autopack core architecture

---

### Phase 9 (Cursor Part): Integration Testing (CURSOR)

**Status**: Pending Autopack completion
**Duration**: 2-3 hours

**Tasks**:
1. Write end-to-end integration tests
2. Test full workflow (scan → classify → cleanup → report)
3. Test error scenarios
4. Performance testing
5. Real system testing

**Why Cursor**: Requires running on real system with external dependencies

---

## 📊 Progress Tracking

### Completed ✅
- [x] Phase 1: Research & Prototyping (Cursor)
  - [x] WizTree CLI research
  - [x] Scanner comparison
  - [x] Windows cleanup APIs research
  - [x] Prototype scanner

### In Progress / Ready for Autopack 🚀
- [ ] Phase 2: Core Module Structure (Autopack) - **START HERE**
- [ ] Phase 4: Classification Engine (Autopack)
- [ ] Phase 5: Cleanup Executor (Autopack)
- [ ] Phase 6: Scheduler (Autopack)
- [ ] Phase 7: Reporting (Autopack)
- [ ] Phase 9 (partial): Unit Testing (Autopack)
- [ ] Phase 10: Documentation (Autopack)

### Blocked (Waiting for Autopack) ⏸️
- [ ] Phase 3: Scanner Wrapper (Cursor) - Wait for Phase 2
- [ ] Phase 8: Executor Integration (Cursor) - Wait for Phases 2-7
- [ ] Phase 9 (partial): Integration Testing (Cursor) - Wait for Phases 2-8

---

## 🎯 Autopack Execution Instructions

### Starting Point

Autopack should begin with **Phase 2: Core Module Structure**.

### Execution Order

```
Phase 2 (Module Structure)
    ↓
Phase 4 (Classifier) ← Depends on Phase 2 models
    ↓
Phase 5 (Cleanup Executor) ← Depends on Phase 2 models, Phase 4 classifier
    ↓
Phase 6 (Scheduler) ← Independent
    ↓
Phase 7 (Reporter) ← Depends on Phase 2 models
    ↓
Phase 9 (Unit Tests) ← Depends on Phases 4, 5, 7
    ↓
Phase 10 (Documentation) ← Depends on all phases
```

### Success Criteria

After Autopack completes its phases, you should have:

1. ✅ Full module structure in `src/autopack/storage_optimizer/`
2. ✅ Working classification engine (9+ rules)
3. ✅ Safe cleanup executor with send2trash
4. ✅ Windows Task Scheduler integration
5. ✅ Comprehensive reporting system
6. ✅ Unit tests with >80% coverage
7. ✅ Complete documentation

---

## 📚 Reference Documents

**Research** (Cursor-created):
- [WIZTREE_CLI_INTEGRATION_RESEARCH.md](research/WIZTREE_CLI_INTEGRATION_RESEARCH.md)
- [STORAGE_SCANNER_COMPARISON.md](research/STORAGE_SCANNER_COMPARISON.md)
- [WINDOWS_CLEANUP_APIS.md](research/WINDOWS_CLEANUP_APIS.md)

**Implementation Plan**:
- [IMPLEMENTATION_PLAN_STORAGE_OPTIMIZER.md](IMPLEMENTATION_PLAN_STORAGE_OPTIMIZER.md) - Full detailed plan

**Prototype**:
- [prototype_scanner.py](../scripts/storage/prototype_scanner.py) - Working scanner prototype

**Code Examples**:
All code templates are in IMPLEMENTATION_PLAN_STORAGE_OPTIMIZER.md sections for each phase.

---

## 🚀 Ready to Start!

Autopack can now autonomously execute Phases 2-7, 9-10.

**First task**: Create the module structure (Phase 2).

**Autopack prompt**:
```
Implement Phase 2 of the Storage Optimizer: Core Module Structure

Create the following:
1. Directory structure: src/autopack/storage_optimizer/ with all subdirectories
2. models.py with all 7 dataclasses (CleanupCategory, SafetyLevel, ScanResult, etc.)
3. config.py with StorageOptimizerConfig and DEFAULT_CONFIG
4. __init__.py with proper exports
5. scripts/storage/ directory
6. tests/autopack/storage_optimizer/ directory

Reference the code templates in docs/IMPLEMENTATION_PLAN_STORAGE_OPTIMIZER.md Phase 2.

After completion, proceed to Phase 4 (Classification Engine).
```

---

**Status**: Ready for Autopack Execution
**Handoff Complete**: 2026-01-01
**Next**: Autopack Phase 2 → Phase 4 → Phase 5 → Phase 6 → Phase 7 → Phase 9 → Phase 10
