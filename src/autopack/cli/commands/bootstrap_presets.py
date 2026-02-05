"""Project-type presets for bootstrap CLI.

Provides pre-configured settings templates for different project types,
allowing users to quickly bootstrap projects with sensible defaults.

Presets define defaults for:
- Risk tolerance
- Research depth
- Skip research flag
- Autonomous mode settings
- Default answers for common Q&A questions

Usage:
    autopack bootstrap run --idea "..." --preset ecommerce
    autopack bootstrap run --idea "..." --preset trading --risk-tolerance high
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from autopack.research.idea_parser import ProjectType, RiskProfile


class BootstrapPresetName(str, Enum):
    """Available bootstrap presets."""

    ECOMMERCE = "ecommerce"
    TRADING = "trading"
    CONTENT = "content"
    AUTOMATION = "automation"
    MINIMAL = "minimal"


@dataclass
class BootstrapPreset:
    """Configuration preset for bootstrap command.

    Defines default values for bootstrap options based on project type.
    Users can override any preset value via command-line flags.
    """

    name: BootstrapPresetName
    description: str
    risk_tolerance: RiskProfile
    skip_research: bool = False
    autonomous: bool = False
    recommended_for_types: list[ProjectType] = None

    def __post_init__(self):
        """Initialize default project types if not provided."""
        if self.recommended_for_types is None:
            self.recommended_for_types = []

    def get_description(self) -> str:
        """Get full preset description.

        Returns:
            Human-readable description of the preset
        """
        return self.description

    def apply_to_options(self, options) -> None:
        """Apply preset values to bootstrap options.

        User-provided values override preset defaults.

        Args:
            options: BootstrapOptions object to update
        """
        # Only apply if not explicitly set by user
        if options.risk_tolerance == "medium":  # Default value
            options.risk_tolerance = self.risk_tolerance.value

        if not options.autonomous and self.autonomous:
            options.autonomous = self.autonomous

        if not options.skip_research and self.skip_research:
            options.skip_research = self.skip_research


# ============================================================================
# Preset Definitions
# ============================================================================

ECOMMERCE_PRESET = BootstrapPreset(
    name=BootstrapPresetName.ECOMMERCE,
    description=(
        "E-commerce platform preset. "
        "Optimized for payment processing, inventory, and order management. "
        "Includes compliance considerations for financial transactions."
    ),
    risk_tolerance=RiskProfile.MEDIUM,
    skip_research=False,
    autonomous=False,
    recommended_for_types=[ProjectType.ECOMMERCE],
)

TRADING_PRESET = BootstrapPreset(
    name=BootstrapPresetName.TRADING,
    description=(
        "Trading system preset. "
        "Configured for high-risk financial applications with strict validation. "
        "Requires extensive research and approval gates."
    ),
    risk_tolerance=RiskProfile.HIGH,
    skip_research=False,
    autonomous=False,
    recommended_for_types=[ProjectType.TRADING],
)

CONTENT_PRESET = BootstrapPreset(
    name=BootstrapPresetName.CONTENT,
    description=(
        "Content management preset. "
        "Optimized for publishing, media, and creator-focused platforms. "
        "Lower risk tolerance with streamlined approval."
    ),
    risk_tolerance=RiskProfile.LOW,
    skip_research=False,
    autonomous=True,
    recommended_for_types=[ProjectType.CONTENT],
)

AUTOMATION_PRESET = BootstrapPreset(
    name=BootstrapPresetName.AUTOMATION,
    description=(
        "Automation and workflow preset. "
        "Configured for task automation, scheduling, and integration work. "
        "Moderate risk with balanced approval requirements."
    ),
    risk_tolerance=RiskProfile.MEDIUM,
    skip_research=False,
    autonomous=False,
    recommended_for_types=[ProjectType.AUTOMATION],
)

MINIMAL_PRESET = BootstrapPreset(
    name=BootstrapPresetName.MINIMAL,
    description=(
        "Minimal/fast-track preset. "
        "Skips research phase and uses defaults for Q&A. "
        "Fastest path to READY_FOR_BUILD state."
    ),
    risk_tolerance=RiskProfile.MEDIUM,
    skip_research=True,
    autonomous=True,
    recommended_for_types=[],
)

# Registry of all presets
PRESETS: dict[BootstrapPresetName, BootstrapPreset] = {
    BootstrapPresetName.ECOMMERCE: ECOMMERCE_PRESET,
    BootstrapPresetName.TRADING: TRADING_PRESET,
    BootstrapPresetName.CONTENT: CONTENT_PRESET,
    BootstrapPresetName.AUTOMATION: AUTOMATION_PRESET,
    BootstrapPresetName.MINIMAL: MINIMAL_PRESET,
}


# ============================================================================
# Preset Management Functions
# ============================================================================


def get_preset(name: str) -> Optional[BootstrapPreset]:
    """Get a preset by name.

    Args:
        name: Preset name (case-insensitive)

    Returns:
        BootstrapPreset or None if not found
    """
    try:
        preset_name = BootstrapPresetName(name.lower())
        return PRESETS.get(preset_name)
    except ValueError:
        return None


def list_presets() -> list[BootstrapPreset]:
    """Get list of all available presets.

    Returns:
        List of BootstrapPreset objects
    """
    return list(PRESETS.values())


def get_preset_for_project_type(project_type: ProjectType) -> Optional[BootstrapPreset]:
    """Get recommended preset for a project type.

    Args:
        project_type: ProjectType enum value

    Returns:
        Recommended BootstrapPreset or None if no specific recommendation
    """
    for preset in PRESETS.values():
        if project_type in preset.recommended_for_types:
            return preset

    return None


def format_preset_help() -> str:
    """Format preset information for CLI help text.

    Returns:
        Formatted string describing all available presets
    """
    lines = ["Available bootstrap presets:\n"]

    for preset in list_presets():
        lines.append(f"  {preset.name.value:12} - {preset.get_description()}")

    lines.append("\nExample: autopack bootstrap run --idea \"...\" --preset ecommerce")

    return "\n".join(lines)
