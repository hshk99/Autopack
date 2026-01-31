"""SOT (Source of Truth) Document Summarizer for research context.

Extracts key insights from BUILD_HISTORY.md and ARCHITECTURE_DECISIONS.md
to provide relevant context for project briefs and research artifacts.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class BuildEntry:
    """Represents a build entry from BUILD_HISTORY.md."""

    build_id: str
    timestamp: str
    phase: str
    summary: str
    files_changed: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "build_id": self.build_id,
            "timestamp": self.timestamp,
            "phase": self.phase,
            "summary": self.summary,
            "files_changed": self.files_changed,
        }


@dataclass
class ArchitectureDecision:
    """Represents an architecture decision from ARCHITECTURE_DECISIONS.md."""

    decision_id: str
    timestamp: str
    title: str
    status: str
    context: str = ""
    rationale: str = ""
    impact: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "decision_id": self.decision_id,
            "timestamp": self.timestamp,
            "title": self.title,
            "status": self.status,
            "context": self.context,
            "rationale": self.rationale,
            "impact": self.impact,
        }


@dataclass
class SOTSummary:
    """Combined summary of SOT documents."""

    build_summary: str
    architecture_summary: str
    recent_builds: List[BuildEntry] = field(default_factory=list)
    key_decisions: List[ArchitectureDecision] = field(default_factory=list)
    total_builds: int = 0
    total_decisions: int = 0
    last_updated: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "build_summary": self.build_summary,
            "architecture_summary": self.architecture_summary,
            "recent_builds": [b.to_dict() for b in self.recent_builds],
            "key_decisions": [d.to_dict() for d in self.key_decisions],
            "total_builds": self.total_builds,
            "total_decisions": self.total_decisions,
            "last_updated": self.last_updated,
        }

    def to_markdown(self) -> str:
        """Generate markdown representation of the summary."""
        sections = []

        # Build History Summary
        if self.build_summary or self.recent_builds:
            sections.append("### Build History Context")
            if self.build_summary:
                sections.append(f"\n{self.build_summary}\n")
            if self.recent_builds:
                sections.append("\n**Recent Builds:**\n")
                for build in self.recent_builds[:5]:  # Limit to 5 for brevity
                    sections.append(
                        f"- **{build.build_id}** ({build.timestamp}): {build.summary[:100]}..."
                    )

        # Architecture Decisions Summary
        if self.architecture_summary or self.key_decisions:
            sections.append("\n### Architecture Decisions Context")
            if self.architecture_summary:
                sections.append(f"\n{self.architecture_summary}\n")
            if self.key_decisions:
                sections.append("\n**Key Decisions:**\n")
                for dec in self.key_decisions[:5]:  # Limit to 5 for brevity
                    status_icon = "✅" if dec.status == "Implemented" else "🧭"
                    sections.append(f"- **{dec.decision_id}** {status_icon}: {dec.title}")

        return "\n".join(sections) if sections else ""


class SOTSummarizer:
    """Summarizes SOT documents for research context.

    Extracts key insights from BUILD_HISTORY.md and ARCHITECTURE_DECISIONS.md
    to provide relevant context for project briefs and artifact generation.
    """

    # Default paths relative to project root
    DEFAULT_BUILD_HISTORY_PATH = "docs/BUILD_HISTORY.md"
    DEFAULT_ARCHITECTURE_DECISIONS_PATH = "docs/ARCHITECTURE_DECISIONS.md"

    def __init__(
        self,
        project_root: Optional[Path] = None,
        max_recent_builds: int = 10,
        max_key_decisions: int = 10,
    ):
        """Initialize the SOT summarizer.

        Args:
            project_root: Root path of the project. Defaults to current working directory.
            max_recent_builds: Maximum number of recent builds to include.
            max_key_decisions: Maximum number of key decisions to include.
        """
        self._project_root = project_root or Path.cwd()
        self._max_recent_builds = max_recent_builds
        self._max_key_decisions = max_key_decisions
        logger.debug(f"[SOTSummarizer] Initialized with project_root={self._project_root}")

    def summarize(
        self,
        build_history_path: Optional[Path] = None,
        architecture_decisions_path: Optional[Path] = None,
    ) -> SOTSummary:
        """Generate a summary of SOT documents.

        Args:
            build_history_path: Path to BUILD_HISTORY.md. Uses default if not provided.
            architecture_decisions_path: Path to ARCHITECTURE_DECISIONS.md. Uses default if not provided.

        Returns:
            SOTSummary containing extracted insights from both documents.
        """
        logger.info("[SOTSummarizer] Generating SOT summary")

        # Resolve paths
        build_path = build_history_path or (self._project_root / self.DEFAULT_BUILD_HISTORY_PATH)
        arch_path = architecture_decisions_path or (
            self._project_root / self.DEFAULT_ARCHITECTURE_DECISIONS_PATH
        )

        # Extract build history
        builds, build_count, build_summary = self._extract_build_history(build_path)

        # Extract architecture decisions
        decisions, decision_count, arch_summary = self._extract_architecture_decisions(arch_path)

        # Determine last updated timestamp
        last_updated = None
        if builds:
            last_updated = builds[0].timestamp

        summary = SOTSummary(
            build_summary=build_summary,
            architecture_summary=arch_summary,
            recent_builds=builds[: self._max_recent_builds],
            key_decisions=decisions[: self._max_key_decisions],
            total_builds=build_count,
            total_decisions=decision_count,
            last_updated=last_updated,
        )

        logger.info(
            f"[SOTSummarizer] Generated summary: {len(summary.recent_builds)} builds, "
            f"{len(summary.key_decisions)} decisions"
        )

        return summary

    def _extract_build_history(self, path: Path) -> tuple[List[BuildEntry], int, str]:
        """Extract build entries from BUILD_HISTORY.md.

        Args:
            path: Path to BUILD_HISTORY.md

        Returns:
            Tuple of (list of BuildEntry, total count, summary text)
        """
        if not path.exists():
            logger.warning(f"[SOTSummarizer] BUILD_HISTORY.md not found at {path}")
            return [], 0, "No build history available."

        try:
            content = path.read_text(encoding="utf-8")
        except Exception as e:
            logger.error(f"[SOTSummarizer] Error reading BUILD_HISTORY.md: {e}")
            return [], 0, f"Error reading build history: {e}"

        builds = []
        total_count = 0

        # Extract summary from header
        summary_match = re.search(
            r"\*\*Summary\*\*:\s*(\d+)\s*build\s*entries",
            content,
            re.IGNORECASE,
        )
        if summary_match:
            total_count = int(summary_match.group(1))

        # Extract build entries from INDEX table
        # Pattern: | 2026-01-30 | BUILD-209 | Phase | Summary | Files |
        table_pattern = re.compile(
            r"\|\s*(\d{4}-\d{2}-\d{2})\s*\|\s*(BUILD-\d+)\s*\|\s*([^|]+)\s*\|\s*([^|]+)\s*\|\s*([^|]*)\s*\|"
        )

        for match in table_pattern.finditer(content):
            timestamp = match.group(1).strip()
            build_id = match.group(2).strip()
            phase = match.group(3).strip()
            summary_text = match.group(4).strip()
            files = match.group(5).strip()

            # Parse files changed
            files_changed = [f.strip() for f in files.split(",") if f.strip()]

            entry = BuildEntry(
                build_id=build_id,
                timestamp=timestamp,
                phase=phase,
                summary=summary_text,
                files_changed=files_changed,
            )
            builds.append(entry)

        if not builds:
            # Fallback: try to extract from section headers
            # Pattern: ### BUILD-XXX | YYYY-MM-DD | Title
            header_pattern = re.compile(r"###\s*(BUILD-\d+)\s*\|\s*(\d{4}-\d{2}-\d{2})\s*\|\s*(.+)")
            for match in header_pattern.finditer(content):
                entry = BuildEntry(
                    build_id=match.group(1).strip(),
                    timestamp=match.group(2).strip(),
                    phase="",
                    summary=match.group(3).strip(),
                )
                builds.append(entry)

        # Generate summary text
        if builds:
            summary_text = (
                f"{total_count or len(builds)} builds documented. "
                f"Most recent: {builds[0].build_id} ({builds[0].timestamp})."
            )
        else:
            summary_text = "No build entries found."

        return builds, total_count or len(builds), summary_text

    def _extract_architecture_decisions(
        self, path: Path
    ) -> tuple[List[ArchitectureDecision], int, str]:
        """Extract architecture decisions from ARCHITECTURE_DECISIONS.md.

        Args:
            path: Path to ARCHITECTURE_DECISIONS.md

        Returns:
            Tuple of (list of ArchitectureDecision, total count, summary text)
        """
        if not path.exists():
            logger.warning(f"[SOTSummarizer] ARCHITECTURE_DECISIONS.md not found at {path}")
            return [], 0, "No architecture decisions available."

        try:
            content = path.read_text(encoding="utf-8")
        except Exception as e:
            logger.error(f"[SOTSummarizer] Error reading ARCHITECTURE_DECISIONS.md: {e}")
            return [], 0, f"Error reading architecture decisions: {e}"

        decisions = []
        total_count = 0

        # Extract summary from header
        summary_match = re.search(
            r"\*\*Summary\*\*:\s*(\d+)\s*decision",
            content,
            re.IGNORECASE,
        )
        if summary_match:
            total_count = int(summary_match.group(1))

        # Extract decisions from INDEX table
        # Pattern: | 2026-01-29 | DEC-052 | Title | Status | Impact |
        table_pattern = re.compile(
            r"\|\s*(\d{4}-\d{2}-\d{2})\s*\|\s*(DEC-\d+)\s*\|\s*([^|]+)\s*\|\s*([^|]+)\s*\|\s*([^|]*)\s*\|"
        )

        for match in table_pattern.finditer(content):
            timestamp = match.group(1).strip()
            decision_id = match.group(2).strip()
            title = match.group(3).strip()
            status_raw = match.group(4).strip()
            impact = match.group(5).strip()

            # Normalize status - handle emoji, text, and bracketed patterns
            status = (
                "Implemented"
                if (
                    "✅" in status_raw
                    or "Implemented" in status_raw
                    or "[Implemented]" in status_raw
                )
                else "Planned"
            )

            decision = ArchitectureDecision(
                decision_id=decision_id,
                timestamp=timestamp,
                title=title,
                status=status,
                impact=impact,
            )
            decisions.append(decision)

        if not decisions:
            # Fallback: try to extract from section headers
            # Pattern: ### DEC-XXX | YYYY-MM-DD | Title
            header_pattern = re.compile(r"###\s*(DEC-\d+)\s*\|\s*(\d{4}-\d{2}-\d{2})\s*\|\s*(.+)")
            for match in header_pattern.finditer(content):
                decision = ArchitectureDecision(
                    decision_id=match.group(1).strip(),
                    timestamp=match.group(2).strip(),
                    title=match.group(3).strip(),
                    status="Unknown",
                )
                decisions.append(decision)

        # Generate summary text
        implemented_count = sum(1 for d in decisions if d.status == "Implemented")
        if decisions:
            summary_text = (
                f"{total_count or len(decisions)} architectural decisions documented. "
                f"{implemented_count} implemented."
            )
        else:
            summary_text = "No architecture decisions found."

        return decisions, total_count or len(decisions), summary_text

    def get_brief_context(
        self,
        build_history_path: Optional[Path] = None,
        architecture_decisions_path: Optional[Path] = None,
    ) -> Dict[str, Any]:
        """Get SOT context suitable for project briefs.

        Returns a dictionary with key insights that can be integrated
        into research findings for project brief generation.

        Args:
            build_history_path: Path to BUILD_HISTORY.md. Uses default if not provided.
            architecture_decisions_path: Path to ARCHITECTURE_DECISIONS.md. Uses default if not provided.

        Returns:
            Dictionary with SOT context for project briefs.
        """
        summary = self.summarize(build_history_path, architecture_decisions_path)

        context = {
            "sot_context": {
                "build_history": {
                    "total_builds": summary.total_builds,
                    "recent_summary": summary.build_summary,
                    "recent_builds": [
                        {
                            "id": b.build_id,
                            "date": b.timestamp,
                            "summary": b.summary[:150],  # Truncate for brevity
                        }
                        for b in summary.recent_builds[:5]
                    ],
                },
                "architecture_decisions": {
                    "total_decisions": summary.total_decisions,
                    "summary": summary.architecture_summary,
                    "key_decisions": [
                        {
                            "id": d.decision_id,
                            "title": d.title,
                            "status": d.status,
                        }
                        for d in summary.key_decisions[:5]
                    ],
                },
                "last_updated": summary.last_updated,
            }
        }

        return context

    def generate_context_section(
        self,
        build_history_path: Optional[Path] = None,
        architecture_decisions_path: Optional[Path] = None,
    ) -> str:
        """Generate a markdown section for SOT context.

        Suitable for direct inclusion in project briefs.

        Args:
            build_history_path: Path to BUILD_HISTORY.md. Uses default if not provided.
            architecture_decisions_path: Path to ARCHITECTURE_DECISIONS.md. Uses default if not provided.

        Returns:
            Markdown string with SOT context section.
        """
        summary = self.summarize(build_history_path, architecture_decisions_path)
        return summary.to_markdown()


def get_sot_summarizer(
    project_root: Optional[Path] = None,
    max_recent_builds: int = 10,
    max_key_decisions: int = 10,
) -> SOTSummarizer:
    """Convenience function to get a SOT summarizer instance.

    Args:
        project_root: Root path of the project. Defaults to current working directory.
        max_recent_builds: Maximum number of recent builds to include.
        max_key_decisions: Maximum number of key decisions to include.

    Returns:
        SOTSummarizer instance.
    """
    return SOTSummarizer(
        project_root=project_root,
        max_recent_builds=max_recent_builds,
        max_key_decisions=max_key_decisions,
    )


def summarize_sot_documents(
    project_root: Optional[Path] = None,
    build_history_path: Optional[Path] = None,
    architecture_decisions_path: Optional[Path] = None,
) -> SOTSummary:
    """Convenience function to summarize SOT documents.

    Args:
        project_root: Root path of the project. Defaults to current working directory.
        build_history_path: Path to BUILD_HISTORY.md. Uses default if not provided.
        architecture_decisions_path: Path to ARCHITECTURE_DECISIONS.md. Uses default if not provided.

    Returns:
        SOTSummary containing extracted insights.
    """
    summarizer = get_sot_summarizer(project_root=project_root)
    return summarizer.summarize(
        build_history_path=build_history_path,
        architecture_decisions_path=architecture_decisions_path,
    )
