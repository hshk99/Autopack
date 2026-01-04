"""
Grounded Context Builder for PlanAnalyzer (BUILD-124 Phase C + BUILD-125 Phase E)

Generates deterministic, token-budgeted context from RepoScanner and PatternMatcher
results to ground LLM-based feasibility analysis in actual repository structure.

Key Features:
- Hard character cap (4000 chars) to control token budget
- Repo summary (top-level directories, detected anchors)
- Phase grounding (PatternMatcher results, candidate files)
- BUILD-125 Phase E: Chunk summaries for large files
- No file contents initially (just paths and metadata)
- Deterministic output (no LLM calls)
"""

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional

from autopack.repo_scanner import RepoScanner
from autopack.pattern_matcher import PatternMatcher, MatchResult
from autopack.context_chunker import ContextChunker

logger = logging.getLogger(__name__)

# Hard character limit for grounded context
MAX_CONTEXT_CHARS = 4000

# Limits for list truncation
MAX_TOP_LEVEL_DIRS = 20
MAX_ANCHORS_PER_CATEGORY = 20
MAX_CANDIDATE_FILES = 30
MAX_CATEGORIES_SHOWN = 5


@dataclass
class GroundedContext:
    """Grounded context for PlanAnalyzer"""

    repo_summary: str
    phase_context: str
    total_chars: int
    truncated: bool

    def to_prompt_section(self) -> str:
        """Format as prompt section for LLM"""
        parts = [
            "## Repository Context (Grounded)",
            "",
            self.repo_summary,
            "",
            "## Phase Analysis Context",
            "",
            self.phase_context,
        ]

        if self.truncated:
            parts.append("")
            parts.append("(Context truncated to fit token budget)")

        return "\n".join(parts)


class GroundedContextBuilder:
    """
    Build deterministic, token-budgeted context for PlanAnalyzer.

    This builder extracts structured information from RepoScanner and
    PatternMatcher to provide grounded context without file contents.
    """

    def __init__(
        self,
        repo_scanner: RepoScanner,
        pattern_matcher: PatternMatcher,
        max_chars: int = MAX_CONTEXT_CHARS
    ):
        """
        Initialize context builder.

        Args:
            repo_scanner: RepoScanner instance with cached scan results
            pattern_matcher: PatternMatcher for category detection
            max_chars: Maximum characters for context (default 4000)
        """
        self.scanner = repo_scanner
        self.matcher = pattern_matcher
        self.max_chars = max_chars
        # BUILD-125 Phase E: Add chunker for large files
        self.chunker = ContextChunker(repo_scanner.workspace)

    def build_context(
        self,
        goal: str,
        phase_id: str,
        description: str = "",
        match_result: Optional[MatchResult] = None
    ) -> GroundedContext:
        """
        Build grounded context for a phase.

        Args:
            goal: Phase goal text
            phase_id: Phase identifier
            description: Optional phase description
            match_result: Optional PatternMatcher result (if already computed)

        Returns:
            GroundedContext with repo and phase information
        """
        # Ensure scanner has scan results
        structure = self.scanner.scan(use_cache=True)

        # Build repo summary
        repo_summary = self._build_repo_summary(structure)

        # Run pattern matcher if not provided
        if match_result is None:
            try:
                match_result = self.matcher.match(
                    goal=goal,
                    phase_id=phase_id,
                    description=description
                )
            except Exception as e:
                logger.error(f"Pattern matching failed: {e}")
                match_result = None

        # Build phase context
        phase_context = self._build_phase_context(
            goal=goal,
            phase_id=phase_id,
            description=description,
            match_result=match_result
        )

        # Calculate total length and check truncation
        total_text = repo_summary + "\n\n" + phase_context
        total_chars = len(total_text)
        truncated = total_chars > self.max_chars

        # Truncate if needed
        if truncated:
            logger.warning(
                f"Context exceeds {self.max_chars} chars ({total_chars}), truncating..."
            )
            # Preserve repo summary, truncate phase context
            available_for_phase = self.max_chars - len(repo_summary) - 100
            if available_for_phase > 0:
                phase_context = phase_context[:available_for_phase] + "\n...(truncated)"
            else:
                # Even repo summary is too long, truncate both
                repo_summary = repo_summary[:self.max_chars // 2] + "\n...(truncated)"
                phase_context = phase_context[:self.max_chars // 2] + "\n...(truncated)"

            total_chars = len(repo_summary) + len(phase_context)

        return GroundedContext(
            repo_summary=repo_summary,
            phase_context=phase_context,
            total_chars=total_chars,
            truncated=truncated
        )

    def _build_repo_summary(self, structure: Dict) -> str:
        """
        Build repository structure summary.

        Args:
            structure: RepoScanner.scan() result dict

        Returns:
            Formatted repo summary with top-level dirs and detected anchors
        """
        lines = ["### Repository Structure"]

        # Top-level directories
        top_level_dirs = self._get_top_level_dirs(structure)
        if top_level_dirs:
            lines.append("")
            lines.append("**Top-level directories:**")
            for dir_name in top_level_dirs[:MAX_TOP_LEVEL_DIRS]:
                lines.append(f"- {dir_name}/")

            if len(top_level_dirs) > MAX_TOP_LEVEL_DIRS:
                lines.append(f"- ... and {len(top_level_dirs) - MAX_TOP_LEVEL_DIRS} more")

        # Detected anchor directories (from RepoScanner)
        anchor_files = structure.get("anchor_files", {})
        if anchor_files:
            lines.append("")
            lines.append("**Detected key directories (anchors):**")

            # Flatten anchor directories from all categories
            all_anchors = []
            for category, anchors in anchor_files.items():
                all_anchors.extend(anchors)

            anchor_list = sorted(set(all_anchors))[:MAX_ANCHORS_PER_CATEGORY]
            for anchor in anchor_list:
                lines.append(f"- {anchor}")

            if len(all_anchors) > MAX_ANCHORS_PER_CATEGORY:
                lines.append(f"- ... and {len(all_anchors) - MAX_ANCHORS_PER_CATEGORY} more")

        # File count summary
        total_files = structure.get("file_count", 0)
        lines.append("")
        lines.append(f"**Total files scanned:** {total_files}")

        return "\n".join(lines)

    def _build_phase_context(
        self,
        goal: str,
        phase_id: str,
        description: str,
        match_result: Optional[MatchResult]
    ) -> str:
        """
        Build phase-specific context.

        Args:
            goal: Phase goal
            phase_id: Phase identifier
            description: Phase description
            match_result: PatternMatcher results

        Returns:
            Formatted phase context
        """
        lines = [f"### Phase: {phase_id}"]
        lines.append("")
        lines.append(f"**Goal:** {goal}")

        if description:
            lines.append(f"**Description:** {description}")

        # Pattern matching results
        if match_result:
            lines.append("")
            lines.append("**Pattern Matching Results:**")
            lines.append(f"- Category: {match_result.category}")
            lines.append(f"- Confidence: {match_result.confidence:.1%}")

            # Confidence breakdown
            if match_result.confidence_breakdown:
                lines.append("")
                lines.append("**Confidence Breakdown:**")
                for signal, score in match_result.confidence_breakdown.items():
                    lines.append(f"  - {signal}: {score:.1%}")

            # Anchor files found
            if match_result.anchor_files_found:
                lines.append("")
                lines.append("**Anchor Files Found:**")
                for anchor in match_result.anchor_files_found[:10]:
                    lines.append(f"  - {anchor}")
                if len(match_result.anchor_files_found) > 10:
                    remaining = len(match_result.anchor_files_found) - 10
                    lines.append(f"  - ... and {remaining} more")

            # Scope paths (candidate files)
            if match_result.scope_paths:
                lines.append("")
                lines.append("**Candidate Files (Scope):**")
                candidates = match_result.scope_paths[:MAX_CANDIDATE_FILES]
                for path in candidates:
                    lines.append(f"  - {path}")

                if len(match_result.scope_paths) > MAX_CANDIDATE_FILES:
                    remaining = len(match_result.scope_paths) - MAX_CANDIDATE_FILES
                    lines.append(f"  - ... and {remaining} more files")

                lines.append(f"  - **Total:** {len(match_result.scope_paths)} files")

                # BUILD-125 Phase E: Add chunk summaries for large files
                large_files_chunks = self._get_chunk_summaries_for_scope(match_result.scope_paths)
                if large_files_chunks:
                    lines.append("")
                    lines.append("**Large File Structure (Chunked):**")
                    lines.append(large_files_chunks)
            else:
                lines.append("")
                lines.append("**Candidate Files:** None (low confidence match)")

            # Readonly context
            if match_result.read_only_context:
                lines.append("")
                lines.append(f"**Readonly Context:** {len(match_result.read_only_context)} files")
        else:
            lines.append("")
            lines.append("**Pattern Matching:** Failed or not available")

        return "\n".join(lines)

    def _get_top_level_dirs(self, structure: Dict) -> List[str]:
        """
        Extract top-level directory names from repo tree.

        Args:
            structure: RepoScanner.scan() result dict

        Returns:
            List of top-level directory names
        """
        tree = structure.get("tree", {})
        if not tree:
            return []

        top_level = []
        for key in tree.keys():
            # Extract first path component
            parts = key.split('/')
            if len(parts) >= 1 and parts[0] and parts[0] not in {".", ""}:
                top_level.append(parts[0])

        # Return unique, sorted
        return sorted(set(top_level))

    def build_multi_phase_context(
        self,
        phases: List[Dict],
        max_phases_shown: int = 5
    ) -> str:
        """
        Build context for multiple phases (for plan-level analysis).

        Args:
            phases: List of phase dictionaries with goal, phase_id, description
            max_phases_shown: Maximum number of phases to include details for

        Returns:
            Formatted multi-phase context string
        """
        # Ensure scanner has scan results
        structure = self.scanner.scan(use_cache=True)

        # Start with repo summary (shared across phases)
        repo_summary = self._build_repo_summary(structure)

        lines = [repo_summary, "", "### Phases Overview"]
        lines.append(f"**Total Phases:** {len(phases)}")
        lines.append("")

        # Show details for first N phases
        phases_to_show = phases[:max_phases_shown]

        for i, phase in enumerate(phases_to_show, 1):
            phase_id = phase.get("phase_id", f"phase-{i}")
            goal = phase.get("goal", "")

            lines.append(f"**{i}. {phase_id}**")
            lines.append(f"   Goal: {goal}")

            # Quick pattern match (no detailed results)
            try:
                match_result = self.matcher.match(
                    goal=goal,
                    phase_id=phase_id,
                    description=phase.get("description", "")
                )
                category = match_result.category
                confidence = match_result.confidence
                file_count = len(match_result.scope_paths)

                lines.append(
                    f"   Category: {category} ({confidence:.0%} confidence, "
                    f"{file_count} files)"
                )
            except Exception as e:
                logger.debug(f"Pattern match failed for {phase_id}: {e}")
                lines.append("   Category: unknown")

            lines.append("")

        if len(phases) > max_phases_shown:
            remaining = len(phases) - max_phases_shown
            lines.append(f"... and {remaining} more phases")

        result = "\n".join(lines)

        # Check length and truncate if needed
        if len(result) > self.max_chars:
            logger.warning(
                f"Multi-phase context exceeds {self.max_chars} chars, truncating..."
            )
            result = result[:self.max_chars - 50] + "\n...(truncated)"

        return result

    def _get_chunk_summaries_for_scope(
        self,
        scope_paths: List[str],
        max_budget_chars: int = 1000
    ) -> str:
        """
        Generate chunk summaries for large files in scope (BUILD-125 Phase E).

        Args:
            scope_paths: List of file paths in scope
            max_budget_chars: Maximum characters to allocate for chunk summaries

        Returns:
            Formatted chunk summaries or empty string if none
        """
        summaries = []
        current_chars = 0

        for file_path in scope_paths:
            try:
                # Profile file to see if it should be chunked
                profile = self.chunker.profile_file(file_path)

                if not profile.should_chunk():
                    continue

                # Get chunks
                chunks = self.chunker.chunk_file(file_path, profile=profile)

                if not chunks:
                    continue

                # Build summary for this file
                file_summary = [f"\n`{file_path}` ({profile.line_count} lines):"]
                chunk_text = self.chunker.build_chunk_summary(chunks, max_chars=300)
                file_summary.append(chunk_text)

                summary_text = "\n".join(file_summary)
                summary_len = len(summary_text)

                if current_chars + summary_len > max_budget_chars:
                    summaries.append("\n... (additional large files omitted)")
                    break

                summaries.append(summary_text)
                current_chars += summary_len

            except Exception as e:
                logger.debug(f"Could not chunk {file_path}: {e}")
                continue

        return "".join(summaries) if summaries else ""
