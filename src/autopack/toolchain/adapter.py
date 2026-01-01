"""Base toolchain adapter interface.

Per IMPLEMENTATION_PLAN_TRUE_AUTONOMY.md Phase 3:
- Modular toolchain detection
- Pluggable command inference
- Safe defaults with fail-fast behavior
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)


@dataclass
class ToolchainDetectionResult:
    """Result of toolchain detection."""

    detected: bool
    confidence: float  # 0.0-1.0
    name: str  # e.g., "python", "node", "go"
    version: Optional[str] = None
    package_manager: Optional[str] = None  # e.g., "pip", "npm", "cargo"
    reason: str = ""  # Why this toolchain was detected


class ToolchainAdapter(ABC):
    """Base interface for toolchain adapters.

    Each adapter implements detection and command inference for a specific
    programming language or framework.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Return toolchain name (e.g., 'python', 'node')."""
        pass

    @abstractmethod
    def detect(self, workspace: Path) -> ToolchainDetectionResult:
        """Detect if this toolchain is present in the workspace.

        Args:
            workspace: Path to workspace root

        Returns:
            ToolchainDetectionResult with confidence score
        """
        pass

    @abstractmethod
    def install_cmds(self, workspace: Path) -> List[str]:
        """Return commands to install dependencies.

        Args:
            workspace: Path to workspace root

        Returns:
            List of shell commands for installing dependencies
        """
        pass

    @abstractmethod
    def build_cmds(self, workspace: Path) -> List[str]:
        """Return commands to build the project.

        Args:
            workspace: Path to workspace root

        Returns:
            List of shell commands for building (empty if no build needed)
        """
        pass

    @abstractmethod
    def test_cmds(self, workspace: Path) -> List[str]:
        """Return commands to run tests.

        Args:
            workspace: Path to workspace root

        Returns:
            List of shell commands for running tests
        """
        pass

    @abstractmethod
    def smoke_checks(self, workspace: Path) -> List[str]:
        """Return commands for basic validation (syntax checks, etc.).

        Args:
            workspace: Path to workspace root

        Returns:
            List of shell commands for smoke checks
        """
        pass

    def detect_version(self, workspace: Path) -> Optional[str]:
        """Optionally detect toolchain version.

        Default implementation returns None. Override if version detection
        is important for this toolchain.

        Args:
            workspace: Path to workspace root

        Returns:
            Version string or None
        """
        return None


def detect_toolchains(workspace: Path) -> List[ToolchainDetectionResult]:
    """Detect all toolchains present in workspace.

    Args:
        workspace: Path to workspace root

    Returns:
        List of detected toolchains, sorted by confidence (highest first)
    """
    from .python_adapter import PythonAdapter
    from .node_adapter import NodeAdapter
    from .go_adapter import GoAdapter
    from .rust_adapter import RustAdapter
    from .java_adapter import JavaAdapter

    adapters = [
        PythonAdapter(),
        NodeAdapter(),
        GoAdapter(),
        RustAdapter(),
        JavaAdapter(),
    ]

    results = []
    for adapter in adapters:
        try:
            result = adapter.detect(workspace)
            if result.detected and result.confidence > 0:
                results.append(result)
                logger.info(
                    f"[Toolchain] Detected {result.name} "
                    f"(confidence={result.confidence:.2f}, reason={result.reason})"
                )
        except Exception as e:
            logger.warning(f"[Toolchain] Failed to detect {adapter.name}: {e}")

    # Sort by confidence (highest first)
    results.sort(key=lambda r: r.confidence, reverse=True)

    return results


def get_primary_toolchain(workspace: Path) -> Optional[ToolchainDetectionResult]:
    """Get the primary (highest confidence) toolchain.

    Args:
        workspace: Path to workspace root

    Returns:
        Primary toolchain or None if no toolchains detected
    """
    detected = detect_toolchains(workspace)
    return detected[0] if detected else None
