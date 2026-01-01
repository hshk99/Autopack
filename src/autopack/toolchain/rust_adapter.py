"""Rust toolchain adapter."""

import logging
from pathlib import Path
from typing import List

from .adapter import ToolchainAdapter, ToolchainDetectionResult

logger = logging.getLogger(__name__)


class RustAdapter(ToolchainAdapter):
    """Rust toolchain adapter."""

    @property
    def name(self) -> str:
        return "rust"

    def detect(self, workspace: Path) -> ToolchainDetectionResult:
        """Detect Rust project."""
        confidence = 0.0
        reasons = []

        # Check for Cargo.toml (very high confidence)
        if (workspace / "Cargo.toml").exists():
            confidence += 0.8
            reasons.append("Cargo.toml")

        # Check for Cargo.lock
        if (workspace / "Cargo.lock").exists():
            confidence += 0.1
            reasons.append("Cargo.lock")

        # Check for .rs files
        rs_files = list(workspace.glob("**/*.rs"))
        if rs_files:
            confidence += min(0.2, len(rs_files) * 0.01)
            reasons.append(f"{len(rs_files)} .rs files")

        confidence = min(1.0, confidence)
        detected = confidence >= 0.5

        return ToolchainDetectionResult(
            detected=detected,
            confidence=confidence,
            name=self.name,
            package_manager="cargo",
            reason=", ".join(reasons) if reasons else "no Rust markers found",
        )

    def install_cmds(self, workspace: Path) -> List[str]:
        """Return install commands for Rust project."""
        if (workspace / "Cargo.toml").exists():
            return ["cargo fetch"]
        return []

    def build_cmds(self, workspace: Path) -> List[str]:
        """Return build commands for Rust project."""
        if (workspace / "Cargo.toml").exists():
            return ["cargo build"]
        return []

    def test_cmds(self, workspace: Path) -> List[str]:
        """Return test commands for Rust project."""
        if (workspace / "Cargo.toml").exists():
            return ["cargo test"]
        return []

    def smoke_checks(self, workspace: Path) -> List[str]:
        """Return smoke check commands for Rust project."""
        return ["cargo check"]
