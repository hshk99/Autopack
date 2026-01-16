"""Tests for SOT runtime enforcement (IMP-SOT-001).

Tests runtime detection of SOT drift during autonomous execution.
Ensures BUILD_HISTORY and DEBUG_LOG remain consistent.
"""

from autopack.gaps.doc_drift import SOTDriftDetector


class TestSOTDriftDetectorQuickCheck:
    """Tests for SOTDriftDetector.quick_check() method."""

    def test_quick_check_passes_for_valid_sot(self, tmp_path):
        """Test that quick_check passes when SOT structure is valid."""
        # Create valid SOT structure
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()
        (docs_dir / "BUILD_HISTORY.md").write_text("# BUILD_HISTORY\n\n## BUILD-001\n- Item 1\n")

        detector = SOTDriftDetector(project_root=str(tmp_path))
        is_consistent, issues = detector.quick_check()

        assert is_consistent
        assert len(issues) == 0

    def test_quick_check_fails_for_missing_build_history(self, tmp_path):
        """Test that quick_check fails when BUILD_HISTORY.md is missing."""
        detector = SOTDriftDetector(project_root=str(tmp_path))
        is_consistent, issues = detector.quick_check()

        assert not is_consistent
        assert "BUILD_HISTORY.md not found" in issues

    def test_quick_check_fails_for_empty_build_history(self, tmp_path):
        """Test that quick_check fails when BUILD_HISTORY.md is empty."""
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()
        (docs_dir / "BUILD_HISTORY.md").write_text("")

        detector = SOTDriftDetector(project_root=str(tmp_path))
        is_consistent, issues = detector.quick_check()

        assert not is_consistent
        assert any("no build entries" in issue.lower() for issue in issues)

    def test_quick_check_fails_for_empty_build_history_content(self, tmp_path):
        """Test that quick_check fails when BUILD_HISTORY.md has no BUILD- entries."""
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()
        (docs_dir / "BUILD_HISTORY.md").write_text("# BUILD_HISTORY\n\nNo builds yet")

        detector = SOTDriftDetector(project_root=str(tmp_path))
        is_consistent, issues = detector.quick_check()

        assert not is_consistent
        assert any("no build entries" in issue.lower() for issue in issues)

    def test_quick_check_detects_orphaned_references(self, tmp_path):
        """Test that quick_check detects orphaned BUILD references in DEBUG_LOG."""
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()

        # Create BUILD_HISTORY with BUILD-001, BUILD-002
        (docs_dir / "BUILD_HISTORY.md").write_text(
            "# BUILD_HISTORY\n\n## BUILD-001\n- Item 1\n\n## BUILD-002\n- Item 2\n"
        )

        # Create DEBUG_LOG with reference to non-existent BUILD-999
        (docs_dir / "DEBUG_LOG.md").write_text(
            "# DEBUG_LOG\n\nPhase executed with BUILD-001\nRelated to BUILD-999\n"
        )

        detector = SOTDriftDetector(project_root=str(tmp_path))
        is_consistent, issues = detector.quick_check()

        assert not is_consistent
        assert any("orphaned" in issue.lower() for issue in issues)

    def test_quick_check_passes_with_valid_debug_log_references(self, tmp_path):
        """Test that quick_check passes when DEBUG_LOG references valid BUILD entries."""
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()

        # Create BUILD_HISTORY with BUILD-001, BUILD-002
        (docs_dir / "BUILD_HISTORY.md").write_text(
            "# BUILD_HISTORY\n\n## BUILD-001\n- Item 1\n\n## BUILD-002\n- Item 2\n"
        )

        # Create DEBUG_LOG with references to existing builds only
        (docs_dir / "DEBUG_LOG.md").write_text(
            "# DEBUG_LOG\n\nPhase executed with BUILD-001\nRelated to BUILD-002\n"
        )

        detector = SOTDriftDetector(project_root=str(tmp_path))
        is_consistent, issues = detector.quick_check()

        assert is_consistent
        assert len(issues) == 0

    def test_quick_check_with_no_debug_log(self, tmp_path):
        """Test that quick_check passes when DEBUG_LOG doesn't exist (it's optional)."""
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()
        (docs_dir / "BUILD_HISTORY.md").write_text("# BUILD_HISTORY\n\n## BUILD-001\n- Item 1\n")

        detector = SOTDriftDetector(project_root=str(tmp_path))
        is_consistent, issues = detector.quick_check()

        assert is_consistent
        assert len(issues) == 0

    def test_find_orphaned_references_empty_when_no_references(self, tmp_path):
        """Test that _find_orphaned_references returns empty list when there are no orphans."""
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()

        build_history = docs_dir / "BUILD_HISTORY.md"
        build_history.write_text("# BUILD_HISTORY\n\n## BUILD-001\n- Item 1\n")

        debug_log = docs_dir / "DEBUG_LOG.md"
        debug_log.write_text("# DEBUG_LOG\n\nNo BUILD references here\n")

        detector = SOTDriftDetector(project_root=str(tmp_path))
        orphans = detector._find_orphaned_references(build_history, debug_log)

        assert len(orphans) == 0

    def test_find_orphaned_references_handles_missing_files(self, tmp_path):
        """Test that _find_orphaned_references gracefully handles missing files."""
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()

        build_history = docs_dir / "BUILD_HISTORY.md"
        debug_log = docs_dir / "DEBUG_LOG.md"  # Doesn't exist

        detector = SOTDriftDetector(project_root=str(tmp_path))
        orphans = detector._find_orphaned_references(build_history, debug_log)

        # Should return empty list, not raise an exception
        assert len(orphans) == 0

    def test_detector_uses_custom_project_root(self, tmp_path):
        """Test that SOTDriftDetector respects custom project_root parameter."""
        # Create structure in subdirectory
        custom_root = tmp_path / "custom"
        custom_root.mkdir()
        docs_dir = custom_root / "docs"
        docs_dir.mkdir()
        (docs_dir / "BUILD_HISTORY.md").write_text("# BUILD_HISTORY\n\n## BUILD-001\n- Item\n")

        detector = SOTDriftDetector(project_root=str(custom_root))
        is_consistent, issues = detector.quick_check()

        assert is_consistent
        assert len(issues) == 0

    def test_quick_check_with_multiple_issues(self, tmp_path):
        """Test that quick_check reports all issues when multiple are found."""
        # Create docs dir but no BUILD_HISTORY
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()

        # Create DEBUG_LOG with orphaned reference
        (docs_dir / "DEBUG_LOG.md").write_text("# DEBUG_LOG\n\nReference to BUILD-999\n")

        detector = SOTDriftDetector(project_root=str(tmp_path))
        is_consistent, issues = detector.quick_check()

        assert not is_consistent
        assert len(issues) >= 1  # At minimum, BUILD_HISTORY not found
