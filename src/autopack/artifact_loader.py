"""BUILD-145 P1: Artifact-First Context Loading

Provides token-efficient context loading by preferring run artifacts over full file contents.

When loading read_only_context, this module:
1. Checks if relevant artifacts exist in the run's artifact directory
2. Loads artifact summaries instead of full file content when available
3. Falls back to full file content if no artifact exists
4. Reports token savings for budgeting

BUILD-145 P2: Extended artifact-first substitution:
5. Automatically pins run/tier/phase summaries as 'history pack' in context (opt-in)
6. Optionally substitutes large SOT docs (BUILD_HISTORY, BUILD_LOG) with summaries (opt-in)
7. Applies artifact-first loading to additional safe contexts (opt-in):
   - Phase descriptions in tier summaries
   - Tier summaries in run summaries
   - Historical context references

Artifact Sources (resolved via RunFileLayout, respects AUTONOMOUS_RUNS_DIR):
- Phase summaries: {autonomous_runs_dir}/{project}/runs/{family}/{run_id}/phases/phase_*.md
- Tier summaries: {autonomous_runs_dir}/{project}/runs/{family}/{run_id}/tiers/tier_*.md
- Run summary: {autonomous_runs_dir}/{project}/runs/{family}/{run_id}/run_summary.md
- Diagnostics: {autonomous_runs_dir}/{project}/runs/{family}/{run_id}/diagnostics/diagnostic_summary.json
- Handoff bundles: {autonomous_runs_dir}/{project}/runs/{family}/{run_id}/diagnostics/handoff_*.md

Token Estimation:
- Uses same conservative estimate as context_budgeter: 1 token ≈ 4 chars
- Reports tokens saved when artifact used instead of full file
"""

import logging
from pathlib import Path
from typing import Dict, Optional, Tuple, List
import json

from autopack.config import settings
from autopack.file_layout import RunFileLayout

logger = logging.getLogger(__name__)


def _read_capped(path: Path, max_bytes: Optional[int] = None) -> Tuple[str, bool]:
    """Read file with size cap, returning content and truncation indicator.

    Args:
        path: Path to file to read
        max_bytes: Maximum bytes to read. If None, uses settings.artifact_read_size_cap_bytes.
                   0 means unlimited.

    Returns:
        Tuple of (content, was_truncated)
        - content: File content (truncated if exceeds cap)
        - was_truncated: True if content was truncated, False otherwise
    """
    if max_bytes is None:
        max_bytes = settings.artifact_read_size_cap_bytes

    try:
        # Read full content first to check size
        full_content = path.read_text(encoding="utf-8", errors="ignore")

        # If no cap (0) or content is within cap, return as-is
        if max_bytes == 0 or len(full_content) <= max_bytes:
            return full_content, False

        # Truncate and add indicator
        truncated_content = full_content[:max_bytes]
        truncation_indicator = (
            f"\n\n... [TRUNCATED - content exceeded size cap of {max_bytes} bytes] ..."
        )
        return truncated_content + truncation_indicator, True
    except Exception as e:
        logger.debug(f"[ArtifactLoader] Could not read {path}: {e}")
        return "", False


def estimate_tokens(content: str) -> int:
    """Estimate token count for content using conservative 4 chars/token ratio.

    Args:
        content: Text content to estimate

    Returns:
        Estimated token count
    """
    return len(content) // 4


class ArtifactLoader:
    """Loads run artifacts for token-efficient context (P2.1: uses RunFileLayout)."""

    def __init__(self, workspace: Path, run_id: str, project_id: Optional[str] = None):
        """Initialize artifact loader.

        Args:
            workspace: Repository root path
            run_id: Current run ID
            project_id: Project ID (optional, detected from run_id if not provided)
        """
        self.workspace = Path(workspace)
        self.run_id = run_id

        # P2.1: Use RunFileLayout to resolve artifact directory (respects AUTONOMOUS_RUNS_DIR)
        autonomous_runs_base = self.workspace / settings.autonomous_runs_dir
        self.layout = RunFileLayout(run_id, project_id=project_id, base_dir=autonomous_runs_base)
        self._primary_artifacts_dir = self.layout.base_dir
        self._legacy_artifacts_dir = self.workspace / ".autonomous_runs" / run_id
        self._artifacts_dir_cache = None

    @property
    def artifacts_dir(self) -> Path:
        """Get artifacts directory with lazy legacy fallback.

        Tries new layout first, falls back to legacy path if new layout doesn't exist.
        This enables backward compatibility with existing runs.
        """
        # Return cached value if available
        if self._artifacts_dir_cache is not None:
            return self._artifacts_dir_cache

        # Try new layout first
        if self._primary_artifacts_dir.exists():
            self._artifacts_dir_cache = self._primary_artifacts_dir
            return self._artifacts_dir_cache

        # Fall back to legacy path if it exists
        if self._legacy_artifacts_dir.exists():
            logger.debug(
                f"[ArtifactLoader] Using legacy path for {self.run_id}: {self._legacy_artifacts_dir}"
            )
            self._artifacts_dir_cache = self._legacy_artifacts_dir
            return self._artifacts_dir_cache

        # Neither exists, return primary (new layout) for potential creation
        self._artifacts_dir_cache = self._primary_artifacts_dir
        return self._artifacts_dir_cache

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
            content, _ = _read_capped(phase_file)
            if not content:
                continue
            # Simple heuristic: if file path appears in summary, it's relevant
            if file_path in content or Path(file_path).name in content:
                results.append(content)

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
            content, _ = _read_capped(tier_file)
            if not content:
                continue
            if file_path in content or Path(file_path).name in content:
                results.append(content)

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
            content, _ = _read_capped(summary_json)
            if content:
                try:
                    data = json.loads(content)
                    # Convert to readable summary
                    if file_path in content or Path(file_path).name in content:
                        return f"Diagnostics Summary:\n{json.dumps(data, indent=2)}"
                except Exception as e:
                    logger.debug(f"[ArtifactLoader] Could not parse diagnostic_summary.json: {e}")

        # Check handoff bundles
        for handoff_file in sorted(diagnostics_dir.glob("handoff_*.md"), reverse=True):
            content, _ = _read_capped(handoff_file)
            if not content:
                continue
            if file_path in content or Path(file_path).name in content:
                return content

        return None

    def _load_run_summary(self) -> Optional[str]:
        """Load run summary if it exists.

        Returns:
            Run summary content if found, None otherwise
        """
        run_summary = self.artifacts_dir / "run_summary.md"

        if not run_summary.exists():
            return None

        content, _ = _read_capped(run_summary)
        return content if content else None

    def load_with_artifacts(
        self, file_path: str, full_content: str, prefer_artifacts: bool = True
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

    def build_history_pack(self) -> Optional[str]:
        """Build a 'history pack' of recent run/tier/phase summaries.

        Returns a compact summary of recent execution history for context.
        Only includes summaries if they exist and are smaller than configured limits.

        Returns:
            History pack content if available, None otherwise
        """
        if not settings.artifact_history_pack_enabled:
            return None

        if not self.artifacts_dir.exists():
            return None

        sections = []

        # Add run summary (always include if exists)
        run_summary = self._load_run_summary()
        if run_summary:
            sections.append("# Run Summary\n\n" + run_summary)

        # Add recent tier summaries
        tiers_dir = self.artifacts_dir / "tiers"
        if tiers_dir.exists():
            tier_files = sorted(tiers_dir.glob("tier_*.md"), reverse=True)
            tier_files = tier_files[: settings.artifact_history_pack_max_tiers]
            for tier_file in tier_files:
                content, _ = _read_capped(tier_file)
                if content:
                    sections.append(f"# Tier: {tier_file.stem}\n\n{content}")

        # Add recent phase summaries
        phases_dir = self.artifacts_dir / "phases"
        if phases_dir.exists():
            phase_files = sorted(phases_dir.glob("phase_*.md"), reverse=True)
            phase_files = phase_files[: settings.artifact_history_pack_max_phases]
            for phase_file in phase_files:
                content, _ = _read_capped(phase_file)
                if content:
                    sections.append(f"# Phase: {phase_file.stem}\n\n{content}")

        if not sections:
            return None

        history_pack = "\n\n---\n\n".join(sections)
        logger.info(
            f"[ArtifactLoader] Built history pack with {len(sections)} sections "
            f"(~{estimate_tokens(history_pack)} tokens)"
        )
        return history_pack

    def should_substitute_sot_doc(self, file_path: str) -> bool:
        """Check if a file is a large SOT doc that should be substituted.

        Args:
            file_path: Relative path to file

        Returns:
            True if file should be substituted with summary, False otherwise
        """
        if not settings.artifact_substitute_sot_docs:
            return False

        # List of large SOT docs that benefit from summarization
        sot_docs = [
            "docs/BUILD_HISTORY.md",
            "docs/BUILD_LOG.md",
            ".autonomous_runs/BUILD_HISTORY.md",
            ".autonomous_runs/BUILD_LOG.md",
        ]

        return any(file_path.endswith(doc) or file_path == doc for doc in sot_docs)

    def get_sot_doc_summary(self, file_path: str) -> Optional[str]:
        """Get summary for a large SOT doc.

        Looks for phase/tier summaries that reference the SOT doc content.

        Args:
            file_path: Relative path to SOT doc

        Returns:
            Summary content if available, None otherwise
        """
        if not self.should_substitute_sot_doc(file_path):
            return None

        # For BUILD_HISTORY/BUILD_LOG, use history pack as summary
        history_pack = self.build_history_pack()
        if history_pack:
            logger.info(
                f"[ArtifactLoader] Substituting {file_path} with history pack "
                f"(~{estimate_tokens(history_pack)} tokens)"
            )
            return f"# Summary of {file_path}\n\n{history_pack}"

    def load_with_extended_contexts(self, content: str, context_type: str) -> Tuple[str, int, str]:
        """Load content with artifact substitution in extended safe contexts.

        Applies artifact-first loading to additional contexts beyond read_only_context:
        - Phase descriptions in tier summaries
        - Tier summaries in run summaries
        - Historical context references

        Args:
            content: Original content to potentially substitute
            context_type: Type of context ('phase_description', 'tier_summary', 'historical')

        Returns:
            Tuple of (final_content, tokens_saved, source_type)
        """
        if not settings.artifact_extended_contexts_enabled:
            return content, 0, "original"

        # Only apply to safe, read-only contexts
        safe_contexts = {"phase_description", "tier_summary", "historical"}
        if context_type not in safe_contexts:
            return content, 0, "original"

        # Check if content references artifacts that could be substituted
        original_tokens = estimate_tokens(content)

        # For historical context, use history pack if available
        if context_type == "historical":
            history_pack = self.build_history_pack()
            if history_pack:
                tokens_saved = original_tokens - estimate_tokens(history_pack)
                if tokens_saved > 0:
                    logger.info(
                        f"[ArtifactLoader] Substituted {context_type} with history pack "
                        f"(saved ~{tokens_saved} tokens)"
                    )
                    return history_pack, tokens_saved, "artifact:history_pack"

        # For phase/tier descriptions, check if we have more recent summaries
        if context_type in {"phase_description", "tier_summary"}:
            # Extract phase/tier references from content
            import re

            phase_refs = re.findall(r"phase[_\s]+(\d+)", content.lower())
            tier_refs = re.findall(r"tier[_\s]+(\d+)", content.lower())

            if phase_refs or tier_refs:
                # Build consolidated summary from referenced artifacts
                summary_parts = []

                for phase_num in phase_refs[:3]:  # Limit to 3 most recent
                    phases_dir = self.artifacts_dir / "phases"
                    if phases_dir.exists():
                        phase_files = sorted(phases_dir.glob(f"phase_{int(phase_num):02d}_*.md"))
                        if phase_files:
                            phase_content, _ = _read_capped(phase_files[0])
                            if phase_content:
                                summary_parts.append(
                                    f"## Phase {phase_num}\n{phase_content[:500]}..."
                                )

                for tier_num in tier_refs[:2]:  # Limit to 2 most recent
                    tiers_dir = self.artifacts_dir / "tiers"
                    if tiers_dir.exists():
                        tier_files = sorted(tiers_dir.glob(f"tier_{int(tier_num):02d}_*.md"))
                        if tier_files:
                            tier_content, _ = _read_capped(tier_files[0])
                            if tier_content:
                                summary_parts.append(f"## Tier {tier_num}\n{tier_content[:500]}...")

                if summary_parts:
                    consolidated = "\n\n".join(summary_parts)
                    tokens_saved = original_tokens - estimate_tokens(consolidated)
                    if tokens_saved > 0:
                        logger.info(
                            f"[ArtifactLoader] Substituted {context_type} with artifact summaries "
                            f"(saved ~{tokens_saved} tokens)"
                        )
                        return consolidated, tokens_saved, f"artifact:{context_type}"

        return content, 0, "original"


def get_artifact_substitution_stats(
    loader: ArtifactLoader, files: Dict[str, str]
) -> Tuple[int, int]:
    """Calculate artifact substitution statistics for a set of files.

    Args:
        loader: ArtifactLoader instance
        files: Dictionary of file_path -> content

    Returns:
        Tuple of (substitution_count, total_tokens_saved)
    """
    substitution_count = 0
    total_tokens_saved = 0

    for file_path, content in files.items():
        _, tokens_saved, source_type = loader.load_with_artifacts(
            file_path, content, prefer_artifacts=True
        )
        if source_type.startswith("artifact:"):
            substitution_count += 1
            total_tokens_saved += tokens_saved

    return substitution_count, total_tokens_saved
