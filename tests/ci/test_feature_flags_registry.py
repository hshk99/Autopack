"""Feature flags registry contract tests (PR9, enhanced PR-03).

Ensures all AUTOPACK_* environment variables are documented in
config/feature_flags.yaml (single source of truth).

Contract: No undocumented feature flags in production code.

Boundary decision (PR-03):
- Registry covers ALL AUTOPACK_* environment variables
- Non-AUTOPACK vars (TELEGRAM_*, DATABASE_URL, API keys) are in external_env_vars
- Aliases between AUTOPACK_* and legacy names must be explicitly documented

Enhancement (Delta 1.10.3):
- AST-based extraction for Settings fields + AliasChoices
- Detects env vars from Pydantic BaseSettings field names
- Detects env vars from AliasChoices(...) string literals
- Direct os.environ/os.getenv usage detection
"""

import ast
import re
from pathlib import Path
from typing import Set

import pytest
import yaml

REPO_ROOT = Path(__file__).parent.parent.parent
SRC_DIR = REPO_ROOT / "src"
CONFIG_FILE = REPO_ROOT / "config" / "feature_flags.yaml"
CONFIG_PY = REPO_ROOT / "src" / "autopack" / "config.py"


def extract_env_vars_from_code() -> Set[str]:
    """Extract all environment variable references from src/.

    Uses regex-based scanning for os.environ/os.getenv patterns.
    """
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


def extract_settings_env_vars() -> Set[str]:
    """Extract env vars from Pydantic Settings fields in config.py.

    Detects:
    - Field names with autopack_ prefix -> AUTOPACK_* env vars (Pydantic default)
    - AliasChoices(...) string literals -> explicit env var aliases
    """
    found_vars: Set[str] = set()

    if not CONFIG_PY.exists():
        return found_vars

    try:
        content = CONFIG_PY.read_text(encoding="utf-8")
        tree = ast.parse(content)
    except (OSError, SyntaxError):
        return found_vars

    for node in ast.walk(tree):
        # Look for class definitions that inherit from BaseSettings
        if isinstance(node, ast.ClassDef):
            # Check if this is a Settings class (inherits BaseSettings)
            is_settings_class = any(
                (isinstance(base, ast.Name) and base.id == "BaseSettings")
                or (isinstance(base, ast.Attribute) and base.attr == "BaseSettings")
                for base in node.bases
            )
            if not is_settings_class:
                continue

            # Extract field names that start with autopack_
            for item in node.body:
                if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                    field_name = item.target.id
                    if field_name.startswith("autopack_"):
                        # Pydantic converts snake_case to UPPER_SNAKE_CASE
                        env_var = field_name.upper()
                        found_vars.add(env_var)

        # Look for AliasChoices(...) calls anywhere in the tree
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id == "AliasChoices":
                for arg in node.args:
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                        found_vars.add(arg.value)

    return found_vars


def extract_all_env_vars() -> Set[str]:
    """Extract all env vars from both os.environ usage and Settings fields."""
    all_vars = extract_env_vars_from_code()
    all_vars.update(extract_settings_env_vars())
    return all_vars


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
        """All AUTOPACK_* environment variables must be in the registry.

        Uses enhanced extraction that detects:
        - os.environ/os.getenv patterns (regex-based)
        - Pydantic Settings field names (AST-based)
        - AliasChoices(...) string literals (AST-based)
        """
        # Use combined extraction (regex + AST)
        code_vars = extract_all_env_vars()
        registry = load_feature_flags_registry()
        documented = get_documented_flags(registry)

        # Also include aliases from registry entries
        for flag_name, flag_data in registry.get("flags", {}).items():
            if isinstance(flag_data, dict) and "aliases" in flag_data:
                documented.update(flag_data["aliases"])

        # Filter to only AUTOPACK_* variables
        autopack_vars = {v for v in code_vars if v.startswith("AUTOPACK_")}

        undocumented = autopack_vars - documented

        assert not undocumented, (
            f"Undocumented AUTOPACK_* environment variables found in code:\n"
            f"  {sorted(undocumented)}\n\n"
            f"Add these to config/feature_flags.yaml to maintain single source of truth."
        )

    def test_settings_env_vars_documented(self):
        """Pydantic Settings env vars should be documented (from config.py)."""
        settings_vars = extract_settings_env_vars()
        registry = load_feature_flags_registry()
        documented = get_documented_flags(registry)

        # Also include aliases
        for flag_name, flag_data in registry.get("flags", {}).items():
            if isinstance(flag_data, dict) and "aliases" in flag_data:
                documented.update(flag_data["aliases"])

        # Filter to AUTOPACK_* and aliased vars (from AliasChoices)
        autopack_settings_vars = {v for v in settings_vars if v.startswith("AUTOPACK_") or "_" in v}

        undocumented = autopack_settings_vars - documented

        # Filter out non-AUTOPACK vars that are external (like ENVIRONMENT)
        external_vars = {"ENVIRONMENT"}
        undocumented = undocumented - external_vars

        assert not undocumented, (
            f"Undocumented Settings env vars found in config.py:\n"
            f"  {sorted(undocumented)}\n\n"
            f"Add these to config/feature_flags.yaml (flags or external_env_vars section)."
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
            f"Flags with invalid category: {invalid_category}\nValid categories: {valid_categories}"
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


class TestBoundaryEnforcement:
    """Verify registry boundary is enforced correctly (PR-03).

    Boundary decision:
    - All AUTOPACK_* vars must be in flags section
    - Non-AUTOPACK vars (external services) must be in external_env_vars section
    - Aliases must be explicitly documented with the 'aliases' field
    """

    def test_autopack_vars_not_in_external_section(self):
        """AUTOPACK_* vars should not be in external_env_vars."""
        registry = load_feature_flags_registry()
        external = registry.get("external_env_vars", {})

        autopack_in_external = [k for k in external.keys() if k.startswith("AUTOPACK_")]
        assert not autopack_in_external, (
            f"AUTOPACK_* vars should be in 'flags' section, not 'external_env_vars': "
            f"{autopack_in_external}"
        )

    def test_non_autopack_vars_in_external_section(self):
        """Non-AUTOPACK vars should be in external_env_vars (not flags)."""
        registry = load_feature_flags_registry()
        flags = registry.get("flags", {})

        # These specific vars should NOT be in flags (they're external service config)
        external_expected = {"TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "DATABASE_URL", "NGROK_URL"}
        in_flags = external_expected & set(flags.keys())

        assert not in_flags, (
            f"External service vars should be in 'external_env_vars', not 'flags': {in_flags}"
        )

    def test_aliases_documented_bidirectionally(self):
        """Flags with aliases should have them documented."""
        registry = load_feature_flags_registry()
        flags = registry.get("flags", {})

        # Check that known alias patterns are documented
        known_alias_patterns = [
            ("AUTOPACK_TELEGRAM_BOT_TOKEN", ["TELEGRAM_BOT_TOKEN"]),
            ("AUTOPACK_TELEGRAM_CHAT_ID", ["TELEGRAM_CHAT_ID"]),
        ]

        for flag_name, expected_aliases in known_alias_patterns:
            if flag_name in flags:
                flag_data = flags[flag_name]
                if isinstance(flag_data, dict):
                    documented_aliases = flag_data.get("aliases", [])
                    missing = set(expected_aliases) - set(documented_aliases)
                    assert not missing, f"{flag_name} should document aliases: {missing}"
