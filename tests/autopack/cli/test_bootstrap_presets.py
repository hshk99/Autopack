"""Tests for bootstrap presets functionality.

Tests cover:
- Preset loading and validation
- Preset application to bootstrap options
- Preset availability and descriptions
- Integration with bootstrap runner
"""

import pytest

from autopack.cli.commands.bootstrap import BootstrapOptions
from autopack.cli.commands.bootstrap_presets import (
    ECOMMERCE_PRESET,
    AUTOMATION_PRESET,
    CONTENT_PRESET,
    MINIMAL_PRESET,
    TRADING_PRESET,
    BootstrapPreset,
    BootstrapPresetName,
    format_preset_help,
    get_preset,
    get_preset_for_project_type,
    list_presets,
)
from autopack.research.idea_parser import ProjectType, RiskProfile


class TestBootstrapPresets:
    """Test bootstrap preset definitions."""

    def test_ecommerce_preset(self):
        """Test ecommerce preset configuration."""
        assert ECOMMERCE_PRESET.name == BootstrapPresetName.ECOMMERCE
        assert ECOMMERCE_PRESET.risk_tolerance == RiskProfile.MEDIUM
        assert ECOMMERCE_PRESET.skip_research is False
        assert ECOMMERCE_PRESET.autonomous is False
        assert ProjectType.ECOMMERCE in ECOMMERCE_PRESET.recommended_for_types

    def test_trading_preset(self):
        """Test trading preset configuration."""
        assert TRADING_PRESET.name == BootstrapPresetName.TRADING
        assert TRADING_PRESET.risk_tolerance == RiskProfile.HIGH
        assert TRADING_PRESET.skip_research is False
        assert TRADING_PRESET.autonomous is False
        assert ProjectType.TRADING in TRADING_PRESET.recommended_for_types

    def test_content_preset(self):
        """Test content preset configuration."""
        assert CONTENT_PRESET.name == BootstrapPresetName.CONTENT
        assert CONTENT_PRESET.risk_tolerance == RiskProfile.LOW
        assert CONTENT_PRESET.skip_research is False
        assert CONTENT_PRESET.autonomous is True
        assert ProjectType.CONTENT in CONTENT_PRESET.recommended_for_types

    def test_automation_preset(self):
        """Test automation preset configuration."""
        assert AUTOMATION_PRESET.name == BootstrapPresetName.AUTOMATION
        assert AUTOMATION_PRESET.risk_tolerance == RiskProfile.MEDIUM
        assert AUTOMATION_PRESET.skip_research is False
        assert AUTOMATION_PRESET.autonomous is False
        assert ProjectType.AUTOMATION in AUTOMATION_PRESET.recommended_for_types

    def test_minimal_preset(self):
        """Test minimal preset configuration."""
        assert MINIMAL_PRESET.name == BootstrapPresetName.MINIMAL
        assert MINIMAL_PRESET.risk_tolerance == RiskProfile.MEDIUM
        assert MINIMAL_PRESET.skip_research is True
        assert MINIMAL_PRESET.autonomous is True
        assert len(MINIMAL_PRESET.recommended_for_types) == 0

    def test_preset_has_description(self):
        """Test that all presets have descriptions."""
        for preset in list_presets():
            assert preset.get_description()
            assert len(preset.get_description()) > 0


class TestPresetRetrieval:
    """Test preset retrieval and lookup functions."""

    def test_get_preset_by_name(self):
        """Test getting preset by name."""
        preset = get_preset("ecommerce")
        assert preset is not None
        assert preset.name == BootstrapPresetName.ECOMMERCE

    def test_get_preset_case_insensitive(self):
        """Test that preset lookup is case-insensitive."""
        preset1 = get_preset("ECOMMERCE")
        preset2 = get_preset("ecommerce")
        assert preset1 == preset2

    def test_get_preset_invalid_name(self):
        """Test that invalid preset names return None."""
        preset = get_preset("invalid_preset")
        assert preset is None

    def test_list_presets(self):
        """Test listing all available presets."""
        presets = list_presets()
        assert len(presets) >= 5  # At least ecommerce, trading, content, automation, minimal
        assert ECOMMERCE_PRESET in presets
        assert TRADING_PRESET in presets
        assert CONTENT_PRESET in presets
        assert AUTOMATION_PRESET in presets
        assert MINIMAL_PRESET in presets

    def test_get_preset_for_project_type_ecommerce(self):
        """Test getting preset for ecommerce project type."""
        preset = get_preset_for_project_type(ProjectType.ECOMMERCE)
        assert preset is not None
        assert preset.name == BootstrapPresetName.ECOMMERCE

    def test_get_preset_for_project_type_trading(self):
        """Test getting preset for trading project type."""
        preset = get_preset_for_project_type(ProjectType.TRADING)
        assert preset is not None
        assert preset.name == BootstrapPresetName.TRADING

    def test_get_preset_for_project_type_content(self):
        """Test getting preset for content project type."""
        preset = get_preset_for_project_type(ProjectType.CONTENT)
        assert preset is not None
        assert preset.name == BootstrapPresetName.CONTENT

    def test_get_preset_for_project_type_automation(self):
        """Test getting preset for automation project type."""
        preset = get_preset_for_project_type(ProjectType.AUTOMATION)
        assert preset is not None
        assert preset.name == BootstrapPresetName.AUTOMATION

    def test_get_preset_for_project_type_other(self):
        """Test that OTHER project type has no specific preset."""
        preset = get_preset_for_project_type(ProjectType.OTHER)
        # OTHER type has no specific preset, should return None
        assert preset is None


class TestPresetApplication:
    """Test applying presets to bootstrap options."""

    def test_apply_ecommerce_preset(self):
        """Test applying ecommerce preset to options."""
        options = BootstrapOptions()
        ECOMMERCE_PRESET.apply_to_options(options)

        assert options.risk_tolerance == RiskProfile.MEDIUM.value
        assert options.skip_research is False
        assert options.autonomous is False

    def test_apply_trading_preset(self):
        """Test applying trading preset to options."""
        options = BootstrapOptions()
        TRADING_PRESET.apply_to_options(options)

        assert options.risk_tolerance == RiskProfile.HIGH.value
        assert options.skip_research is False
        assert options.autonomous is False

    def test_apply_minimal_preset(self):
        """Test applying minimal preset to options."""
        options = BootstrapOptions()
        MINIMAL_PRESET.apply_to_options(options)

        assert options.risk_tolerance == RiskProfile.MEDIUM.value
        assert options.skip_research is True
        assert options.autonomous is True

    def test_apply_content_preset(self):
        """Test applying content preset to options."""
        options = BootstrapOptions()
        CONTENT_PRESET.apply_to_options(options)

        assert options.risk_tolerance == RiskProfile.LOW.value
        assert options.skip_research is False
        assert options.autonomous is True

    def test_preset_override_default_values(self):
        """Test that preset overrides default values only."""
        options = BootstrapOptions()
        # Options with default values should be overridden
        assert options.risk_tolerance == "medium"  # Default
        assert options.autonomous is False  # Default

        TRADING_PRESET.apply_to_options(options)

        assert options.risk_tolerance == RiskProfile.HIGH.value
        assert options.skip_research is False

    def test_preset_with_none_recommended_types(self):
        """Test that presets with no recommended types work correctly."""
        assert MINIMAL_PRESET.recommended_for_types is not None
        assert len(MINIMAL_PRESET.recommended_for_types) == 0


class TestPresetFormatting:
    """Test preset help text formatting."""

    def test_format_preset_help(self):
        """Test formatting of preset help text."""
        help_text = format_preset_help()

        assert "Available bootstrap presets:" in help_text
        assert "ecommerce" in help_text
        assert "trading" in help_text
        assert "content" in help_text
        assert "automation" in help_text
        assert "minimal" in help_text
        assert "Example:" in help_text

    def test_preset_help_includes_descriptions(self):
        """Test that help text includes preset descriptions."""
        help_text = format_preset_help()

        for preset in list_presets():
            # Preset name should be in help text
            assert preset.name.value in help_text


class TestPresetEnum:
    """Test BootstrapPresetName enum."""

    def test_preset_enum_values_correct(self):
        """Test that all preset enum values are correct."""
        assert BootstrapPresetName.ECOMMERCE.value == "ecommerce"
        assert BootstrapPresetName.TRADING.value == "trading"
        assert BootstrapPresetName.CONTENT.value == "content"
        assert BootstrapPresetName.AUTOMATION.value == "automation"
        assert BootstrapPresetName.MINIMAL.value == "minimal"

    def test_preset_enum_all_exist(self):
        """Test that all expected preset enum members exist."""
        expected_names = {"ecommerce", "trading", "content", "automation", "minimal"}
        actual_names = {member.value for member in BootstrapPresetName}
        assert expected_names.issubset(actual_names)
