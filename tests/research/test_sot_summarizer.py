"""Tests for SOT document summarizer."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from autopack.research.sot_summarizer import (
    ArchitectureDecision,
    BuildEntry,
    SOTSummarizer,
    SOTSummary,
    get_sot_summarizer,
    summarize_sot_documents,
)


class TestBuildEntry:
    """Test BuildEntry dataclass."""

    def test_build_entry_creation(self) -> None:
        """Test creating a BuildEntry."""
        entry = BuildEntry(
            build_id="BUILD-001",
            timestamp="2026-01-30",
            phase="Implementation",
            summary="Added feature X",
            files_changed=["src/module.py", "tests/test_module.py"],
        )

        assert entry.build_id == "BUILD-001"
        assert entry.timestamp == "2026-01-30"
        assert entry.phase == "Implementation"
        assert entry.summary == "Added feature X"
        assert len(entry.files_changed) == 2

    def test_build_entry_to_dict(self) -> None:
        """Test converting BuildEntry to dictionary."""
        entry = BuildEntry(
            build_id="BUILD-002",
            timestamp="2026-01-29",
            phase="Bug Fix",
            summary="Fixed bug Y",
        )

        result = entry.to_dict()

        assert result["build_id"] == "BUILD-002"
        assert result["timestamp"] == "2026-01-29"
        assert result["phase"] == "Bug Fix"
        assert result["summary"] == "Fixed bug Y"
        assert result["files_changed"] == []


class TestArchitectureDecision:
    """Test ArchitectureDecision dataclass."""

    def test_architecture_decision_creation(self) -> None:
        """Test creating an ArchitectureDecision."""
        decision = ArchitectureDecision(
            decision_id="DEC-001",
            timestamp="2026-01-28",
            title="Use PostgreSQL for main database",
            status="Implemented",
            context="Need reliable RDBMS",
            rationale="Best fit for our use case",
            impact="All data storage will use PostgreSQL",
        )

        assert decision.decision_id == "DEC-001"
        assert decision.timestamp == "2026-01-28"
        assert decision.title == "Use PostgreSQL for main database"
        assert decision.status == "Implemented"

    def test_architecture_decision_to_dict(self) -> None:
        """Test converting ArchitectureDecision to dictionary."""
        decision = ArchitectureDecision(
            decision_id="DEC-002",
            timestamp="2026-01-27",
            title="Adopt microservices architecture",
            status="Planned",
        )

        result = decision.to_dict()

        assert result["decision_id"] == "DEC-002"
        assert result["title"] == "Adopt microservices architecture"
        assert result["status"] == "Planned"


class TestSOTSummary:
    """Test SOTSummary dataclass."""

    def test_sot_summary_creation(self) -> None:
        """Test creating an SOTSummary."""
        build = BuildEntry(
            build_id="BUILD-001",
            timestamp="2026-01-30",
            phase="Test",
            summary="Test build",
        )
        decision = ArchitectureDecision(
            decision_id="DEC-001",
            timestamp="2026-01-29",
            title="Test decision",
            status="Implemented",
        )

        summary = SOTSummary(
            build_summary="5 builds documented.",
            architecture_summary="3 decisions documented.",
            recent_builds=[build],
            key_decisions=[decision],
            total_builds=5,
            total_decisions=3,
            last_updated="2026-01-30",
        )

        assert summary.total_builds == 5
        assert summary.total_decisions == 3
        assert len(summary.recent_builds) == 1
        assert len(summary.key_decisions) == 1

    def test_sot_summary_to_dict(self) -> None:
        """Test converting SOTSummary to dictionary."""
        summary = SOTSummary(
            build_summary="Test",
            architecture_summary="Test",
            total_builds=10,
            total_decisions=5,
        )

        result = summary.to_dict()

        assert result["total_builds"] == 10
        assert result["total_decisions"] == 5
        assert "recent_builds" in result
        assert "key_decisions" in result

    def test_sot_summary_to_markdown(self) -> None:
        """Test generating markdown from SOTSummary."""
        build = BuildEntry(
            build_id="BUILD-100",
            timestamp="2026-01-30",
            phase="Feature",
            summary="Added new feature for user management",
        )
        decision = ArchitectureDecision(
            decision_id="DEC-050",
            timestamp="2026-01-29",
            title="Implement caching layer",
            status="Implemented",
        )

        summary = SOTSummary(
            build_summary="100 builds documented.",
            architecture_summary="50 decisions documented.",
            recent_builds=[build],
            key_decisions=[decision],
            total_builds=100,
            total_decisions=50,
        )

        markdown = summary.to_markdown()

        assert "### Build History Context" in markdown
        assert "BUILD-100" in markdown
        assert "### Architecture Decisions Context" in markdown
        assert "DEC-050" in markdown
        assert "Implement caching layer" in markdown

    def test_sot_summary_to_markdown_empty(self) -> None:
        """Test generating markdown from empty SOTSummary."""
        summary = SOTSummary(
            build_summary="",
            architecture_summary="",
        )

        markdown = summary.to_markdown()

        assert markdown == ""


class TestSOTSummarizer:
    """Test SOTSummarizer class."""

    def test_summarizer_initialization(self) -> None:
        """Test initializing SOTSummarizer."""
        summarizer = SOTSummarizer(
            project_root=Path("/test/path"),
            max_recent_builds=5,
            max_key_decisions=5,
        )

        assert summarizer._project_root == Path("/test/path")
        assert summarizer._max_recent_builds == 5
        assert summarizer._max_key_decisions == 5

    def test_summarizer_default_initialization(self) -> None:
        """Test default initialization of SOTSummarizer."""
        summarizer = SOTSummarizer()

        assert summarizer._project_root == Path.cwd()
        assert summarizer._max_recent_builds == 10
        assert summarizer._max_key_decisions == 10

    def test_summarize_missing_files(self) -> None:
        """Test summarize with missing SOT files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            summarizer = SOTSummarizer(project_root=Path(tmpdir))
            summary = summarizer.summarize()

            assert summary.total_builds == 0
            assert summary.total_decisions == 0
            assert "not found" in summary.build_summary.lower() or "no build" in summary.build_summary.lower()

    def test_summarize_with_build_history(self) -> None:
        """Test summarize with BUILD_HISTORY.md present."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            docs_dir = tmpdir_path / "docs"
            docs_dir.mkdir()

            # Create a sample BUILD_HISTORY.md
            build_history_content = """# Build History

**Summary**: 3 build entries documented

## INDEX (Chronological - Most Recent First)
| Timestamp | BUILD-ID | Phase | Summary | Files Changed |
|-----------|----------|-------|---------|---------------|
| 2026-01-30 | BUILD-003 | Feature | Added auth module | src/auth.py |
| 2026-01-29 | BUILD-002 | Bug Fix | Fixed login issue | src/login.py |
| 2026-01-28 | BUILD-001 | Initial | Project setup | README.md |
"""
            (docs_dir / "BUILD_HISTORY.md").write_text(build_history_content, encoding="utf-8")

            summarizer = SOTSummarizer(project_root=tmpdir_path)
            summary = summarizer.summarize()

            assert summary.total_builds == 3
            assert len(summary.recent_builds) == 3
            assert summary.recent_builds[0].build_id == "BUILD-003"

    def test_summarize_with_architecture_decisions(self) -> None:
        """Test summarize with ARCHITECTURE_DECISIONS.md present."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            docs_dir = tmpdir_path / "docs"
            docs_dir.mkdir()

            # Create a sample ARCHITECTURE_DECISIONS.md
            arch_decisions_content = """# Architecture Decisions

**Summary**: 2 decisions documented

## INDEX
| Timestamp | DEC-ID | Decision | Status | Impact |
|-----------|--------|----------|--------|--------|
| 2026-01-30 | DEC-002 | Use Redis for caching | ✅ Implemented | Improved performance |
| 2026-01-28 | DEC-001 | Adopt FastAPI framework | ✅ Implemented | Modern async API |
"""
            (docs_dir / "ARCHITECTURE_DECISIONS.md").write_text(arch_decisions_content, encoding="utf-8")

            summarizer = SOTSummarizer(project_root=tmpdir_path)
            summary = summarizer.summarize()

            assert summary.total_decisions == 2
            assert len(summary.key_decisions) == 2
            assert summary.key_decisions[0].decision_id == "DEC-002"
            assert summary.key_decisions[0].status == "Implemented"

    def test_get_brief_context(self) -> None:
        """Test get_brief_context method."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            docs_dir = tmpdir_path / "docs"
            docs_dir.mkdir()

            # Create sample files
            build_history = """# Build History
**Summary**: 2 build entries

## INDEX
| Timestamp | BUILD-ID | Phase | Summary | Files Changed |
|-----------|----------|-------|---------|---------------|
| 2026-01-30 | BUILD-002 | Feature | New API endpoint | api.py |
| 2026-01-29 | BUILD-001 | Setup | Initial commit | all |
"""
            (docs_dir / "BUILD_HISTORY.md").write_text(build_history, encoding="utf-8")

            arch_decisions = """# Architecture Decisions
**Summary**: 1 decision

## INDEX
| Timestamp | DEC-ID | Decision | Status | Impact |
|-----------|--------|----------|--------|--------|
| 2026-01-30 | DEC-001 | Use PostgreSQL | [Implemented] | Database |
"""
            (docs_dir / "ARCHITECTURE_DECISIONS.md").write_text(arch_decisions, encoding="utf-8")

            summarizer = SOTSummarizer(project_root=tmpdir_path)
            context = summarizer.get_brief_context()

            assert "sot_context" in context
            assert "build_history" in context["sot_context"]
            assert "architecture_decisions" in context["sot_context"]
            assert context["sot_context"]["build_history"]["total_builds"] == 2
            assert context["sot_context"]["architecture_decisions"]["total_decisions"] == 1

    def test_generate_context_section(self) -> None:
        """Test generate_context_section method."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            docs_dir = tmpdir_path / "docs"
            docs_dir.mkdir()

            # Create sample files
            build_history = """# Build History
**Summary**: 1 build entry

## INDEX
| Timestamp | BUILD-ID | Phase | Summary | Files Changed |
|-----------|----------|-------|---------|---------------|
| 2026-01-30 | BUILD-001 | Test | Test build | test.py |
"""
            (docs_dir / "BUILD_HISTORY.md").write_text(build_history, encoding="utf-8")
            (docs_dir / "ARCHITECTURE_DECISIONS.md").write_text("# No decisions", encoding="utf-8")

            summarizer = SOTSummarizer(project_root=tmpdir_path)
            section = summarizer.generate_context_section()

            assert "### Build History Context" in section
            assert "BUILD-001" in section


class TestConvenienceFunctions:
    """Test convenience functions."""

    def test_get_sot_summarizer(self) -> None:
        """Test get_sot_summarizer function."""
        summarizer = get_sot_summarizer(
            max_recent_builds=5,
            max_key_decisions=5,
        )

        assert isinstance(summarizer, SOTSummarizer)
        assert summarizer._max_recent_builds == 5
        assert summarizer._max_key_decisions == 5

    def test_summarize_sot_documents(self) -> None:
        """Test summarize_sot_documents function."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            docs_dir = tmpdir_path / "docs"
            docs_dir.mkdir()

            # Create minimal files
            (docs_dir / "BUILD_HISTORY.md").write_text("# Build History\n**Summary**: 0 builds", encoding="utf-8")
            (docs_dir / "ARCHITECTURE_DECISIONS.md").write_text("# Decisions\n**Summary**: 0 decisions", encoding="utf-8")

            summary = summarize_sot_documents(project_root=tmpdir_path)

            assert isinstance(summary, SOTSummary)


class TestProjectBriefGeneratorSOTIntegration:
    """Test ProjectBriefGenerator with SOT integration."""

    def test_project_brief_generator_with_sot_summarizer(self) -> None:
        """Test ProjectBriefGenerator with SOTSummarizer."""
        from autopack.research.artifact_generators import ProjectBriefGenerator

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            docs_dir = tmpdir_path / "docs"
            docs_dir.mkdir()

            # Create sample BUILD_HISTORY.md
            build_history = """# Build History
**Summary**: 2 build entries

## INDEX
| Timestamp | BUILD-ID | Phase | Summary | Files Changed |
|-----------|----------|-------|---------|---------------|
| 2026-01-30 | BUILD-002 | Feature | Added user auth | auth.py |
| 2026-01-29 | BUILD-001 | Initial | Project setup | all |
"""
            (docs_dir / "BUILD_HISTORY.md").write_text(build_history, encoding="utf-8")

            # Create sample ARCHITECTURE_DECISIONS.md
            arch_decisions = """# Architecture Decisions
**Summary**: 1 decision

## INDEX
| Timestamp | DEC-ID | Decision | Status | Impact |
|-----------|--------|----------|--------|--------|
| 2026-01-30 | DEC-001 | FastAPI framework | [Implemented] | API layer |
"""
            (docs_dir / "ARCHITECTURE_DECISIONS.md").write_text(arch_decisions, encoding="utf-8")

            # Create generator with SOT summarizer
            summarizer = SOTSummarizer(project_root=tmpdir_path)
            generator = ProjectBriefGenerator(
                sot_summarizer=summarizer,
                include_sot_context=True,
            )

            # Generate brief
            research_findings = {
                "problem_statement": "Need project management tool",
                "solution": "Build comprehensive PM solution",
            }
            brief = generator.generate(research_findings)

            # Verify SOT context is included
            assert "## Historical Context (SOT)" in brief
            assert "BUILD-002" in brief or "Build History" in brief

    def test_project_brief_generator_without_sot_context(self) -> None:
        """Test ProjectBriefGenerator without SOT context."""
        from autopack.research.artifact_generators import ProjectBriefGenerator

        generator = ProjectBriefGenerator(include_sot_context=False)

        research_findings = {
            "problem_statement": "Test problem",
        }
        brief = generator.generate(research_findings)

        # SOT context should not be included
        assert "## Historical Context (SOT)" not in brief

    def test_project_brief_generator_with_sot_context_override(self) -> None:
        """Test ProjectBriefGenerator with SOT context override."""
        from autopack.research.artifact_generators import ProjectBriefGenerator

        generator = ProjectBriefGenerator(include_sot_context=True)

        research_findings = {
            "problem_statement": "Test problem",
        }
        # Override to disable SOT context
        brief = generator.generate(research_findings, include_sot_context=False)

        # SOT context should not be included due to override
        assert "## Historical Context (SOT)" not in brief

    def test_project_brief_generator_with_precomputed_sot_summary(self) -> None:
        """Test ProjectBriefGenerator with pre-computed SOT summary."""
        from autopack.research.artifact_generators import ProjectBriefGenerator

        # Create a pre-computed summary
        build = BuildEntry(
            build_id="BUILD-TEST",
            timestamp="2026-01-30",
            phase="Test",
            summary="Test build summary",
        )
        decision = ArchitectureDecision(
            decision_id="DEC-TEST",
            timestamp="2026-01-29",
            title="Test decision",
            status="Implemented",
        )
        sot_summary = SOTSummary(
            build_summary="Pre-computed summary",
            architecture_summary="Pre-computed decisions",
            recent_builds=[build],
            key_decisions=[decision],
            total_builds=1,
            total_decisions=1,
        )

        generator = ProjectBriefGenerator(include_sot_context=True)

        research_findings = {"problem_statement": "Test"}
        brief = generator.generate(
            research_findings,
            sot_summary=sot_summary,
        )

        # Verify pre-computed summary is used
        assert "## Historical Context (SOT)" in brief
        assert "BUILD-TEST" in brief
        assert "DEC-TEST" in brief

    def test_project_brief_generator_with_sot_context_in_findings(self) -> None:
        """Test ProjectBriefGenerator with SOT context in research_findings."""
        from autopack.research.artifact_generators import ProjectBriefGenerator

        generator = ProjectBriefGenerator(include_sot_context=True)

        research_findings = {
            "problem_statement": "Test",
            "sot_context": {
                "build_history": {
                    "total_builds": 5,
                    "recent_summary": "5 builds documented",
                    "recent_builds": [
                        {"id": "BUILD-FROM-FINDINGS", "date": "2026-01-30", "summary": "Test"},
                    ],
                },
                "architecture_decisions": {
                    "total_decisions": 3,
                    "summary": "3 decisions documented",
                    "key_decisions": [
                        {"id": "DEC-FROM-FINDINGS", "title": "Test decision", "status": "Implemented"},
                    ],
                },
            },
        }
        brief = generator.generate(research_findings)

        # Verify context from findings is used
        assert "## Historical Context (SOT)" in brief
        assert "BUILD-FROM-FINDINGS" in brief or "5 builds documented" in brief


class TestGetProjectBriefGeneratorWithSot:
    """Test get_project_brief_generator_with_sot function."""

    def test_get_project_brief_generator_with_sot(self) -> None:
        """Test convenience function for getting generator with SOT."""
        from autopack.research.artifact_generators import get_project_brief_generator_with_sot

        with tempfile.TemporaryDirectory() as tmpdir:
            generator = get_project_brief_generator_with_sot(project_root=tmpdir)

            assert generator._sot_summarizer is not None
            assert generator._include_sot_context is True
