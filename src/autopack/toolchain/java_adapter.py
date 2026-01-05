"""Java toolchain adapter.

Supports:
- Maven (pom.xml)
- Gradle (build.gradle / build.gradle.kts)
"""

import logging
from pathlib import Path
from typing import List

from .adapter import ToolchainAdapter, ToolchainDetectionResult

logger = logging.getLogger(__name__)


class JavaAdapter(ToolchainAdapter):
    """Java toolchain adapter."""

    @property
    def name(self) -> str:
        return "java"

    def detect(self, workspace: Path) -> ToolchainDetectionResult:
        """Detect Java project."""
        confidence = 0.0
        reasons = []
        package_manager = None

        # Check for pom.xml (Maven)
        if (workspace / "pom.xml").exists():
            confidence += 0.7
            reasons.append("pom.xml")
            package_manager = "maven"

        # Check for build.gradle (Gradle)
        if (workspace / "build.gradle").exists() or (workspace / "build.gradle.kts").exists():
            confidence += 0.7
            reasons.append("build.gradle")
            package_manager = "gradle"

        # Check for .java files
        java_files = list(workspace.glob("**/*.java"))
        if java_files:
            confidence += min(0.2, len(java_files) * 0.01)
            reasons.append(f"{len(java_files)} .java files")

        confidence = min(1.0, confidence)
        detected = confidence >= 0.5

        return ToolchainDetectionResult(
            detected=detected,
            confidence=confidence,
            name=self.name,
            package_manager=package_manager or "maven",
            reason=", ".join(reasons) if reasons else "no Java markers found",
        )

    def install_cmds(self, workspace: Path) -> List[str]:
        """Return install commands for Java project."""
        detection = self.detect(workspace)

        if not detection.detected:
            return []

        if detection.package_manager == "gradle":
            return ["./gradlew build --no-daemon"]
        elif detection.package_manager == "maven":
            return ["mvn dependency:resolve"]

        return []

    def build_cmds(self, workspace: Path) -> List[str]:
        """Return build commands for Java project."""
        detection = self.detect(workspace)

        if not detection.detected:
            return []

        if detection.package_manager == "gradle":
            return ["./gradlew build --no-daemon"]
        elif detection.package_manager == "maven":
            return ["mvn compile"]

        return []

    def test_cmds(self, workspace: Path) -> List[str]:
        """Return test commands for Java project."""
        detection = self.detect(workspace)

        if not detection.detected:
            return []

        if detection.package_manager == "gradle":
            return ["./gradlew test --no-daemon"]
        elif detection.package_manager == "maven":
            return ["mvn test"]

        return []

    def smoke_checks(self, workspace: Path) -> List[str]:
        """Return smoke check commands for Java project."""
        detection = self.detect(workspace)

        if not detection.detected:
            return []

        # Basic compilation check
        if detection.package_manager == "gradle":
            return ["./gradlew compileJava --no-daemon"]
        elif detection.package_manager == "maven":
            return ["mvn compiler:compile"]

        return []
