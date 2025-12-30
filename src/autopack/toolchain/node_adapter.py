"""Node.js toolchain adapter.

Supports:
- npm (package.json with npm)
- pnpm (package.json with pnpm-lock.yaml)
- yarn (package.json with yarn.lock)
"""

import logging
from pathlib import Path
from typing import List

from .adapter import ToolchainAdapter, ToolchainDetectionResult

logger = logging.getLogger(__name__)


class NodeAdapter(ToolchainAdapter):
    """Node.js toolchain adapter."""

    @property
    def name(self) -> str:
        return "node"

    def detect(self, workspace: Path) -> ToolchainDetectionResult:
        """Detect Node.js project.

        Detection signals:
        - package.json (high confidence)
        - yarn.lock / pnpm-lock.yaml (package manager detection)
        - *.js, *.ts files
        """
        confidence = 0.0
        reasons = []
        package_manager = "npm"  # Default

        # Check for package.json (very high confidence)
        package_json = workspace / "package.json"
        if package_json.exists():
            confidence += 0.7
            reasons.append("package.json")

            # Detect package manager
            if (workspace / "yarn.lock").exists():
                package_manager = "yarn"
                confidence += 0.1
                reasons.append("yarn.lock")
            elif (workspace / "pnpm-lock.yaml").exists():
                package_manager = "pnpm"
                confidence += 0.1
                reasons.append("pnpm-lock.yaml")
            elif (workspace / "package-lock.json").exists():
                package_manager = "npm"
                confidence += 0.1
                reasons.append("package-lock.json")

        # Check for .js/.ts files (low confidence)
        js_files = list(workspace.glob("**/*.js")) + list(workspace.glob("**/*.ts"))
        if js_files:
            confidence += min(0.2, len(js_files) * 0.01)
            reasons.append(f"{len(js_files)} .js/.ts files")

        # Check for tsconfig.json (TypeScript)
        if (workspace / "tsconfig.json").exists():
            confidence += 0.2
            reasons.append("tsconfig.json")

        # Cap total confidence at 1.0
        confidence = min(1.0, confidence)

        detected = confidence >= 0.5  # Require package.json or strong signals

        return ToolchainDetectionResult(
            detected=detected,
            confidence=confidence,
            name=self.name,
            package_manager=package_manager,
            reason=", ".join(reasons) if reasons else "no Node.js markers found",
        )

    def install_cmds(self, workspace: Path) -> List[str]:
        """Return install commands for Node.js project."""
        detection = self.detect(workspace)

        if not detection.detected:
            return []

        package_manager = detection.package_manager or "npm"

        if package_manager == "yarn":
            return ["yarn install"]
        elif package_manager == "pnpm":
            return ["pnpm install"]
        else:
            return ["npm install"]

    def build_cmds(self, workspace: Path) -> List[str]:
        """Return build commands for Node.js project."""
        # Check package.json for build script
        package_json = workspace / "package.json"
        if not package_json.exists():
            return []

        try:
            import json

            with open(package_json, encoding="utf-8") as f:
                package_data = json.load(f)

            scripts = package_data.get("scripts", {})

            # Common build script names
            if "build" in scripts:
                detection = self.detect(workspace)
                pm = detection.package_manager or "npm"
                return [f"{pm} run build"]
            elif "compile" in scripts:
                detection = self.detect(workspace)
                pm = detection.package_manager or "npm"
                return [f"{pm} run compile"]

        except Exception as e:
            logger.debug(f"Failed to read package.json: {e}")

        return []

    def test_cmds(self, workspace: Path) -> List[str]:
        """Return test commands for Node.js project."""
        # Check package.json for test script
        package_json = workspace / "package.json"
        if not package_json.exists():
            return []

        try:
            import json

            with open(package_json, encoding="utf-8") as f:
                package_data = json.load(f)

            scripts = package_data.get("scripts", {})

            if "test" in scripts:
                detection = self.detect(workspace)
                pm = detection.package_manager or "npm"
                return [f"{pm} test"]

        except Exception as e:
            logger.debug(f"Failed to read package.json: {e}")

        return []

    def smoke_checks(self, workspace: Path) -> List[str]:
        """Return smoke check commands for Node.js project."""
        checks = []

        # If TypeScript, run tsc for type checking
        if (workspace / "tsconfig.json").exists():
            checks.append("npx tsc --noEmit")

        # If ESLint config exists, run linting
        if (
            (workspace / ".eslintrc.js").exists()
            or (workspace / ".eslintrc.json").exists()
            or (workspace / ".eslintrc.yml").exists()
        ):
            checks.append("npx eslint . --max-warnings 0")

        # Fallback: basic syntax check with node
        if not checks:
            js_files = list(workspace.glob("**/*.js"))[:10]  # Limit to 10 files
            if js_files:
                for js_file in js_files:
                    rel_path = js_file.relative_to(workspace)
                    checks.append(f"node --check {rel_path}")

        return checks
