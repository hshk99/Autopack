#!/usr/bin/env python3
"""
Fix Phase D issues found in tests
"""

import sys
from pathlib import Path

# Fix 1: Update PlanAnalyzer initialization in manifest_generator.py
MANIFEST_PATH = Path(__file__).parent.parent / "src" / "autopack" / "manifest_generator.py"

print("Fixing PlanAnalyzer initialization...")
with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
    content = f.read()

# Replace incorrect PlanAnalyzer initialization
old_init = """        if self._plan_analyzer is None:
            # Lazy import (only when actually needed)
            from autopack.plan_analyzer import PlanAnalyzer

            self._plan_analyzer = PlanAnalyzer(
                repo_scanner=self.scanner,
                pattern_matcher=self.matcher,
                workspace=self.workspace
            )"""

new_init = """        if self._plan_analyzer is None:
            # Lazy import (only when actually needed)
            from autopack.plan_analyzer import PlanAnalyzer

            self._plan_analyzer = PlanAnalyzer(
                workspace=self.workspace
            )"""

content = content.replace(old_init, new_init)

with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
    f.write(content)

print("✓ Fixed PlanAnalyzer initialization")

# Fix 2: Update test file to fix import paths
TEST_PATH = Path(__file__).parent.parent / "tests" / "test_plan_analyzer_integration.py"

print("\nFixing test import paths...")
with open(TEST_PATH, "r", encoding="utf-8") as f:
    test_content = f.read()

# Fix LLMService → LlmService path
test_content = test_content.replace(
    "autopack.plan_analyzer.LLMService", "autopack.llm_service.LlmService"
)

# Fix PlanAnalyzer patching to patch the import location
test_content = test_content.replace(
    "with patch('autopack.manifest_generator.PlanAnalyzer')",
    "with patch('autopack.plan_analyzer.PlanAnalyzer')",
)

with open(TEST_PATH, "w", encoding="utf-8") as f:
    f.write(test_content)

print("✓ Fixed test import paths")
print("\n✅ All fixes applied!")
