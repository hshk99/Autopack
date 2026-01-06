"""
Tests for verify_workspace_structure.py allowlist behavior.

BUILD-183: Ensures workspace verifier correctly allows:
- Root security/ directory
- docs/ files matching allowlisted patterns
- Archive buckets when present

Also ensures default-warn behavior is preserved for unknown files.
"""

from __future__ import annotations

from pathlib import Path

import pytest

# Import verifier functions and configuration
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scripts" / "tidy"))
from verify_workspace_structure import (
    ROOT_ALLOWED_DIRS,
    DOCS_ALLOWED_PATTERNS,
    ARCHIVE_REQUIRED_BUCKETS,
    is_docs_file_allowed,
    matches_pattern,
    verify_root_structure,
    verify_docs_structure,
    verify_archive_structure,
)


class TestRootSecurityDirectoryAllowlist:
    """BUILD-183: Verifier does NOT warn on root 'security/' directory."""

    def test_security_in_root_allowed_dirs(self) -> None:
        """security/ must be in ROOT_ALLOWED_DIRS."""
        assert "security" in ROOT_ALLOWED_DIRS

    def test_verify_root_no_warning_for_security_dir(self, tmp_path: Path) -> None:
        """verify_root_structure should NOT emit warning for security/ directory."""
        # Create a minimal repo root structure
        (tmp_path / "security").mkdir()
        (tmp_path / ".git").mkdir()
        (tmp_path / "README.md").touch()

        # Patch REPO_ROOT temporarily by using the function directly
        # The function uses repo_root parameter, so we can test it directly
        is_valid, errors, warnings = verify_root_structure(tmp_path)

        # Should be valid with no errors
        assert is_valid is True
        assert len(errors) == 0

        # Should NOT have warning about security directory
        security_warnings = [w for w in warnings if "security" in w.lower()]
        assert len(security_warnings) == 0, f"Unexpected security warnings: {security_warnings}"


class TestDocsPatternAllowlist:
    """BUILD-183: Verifier does NOT warn on allowlisted docs patterns."""

    @pytest.mark.parametrize(
        "filename,should_allow",
        [
            # BUILD-*.md patterns (explicitly in task requirements)
            ("BUILD-123_SOME_FEATURE.md", True),
            ("BUILD-183_WORKSPACE_STRUCTURE_WARNINGS_REDUCTION.md", True),
            ("BUILD_155_SOT_TELEMETRY.md", True),
            # Completion reports
            ("COMPLETION_REPORT_2026-01-03.md", True),
            ("INTENTION_ANCHOR_COMPLETION_SUMMARY.md", True),
            # Report patterns
            ("DOC_LINK_TRIAGE_REPORT.md", True),
            ("CANARY_TEST_REPORT.md", True),
            # Operations and playbooks
            ("AUTOPILOT_OPERATIONS.md", True),
            ("DOC_LINK_TRIAGE_PLAYBOOK_NEXT_STEPS.md", True),
            # Status and plan patterns
            ("IMPLEMENTATION_STATUS_2026-01-03.md", True),
            ("STORAGE_OPTIMIZER_PHASE3_PLAN.md", True),
            # Security docs
            ("SECURITY_BASELINE_AUTOMATION_STATUS.md", True),
            ("SECURITY_LOG.md", True),
            # Other allowlisted patterns
            ("LEARNED_ERROR_MITIGATIONS.json", True),
            ("CHAT_HISTORY_EXTRACT.md", True),
            ("P0_RELIABILITY_DECISIONS.md", True),
            # Unknown files should NOT be allowed (default-warn preserved)
            ("RANDOM_UNKNOWN_FILE.md", False),
            ("my_notes.md", False),
            ("todo_list.txt", False),
        ],
    )
    def test_docs_file_allowlist(self, filename: str, should_allow: bool) -> None:
        """Test that is_docs_file_allowed correctly identifies allowlisted files."""
        result = is_docs_file_allowed(filename)
        assert (
            result == should_allow
        ), f"is_docs_file_allowed('{filename}') returned {result}, expected {should_allow}"

    def test_build_pattern_in_allowed_patterns(self) -> None:
        """BUILD-*.md pattern must be in DOCS_ALLOWED_PATTERNS."""
        assert "BUILD-*.md" in DOCS_ALLOWED_PATTERNS
        assert "BUILD_*.md" in DOCS_ALLOWED_PATTERNS

    def test_verify_docs_no_warning_for_build_docs(self, tmp_path: Path) -> None:
        """verify_docs_structure should NOT warn on BUILD-*.md files."""
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()

        # Create required SOT files
        for sot_file in [
            "PROJECT_INDEX.json",
            "BUILD_HISTORY.md",
            "DEBUG_LOG.md",
            "ARCHITECTURE_DECISIONS.md",
            "FUTURE_PLAN.md",
            "LEARNED_RULES.json",
        ]:
            (docs_dir / sot_file).touch()

        # Create allowlisted files
        (docs_dir / "BUILD-183_TEST.md").touch()
        (docs_dir / "COMPLETION_REPORT_TEST.md").touch()

        is_valid, errors, warnings = verify_docs_structure(docs_dir)

        assert is_valid is True
        assert len(errors) == 0

        # Should NOT warn about BUILD-183_TEST.md or COMPLETION_REPORT_TEST.md
        build_warnings = [w for w in warnings if "BUILD-183_TEST.md" in w]
        assert len(build_warnings) == 0, f"Unexpected BUILD doc warnings: {build_warnings}"

        completion_warnings = [w for w in warnings if "COMPLETION_REPORT_TEST.md" in w]
        assert (
            len(completion_warnings) == 0
        ), f"Unexpected completion warnings: {completion_warnings}"


class TestDocsDefaultWarnPreserved:
    """BUILD-183: Verifier DOES warn on unknown/unclassified docs files."""

    def test_verify_docs_warns_on_unknown_file(self, tmp_path: Path) -> None:
        """verify_docs_structure should warn on unknown docs files."""
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()

        # Create required SOT files
        for sot_file in [
            "PROJECT_INDEX.json",
            "BUILD_HISTORY.md",
            "DEBUG_LOG.md",
            "ARCHITECTURE_DECISIONS.md",
            "FUTURE_PLAN.md",
            "LEARNED_RULES.json",
        ]:
            (docs_dir / sot_file).touch()

        # Create an unknown file that should trigger warning
        unknown_file = "SYNTHETIC_UNKNOWN_FILE_FOR_TEST.md"
        (docs_dir / unknown_file).touch()

        is_valid, errors, warnings = verify_docs_structure(docs_dir)

        # Should still be valid (warnings don't make it invalid)
        assert is_valid is True

        # Should have warning about the unknown file
        unknown_warnings = [w for w in warnings if unknown_file in w]
        assert (
            len(unknown_warnings) == 1
        ), f"Expected 1 warning for unknown file, got {len(unknown_warnings)}: {warnings}"
        assert "Non-SOT file in docs/" in unknown_warnings[0]


class TestArchiveBucketsExist:
    """BUILD-183: Verifier does NOT warn about missing buckets when present."""

    def test_required_buckets_defined(self) -> None:
        """Verify required archive buckets are defined."""
        required = {"plans", "prompts", "scripts", "unsorted"}
        assert required.issubset(ARCHIVE_REQUIRED_BUCKETS)

    def test_verify_archive_no_warning_when_buckets_exist(self, tmp_path: Path) -> None:
        """verify_archive_structure should NOT warn when all buckets exist."""
        archive_dir = tmp_path / "archive"
        archive_dir.mkdir()

        # Create all required buckets
        for bucket in ARCHIVE_REQUIRED_BUCKETS:
            (archive_dir / bucket).mkdir()

        is_valid, errors, warnings = verify_archive_structure(archive_dir)

        assert is_valid is True
        assert len(errors) == 0

        # Should NOT have warning about missing buckets
        bucket_warnings = [w for w in warnings if "bucket" in w.lower()]
        assert len(bucket_warnings) == 0, f"Unexpected bucket warnings: {bucket_warnings}"

    def test_verify_archive_warns_when_bucket_missing(self, tmp_path: Path) -> None:
        """verify_archive_structure should warn when a bucket is missing."""
        archive_dir = tmp_path / "archive"
        archive_dir.mkdir()

        # Create most buckets but leave one out
        for bucket in list(ARCHIVE_REQUIRED_BUCKETS)[:-1]:
            (archive_dir / bucket).mkdir()

        missing_bucket = list(ARCHIVE_REQUIRED_BUCKETS)[-1]

        is_valid, errors, warnings = verify_archive_structure(archive_dir)

        # Should be valid (missing buckets are warnings, not errors)
        assert is_valid is True

        # Should have warning about missing bucket
        bucket_warnings = [w for w in warnings if "bucket" in w.lower()]
        assert len(bucket_warnings) == 1
        assert missing_bucket in bucket_warnings[0]


class TestEnforcementRemains:
    """BUILD-183: Enforcement remains blocking on errors."""

    def test_disallowed_docs_subdir_is_error(self, tmp_path: Path) -> None:
        """Disallowed subdirectory in docs/ should be an error (not warning)."""
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()

        # Create required SOT files
        for sot_file in [
            "PROJECT_INDEX.json",
            "BUILD_HISTORY.md",
            "DEBUG_LOG.md",
            "ARCHITECTURE_DECISIONS.md",
            "FUTURE_PLAN.md",
            "LEARNED_RULES.json",
        ]:
            (docs_dir / sot_file).touch()

        # Create disallowed subdirectory
        (docs_dir / "forbidden_subdir").mkdir()

        is_valid, errors, warnings = verify_docs_structure(docs_dir)

        # Should be INVALID due to error
        assert is_valid is False
        assert len(errors) >= 1

        # Error should mention the disallowed subdirectory
        subdir_errors = [e for e in errors if "forbidden_subdir" in e]
        assert len(subdir_errors) == 1

    def test_disallowed_root_file_is_error(self, tmp_path: Path) -> None:
        """Disallowed file at root should be an error (not warning)."""
        # Create minimal structure
        (tmp_path / ".git").mkdir()
        (tmp_path / "README.md").touch()

        # Create disallowed file
        (tmp_path / "forbidden_file.xyz").touch()

        is_valid, errors, warnings = verify_root_structure(tmp_path)

        # Should be INVALID due to error
        assert is_valid is False
        assert len(errors) >= 1

        # Error should mention the disallowed file
        file_errors = [e for e in errors if "forbidden_file.xyz" in e]
        assert len(file_errors) == 1


class TestMatchesPatternHelper:
    """Test the matches_pattern helper function."""

    @pytest.mark.parametrize(
        "filename,pattern,expected",
        [
            ("BUILD-123.md", "BUILD-*.md", True),
            ("BUILD_123.md", "BUILD_*.md", True),
            ("COMPLETION_REPORT.md", "*_REPORT*.md", True),
            ("MY_REPORT_TEST.md", "*_REPORT*.md", True),
            ("SECURITY_LOG.md", "*_LOG*.md", True),
            ("random.md", "BUILD-*.md", False),
            ("build-123.md", "BUILD-*.md", False),  # Case sensitive
        ],
    )
    def test_matches_pattern(self, filename: str, pattern: str, expected: bool) -> None:
        """Test pattern matching behavior."""
        result = matches_pattern(filename, pattern)
        assert result == expected
