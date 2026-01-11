"""Tests for check_canonical_doc_refs.py (P2.5: Legacy-doc containment)."""

import sys
from pathlib import Path

import pytest

# Add scripts/ci to path for import
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts" / "ci"))

from check_canonical_doc_refs import (
    CANONICAL_OPERATOR_DOCS,
    LEGACY_PATH_PATTERNS,
    check_canonical_docs,
    check_content_for_legacy_paths,
)


class TestP25LegacyPathDetection:
    """Tests for legacy path detection in canonical docs."""

    def test_detects_src_backend_reference(self):
        """Should detect src/backend/ reference."""
        content = "The API is in src/backend/api.py"
        violations = check_content_for_legacy_paths(content, "docs/test.md")
        assert len(violations) == 1
        assert "src/backend/" in violations[0].pattern

    def test_allows_src_frontend_reference(self):
        """Should allow src/frontend/ reference (canonical root Vite app path)."""
        content = "See src/frontend/components/ for UI"
        violations = check_content_for_legacy_paths(content, "docs/test.md")
        # src/frontend/ is CANONICAL in this repo (root Vite app), not legacy
        assert len(violations) == 0

    def test_detects_backend_reference(self):
        """Should detect backend/ reference."""
        content = "Run backend/server.py to start"
        violations = check_content_for_legacy_paths(content, "docs/test.md")
        assert len(violations) == 1
        assert "backend/" in violations[0].pattern

    def test_allows_current_paths(self):
        """Should allow current codebase paths."""
        content = """
        The API is in src/autopack/main.py
        Dashboard is in src/autopack/dashboard/
        Tests are in tests/
        """
        violations = check_content_for_legacy_paths(content, "docs/test.md")
        assert len(violations) == 0

    def test_skips_explicitly_marked_legacy(self):
        """Should skip lines explicitly marked as LEGACY."""
        content = "LEGACY: The old path was src/backend/api.py"
        violations = check_content_for_legacy_paths(content, "docs/test.md")
        assert len(violations) == 0

    def test_skips_explicitly_marked_deprecated(self):
        """Should skip lines explicitly marked as DEPRECATED."""
        content = "DEPRECATED: src/backend/ is no longer used"
        violations = check_content_for_legacy_paths(content, "docs/test.md")
        assert len(violations) == 0

    def test_skips_explicitly_marked_historical(self):
        """Should skip lines explicitly marked as HISTORICAL."""
        content = "HISTORICAL: Was in src/backend/ before migration"
        violations = check_content_for_legacy_paths(content, "docs/test.md")
        assert len(violations) == 0

    def test_reports_correct_line_number(self):
        """Should report correct line number."""
        content = """Line 1
Line 2
src/backend/api.py is here
Line 4
"""
        violations = check_content_for_legacy_paths(content, "docs/test.md")
        assert len(violations) == 1
        assert violations[0].line_number == 3

    def test_one_violation_per_line(self):
        """Should report only one violation per line (first match)."""
        content = "See src/backend/ and backend/api/ together"
        violations = check_content_for_legacy_paths(content, "docs/test.md")
        # Only first match reported (src/backend/ is first)
        assert len(violations) == 1
        assert "src/backend/" in violations[0].pattern


class TestCanonicalDocsCheck:
    """Tests for canonical docs checking."""

    def test_canonical_docs_list_not_empty(self):
        """Should have canonical docs defined."""
        assert len(CANONICAL_OPERATOR_DOCS) > 0

    def test_canonical_docs_include_key_files(self):
        """Should include key operator docs."""
        docs = set(CANONICAL_OPERATOR_DOCS)
        assert "docs/QUICKSTART.md" in docs
        assert "docs/DEPLOYMENT.md" in docs
        assert "docs/GOVERNANCE.md" in docs
        assert "docs/CANONICAL_API_CONTRACT.md" in docs

    def test_legacy_patterns_defined(self):
        """Should have legacy patterns defined."""
        assert len(LEGACY_PATH_PATTERNS) > 0

    def test_check_canonical_docs_returns_result(self):
        """Should return a CheckResult."""
        # Use a temp directory to avoid checking real docs
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as tmpdir:
            result = check_canonical_docs(Path(tmpdir))
            # Should succeed with no files
            assert result.exit_code == 0
            assert result.violations == []


class TestFencedCodeBlockHandling:
    """Tests for fenced code block handling (PR-04 fix)."""

    def test_fenced_block_scanned_by_default(self):
        """Code blocks without HISTORICAL marker should be scanned."""
        content = """
Normal text.

```bash
cd src/backend/
```

More text.
"""
        violations = check_content_for_legacy_paths(content, "docs/test.md")
        assert len(violations) == 1
        assert violations[0].line_number == 5

    def test_fenced_block_with_historical_marker_skipped(self):
        """Code blocks with HISTORICAL marker should be skipped."""
        content = """
Normal text.

HISTORICAL: This shows the old directory structure:
```bash
cd src/backend/
ls backend/files/
```

Current structure uses src/autopack/.
"""
        violations = check_content_for_legacy_paths(content, "docs/test.md")
        assert len(violations) == 0

    def test_historical_marker_within_3_lines(self):
        """HISTORICAL marker should work within 3 lines of fence."""
        content = """
This was the old structure:

HISTORICAL EXAMPLE:

```bash
src/backend/api.py
```
"""
        violations = check_content_for_legacy_paths(content, "docs/test.md")
        assert len(violations) == 0

    def test_historical_marker_too_far_away(self):
        """HISTORICAL marker more than 3 lines away should not apply."""
        content = """
HISTORICAL: This was old

Line 2
Line 3
Line 4
Line 5

```bash
src/backend/api.py
```
"""
        violations = check_content_for_legacy_paths(content, "docs/test.md")
        assert len(violations) == 1

    def test_multiple_fenced_blocks_independent(self):
        """Each fenced block should be checked independently."""
        content = """
HISTORICAL:
```bash
src/backend/  # This should be skipped
```

```bash
src/backend/  # This should be flagged
```
"""
        violations = check_content_for_legacy_paths(content, "docs/test.md")
        assert len(violations) == 1

    def test_nested_looking_fences_handled(self):
        """Consecutive fences should be handled correctly."""
        content = """
```json
{"path": "src/backend/"}
```

Normal text with src/backend/ reference.
"""
        violations = check_content_for_legacy_paths(content, "docs/test.md")
        # Both the JSON content and normal text should be flagged
        assert len(violations) == 2

    def test_text_outside_fence_always_scanned(self):
        """Text outside fences should always be scanned."""
        content = """
HISTORICAL:
```bash
src/backend/  # skipped
```

But src/backend/ outside the fence is still flagged.
"""
        violations = check_content_for_legacy_paths(content, "docs/test.md")
        assert len(violations) == 1
        assert "outside the fence" in violations[0].line_content


class TestCurrentCanonicalDocsClean:
    """Tests that current canonical docs are clean of legacy refs.

    This is a contract test - if it fails, canonical docs have
    legacy path references that need fixing.
    """

    def test_canonical_docs_no_legacy_paths(self):
        """Canonical docs should not have legacy path references."""
        repo_root = Path(__file__).parent.parent.parent
        result = check_canonical_docs(repo_root)

        if result.violations:
            # Build helpful error message
            violation_summary = "\n".join(
                f"  {v.file_path}:{v.line_number} - {v.pattern}" for v in result.violations
            )
            pytest.fail(
                f"Found {len(result.violations)} legacy path reference(s) in canonical docs:\n"
                f"{violation_summary}\n\n"
                f"Fix these or mark them with LEGACY:/HISTORICAL: prefix."
            )
