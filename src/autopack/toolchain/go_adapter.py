"""Go toolchain adapter."""

import logging
from pathlib import Path
from typing import List

from .adapter import ToolchainAdapter, ToolchainDetectionResult

logger = logging.getLogger(__name__)


class GoAdapter(ToolchainAdapter):
    """Go toolchain adapter."""

    @property
    def name(self) -> str:
        return "go"

    def detect(self, workspace: Path) -> ToolchainDetectionResult:
        """Detect Go project."""
        confidence = 0.0
        reasons = []

        # Check for go.mod (very high confidence)
        if (workspace / "go.mod").exists():
            confidence += 0.8
            reasons.append("go.mod")

        # Check for go.sum
        if (workspace / "go.sum").exists():
            confidence += 0.1
            reasons.append("go.sum")

        # Check for .go files
        go_files = list(workspace.glob("**/*.go"))
        if go_files:
            confidence += min(0.2, len(go_files) * 0.01)
            reasons.append(f"{len(go_files)} .go files")

        confidence = min(1.0, confidence)
        detected = confidence >= 0.5

        return ToolchainDetectionResult(
            detected=detected,
            confidence=confidence,
            name=self.name,
            package_manager="go",
            reason=", ".join(reasons) if reasons else "no Go markers found",
        )

    def install_cmds(self, workspace: Path) -> List[str]:
        """Return install commands for Go project."""
        if (workspace / "go.mod").exists():
            return ["go mod download"]
        return []

    def build_cmds(self, workspace: Path) -> List[str]:
        """Return build commands for Go project."""
        if (workspace / "go.mod").exists():
            return ["go build ./..."]
        return []

    def test_cmds(self, workspace: Path) -> List[str]:
        """Return test commands for Go project."""
        if (workspace / "go.mod").exists():
            return ["go test ./... -v"]
        return []

    def smoke_checks(self, workspace: Path) -> List[str]:
        """Return smoke check commands for Go project."""
        return ["go vet ./..."]
