# BUILD-186: Deterministic Console Glyph Normalization (Critical Path Only)

## Summary

This PR implements deterministic, mechanical normalization of Unicode console glyphs to ASCII equivalents in critical-path scripts. This prevents Windows console crashes due to 'charmap' codec errors when running scripts that print Unicode characters.

## Problem

On Windows, console output uses legacy codepages (e.g., cp1252/cp437) by default. When scripts print Unicode characters like `->`, `[x]`, or `[OK]`, they can crash with:

```
'charmap' codec can't encode character '\u2192' in position 4: character maps to <undefined>
```

## Solution

### Tool: `scripts/tools/normalize_console_glyphs.py`

A deterministic tool that:

1. **Mechanically identifies critical-path scripts** by parsing:
   - CI workflow files (`.github/workflows/*.yml`)
   - Test files that invoke scripts via subprocess

2. **Normalizes Unicode glyphs** in those scripts to ASCII equivalents:
   | Unicode | ASCII | Name |
   |---------|-------|------|
   | `->` | `->` | RIGHTWARDS ARROW |
   | `<-` | `<-` | LEFTWARDS ARROW |
   | `<->` | `<->` | LEFT RIGHT ARROW |
   | `[x]` | `[x]` | CHECK MARK |
   | `[x]` | `[x]` | HEAVY CHECK MARK |
   | `[OK]` | `[OK]` | WHITE HEAVY CHECK MARK (emoji) |
   | `[X]` | `[X]` | BALLOT X |
   | `[X]` | `[X]` | HEAVY BALLOT X |
   | `[X]` | `[X]` | CROSS MARK (emoji) |
   | `*` | `*` | BULLET |
   | `[!]` | `[!]` | WARNING SIGN |
   | `[i]` | `[i]` | INFORMATION SOURCE |

3. **Three operating modes**:
   - `--list-critical`: List all critical-path scripts
   - `--check --files-from <path>`: Check mode (exits non-zero if changes needed)
   - Default: Fix mode (writes normalized content)

### CI Enforcement

The lint job runs the check in CI:

```yaml
- name: Normalize console glyphs in critical scripts (BUILD-186)
  run: |
    python scripts/tools/normalize_console_glyphs.py --list-critical > /tmp/critical_scripts.txt
    python scripts/tools/normalize_console_glyphs.py --check \
      --files-from /tmp/critical_scripts.txt \
      --exclude scripts/ci/check_windows_console_unicode.py
```

**Key properties**:
- CI only runs `--check` mode - never auto-writes
- Exclusion for `check_windows_console_unicode.py` (intentionally contains Unicode as data)
- Requires explicit operator action to fix violations

## Files Changed

### New Files
- `scripts/tools/normalize_console_glyphs.py` - The normalization tool
- `tests/ci/test_normalize_console_glyphs.py` - Comprehensive tests
- `docs/BUILD-186_DETERMINISTIC_CONSOLE_GLYPH_NORMALIZATION.md` - This document

### Modified Files (Normalized)
- `scripts/check_dependency_sync.py`
- `scripts/check_doc_links.py`
- `scripts/check_sot_write_protection.py`
- `scripts/check_version_consistency.py`
- `scripts/migrations/add_total_tokens_build144.py`
- `scripts/security/diff_gate.py`
- `scripts/security/normalize_sarif.py`
- `scripts/security/update_baseline.py`
- `scripts/storage/scan_and_report.py`
- `scripts/tidy/sot_db_sync.py`
- `scripts/tidy/sot_summary_refresh.py`
- `scripts/tidy/tidy_up.py`
- `scripts/tidy/verify_workspace_structure.py`

### CI Configuration
- `.github/workflows/ci.yml` - Added glyph normalization check step

## How to Use

### List critical scripts
```bash
python scripts/tools/normalize_console_glyphs.py --list-critical
```

### Check for violations (CI mode)
```bash
python scripts/tools/normalize_console_glyphs.py --list-critical > /tmp/critical_scripts.txt
python scripts/tools/normalize_console_glyphs.py --check --files-from /tmp/critical_scripts.txt
```

### Fix violations (explicit operator action)
```bash
python scripts/tools/normalize_console_glyphs.py --list-critical > /tmp/critical_scripts.txt
python scripts/tools/normalize_console_glyphs.py --files-from /tmp/critical_scripts.txt
```

## Design Principles

1. **Intentional operator change required**: CI blocks but never auto-fixes
2. **Mechanical identification**: No manual allowlists; critical scripts derived from CI/test analysis
3. **Idempotent**: Running the fix twice produces identical results
4. **ASCII-safe output**: The tool itself never crashes on Windows
5. **Narrow scope**: Only normalizes critical-path scripts, not all source files

## Relationship to BUILD-184/185

- **BUILD-184**: Runtime `safe_print()` fallback for unknown glyphs
- **BUILD-185**: CI guard blocking Unicode arrows in `print()` calls within `src/`
- **BUILD-186**: Proactive normalization of critical scripts to prevent issues entirely

These layers complement each other:
1. BUILD-186 proactively normalizes known critical scripts
2. BUILD-185 blocks new violations in production library code
3. BUILD-184 provides runtime safety for anything that slips through
