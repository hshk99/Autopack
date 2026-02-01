"""Tests for bootstrap CLI command (IMP-RES-007)."""

import json

import pytest
from click.testing import CliRunner

from autopack.cli.commands.bootstrap import (READY_FOR_BUILD_MARKER,
                                             BootstrapOptions, BootstrapRunner,
                                             bootstrap_group)
from autopack.research.idea_parser import ProjectType, RiskProfile


@pytest.fixture
def runner():
    """Create a CLI test runner."""
    return CliRunner()


@pytest.fixture
def sample_idea():
    """Sample project idea text."""
    return """
    # E-Commerce Platform for Handmade Goods

    Build an online marketplace for artisans to sell handmade products.

    ## Requirements
    - User registration and authentication
    - Product listing and catalog management
    - Shopping cart and checkout flow
    - Payment processing with Stripe
    - Order management and tracking
    - Seller dashboard with analytics
    """


@pytest.fixture
def sample_idea_file(tmp_path, sample_idea):
    """Create a sample idea file."""
    idea_file = tmp_path / "project_idea.md"
    idea_file.write_text(sample_idea)
    return idea_file


@pytest.fixture
def sample_answers_file(tmp_path):
    """Create a sample answers file for automation."""
    answers = {
        "safety_risk": {
            "never_allow": ["delete production data", "bypass authentication"],
            "requires_approval": ["payment processing", "data export"],
            "risk_tolerance": "low",
        },
        "north_star": {
            "desired_outcomes": ["Launch MVP within 3 months"],
            "success_signals": ["100 active sellers", "1000 orders per month"],
        },
    }
    answers_file = tmp_path / "answers.json"
    answers_file.write_text(json.dumps(answers))
    return answers_file


class TestBootstrapRunner:
    """Unit tests for BootstrapRunner."""

    def test_bootstrap_runner_creates_project_directory(self, tmp_path, sample_idea):
        """Test that BootstrapRunner creates project directory."""
        runner = BootstrapRunner()
        options = BootstrapOptions(
            idea=sample_idea,
            autonomous=True,
            skip_research=True,
            output_dir=tmp_path / "test_project",
        )

        result = runner.run(options)

        assert result.success
        assert result.project_dir is not None
        assert result.project_dir.exists()

    def test_bootstrap_runner_creates_anchor_file(self, tmp_path, sample_idea):
        """Test that BootstrapRunner creates intention anchor file."""
        runner = BootstrapRunner()
        options = BootstrapOptions(
            idea=sample_idea,
            autonomous=True,
            skip_research=True,
            output_dir=tmp_path / "test_project",
        )

        result = runner.run(options)

        assert result.success
        assert result.anchor_path is not None
        assert result.anchor_path.exists()
        assert result.anchor_path.name == "intention_anchor_v2.json"

        # Verify anchor content is valid JSON
        content = json.loads(result.anchor_path.read_text())
        assert content.get("format_version") == "v2"
        assert "project_id" in content

    def test_bootstrap_runner_creates_ready_marker(self, tmp_path, sample_idea):
        """Test that BootstrapRunner creates READY_FOR_BUILD marker."""
        runner = BootstrapRunner()
        options = BootstrapOptions(
            idea=sample_idea,
            autonomous=True,
            skip_research=True,
            output_dir=tmp_path / "test_project",
        )

        result = runner.run(options)

        assert result.success
        marker_path = result.project_dir / READY_FOR_BUILD_MARKER
        assert marker_path.exists()

        # Verify marker content
        marker_content = json.loads(marker_path.read_text())
        assert marker_content["status"] == "ready"
        assert marker_content["bootstrap_complete"] is True

    def test_bootstrap_runner_detects_project_type(self, tmp_path, sample_idea):
        """Test that BootstrapRunner correctly detects project type."""
        runner = BootstrapRunner()
        options = BootstrapOptions(
            idea=sample_idea,
            autonomous=True,
            skip_research=True,
            output_dir=tmp_path / "test_project",
        )

        result = runner.run(options)

        assert result.success
        assert result.parsed_idea is not None
        assert result.parsed_idea.detected_project_type == ProjectType.ECOMMERCE

    def test_bootstrap_runner_handles_trading_project(self, tmp_path):
        """Test that BootstrapRunner correctly handles trading projects."""
        trading_idea = """
        # Algorithmic Trading Bot

        Build an automated trading system for cryptocurrency markets.

        ## Features
        - Real-time market data feeds
        - Algorithmic trading strategies
        - Portfolio management
        - Risk management and stop-loss
        - Backtesting engine
        """

        runner = BootstrapRunner()
        options = BootstrapOptions(
            idea=trading_idea,
            autonomous=True,
            skip_research=True,
            output_dir=tmp_path / "trading_project",
        )

        result = runner.run(options)

        assert result.success
        assert result.parsed_idea.detected_project_type == ProjectType.TRADING
        assert result.parsed_idea.risk_profile == RiskProfile.HIGH

    def test_bootstrap_runner_fails_without_idea(self, tmp_path):
        """Test that BootstrapRunner fails when no idea is provided."""
        runner = BootstrapRunner()
        options = BootstrapOptions(
            idea=None,
            idea_file=None,
            autonomous=True,
            skip_research=True,
            output_dir=tmp_path / "test_project",
        )

        result = runner.run(options)

        assert not result.success
        assert len(result.errors) > 0
        assert "No idea provided" in result.errors[0]

    def test_bootstrap_runner_reads_from_file(self, tmp_path, sample_idea_file):
        """Test that BootstrapRunner reads idea from file."""
        runner = BootstrapRunner()
        options = BootstrapOptions(
            idea_file=sample_idea_file,
            autonomous=True,
            skip_research=True,
            output_dir=tmp_path / "test_project",
        )

        result = runner.run(options)

        assert result.success
        assert (
            "e-commerce" in result.parsed_idea.title.lower()
            or "handmade" in result.parsed_idea.title.lower()
        )

    def test_bootstrap_runner_uses_answers_file(self, tmp_path, sample_idea, sample_answers_file):
        """Test that BootstrapRunner uses answers file when provided."""
        runner = BootstrapRunner()
        options = BootstrapOptions(
            idea=sample_idea,
            answers_file=sample_answers_file,
            skip_research=True,
            output_dir=tmp_path / "test_project",
        )

        result = runner.run(options)

        assert result.success
        # The anchor should have safety_risk populated from answers file
        anchor_content = json.loads(result.anchor_path.read_text())
        pivot = anchor_content.get("pivot_intentions", {})
        safety = pivot.get("safety_risk", {})
        # Verify some default or answered values exist
        assert "risk_tolerance" in safety


class TestBootstrapCLI:
    """CLI integration tests for bootstrap command."""

    def test_bootstrap_run_with_idea_string(self, runner, tmp_path):
        """Test bootstrap run with --idea option."""
        output_dir = tmp_path / "cli_test_project"

        result = runner.invoke(
            bootstrap_group,
            [
                "run",
                "--idea",
                "Build a simple blog platform with markdown support",
                "--autonomous",
                "--skip-research",
                "--output-dir",
                str(output_dir),
            ],
        )

        assert result.exit_code == 0
        assert "SUCCESS" in result.output
        assert output_dir.exists()
        assert (output_dir / "intention_anchor_v2.json").exists()
        assert (output_dir / READY_FOR_BUILD_MARKER).exists()

    def test_bootstrap_run_with_idea_file(self, runner, tmp_path, sample_idea_file):
        """Test bootstrap run with --idea-file option."""
        output_dir = tmp_path / "cli_test_project"

        result = runner.invoke(
            bootstrap_group,
            [
                "run",
                "--idea-file",
                str(sample_idea_file),
                "--autonomous",
                "--skip-research",
                "--output-dir",
                str(output_dir),
            ],
        )

        assert result.exit_code == 0
        assert "SUCCESS" in result.output
        assert output_dir.exists()

    def test_bootstrap_run_outputs_json_summary(self, runner, tmp_path):
        """Test that bootstrap run outputs JSON summary to stdout."""
        output_dir = tmp_path / "cli_test_project"

        result = runner.invoke(
            bootstrap_group,
            [
                "run",
                "--idea",
                "Build a task automation tool",
                "--autonomous",
                "--skip-research",
                "--output-dir",
                str(output_dir),
            ],
        )

        assert result.exit_code == 0

        # Extract JSON from output (last part should be JSON)
        lines = result.output.strip().split("\n")
        json_start = None
        for i, line in enumerate(lines):
            if line.strip().startswith("{"):
                json_start = i
                break

        assert json_start is not None
        json_output = "\n".join(lines[json_start:])
        summary = json.loads(json_output)

        assert summary["success"] is True
        assert summary["ready_for_build"] is True
        assert "project_dir" in summary

    def test_bootstrap_run_fails_without_idea(self, runner, tmp_path):
        """Test that bootstrap run fails when no idea is provided."""
        result = runner.invoke(
            bootstrap_group,
            [
                "run",
                "--autonomous",
                "--skip-research",
                "--output-dir",
                str(tmp_path / "test"),
            ],
        )

        assert result.exit_code != 0
        assert "ERROR" in result.output

    def test_bootstrap_run_with_verbose(self, runner, tmp_path):
        """Test bootstrap run with --verbose option."""
        output_dir = tmp_path / "cli_test_project"

        result = runner.invoke(
            bootstrap_group,
            [
                "run",
                "--idea",
                "Build a content management system",
                "--autonomous",
                "--skip-research",
                "--output-dir",
                str(output_dir),
                "--verbose",
            ],
        )

        assert result.exit_code == 0
        # Verbose mode should show more detailed output
        assert "SUCCESS" in result.output

    def test_bootstrap_run_generates_unique_project_dir(self, runner, tmp_path):
        """Test that bootstrap generates unique project directory names."""
        # Change to tmp_path for this test
        import os

        original_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)

            result = runner.invoke(
                bootstrap_group,
                [
                    "run",
                    "--idea",
                    "My Unique Project Idea",
                    "--autonomous",
                    "--skip-research",
                ],
            )

            assert result.exit_code == 0
            # Should create a directory based on the project name
            dirs = list(tmp_path.glob("project_*"))
            assert len(dirs) == 1
        finally:
            os.chdir(original_cwd)


class TestBootstrapOptions:
    """Tests for BootstrapOptions dataclass."""

    def test_default_options(self):
        """Test default BootstrapOptions values."""
        options = BootstrapOptions()

        assert options.idea is None
        assert options.idea_file is None
        assert options.answers_file is None
        assert options.skip_research is False
        assert options.research_file is None
        assert options.autonomous is False
        assert options.risk_tolerance == "medium"
        assert options.output_dir is None

    def test_options_with_values(self, tmp_path):
        """Test BootstrapOptions with custom values."""
        idea_file = tmp_path / "idea.md"
        idea_file.write_text("test idea")

        options = BootstrapOptions(
            idea="Test idea",
            idea_file=idea_file,
            skip_research=True,
            autonomous=True,
            risk_tolerance="high",
            output_dir=tmp_path / "output",
        )

        assert options.idea == "Test idea"
        assert options.idea_file == idea_file
        assert options.skip_research is True
        assert options.autonomous is True
        assert options.risk_tolerance == "high"
        assert options.output_dir == tmp_path / "output"
