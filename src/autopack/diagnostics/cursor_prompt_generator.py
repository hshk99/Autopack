"""Cursor-Ready Prompt Generator for Diagnostics Handoff (Stage 1B)

Generates a copy/paste-ready prompt for Cursor that includes:
- Background intent (vibe-coding-first context)
- Run + phase context details
- Failure symptoms with relevant excerpts
- Exact file list to open/attach (absolute or repo-relative paths)
- Constraints: protected paths, allowed paths, deliverables
- Explicit questions / unknowns
- Next steps for human operator

Design Principles:
- Copy/paste ready: No manual editing needed
- Context-rich: All info operator needs to understand the failure
- Actionable: Clear next steps and constraints
- Integrated: Works seamlessly with HandoffBundler artifacts
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class CursorPromptGenerator:
    """Generates Cursor-ready diagnostic prompts from handoff bundles."""

    def __init__(self, handoff_dir: Path, run_dir: Optional[Path] = None):
        """Initialize prompt generator.

        Args:
            handoff_dir: Path to handoff/ directory
            run_dir: Optional path to run directory (parent of handoff_dir)
        """
        self.handoff_dir = Path(handoff_dir)
        self.run_dir = run_dir or self.handoff_dir.parent

        if not self.handoff_dir.exists():
            raise ValueError(f"Handoff directory does not exist: {self.handoff_dir}")

        # Load index.json for metadata
        index_path = self.handoff_dir / "index.json"
        if index_path.exists():
            with open(index_path, "r", encoding="utf-8") as f:
                self.index_data = json.load(f)
        else:
            self.index_data = {}

    def generate_prompt(
        self,
        phase_context: Optional[Dict[str, Any]] = None,
        error_context: Optional[Dict[str, Any]] = None,
        constraints: Optional[Dict[str, Any]] = None,
        questions: Optional[List[str]] = None,
    ) -> str:
        """Generate complete Cursor-ready prompt.

        Args:
            phase_context: Phase details (phase_id, name, complexity, attempts, etc.)
            error_context: Error details (message, category, timestamp, stack trace, etc.)
            constraints: Constraints (protected_paths, allowed_paths, deliverables)
            questions: Explicit questions/unknowns to investigate

        Returns:
            Formatted markdown prompt ready for copy/paste into Cursor
        """
        logger.info(
            f"[CursorPrompt] Generating prompt for {self.index_data.get('run_id', 'unknown')}"
        )

        sections = []

        # Header
        sections.append(self._generate_header())
        sections.append("")

        # Background Intent
        sections.append(self._generate_background_intent())
        sections.append("")

        # Run Context
        sections.append(self._generate_run_context(phase_context))
        sections.append("")

        # Failure Symptoms
        if error_context:
            sections.append(self._generate_failure_symptoms(error_context))
            sections.append("")

        # Relevant Excerpts
        sections.append(self._generate_excerpts_section())
        sections.append("")

        # Files to Open/Attach
        sections.append(self._generate_files_section(error_context))
        sections.append("")

        # Constraints
        if constraints:
            sections.append(self._generate_constraints_section(constraints))
            sections.append("")

        # Explicit Questions
        if questions:
            sections.append(self._generate_questions_section(questions))
            sections.append("")

        # Next Steps
        sections.append(self._generate_next_steps(phase_context))
        sections.append("")

        prompt = "\n".join(sections)

        # Save prompt to handoff bundle
        prompt_path = self.handoff_dir / "cursor_prompt.md"
        with open(prompt_path, "w", encoding="utf-8") as f:
            f.write(prompt)
        logger.info(f"[CursorPrompt] Saved prompt to {prompt_path}")

        return prompt

    def _generate_header(self) -> str:
        """Generate prompt header."""
        run_id = self.index_data.get("run_id", "unknown")
        return f"# Autopack Diagnostics Handoff: {run_id}"

    def _generate_background_intent(self) -> str:
        """Generate background intent section."""
        return """## Background Intent

Autopack uses **"vibe-coding-first"** builder mode with autonomous execution. The executor attempted to complete a phase but encountered a failure that requires human intervention.

**Expected Workflow**:
1. Autopack executor runs governed probes and gathers diagnostic evidence
2. Handoff bundle is generated with all relevant artifacts
3. Human operator (you) reviews context and makes targeted fixes
4. Executor resumes from checkpoint once issue is resolved

**Your Role**: Review the failure context below, make necessary fixes, and either resume the executor or mark the phase as complete."""

    def _generate_run_context(self, phase_context: Optional[Dict[str, Any]]) -> str:
        """Generate run context section."""
        lines = ["## Run Context", ""]

        run_id = self.index_data.get("run_id", "unknown")
        generated_at = self.index_data.get("generated_at", "unknown")

        lines.append(f"- **Run ID**: `{run_id}`")
        lines.append(f"- **Generated**: {generated_at}")

        if phase_context:
            phase_id = phase_context.get("phase_id", "unknown")
            phase_name = phase_context.get("name", "N/A")
            complexity = phase_context.get("complexity", "unknown")
            builder_attempts = phase_context.get("builder_attempts", 0)
            max_attempts = phase_context.get("max_builder_attempts", 5)
            failure_class = phase_context.get("failure_class", "unknown")
            token_budget = phase_context.get("token_budget", "unknown")

            lines.append(f"- **Phase**: `{phase_id}` ({phase_name})")
            lines.append(f"- **Complexity**: {complexity} (token budget: {token_budget})")
            lines.append(f"- **Builder Attempts**: {builder_attempts}/{max_attempts}")
            lines.append(f"- **Failure Class**: {failure_class}")

        return "\n".join(lines)

    def _generate_failure_symptoms(self, error_context: Dict[str, Any]) -> str:
        """Generate failure symptoms section."""
        lines = ["## Failure Symptoms", ""]

        error_message = error_context.get("message", "Unknown error")
        error_category = error_context.get("category", "unknown")
        timestamp = error_context.get("timestamp", datetime.utcnow().isoformat() + "Z")

        lines.append(f"**Last error at {timestamp}:**")
        lines.append("```python")
        lines.append(error_message)
        lines.append("```")
        lines.append("")
        lines.append(f"**Category**: {error_category}")

        # Include stack trace if available
        stack_trace = error_context.get("stack_trace")
        if stack_trace:
            lines.append("")
            lines.append("**Stack Trace** (last 10 frames):")
            lines.append("```")
            stack_lines = stack_trace.split("\n")[-10:]
            lines.extend(stack_lines)
            lines.append("```")

        # Include test failures if available
        test_failures = error_context.get("test_failures")
        if test_failures:
            lines.append("")
            lines.append(
                f"**Test Results**: {test_failures.get('failed', 0)} failed, {test_failures.get('passed', 0)} passed"
            )

        return "\n".join(lines)

    def _generate_excerpts_section(self) -> str:
        """Generate relevant excerpts section."""
        lines = ["## Relevant Excerpts", ""]

        excerpts_dir = self.handoff_dir / "excerpts"
        if not excerpts_dir.exists():
            lines.append("*No excerpts available*")
            return "\n".join(lines)

        # List available excerpts
        excerpt_files = sorted(excerpts_dir.glob("*.excerpt"))
        if not excerpt_files:
            lines.append("*No excerpts available*")
            return "\n".join(lines)

        for excerpt_file in excerpt_files[:5]:  # Show top 5 excerpts
            lines.append(
                f"- **{excerpt_file.stem}**: `{excerpt_file.relative_to(self.handoff_dir)}`"
            )

        if len(excerpt_files) > 5:
            lines.append(
                f"- *(+{len(excerpt_files) - 5} more excerpts available in `excerpts/` directory)*"
            )

        return "\n".join(lines)

    def _generate_files_section(self, error_context: Optional[Dict[str, Any]]) -> str:
        """Generate files to open/attach section."""
        lines = ["## Files to Open/Attach", ""]

        files_to_open = []

        # Add error report if available
        error_report = error_context.get("error_report_path") if error_context else None
        if error_report:
            files_to_open.append((error_report, "error report with full context"))

        # Add phase log if available
        phase_id = error_context.get("phase_id") if error_context else None
        if phase_id:
            phase_log = self.run_dir / f"phase_{phase_id}.log"
            if phase_log.exists():
                files_to_open.append((str(phase_log), "phase execution log"))

        # Add executor log
        executor_log = self.run_dir / "executor.log"
        if executor_log.exists():
            files_to_open.append((str(executor_log), "main executor log"))

        # Add handoff summary
        summary_path = self.handoff_dir / "summary.md"
        if summary_path.exists():
            files_to_open.append((str(summary_path), "handoff summary"))

        # Add source files mentioned in error message if available
        if error_context and "source_files" in error_context:
            for src_file in error_context["source_files"]:
                files_to_open.append((src_file, "source file referenced in error"))

        # Format file list
        for i, (file_path, description) in enumerate(files_to_open, 1):
            lines.append(f"{i}. `{file_path}` - {description}")

        if not files_to_open:
            lines.append("*No specific files identified - review handoff bundle artifacts*")

        return "\n".join(lines)

    def _generate_constraints_section(self, constraints: Dict[str, Any]) -> str:
        """Generate constraints section."""
        lines = ["## Constraints", ""]

        protected_paths = constraints.get("protected_paths", [])
        if protected_paths:
            lines.append("### Protected Paths (DO NOT MODIFY)")
            for path in protected_paths:
                lines.append(f"- `{path}`")
            lines.append("")

        allowed_paths = constraints.get("allowed_paths", [])
        if allowed_paths:
            lines.append("### Allowed Paths (Safe to Edit)")
            for path in allowed_paths:
                lines.append(f"- `{path}`")
            lines.append("")

        deliverables = constraints.get("deliverables", [])
        if deliverables:
            lines.append("### Expected Deliverables")
            for deliverable in deliverables:
                lines.append(f"- {deliverable}")
            lines.append("")

        # Add quality requirements
        test_threshold = constraints.get("test_threshold")
        if test_threshold:
            lines.append("### Quality Requirements")
            lines.append(f"- Must pass ≥{test_threshold}% of tests")
            lines.append("")

        return "\n".join(lines)

    def _generate_questions_section(self, questions: List[str]) -> str:
        """Generate explicit questions/unknowns section."""
        lines = ["## Explicit Questions / Unknowns", ""]

        for i, question in enumerate(questions, 1):
            lines.append(f"{i}. {question}")

        return "\n".join(lines)

    def _generate_next_steps(self, phase_context: Optional[Dict[str, Any]]) -> str:
        """Generate next steps section."""
        run_id = self.index_data.get("run_id", "unknown")
        phase_id = phase_context.get("phase_id") if phase_context else "unknown"

        lines = ["## Next Steps", ""]
        lines.append("1. **Review Context**: Open the files listed above in Cursor")
        lines.append(
            "2. **Investigate**: Answer the explicit questions and examine failure symptoms"
        )
        lines.append("3. **Fix**: Make targeted changes to resolve the issue")
        lines.append("4. **Verify**: Run relevant tests to confirm the fix")
        lines.append("5. **Resume**: Notify Autopack to continue execution")
        lines.append("")
        lines.append("### Resume Commands")
        lines.append("```bash")
        lines.append("# If fix is complete, resume executor")
        lines.append(f"autopack resume {run_id}")
        lines.append("")
        lines.append("# Or mark phase as complete and proceed")
        lines.append(f"autopack complete-phase {run_id} {phase_id}")
        lines.append("")
        lines.append("# Or mark phase as failed (skip and continue)")
        lines.append(
            f"autopack skip-phase {run_id} {phase_id} --reason 'Manual intervention required'"
        )
        lines.append("```")

        return "\n".join(lines)


def generate_cursor_prompt(*args: Any, **kwargs: Any) -> str:
    """Generate a Cursor-ready prompt (supports both legacy and new call styles).

    Args:
        Legacy (unit tests):
            handoff_bundle_path: str
            error_message: str
            file_list: List[str]
            constraints: Dict[str, str] with keys "protected paths", "allowed paths", "deliverables"

        New (handoff bundle generator):
            handoff_dir: Path
            phase_context: Optional[Dict[str, Any]]
            error_context: Optional[Dict[str, Any]]
            constraints: Optional[Dict[str, Any]]
            questions: Optional[List[str]]

    Returns:
        Prompt string

    Example:
        >>> from pathlib import Path
        >>> from autopack.diagnostics.cursor_prompt_generator import generate_cursor_prompt
        >>>
        >>> handoff_dir = Path(".autonomous_runs/my-run-20251220/handoff")
        >>> phase_context = {
        ...     "phase_id": "phase-123",
        ...     "name": "Integration Testing",
        ...     "complexity": "high",
        ...     "builder_attempts": 3,
        ...     "max_builder_attempts": 5,
        ...     "failure_class": "PATCH_FAILED"
        ... }
        >>> error_context = {
        ...     "message": "ImportError: cannot import name 'TracerBullet'",
        ...     "category": "import_error",
        ...     "timestamp": "2025-12-21T15:30:22Z"
        ... }
        >>> constraints = {
        ...     "protected_paths": ["src/autopack/core/", "src/autopack/database.py"],
        ...     "allowed_paths": ["src/autopack/research/"],
        ...     "deliverables": ["src/autopack/research/tracer_bullet.py", "tests/test_tracer_bullet.py"]
        ... }
        >>> questions = [
        ...     "Is TracerBullet class defined in tracer_bullet.py?",
        ...     "Is it exported in __init__.py?",
        ...     "Are there circular imports?"
        ... ]
        >>>
        >>> prompt = generate_cursor_prompt(handoff_dir, phase_context, error_context, constraints, questions)
        >>> print(prompt)
    """
    # Legacy deterministic helper used by unit tests:
    # generate_cursor_prompt(handoff_bundle_path, error_message, file_list, constraints)
    if (
        len(args) == 4
        and not kwargs
        and isinstance(args[0], str)
        and isinstance(args[1], str)
        and isinstance(args[2], list)
        and isinstance(args[3], dict)
    ):
        handoff_bundle_path, error_message, file_list, constraints = args

        lines: List[str] = []
        lines.append(f"Diagnostics Handoff Bundle Reference: {handoff_bundle_path}")
        lines.append("")
        lines.append("Current Failure:")
        lines.append(f"- Error: {error_message}")
        lines.append("")
        lines.append("Files to Attach/Open:")
        for f in file_list:
            lines.append(f"- {f}")
        lines.append("")
        lines.append("Constraints:")
        # Preserve key casing exactly as test expects
        if "protected paths" in constraints:
            lines.append(f"- Protected paths: {constraints['protected paths']}")
        if "allowed paths" in constraints:
            lines.append(f"- Allowed paths: {constraints['allowed paths']}")
        if "deliverables" in constraints:
            lines.append(f"- Deliverables: {constraints['deliverables']}")
        return "\n".join(lines)

    # New form:
    # generate_cursor_prompt(handoff_dir, phase_context=None, error_context=None, constraints=None, questions=None)
    if not args:
        raise TypeError(
            "generate_cursor_prompt() missing required positional argument: 'handoff_dir'"
        )

    handoff_dir = Path(args[0])
    phase_context = args[1] if len(args) > 1 else kwargs.get("phase_context")
    error_context = args[2] if len(args) > 2 else kwargs.get("error_context")
    constraints = args[3] if len(args) > 3 else kwargs.get("constraints")
    questions = args[4] if len(args) > 4 else kwargs.get("questions")

    generator = CursorPromptGenerator(handoff_dir)
    return generator.generate_prompt(phase_context, error_context, constraints, questions)


if __name__ == "__main__":
    # Example usage for testing
    import sys

    if len(sys.argv) < 2:
        print("Usage: python cursor_prompt_generator.py <handoff_dir>")
        sys.exit(1)

    handoff_dir = Path(sys.argv[1])

    # Example context
    phase_context = {
        "phase_id": "test-phase-001",
        "name": "Test Phase",
        "complexity": "medium",
        "builder_attempts": 2,
        "max_builder_attempts": 5,
        "failure_class": "PATCH_FAILED",
        "token_budget": 16384,
    }

    error_context = {
        "message": "ImportError: cannot import name 'format_rules_for_prompt' from 'autopack.learned_rules'",
        "category": "import_error",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "phase_id": "test-phase-001",
    }

    constraints = {
        "protected_paths": ["src/autopack/core/", "src/autopack/database.py"],
        "allowed_paths": ["src/autopack/diagnostics/"],
        "deliverables": ["src/autopack/diagnostics/cursor_prompt_generator.py"],
        "test_threshold": 80,
    }

    questions = [
        "Is the function 'format_rules_for_prompt' defined in learned_rules.py?",
        "Is it exported in the module's __init__.py?",
        "Are there any circular import issues?",
    ]

    prompt = generate_cursor_prompt(
        handoff_dir, phase_context, error_context, constraints, questions
    )
    print(prompt)
