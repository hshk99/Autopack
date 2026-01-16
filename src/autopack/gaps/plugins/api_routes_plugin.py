"""Example plugin: detect API routes without tests."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import List

from ..gap_plugin import GapDetectorPlugin, GapResult

logger = logging.getLogger(__name__)


class ApiRoutesWithoutTestsPlugin(GapDetectorPlugin):
    """Detects API routes that don't have corresponding tests."""

    @property
    def name(self) -> str:
        """Plugin name."""
        return "api_routes_without_tests"

    @property
    def gap_type(self) -> str:
        """Gap type this plugin detects."""
        return "untested_api_route"

    def detect(self, context: dict) -> List[GapResult]:
        """Detect API routes without tests.

        Args:
            context: Context dictionary with project_root and other metadata

        Returns:
            List of detected GapResult objects for untested routes
        """
        results = []
        project_root = Path(context.get("project_root", "."))

        # Find all route files matching pattern src/**/routes.py
        route_files = list(project_root.glob("src/**/routes.py"))
        test_files = {f.stem for f in project_root.glob("tests/**/test_*.py")}

        # Check for missing tests
        for route_file in route_files:
            # Expected test file name would be test_<parent_dir>.py
            parent_dir = route_file.parent.name
            expected_test = f"test_{parent_dir}"

            if expected_test not in test_files:
                results.append(
                    GapResult(
                        gap_type=self.gap_type,
                        description=f"Route file {route_file.relative_to(project_root)} has no corresponding test",
                        file_path=str(route_file.relative_to(project_root)),
                        severity="high",
                        auto_fixable=False,
                        suggested_fix=f"Create tests/{expected_test}.py",
                    )
                )
                logger.debug(f"Found untested route: {route_file}")

        return results
