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

    def test_detects_src_frontend_reference(self):
        """Should detect src/frontend/ reference."""
        content = "See src/frontend/components/ for UI"
        violations = check_content_for_legacy_paths(content, "docs/test.md")
        assert len(violations) == 1
        assert "src/frontend/" in violations[0].pattern

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
        content = "See src/backend/ and src/frontend/ together"
        violations = check_content_for_legacy_paths(content, "docs/test.md")
        # Only first match reported
        assert len(violations) == 1


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
                f"  {v.file_path}:{v.line_number} - {v.pattern}"
                for v in result.violations
            )
            pytest.fail(
                f"Found {len(result.violations)} legacy path reference(s) in canonical docs:\n"
                f"{violation_summary}\n\n"
                f"Fix these or mark them with LEGACY:/HISTORICAL: prefix."
            )
