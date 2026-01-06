# BUILD-184: Windows UTF-8 + Unicode-Safe IO

## Repro Summary

On Windows, running scripts that print Unicode characters (e.g., `→`) to the console fails with:

```
'charmap' codec can't encode character '\u2192' in position 4: character maps to <undefined>
```

This happens because Windows console uses legacy codepages (e.g., `cp1252`) by default, which cannot encode many Unicode characters.

## Root Cause

1. **Console encoding**: Python's `print()` uses `sys.stdout.encoding`, which defaults to the Windows console's codepage (often `cp1252` or `cp437`).

2. **Unicode characters in code**: Several scripts use Unicode arrows (`→`, U+2192) for visual formatting:
   - `scripts/tidy/sot_db_sync.py:767` - "SOT → DB/Qdrant Sync"
   - 35+ other scripts with similar patterns

3. **File writes without encoding**: Some `Path.write_text()` and `open()` calls lack explicit `encoding="utf-8"`, defaulting to system encoding.

## Solution

### 1. Safe Print Helper

Created `src/autopack/safe_print.py` with:

- `safe_print(*args, **kwargs)`: Wrapper around `print()` that catches `UnicodeEncodeError` and falls back to ASCII-safe replacements
- `ASCII_REPLACEMENTS`: Dict mapping Unicode chars to ASCII equivalents (e.g., `→` to `->`)
- `configure_utf8_stdout()`: Reconfigures stdout/stderr to use UTF-8 with error handling

### 2. Fixed Immediate Crash

Updated `scripts/tidy/sot_db_sync.py` to use ASCII-safe output directly (replaced `→` with `->`).

### 3. Unit Test Enforcement

- **Unit tests**: Verify `safe_print` works with cp1252 stdout simulation
- Tests cover ASCII passthrough, Unicode replacement, and fallback behavior

## Acceptance Criteria

1. `test_cli_smoke_docs_only` no longer crashes on Windows
2. All existing tests pass
3. New unit tests verify Unicode-safe output

## Files Changed

- `src/autopack/safe_print.py` - New safe print utility
- `scripts/tidy/sot_db_sync.py` - Fixed immediate crash (ASCII arrow)
- `tests/encoding/test_unicode_safe_output.py` - New unit tests

## Non-Goals

- Converting all 36+ scripts to use `safe_print()` (future work)
- Changing file content encoding (most already use UTF-8)
- Windows console configuration changes (user responsibility)

## How to Verify on Windows

```bash
# This should no longer crash
python scripts/tidy/sot_db_sync.py --docs-only

# Run the encoding tests
python -m pytest tests/encoding/test_unicode_safe_output.py -v
```

## Enforcement Model

The current posture is **narrow CI guard + broad runtime mitigation**:

- **CI guard** (`scripts/ci/check_windows_console_unicode.py`): Blocks only arrow glyphs (`→`, `←`, `↔`) in `print(...)` calls within `src/` and critical-path scripts. This prevents regression of the known crash without repo-wide churn.
- **`safe_print()` runtime**: Handles many glyphs via `ASCII_REPLACEMENTS` (checkmarks, bullets, box-drawing, etc.), so most Unicode won't crash even if it slips past the guard.
- **New glyph crashes**: If a glyph not in the CI guard causes a crash, **intentional operator change is required** — either extend `UNICODE_ARROW_CHARS` in the guard, or migrate the offending line to `safe_print()`. Nothing auto-applies.

## Future Work

- Gradually migrate scripts to use `safe_print()` for console output
- Consider expanding CI guard to cover all `ASCII_REPLACEMENTS` glyphs if crashes recur
