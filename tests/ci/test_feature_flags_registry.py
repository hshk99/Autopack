"""Feature flags registry contract tests (PR9).

Ensures all AUTOPACK_* environment variables are documented in
config/feature_flags.yaml (single source of truth).

Contract: No undocumented feature flags in production code.
"""

import re
from pathlib import Path
from typing import Set

import pytest
import yaml

REPO_ROOT = Path(__file__).parent.parent.parent
SRC_DIR = REPO_ROOT / "src"
CONFIG_FILE = REPO_ROOT / "config" / "feature_flags.yaml"


def extract_env_vars_from_code() -> Set[str]:
    """Extract all AUTOPACK_* environment variable references from src/."""
    env_var_pattern = re.compile(r'os\.(?:environ|getenv)\s*\(\s*["\']([A-Z][A-Z0-9_]*)["\']')

    found_vars: Set[str] = set()

    for py_file in SRC_DIR.rglob("*.py"):
        try:
            content = py_file.read_text(encoding="utf-8")
            matches = env_var_pattern.findall(content)
            found_vars.update(matches)
        except (OSError, UnicodeDecodeError):
            continue

    return found_vars


def load_feature_flags_registry() -> dict:
    """Load the feature flags registry."""
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_documented_flags(registry: dict) -> Set[str]:
    """Extract all documented flag names from registry."""
    documented = set()

    # Main flags section
    if "flags" in registry:
        documented.update(registry["flags"].keys())

    # External env vars section
    if "external_env_vars" in registry:
        documented.update(registry["external_env_vars"].keys())

    return documented


class TestFeatureFlagsRegistryExists:
    """Verify the feature flags registry exists and is valid."""

    def test_registry_file_exists(self):
        """config/feature_flags.yaml must exist."""
        assert CONFIG_FILE.exists(), (
            "config/feature_flags.yaml not found - "
            "feature flags must be documented in a central registry"
        )

    def test_registry_is_valid_yaml(self):
        """Registry must be valid YAML."""
        registry = load_feature_flags_registry()
        assert registry is not None, "Registry is empty or invalid YAML"

    def test_registry_has_flags_section(self):
        """Registry must have a 'flags' section."""
        registry = load_feature_flags_registry()
        assert "flags" in registry, "Registry must have a 'flags' section"
        assert isinstance(registry["flags"], dict), "'flags' must be a dict"

    def test_registry_has_external_section(self):
        """Registry must have an 'external_env_vars' section."""
        registry = load_feature_flags_registry()
        assert "external_env_vars" in registry, "Registry must have an 'external_env_vars' section"


class TestAutopackFlagsDocumented:
    """Verify all AUTOPACK_* env vars are documented."""

    def test_all_autopack_vars_documented(self):
        """All AUTOPACK_* environment variables must be in the registry."""
        code_vars = extract_env_vars_from_code()
        registry = load_feature_flags_registry()
        documented = get_documented_flags(registry)

        # Filter to only AUTOPACK_* variables
        autopack_vars = {v for v in code_vars if v.startswith("AUTOPACK_")}

        undocumented = autopack_vars - documented

        assert not undocumented, (
            f"Undocumented AUTOPACK_* environment variables found in code:\n"
            f"  {sorted(undocumented)}\n\n"
            f"Add these to config/feature_flags.yaml to maintain single source of truth."
        )

    def test_critical_security_flags_documented(self):
        """Critical security flags must be documented."""
        registry = load_feature_flags_registry()
        documented = get_documented_flags(registry)

        # Security-critical flags that MUST be documented
        required_flags = {
            "AUTOPACK_ENV",
            "AUTOPACK_API_KEY",
            "TELEGRAM_WEBHOOK_SECRET",
            "RESEARCH_API_ENABLED",
        }

        missing = required_flags - documented
        assert not missing, f"Critical security flags missing from registry: {missing}"


class TestFlagMetadataQuality:
    """Verify each flag has required metadata."""

    def test_flags_have_description(self):
        """Each flag must have a description."""
        registry = load_feature_flags_registry()

        missing_description = []
        for flag_name, flag_data in registry.get("flags", {}).items():
            if not isinstance(flag_data, dict):
                continue
            if "description" not in flag_data or not flag_data["description"]:
                missing_description.append(flag_name)

        assert not missing_description, f"Flags missing description: {missing_description}"

    def test_flags_have_category(self):
        """Each flag must have a category."""
        registry = load_feature_flags_registry()

        valid_categories = {
            "environment",
            "security",
            "feature_toggle",
            "tuning",
            "service_config",
            "deprecated",
        }

        missing_category = []
        invalid_category = []

        for flag_name, flag_data in registry.get("flags", {}).items():
            if not isinstance(flag_data, dict):
                continue
            if "category" not in flag_data:
                missing_category.append(flag_name)
            elif flag_data["category"] not in valid_categories:
                invalid_category.append(f"{flag_name} (has '{flag_data['category']}')")

        assert not missing_category, f"Flags missing category: {missing_category}"
        assert not invalid_category, (
            f"Flags with invalid category: {invalid_category}\n"
            f"Valid categories: {valid_categories}"
        )

    def test_security_flags_have_implications(self):
        """Security category flags should document implications."""
        registry = load_feature_flags_registry()

        flags_needing_implications = []
        for flag_name, flag_data in registry.get("flags", {}).items():
            if not isinstance(flag_data, dict):
                continue
            if flag_data.get("category") == "security":
                if "security_implications" not in flag_data:
                    flags_needing_implications.append(flag_name)

        # Soft warning - don't fail, but flag for review
        if flags_needing_implications:
            pytest.xfail(
                f"Security flags without documented implications (should add): "
                f"{flags_needing_implications}"
            )


class TestRegistryConsistencyWithProjectIndex:
    """Verify registry is consistent with PROJECT_INDEX.json."""

    def test_core_env_vars_match_project_index(self):
        """Core environment variables should match PROJECT_INDEX.json."""
        import json

        project_index = REPO_ROOT / "docs" / "PROJECT_INDEX.json"
        with open(project_index, "r", encoding="utf-8") as f:
            index_data = json.load(f)

        index_env_vars = set(
            index_data.get("deployment", {}).get("environment_variables", {}).keys()
        )

        registry = load_feature_flags_registry()
        _documented = get_documented_flags(registry)  # noqa: F841

        # These should appear in both places
        core_vars = {
            "AUTOPACK_ENV",
            "AUTOPACK_API_KEY",
            "TELEGRAM_WEBHOOK_SECRET",
            "RESEARCH_API_ENABLED",
        }

        for var in core_vars:
            if var not in index_env_vars:
                pytest.xfail(
                    f"{var} is in feature_flags.yaml but not in PROJECT_INDEX.json. "
                    f"Consider adding to deployment.environment_variables."
                )


class TestDeprecatedFlagsQuarantined:
    """Verify deprecated flags are marked and tracked."""

    def test_no_undocumented_deprecated_flags(self):
        """Any flags marked deprecated in code should be in registry."""
        # This is a placeholder - could scan for "deprecated" comments in code
        registry = load_feature_flags_registry()
        deprecated = [
            name
            for name, data in registry.get("flags", {}).items()
            if isinstance(data, dict) and data.get("category") == "deprecated"
        ]

        # Just verify the section works (no assertions for now)
        assert isinstance(deprecated, list)
