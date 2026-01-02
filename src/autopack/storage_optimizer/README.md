# Storage Optimizer Module

Policy-aware disk space analysis and cleanup recommendations for Autopack.

## Quick Start

```bash
# Scan C: drive and generate report
python scripts/storage/scan_and_report.py

# Scan specific directory
python scripts/storage/scan_and_report.py --dir c:/dev/Autopack

# See all options
python scripts/storage/scan_and_report.py --help
```

## Features (MVP)

- ✅ Policy-aware scanning and classification
- ✅ Protected path enforcement (NEVER flags SOT, src/, tests/, databases)
- ✅ Retention window compliance
- ✅ Comprehensive reporting (text + JSON)
- ✅ Dry-run only (no actual deletion)

## Module Structure

```
storage_optimizer/
├── policy.py       - Policy loader and enforcement
├── models.py       - Core data structures
├── scanner.py      - Disk scanning (Python-based)
├── classifier.py   - Policy-aware classification
├── reporter.py     - Report generation
└── __init__.py     - Module exports
```

## Programmatic Usage

```python
from autopack.storage_optimizer import (
    load_policy,
    StorageScanner,
    FileClassifier,
    StorageReporter
)

# Load policy
policy = load_policy()  # Loads config/protection_and_retention_policy.yaml

# Scan
scanner = StorageScanner(max_depth=3)
results = scanner.scan_high_value_directories("C")

# Classify
classifier = FileClassifier(policy)
candidates = classifier.classify_batch(results)

# Report
reporter = StorageReporter()
# ... (see completion doc for full example)
```

## Policy Integration

This module enforces policies from:
- **Machine-readable**: `config/protection_and_retention_policy.yaml`
- **Human-readable**: `docs/DATA_RETENTION_AND_STORAGE_POLICY.md`

### Protected Paths (Never Flagged)

- `src/**`, `tests/**` - Source and tests
- `.git/**`, `.github/**` - Repository metadata
- `docs/PROJECT_INDEX.json`, `docs/BUILD_HISTORY.md`, etc. - SOT core files
- `archive/superseded/**` - Audit trail
- `*.db`, `*.sqlite` - Databases

### Categories

- `dev_caches` - node_modules, venv, __pycache__, dist/, build/
- `diagnostics_logs` - Diagnostic outputs and error logs
- `runs` - Autonomous run artifacts
- `archive_buckets` - Archive directories (coordinated with Tidy)
- `unknown` - Unrecognized items (report only)

## Retention Windows

- **Diagnostics**: Delete after 90 days (approval required)
- **Runs**: Delete after 180 days (approval required)
- **Superseded**: Delete after 365 days (approval required)

## Safety Features

1. **Protected path checking** - First check in classification pipeline
2. **Approval requirements** - Marks items needing manual approval
3. **Dry-run only** - MVP does NOT delete anything
4. **Policy-driven** - All rules centralized in policy file

## Documentation

- **Completion Report**: [docs/STORAGE_OPTIMIZER_MVP_COMPLETION.md](../../../docs/STORAGE_OPTIMIZER_MVP_COMPLETION.md)
- **Implementation Plan**: [docs/IMPLEMENTATION_PLAN_STORAGE_OPTIMIZER_REVISED.md](../../../docs/IMPLEMENTATION_PLAN_STORAGE_OPTIMIZER_REVISED.md)
- **Policy Specification**: [docs/DATA_RETENTION_AND_STORAGE_POLICY.md](../../../docs/DATA_RETENTION_AND_STORAGE_POLICY.md)

## Future Phases

### Phase 2: Execution (Not in MVP)
- Actual file deletion via send2trash
- Approval workflow
- Undo/rollback

### Phase 3: Automation (Not in MVP)
- Windows Task Scheduler integration
- Fortnightly automated runs
- Email notifications

### Phase 4: Performance (Not in MVP)
- WizTree CLI integration (30-50x faster scanning)
- Caching layer
- Parallel scanning

### Phase 5: Integration (Not in MVP)
- Autopack executor phase handler
- Database schema
- Telemetry tracking

## Current Status

**Version**: 1.0 (MVP)
**Status**: ✅ Complete and Tested
**Date**: 2026-01-01

MVP delivers safe, policy-aware disk analysis and reporting.
Execution features will be added in future phases.
