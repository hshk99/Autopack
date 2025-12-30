"""BUILD-145 P1: Artifact-First Context Loading

Provides token-efficient context loading by preferring run artifacts over full file contents.

When loading read_only_context, this module:
1. Checks if relevant artifacts exist in .autonomous_runs/<run_id>/
2. Loads artifact summaries instead of full file content when available
3. Falls back to full file content if no artifact exists
4. Reports token savings for budgeting

Artifact Sources (in priority order):
- Phase summaries: .autonomous_runs/<run_id>/phases/phase_*.md
- Tier summaries: .autonomous_runs/<run_id>/tiers/tier_*.md
- Run summary: .autonomous_runs/<run_id>/run_summary.md
- Diagnostics: .autonomous_runs/<run_id>/diagnostics/diagnostic_summary.json
- Handoff bundles: .autonomous_runs/<run_id>/diagnostics/handoff_*.md

Token Estimation:
- Uses same conservative estimate as context_budgeter: 1 token ≈ 4 chars
- Reports tokens saved when artifact used instead of full file
"""

import logging
from pathlib import Path
from typing import Dict, Optional, Tuple, List
import json

logger = logging.getLogger(__name__)


def estimate_tokens(content: str) -> int:
    """Estimate token count for content using conservative 4 chars/token ratio.

    Args:
        content: Text content to estimate

    Returns:
        Estimated token count
    """
    return len(content) // 4


class ArtifactLoader:
    """Loads run artifacts for token-efficient context."""

    def __init__(self, workspace: Path, run_id: str):
        """Initialize artifact loader.

        Args:
            workspace: Repository root path
            run_id: Current run ID
        """
        self.workspace = Path(workspace)
        self.run_id = run_id
        self.artifacts_dir = workspace / ".autonomous_runs" / run_id

    def find_artifact_for_path(self, file_path: str) -> Optional[Tuple[str, str]]:
        """Find relevant artifact for a file path.

        Searches for artifacts that might contain summary information about
        the given file path. Returns the artifact content and type if found.

        Args:
            file_path: Relative path to file (e.g., "src/auth.py")

        Returns:
            Tuple of (artifact_content, artifact_type) if found, None otherwise
            artifact_type is one of: "phase_summary", "tier_summary", "run_summary", "diagnostics"
        """
        if not self.artifacts_dir.exists():
            return None

        # Try phase summaries first (most specific)
        phase_summaries = self._find_phase_summaries_mentioning(file_path)
        if phase_summaries:
            return phase_summaries[0], "phase_summary"

        # Try tier summaries (broader scope)
        tier_summaries = self._find_tier_summaries_mentioning(file_path)
        if tier_summaries:
            return tier_summaries[0], "tier_summary"

        # Try diagnostics (if file appears in diagnostic context)
        diagnostics = self._find_diagnostics_mentioning(file_path)
        if diagnostics:
            return diagnostics, "diagnostics"

        # Fall back to run summary (least specific, rarely useful for individual files)
        run_summary = self._load_run_summary()
        if run_summary and file_path in run_summary:
            return run_summary, "run_summary"

        return None

    def _find_phase_summaries_mentioning(self, file_path: str) -> List[str]:
        """Find phase summaries that mention the given file path.

        Args:
            file_path: Relative file path to search for

        Returns:
            List of phase summary contents that mention the file
        """
        results = []
        phases_dir = self.artifacts_dir / "phases"

        if not phases_dir.exists():
            return results

        for phase_file in sorted(phases_dir.glob("phase_*.md"), reverse=True):
            try:
                content = phase_file.read_text(encoding="utf-8", errors="ignore")
                # Simple heuristic: if file path appears in summary, it's relevant
                if file_path in content or Path(file_path).name in content:
                    results.append(content)
            except Exception as e:
                logger.debug(f"[ArtifactLoader] Could not read {phase_file}: {e}")

        return results

    def _find_tier_summaries_mentioning(self, file_path: str) -> List[str]:
        """Find tier summaries that mention the given file path.

        Args:
            file_path: Relative file path to search for

        Returns:
            List of tier summary contents that mention the file
        """
        results = []
        tiers_dir = self.artifacts_dir / "tiers"

        if not tiers_dir.exists():
            return results

        for tier_file in sorted(tiers_dir.glob("tier_*.md"), reverse=True):
            try:
                content = tier_file.read_text(encoding="utf-8", errors="ignore")
                if file_path in content or Path(file_path).name in content:
                    results.append(content)
            except Exception as e:
                logger.debug(f"[ArtifactLoader] Could not read {tier_file}: {e}")

        return results

    def _find_diagnostics_mentioning(self, file_path: str) -> Optional[str]:
        """Find diagnostics that mention the given file path.

        Args:
            file_path: Relative file path to search for

        Returns:
            Diagnostics content if found, None otherwise
        """
        diagnostics_dir = self.artifacts_dir / "diagnostics"

        if not diagnostics_dir.exists():
            return None

        # Check diagnostic_summary.json if exists
        summary_json = diagnostics_dir / "diagnostic_summary.json"
        if summary_json.exists():
            try:
                content = summary_json.read_text(encoding="utf-8", errors="ignore")
                data = json.loads(content)
                # Convert to readable summary
                if file_path in content or Path(file_path).name in content:
                    return f"Diagnostics Summary:\n{json.dumps(data, indent=2)}"
            except Exception as e:
                logger.debug(f"[ArtifactLoader] Could not parse diagnostic_summary.json: {e}")

        # Check handoff bundles
        for handoff_file in sorted(diagnostics_dir.glob("handoff_*.md"), reverse=True):
            try:
                content = handoff_file.read_text(encoding="utf-8", errors="ignore")
                if file_path in content or Path(file_path).name in content:
                    return content
            except Exception as e:
                logger.debug(f"[ArtifactLoader] Could not read {handoff_file}: {e}")

        return None

    def _load_run_summary(self) -> Optional[str]:
        """Load run summary if it exists.

        Returns:
            Run summary content if found, None otherwise
        """
        run_summary = self.artifacts_dir / "run_summary.md"

        if not run_summary.exists():
            return None

        try:
            return run_summary.read_text(encoding="utf-8", errors="ignore")
        except Exception as e:
            logger.debug(f"[ArtifactLoader] Could not read run_summary.md: {e}")
            return None

    def load_with_artifacts(
        self,
        file_path: str,
        full_content: str,
        prefer_artifacts: bool = True
    ) -> Tuple[str, int, str]:
        """Load content with artifact substitution if available.

        Args:
            file_path: Relative path to file
            full_content: Full file content (fallback)
            prefer_artifacts: If True, prefer artifact over full content

        Returns:
            Tuple of (content, tokens_saved, source_type)
            - content: Artifact content or full content
            - tokens_saved: Estimated tokens saved (0 if no artifact used)
            - source_type: "artifact:<type>" or "full_file"
        """
        if not prefer_artifacts:
            return full_content, 0, "full_file"

        artifact_result = self.find_artifact_for_path(file_path)

        if artifact_result:
            artifact_content, artifact_type = artifact_result

            # Estimate token savings
            full_tokens = estimate_tokens(full_content)
            artifact_tokens = estimate_tokens(artifact_content)
            tokens_saved = max(0, full_tokens - artifact_tokens)

            # Only use artifact if it's actually smaller (token efficient)
            if artifact_tokens < full_tokens:
                logger.info(
                    f"[ArtifactLoader] Using {artifact_type} for {file_path} "
                    f"(~{tokens_saved} tokens saved, {artifact_tokens} vs {full_tokens})"
                )
                return artifact_content, tokens_saved, f"artifact:{artifact_type}"
            else:
                logger.debug(
                    f"[ArtifactLoader] Artifact for {file_path} is larger than full content, using full content"
                )

        return full_content, 0, "full_file"
