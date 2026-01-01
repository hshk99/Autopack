# Autopack Execution Prompt: Storage Optimizer Implementation

**Project**: Storage Optimizer Module
**Phases**: 2, 4, 5, 6, 7, 9 (partial), 10
**Estimated Duration**: 11-14 hours
**Status**: Ready to Execute

---

## 📋 Quick Start for Autopack

Copy this prompt to start Autopack autonomous execution:

```
TASK: Implement Storage Optimizer Module for Autopack

CONTEXT:
Cursor has completed Phase 1 (Research & Prototyping) for a new Storage Optimizer module.
Research findings, prototype, and detailed implementation plan are ready.

YOUR OBJECTIVE:
Autonomously implement Phases 2-7, 9-10 of the Storage Optimizer module.

PHASES TO IMPLEMENT:
1. Phase 2: Core Module Structure (1-2 hours)
2. Phase 4: Classification Engine (2-3 hours)
3. Phase 5: Cleanup Executor (2-3 hours)
4. Phase 6: Scheduler Integration (1-2 hours)
5. Phase 7: Reporting System (2-3 hours)
6. Phase 9 (partial): Unit Testing (1-2 hours)
7. Phase 10: Documentation (1-2 hours)

REFERENCE DOCUMENTS:
- Primary: docs/IMPLEMENTATION_PLAN_STORAGE_OPTIMIZER.md (detailed plan with code templates)
- Handoff: docs/CURSOR_TO_AUTOPACK_HANDOFF_STORAGE_OPTIMIZER.md (phase-by-phase guidance)
- Research: docs/research/WIZTREE_CLI_INTEGRATION_RESEARCH.md
- Research: docs/research/STORAGE_SCANNER_COMPARISON.md
- Research: docs/research/WINDOWS_CLEANUP_APIS.md
- Prototype: scripts/storage/prototype_scanner.py

EXECUTION ORDER:
Phase 2 → Phase 4 → Phase 5 → Phase 6 → Phase 7 → Phase 9 → Phase 10

START WITH: Phase 2 (Core Module Structure)

ACCEPTANCE CRITERIA:
- All code follows Autopack patterns and conventions
- Unit tests achieve >80% coverage
- All safety features implemented (protected paths, approval workflow)
- Documentation is complete and clear
- Code is production-ready

AFTER COMPLETION:
Notify that Cursor phases (3, 8, 9 integration tests) can proceed.
```

---

## 📖 Detailed Phase Instructions

### Phase 2: Core Module Structure

**Duration**: 1-2 hours

**Create**:
```
src/autopack/storage_optimizer/
├── __init__.py
├── models.py
├── config.py
├── scanner.py (placeholder, Cursor will complete)
├── classifier.py (you implement)
├── cleanup_rules.py (you implement)
├── cleanup_executor.py (you implement)
├── scheduler.py (you implement)
└── reporter.py (you implement)

scripts/storage/
├── scan_disk.py (you implement)
├── cleanup_storage.py (you implement)
├── storage_report.py (you implement)
└── prototype_scanner.py (✅ already exists)

tests/autopack/storage_optimizer/
├── test_classifier.py (you implement)
├── test_cleanup_executor.py (you implement)
├── test_reporter.py (you implement)
└── fixtures/
    └── sample_scan_results.csv (you create)
```

**Implementation**:
1. Create all directories
2. Implement `models.py` with 7 dataclasses:
   - CleanupCategory (enum)
   - SafetyLevel (enum)
   - ScanResult
   - CleanupCandidate
   - CleanupPlan
   - CleanupResult
   - StorageReport

3. Implement `config.py` with:
   - StorageOptimizerConfig dataclass
   - DEFAULT_CONFIG instance

4. Create `__init__.py` with proper exports

**Code Templates**: See IMPLEMENTATION_PLAN_STORAGE_OPTIMIZER.md Phase 2

**Validation**:
```python
# Test that module can be imported
from autopack.storage_optimizer import (
    CleanupCategory,
    SafetyLevel,
    CleanupCandidate,
    DEFAULT_CONFIG
)
```

---

### Phase 4: Classification Engine

**Duration**: 2-3 hours

**Implement**: `src/autopack/storage_optimizer/classifier.py`

**Key Methods**:
- `FileClassifier.__init__(config)`
- `FileClassifier.classify(scan_result) -> Optional[CleanupCandidate]`
- `FileClassifier.classify_batch(scan_results) -> List[CleanupCandidate]`

**Classification Rules** (9 methods to implement):
1. `_classify_temp_files()` - Temp files older than 7 days
2. `_classify_browser_cache()` - Chrome/Edge/Firefox caches
3. `_classify_dev_artifacts()` - node_modules, venv (60+ days old)
4. `_classify_windows_update()` - SoftwareDistribution\Download
5. `_classify_windows_old()` - C:\Windows.old
6. `_classify_docker_wsl()` - Docker/WSL data
7. `_classify_build_artifacts()` - dist, build, target (7+ days)
8. `_classify_old_downloads()` - Downloads folder (30+ days)
9. `_classify_recycle_bin()` - $Recycle.Bin

**Code Templates**: See IMPLEMENTATION_PLAN_STORAGE_OPTIMIZER.md Phase 4

**Unit Tests**: Create `tests/autopack/storage_optimizer/test_classifier.py`

---

### Phase 5: Cleanup Executor

**Duration**: 2-3 hours

**Implement**: `src/autopack/storage_optimizer/cleanup_executor.py`

**Dependencies**: Install `send2trash`
```bash
pip install send2trash
```

**Key Methods**:
- `CleanupExecutor.__init__(config)`
- `CleanupExecutor.create_plan(candidates) -> CleanupPlan`
- `CleanupExecutor.execute_plan(plan, approved_paths, dry_run) -> List[CleanupResult]`
- `CleanupExecutor._delete_item(candidate) -> CleanupResult`
- `CleanupExecutor._is_protected_path(path) -> bool`

**Safety Features Required**:
- Protected path checking (Windows, Program Files)
- Size threshold (auto-delete only < 100 MB)
- Total deletion limit (max 10 GB per run)
- Dry-run mode support
- Use send2trash by default (Recycle Bin)

**Code Templates**: See IMPLEMENTATION_PLAN_STORAGE_OPTIMIZER.md Phase 5

**Unit Tests**: Create `tests/autopack/storage_optimizer/test_cleanup_executor.py`

---

### Phase 6: Scheduler Integration

**Duration**: 1-2 hours

**Implement**: `src/autopack/storage_optimizer/scheduler.py`

**Key Methods**:
- `StorageScheduler.__init__(config)`
- `StorageScheduler.create_schedule() -> bool`
- `StorageScheduler.delete_schedule() -> bool`
- `StorageScheduler.check_schedule_status() -> dict`

**Windows Task Scheduler Commands**:
```bash
# Create task
schtasks /create /tn AutopackStorageOptimizer /tr "python cleanup_storage.py --auto" /sc daily /mo 14 /st 02:00 /f

# Delete task
schtasks /delete /tn AutopackStorageOptimizer /f

# Check status
schtasks /query /tn AutopackStorageOptimizer /fo csv
```

**Code Templates**: See IMPLEMENTATION_PLAN_STORAGE_OPTIMIZER.md Phase 6

---

### Phase 7: Reporting System

**Duration**: 2-3 hours

**Implement**: `src/autopack/storage_optimizer/reporter.py`

**Key Methods**:
- `StorageReporter.__init__(config)`
- `StorageReporter.create_report(...) -> StorageReport`
- `StorageReporter.generate_summary(report, results) -> str`
- `StorageReporter._save_report(report) -> None`
- `StorageReporter._load_historical_trend() -> List[dict]`

**Report Format**:
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
  1. 52.00 GB - C:\Program Files (x86)\Steam\...
  ...

CLEANUP OPPORTUNITIES:
  Total Potential Savings: 85.00 GB
  Candidates: 25

  By Category:
    dev_artifacts: 45.00 GB (8 items)
    temp_files: 20.00 GB (12 items)
    ...

CLEANUP RESULTS:
  Total Space Freed: 25.00 GB
  Successful: 18
  Failed: 2
======================================================================
```

**Code Templates**: See IMPLEMENTATION_PLAN_STORAGE_OPTIMIZER.md Phase 7

**Unit Tests**: Create `tests/autopack/storage_optimizer/test_reporter.py`

---

### Phase 9: Unit Testing (Partial)

**Duration**: 1-2 hours

**Create Test Files**:
1. `tests/autopack/storage_optimizer/test_classifier.py`
2. `tests/autopack/storage_optimizer/test_cleanup_executor.py`
3. `tests/autopack/storage_optimizer/test_reporter.py`
4. `tests/autopack/storage_optimizer/fixtures/sample_scan_results.csv`

**Coverage Goal**: >80%

**Test Framework**: pytest

**Example Test**:
```python
def test_classify_temp_files():
    classifier = FileClassifier(DEFAULT_CONFIG)

    old_temp = ScanResult(
        path="C:\\Users\\test\\AppData\\Local\\Temp\\oldfile.txt",
        size_bytes=1024 * 1024,
        modified=datetime.now() - timedelta(days=30),
        is_folder=False,
        attributes='-'
    )

    candidate = classifier.classify(old_temp)

    assert candidate is not None
    assert candidate.category == CleanupCategory.TEMP_FILES
    assert candidate.safety_level == SafetyLevel.SAFE
```

**Code Templates**: See IMPLEMENTATION_PLAN_STORAGE_OPTIMIZER.md Phase 9

---

### Phase 10: Documentation

**Duration**: 1-2 hours

**Create Documents**:

1. **docs/guides/STORAGE_OPTIMIZER_USER_GUIDE.md**
   - Installation
   - Quick start
   - Command reference
   - Configuration
   - Scheduling setup
   - Understanding reports
   - FAQ

2. **docs/api/STORAGE_OPTIMIZER_API.md**
   - Module structure
   - Class reference
   - Method signatures
   - Usage examples

3. **README_STORAGE_OPTIMIZER.md** (root)
   - Overview
   - Features
   - Quick start
   - Links to docs

**Content Guidelines**:
- Clear, concise language
- Working code examples
- Troubleshooting section
- Links to related docs

---

## 🎯 Success Criteria

After completing all phases, verify:

### Code Quality
- [ ] All files follow Autopack conventions
- [ ] No hardcoded values (use config)
- [ ] Proper error handling throughout
- [ ] Type hints on all functions
- [ ] Docstrings on all public methods

### Functionality
- [ ] Module can be imported without errors
- [ ] Classification identifies 9+ categories
- [ ] Cleanup executor uses send2trash by default
- [ ] Protected paths are never deleted
- [ ] Scheduler can create Windows tasks
- [ ] Reports are saved and loaded correctly

### Testing
- [ ] All unit tests pass
- [ ] Code coverage >80%
- [ ] No test errors or warnings
- [ ] Test fixtures created

### Documentation
- [ ] User guide is complete
- [ ] API docs are accurate
- [ ] All examples work
- [ ] README is clear

---

## 🚫 What NOT to Implement

**Skip these (Cursor will complete)**:

1. **scanner.py** - Leave placeholder/stub only
   - Cursor will integrate WizTree wrapper
   - Too complex for autonomous implementation

2. **Autopack executor integration** - Don't modify core
   - Cursor will add PhaseType.STORAGE_OPTIMIZATION
   - Cursor will create StorageOptimizationPhase handler
   - Requires understanding existing architecture

3. **Integration tests** - Only unit tests
   - Cursor will test end-to-end workflow
   - Requires real system testing

---

## 📊 Progress Tracking

Update this checklist as you complete each phase:

- [ ] Phase 2: Core Module Structure
  - [ ] Directory structure created
  - [ ] models.py implemented
  - [ ] config.py implemented
  - [ ] __init__.py with exports

- [ ] Phase 4: Classification Engine
  - [ ] FileClassifier class implemented
  - [ ] 9 classification rules working
  - [ ] Unit tests pass

- [ ] Phase 5: Cleanup Executor
  - [ ] CleanupExecutor class implemented
  - [ ] send2trash integration working
  - [ ] Protected path checking
  - [ ] Unit tests pass

- [ ] Phase 6: Scheduler
  - [ ] StorageScheduler class implemented
  - [ ] Windows Task Scheduler integration
  - [ ] Schedule management methods

- [ ] Phase 7: Reporting
  - [ ] StorageReporter class implemented
  - [ ] Report generation working
  - [ ] Historical trends tracked
  - [ ] Unit tests pass

- [ ] Phase 9: Unit Testing
  - [ ] All test files created
  - [ ] Tests pass with >80% coverage
  - [ ] Test fixtures created

- [ ] Phase 10: Documentation
  - [ ] User guide created
  - [ ] API docs created
  - [ ] README created

---

## 🎉 Completion Notification

When all phases are complete, create a summary:

**File**: `docs/AUTOPACK_COMPLETION_STORAGE_OPTIMIZER.md`

**Content**:
```markdown
# Autopack Completion Report: Storage Optimizer

Date: [completion date]
Status: ✅ Autopack Phases Complete

## Completed Phases
- ✅ Phase 2: Core Module Structure
- ✅ Phase 4: Classification Engine
- ✅ Phase 5: Cleanup Executor
- ✅ Phase 6: Scheduler
- ✅ Phase 7: Reporting
- ✅ Phase 9: Unit Testing (partial)
- ✅ Phase 10: Documentation

## Deliverables
- [List all created files]

## Test Results
- Unit tests: [pass count] / [total count]
- Coverage: [percentage]%

## Ready for Cursor
Phases 3, 8, 9 (integration tests) can now be completed by Cursor.

## Next Steps
1. Cursor implements Phase 3 (Scanner Wrapper)
2. Cursor implements Phase 8 (Executor Integration)
3. Cursor implements Phase 9 (Integration Tests)
4. System ready for production use
```

---

**Status**: Ready for Execution
**Start Command**: Copy "Quick Start for Autopack" prompt above
**References**: All documents in `docs/` directory
