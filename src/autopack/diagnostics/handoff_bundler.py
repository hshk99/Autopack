"""Handoff Bundle Generator for Diagnostics Parity (Stage 1A)

Generates a stable, reproducible handoff/ folder from a run directory:
- index.json: Manifest of artifacts with metadata
- summary.md: High-signal narrative of run execution
- excerpts/: Tailed/snippets of key artifacts for quick review

Design Principles:
- Deterministic: Same run directory always produces same bundle
- Reproducible: No timestamps, no random ordering
- Stable: Sorted keys, consistent formatting
- High-signal: Focus on actionable insights, not raw dumps
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


class HandoffBundler:
    """Generates deterministic handoff bundles from run directories."""

    def __init__(self, run_dir: Path):
        """Initialize bundler for a specific run directory.

        Args:
            run_dir: Path to .autonomous_runs/<run_id>/ directory
        """
        self.run_dir = Path(run_dir)
        self.handoff_dir = self.run_dir / "handoff"
        self.excerpts_dir = self.handoff_dir / "excerpts"

        if not self.run_dir.exists():
            raise ValueError(f"Run directory does not exist: {self.run_dir}")

    def generate_bundle(self) -> Path:
        """Generate complete handoff bundle.

        Returns:
            Path to generated handoff/ directory

        Raises:
            ValueError: If run directory is invalid or missing required files
        """
        logger.info(f"[HandoffBundler] Generating bundle for {self.run_dir.name}")

        # Create handoff directory structure
        self.handoff_dir.mkdir(exist_ok=True)
        self.excerpts_dir.mkdir(exist_ok=True)

        # Generate components
        index_data = self._generate_index()
        self._write_index(index_data)
        self._generate_summary(index_data)
        self._generate_excerpts(index_data)

        logger.info(f"[HandoffBundler] Bundle complete: {self.handoff_dir}")
        return self.handoff_dir

    def _generate_index(self) -> Dict[str, Any]:
        """Generate index.json manifest of artifacts.

        Returns:
            Dictionary with artifact metadata (sorted for determinism)
        """
        artifacts = []

        # Scan run directory for key artifacts (using rglob for recursive search)
        artifact_patterns = [
            ("executor.log", "log", "Main executor log"),
            ("phase_*.log", "log", "Phase execution log"),
            ("*.md", "doc", "Documentation/analysis"),
            ("*.json", "data", "Structured data"),
            ("*.yaml", "config", "Configuration file"),
            ("*.yml", "config", "Configuration file"),
            ("*.txt", "text", "Text file"),
            ("*.bin", "binary", "Binary file"),
        ]

        for pattern, artifact_type, description in artifact_patterns:
            for file_path in self.run_dir.rglob(pattern):
                if file_path.is_file() and "handoff" not in str(file_path):
                    artifacts.append(
                        self._create_artifact_entry(file_path, artifact_type, description)
                    )

        # Sort artifacts by (type, name) for determinism
        artifacts.sort(key=lambda x: (x["type"], x["name"]))

        return {
            "version": "1.0",
            "run_id": self.run_dir.name,
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "artifact_count": len(artifacts),
            "artifacts": artifacts,
        }

    def _create_artifact_entry(
        self, file_path: Path, artifact_type: str, description: str
    ) -> Dict[str, Any]:
        """Create artifact metadata entry.

        Args:
            file_path: Path to artifact file
            artifact_type: Type classification (log, doc, data, config)
            description: Human-readable description

        Returns:
            Artifact metadata dictionary
        """
        rel_path = file_path.relative_to(self.run_dir)
        stat = file_path.stat()

        return {
            "name": file_path.name,
            "path": str(rel_path),
            "type": artifact_type,
            "description": description,
            "size_bytes": stat.st_size,
            "excerpt_available": self._should_excerpt(file_path),
        }

    def _should_excerpt(self, file_path: Path) -> bool:
        """Determine if file should have an excerpt generated.

        Args:
            file_path: Path to file

        Returns:
            True if excerpt should be generated
        """
        # Generate excerpts for logs and markdown docs
        if file_path.suffix in [".log", ".md"]:
            return True

        # Skip binary files, very small files, and very large files
        stat = file_path.stat()
        if stat.st_size < 100 or stat.st_size > 10_000_000:
            return False

        return False

    def _write_index(self, index_data: Dict[str, Any]) -> None:
        """Write index.json manifest.

        Args:
            index_data: Index data dictionary
        """
        index_path = self.handoff_dir / "index.json"
        with open(index_path, "w", encoding="utf-8") as f:
            json.dump(index_data, f, indent=2, sort_keys=True)
        logger.info(f"[HandoffBundler] Wrote index: {index_path}")

    def _generate_summary(self, index_data: Dict[str, Any]) -> None:
        """Generate summary.md high-signal narrative.

        Args:
            index_data: Index data from _generate_index()
        """
        summary_path = self.handoff_dir / "summary.md"

        # Build summary content
        lines = [
            f"# Run Summary: {index_data['run_id']}",
            "",
            f"**Generated**: {index_data['generated_at']}",
            f"**Artifacts**: {index_data['artifact_count']}",
            "",
            "## Artifact Inventory",
            "",
        ]

        # Group artifacts by type
        by_type: Dict[str, List[Dict[str, Any]]] = {}
        for artifact in index_data["artifacts"]:
            artifact_type = artifact["type"]
            if artifact_type not in by_type:
                by_type[artifact_type] = []
            by_type[artifact_type].append(artifact)

        # Write grouped artifacts
        for artifact_type in sorted(by_type.keys()):
            lines.append(f"### {artifact_type.capitalize()} Files")
            lines.append("")
            for artifact in by_type[artifact_type]:
                size_kb = artifact["size_bytes"] / 1024
                excerpt_marker = " ✓" if artifact["excerpt_available"] else ""
                lines.append(f"- **{artifact['name']}** ({size_kb:.1f} KB){excerpt_marker}")
                lines.append(f"  - Path: `{artifact['path']}`")
                lines.append(f"  - {artifact['description']}")
                lines.append("")

        # Add excerpt guide
        lines.extend(
            [
                "## Excerpt Guide",
                "",
                "Files marked with ✓ have excerpts available in `excerpts/` directory.",
                "Excerpts show the last 100 lines (for logs) or first 50 lines (for docs).",
                "",
                "## Next Steps",
                "",
                "1. Review `index.json` for complete artifact metadata",
                "2. Check `excerpts/` for quick previews of key files",
                "3. Examine full artifacts in parent directory as needed",
                "",
            ]
        )

        with open(summary_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        logger.info(f"[HandoffBundler] Wrote summary: {summary_path}")

    def _generate_excerpts(self, index_data: Dict[str, Any]) -> None:
        """Generate excerpts/ directory with tailed/snippets.

        Args:
            index_data: Index data from _generate_index()
        """
        excerpt_count = 0

        for artifact in index_data["artifacts"]:
            if not artifact["excerpt_available"]:
                continue

            source_path = self.run_dir / artifact["path"]
            excerpt_name = f"{artifact['name']}.excerpt"
            excerpt_path = self.excerpts_dir / excerpt_name

            try:
                self._create_excerpt(source_path, excerpt_path, artifact["type"])
                excerpt_count += 1
            except Exception as e:
                logger.warning(
                    f"[HandoffBundler] Failed to create excerpt for {artifact['name']}: {e}"
                )

        logger.info(f"[HandoffBundler] Generated {excerpt_count} excerpts")

    def _create_excerpt(self, source_path: Path, excerpt_path: Path, artifact_type: str) -> None:
        """Create excerpt file from source.

        Args:
            source_path: Path to source file
            excerpt_path: Path to excerpt output
            artifact_type: Type of artifact (log, doc, etc.)
        """
        with open(source_path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()

        # Determine excerpt strategy based on type
        if artifact_type == "log":
            # Tail last 100 lines for logs
            excerpt_lines = lines[-100:] if len(lines) > 100 else lines
            header = f"# Last {len(excerpt_lines)} lines of {source_path.name}\n\n"
        else:
            # Head first 50 lines for docs
            excerpt_lines = lines[:50] if len(lines) > 50 else lines
            header = f"# First {len(excerpt_lines)} lines of {source_path.name}\n\n"

        with open(excerpt_path, "w", encoding="utf-8") as f:
            f.write(header)
            f.writelines(excerpt_lines)

        logger.debug(f"[HandoffBundler] Created excerpt: {excerpt_path.name}")


def generate_handoff_bundle(run_dir: Path) -> Path:
    """Convenience function to generate handoff bundle.

    Args:
        run_dir: Path to .autonomous_runs/<run_id>/ directory

    Returns:
        Path to generated handoff/ directory

    Example:
        >>> from pathlib import Path
        >>> from autopack.diagnostics.handoff_bundler import generate_handoff_bundle
        >>> run_dir = Path(".autonomous_runs/my-run-20251220")
        >>> handoff_dir = generate_handoff_bundle(run_dir)
        >>> print(f"Bundle generated: {handoff_dir}")
    """
    bundler = HandoffBundler(run_dir)
    return bundler.generate_bundle()
