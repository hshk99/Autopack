"""CLI command for project bootstrap (IMP-RES-007).

Provides the `autopack bootstrap` command as the entry point for starting
a new project from an idea. Orchestrates the full pipeline:
    idea -> research -> anchor -> READY_FOR_BUILD

Usage:
    autopack bootstrap --idea "Build an e-commerce platform"
    autopack bootstrap --idea-file ./project_idea.md
    autopack bootstrap --idea "..." --autonomous --skip-research
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import click

from autopack.intention_anchor.v2 import IntentionAnchorV2
from autopack.research.anchor_mapper import ResearchToAnchorMapper
from autopack.research.idea_parser import IdeaParser, ParsedIdea
from autopack.research.models.bootstrap_session import BootstrapSession
from autopack.research.orchestrator import ResearchOrchestrator
from autopack.research.qa_controller import AnswerSource, QAController

logger = logging.getLogger(__name__)

# Marker file name indicating project is ready for build phase
READY_FOR_BUILD_MARKER = "READY_FOR_BUILD"


@dataclass
class BootstrapOptions:
    """Configuration options for bootstrap execution."""

    idea: Optional[str] = None
    idea_file: Optional[Path] = None
    answers_file: Optional[Path] = None
    skip_research: bool = False
    research_file: Optional[Path] = None
    autonomous: bool = False
    risk_tolerance: str = "medium"
    output_dir: Optional[Path] = None


@dataclass
class BootstrapResult:
    """Result of bootstrap execution."""

    success: bool
    project_dir: Optional[Path] = None
    anchor_path: Optional[Path] = None
    anchor: Optional[IntentionAnchorV2] = None
    parsed_idea: Optional[ParsedIdea] = None
    bootstrap_session: Optional[BootstrapSession] = None
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class BootstrapRunner:
    """Orchestrates the full bootstrap pipeline.

    Pipeline stages:
    1. Parse idea (IdeaParser)
    2. Run research (ResearchOrchestrator) - optional, can be skipped
    3. Map to anchor (ResearchToAnchorMapper)
    4. Q&A for clarification (QAController)
    5. Create project directory and write anchor
    6. Write READY_FOR_BUILD marker
    """

    def __init__(
        self,
        idea_parser: Optional[IdeaParser] = None,
        research_orchestrator: Optional[ResearchOrchestrator] = None,
        anchor_mapper: Optional[ResearchToAnchorMapper] = None,
    ):
        """Initialize the BootstrapRunner.

        Args:
            idea_parser: Optional IdeaParser instance
            research_orchestrator: Optional ResearchOrchestrator instance
            anchor_mapper: Optional ResearchToAnchorMapper instance
        """
        self.idea_parser = idea_parser or IdeaParser()
        self.research_orchestrator = research_orchestrator or ResearchOrchestrator()
        self.anchor_mapper = anchor_mapper or ResearchToAnchorMapper()

    def run(self, options: BootstrapOptions) -> BootstrapResult:
        """Run the full bootstrap pipeline.

        Args:
            options: BootstrapOptions with configuration

        Returns:
            BootstrapResult with outcome
        """
        logger.info("[Bootstrap] Starting bootstrap pipeline")

        warnings: list[str] = []

        # Step 1: Get idea text
        idea_text = self._get_idea_text(options)
        if not idea_text:
            return BootstrapResult(
                success=False,
                errors=["No idea provided. Use --idea or --idea-file."],
            )

        # Step 2: Parse idea
        logger.info("[Bootstrap] Parsing idea...")
        parsed_idea = self.idea_parser.parse_single(idea_text)
        if not parsed_idea:
            return BootstrapResult(
                success=False,
                errors=["Failed to parse idea. Please provide more detail."],
            )

        logger.info(
            f"[Bootstrap] Parsed idea: {parsed_idea.title} "
            f"(type={parsed_idea.detected_project_type.value}, "
            f"confidence={parsed_idea.confidence_score:.2f})"
        )

        # Step 3: Run research (or load from file, or skip)
        bootstrap_session: Optional[BootstrapSession] = None

        if options.research_file and options.research_file.exists():
            logger.info(f"[Bootstrap] Loading research from file: {options.research_file}")
            bootstrap_session = self._load_research_from_file(options.research_file)
            if not bootstrap_session:
                warnings.append(
                    f"Failed to load research from {options.research_file}, running fresh"
                )

        if not bootstrap_session and not options.skip_research:
            logger.info("[Bootstrap] Running research...")
            bootstrap_session = asyncio.run(
                self.research_orchestrator.start_bootstrap_session(
                    parsed_idea=parsed_idea,
                    use_cache=True,
                    parallel=True,
                )
            )
            logger.info(
                f"[Bootstrap] Research completed: session_id={bootstrap_session.session_id}"
            )

        if options.skip_research:
            logger.info("[Bootstrap] Research skipped (--skip-research)")
            # Create minimal bootstrap session for mapping
            bootstrap_session = self._create_minimal_session(parsed_idea)

        # Step 4: Map to anchor
        logger.info("[Bootstrap] Mapping research to anchor...")
        anchor, clarifying_questions = self.anchor_mapper.map_to_anchor(
            bootstrap_session=bootstrap_session,
            parsed_idea=parsed_idea,
        )

        logger.info(f"[Bootstrap] Anchor created: {len(clarifying_questions)} clarifying questions")

        # Step 5: Q&A session for clarification
        if clarifying_questions:
            anchor = self._run_qa_session(
                anchor=anchor,
                questions=clarifying_questions,
                options=options,
                parsed_idea=parsed_idea,
            )

        # Step 6: Create project directory and write files
        project_dir = self._get_project_dir(options, parsed_idea)
        project_dir.mkdir(parents=True, exist_ok=True)

        # Write anchor file
        anchor_path = project_dir / "intention_anchor_v2.json"
        anchor.save_to_file(anchor_path)
        logger.info(f"[Bootstrap] Anchor written to: {anchor_path}")

        # Write research session if available
        if bootstrap_session and not options.skip_research:
            research_path = project_dir / "bootstrap_research.json"
            self._save_research_session(bootstrap_session, research_path)
            logger.info(f"[Bootstrap] Research written to: {research_path}")

        # Step 7: Write READY_FOR_BUILD marker
        ready_marker_path = project_dir / READY_FOR_BUILD_MARKER
        self._write_ready_marker(ready_marker_path, anchor, parsed_idea)
        logger.info(f"[Bootstrap] READY_FOR_BUILD marker written to: {ready_marker_path}")

        return BootstrapResult(
            success=True,
            project_dir=project_dir,
            anchor_path=anchor_path,
            anchor=anchor,
            parsed_idea=parsed_idea,
            bootstrap_session=bootstrap_session,
            warnings=warnings,
        )

    def _get_idea_text(self, options: BootstrapOptions) -> Optional[str]:
        """Get idea text from options.

        Args:
            options: BootstrapOptions

        Returns:
            Idea text or None
        """
        if options.idea:
            return options.idea

        if options.idea_file and options.idea_file.exists():
            return options.idea_file.read_text(encoding="utf-8")

        return None

    def _load_research_from_file(self, path: Path) -> Optional[BootstrapSession]:
        """Load research session from file.

        Args:
            path: Path to research JSON file

        Returns:
            BootstrapSession or None
        """
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return BootstrapSession.model_validate(data)
        except Exception as e:
            logger.warning(f"Failed to load research from file: {e}")
            return None

    def _create_minimal_session(self, parsed_idea: ParsedIdea) -> BootstrapSession:
        """Create minimal bootstrap session when research is skipped.

        Args:
            parsed_idea: Parsed idea

        Returns:
            Minimal BootstrapSession
        """
        from uuid import uuid4

        return BootstrapSession(
            session_id=str(uuid4()),
            idea_hash="skip-research",
            parsed_idea_title=parsed_idea.title,
            parsed_idea_type=parsed_idea.detected_project_type.value,
        )

    def _run_qa_session(
        self,
        anchor: IntentionAnchorV2,
        questions: list[str],
        options: BootstrapOptions,
        parsed_idea: ParsedIdea,
    ) -> IntentionAnchorV2:
        """Run Q&A session to clarify anchor.

        Args:
            anchor: Initial anchor
            questions: Clarifying questions
            options: Bootstrap options
            parsed_idea: Parsed idea for project type

        Returns:
            Updated anchor
        """
        # Determine answer source
        if options.answers_file and options.answers_file.exists():
            source = AnswerSource.FILE
        elif options.autonomous:
            source = AnswerSource.DEFAULT
        else:
            source = AnswerSource.CLI

        controller = QAController(
            answer_source=source,
            answers_file=options.answers_file,
            project_type=parsed_idea.detected_project_type,
            autonomous=options.autonomous,
        )

        result = controller.run_qa_session(questions, anchor)

        if result.unanswered_critical:
            logger.warning(
                f"[Bootstrap] {len(result.unanswered_critical)} critical questions unanswered"
            )

        return result.anchor

    def _get_project_dir(self, options: BootstrapOptions, parsed_idea: ParsedIdea) -> Path:
        """Get project directory path.

        Args:
            options: Bootstrap options
            parsed_idea: Parsed idea

        Returns:
            Path to project directory
        """
        if options.output_dir:
            return options.output_dir

        # Generate directory name from project title
        safe_name = "".join(
            c if c.isalnum() or c in "-_" else "_" for c in parsed_idea.title.lower()
        )
        safe_name = safe_name[:50].strip("_")

        return Path.cwd() / f"project_{safe_name}"

    def _save_research_session(self, session: BootstrapSession, path: Path) -> None:
        """Save research session to file.

        Args:
            session: BootstrapSession to save
            path: Path to save to
        """
        data = session.model_dump(mode="json")
        path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )

    def _write_ready_marker(
        self,
        path: Path,
        anchor: IntentionAnchorV2,
        parsed_idea: ParsedIdea,
    ) -> None:
        """Write READY_FOR_BUILD marker file.

        Args:
            path: Path to marker file
            anchor: Intention anchor
            parsed_idea: Parsed idea
        """
        marker_content = {
            "status": "ready",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "project_id": anchor.project_id,
            "project_title": parsed_idea.title,
            "project_type": parsed_idea.detected_project_type.value,
            "anchor_digest": anchor.raw_input_digest,
            "bootstrap_complete": True,
        }

        path.write_text(
            json.dumps(marker_content, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )


@click.group("bootstrap")
def bootstrap_group() -> None:
    """Bootstrap commands (project initialization from idea)."""
    pass


@bootstrap_group.command("run")
@click.option(
    "--idea",
    type=str,
    default=None,
    help="Project idea as string",
)
@click.option(
    "--idea-file",
    type=click.Path(exists=True, file_okay=True, dir_okay=False, path_type=Path),
    default=None,
    help="Path to idea document file",
)
@click.option(
    "--answers-file",
    type=click.Path(exists=True, file_okay=True, dir_okay=False, path_type=Path),
    default=None,
    help="Path to pre-answers JSON file for Q&A",
)
@click.option(
    "--skip-research",
    is_flag=True,
    help="Skip research phase (use minimal defaults)",
)
@click.option(
    "--research-file",
    type=click.Path(exists=True, file_okay=True, dir_okay=False, path_type=Path),
    default=None,
    help="Path to existing research results file",
)
@click.option(
    "--autonomous",
    is_flag=True,
    help="Fully autonomous mode (use defaults for optional Q&A)",
)
@click.option(
    "--risk-tolerance",
    type=click.Choice(["low", "medium", "high"]),
    default="medium",
    help="Risk tolerance level (default: medium)",
)
@click.option(
    "--output-dir",
    type=click.Path(file_okay=False, dir_okay=True, path_type=Path),
    default=None,
    help="Output directory for project files",
)
@click.option(
    "-v",
    "--verbose",
    is_flag=True,
    help="Enable verbose logging",
)
def run_command(
    idea: Optional[str],
    idea_file: Optional[Path],
    answers_file: Optional[Path],
    skip_research: bool,
    research_file: Optional[Path],
    autonomous: bool,
    risk_tolerance: str,
    output_dir: Optional[Path],
    verbose: bool,
) -> None:
    """Bootstrap a new project from an idea.

    Runs the full bootstrap pipeline:
    1. Parse idea document
    2. Run research (market, competitive, technical)
    3. Map research to IntentionAnchorV2
    4. Interactive Q&A for clarification
    5. Create project directory with anchor
    6. Write READY_FOR_BUILD marker

    Examples:

        # Start from idea string:
        autopack bootstrap run --idea "Build an e-commerce platform for handmade goods"

        # Start from idea file:
        autopack bootstrap run --idea-file ./my_project_idea.md

        # Fully autonomous (no interactive Q&A):
        autopack bootstrap run --idea "..." --autonomous

        # Skip research and use defaults:
        autopack bootstrap run --idea "..." --skip-research --autonomous

        # Use pre-defined answers:
        autopack bootstrap run --idea "..." --answers-file ./answers.json
    """
    # Configure logging
    log_level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Validate inputs
    if not idea and not idea_file:
        click.secho(
            "[Bootstrap] ERROR: Must provide --idea or --idea-file",
            fg="red",
            err=True,
        )
        sys.exit(1)

    # Build options
    options = BootstrapOptions(
        idea=idea,
        idea_file=idea_file,
        answers_file=answers_file,
        skip_research=skip_research,
        research_file=research_file,
        autonomous=autonomous,
        risk_tolerance=risk_tolerance,
        output_dir=output_dir,
    )

    # Run bootstrap
    runner = BootstrapRunner()
    result = runner.run(options)

    # Report result
    if result.success:
        click.secho("[Bootstrap] SUCCESS!", fg="green", err=True)
        click.echo(f"[Bootstrap] Project directory: {result.project_dir}", err=True)
        click.echo(f"[Bootstrap] Anchor file: {result.anchor_path}", err=True)
        click.echo(
            f"[Bootstrap] Project type: {result.parsed_idea.detected_project_type.value}",
            err=True,
        )
        click.echo("[Bootstrap] READY_FOR_BUILD marker created", err=True)

        if result.warnings:
            for warning in result.warnings:
                click.secho(f"[Bootstrap] WARNING: {warning}", fg="yellow", err=True)

        # Print JSON summary to stdout
        summary = {
            "success": True,
            "project_dir": str(result.project_dir),
            "anchor_path": str(result.anchor_path),
            "project_id": result.anchor.project_id if result.anchor else None,
            "project_title": result.parsed_idea.title if result.parsed_idea else None,
            "project_type": (
                result.parsed_idea.detected_project_type.value if result.parsed_idea else None
            ),
            "ready_for_build": True,
        }
        click.echo(json.dumps(summary, indent=2, ensure_ascii=False))

    else:
        click.secho("[Bootstrap] FAILED!", fg="red", err=True)
        for error in result.errors:
            click.secho(f"[Bootstrap] ERROR: {error}", fg="red", err=True)
        sys.exit(1)


def register_command(cli_group) -> None:
    """Register bootstrap command group with CLI group.

    Args:
        cli_group: Click group to register command with
    """
    cli_group.add_command(bootstrap_group)
