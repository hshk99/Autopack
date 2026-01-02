# Pending Moves Queue - Actionable Report

**Generated**: 2026-01-02T17:33:34.205527Z

## Summary

- **Total Pending**: 13 items
- **Total Size Estimate**: 3.77 MB
- **Eligible Now**: 13 items
- **Showing Top**: 5 items

## Top Pending Items (by priority)

| Priority | Attempts | Age (days) | Reason | Source | Last Error |
|----------|----------|------------|--------|--------|------------|
| 20 | 2 | 0 | locked | `autopack_telemetry_seed.db` | [WinError 32] The process cannot access the file b... |
| 20 | 2 | 0 | locked | `autopack_telemetry_seed_v2.db` | [WinError 32] The process cannot access the file b... |
| 20 | 2 | 0 | locked | `telemetry_seed_debug.db` | [WinError 32] The process cannot access the file b... |
| 20 | 2 | 0 | locked | `telemetry_seed_final_green.db` | [WinError 32] The process cannot access the file b... |
| 20 | 2 | 0 | locked | `telemetry_seed_final_green2.db` | [WinError 32] The process cannot access the file b... |

## Suggested Next Actions

- **🔴 Close Locking Processes**
  - Close processes that may be locking files (database browsers, file explorers, IDEs)
- **🟡 Reboot**
  - Reboot the system to release all file locks
- **🔴 Rerun Tidy**
  - Run 'python scripts/tidy/tidy_up.py --execute' to retry pending moves

---

*This report shows the most problematic pending items. Close locking processes and rerun tidy to resolve.*
