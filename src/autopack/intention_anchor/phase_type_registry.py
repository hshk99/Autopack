"""Registry mapping phase types to required/optional pivot types.

This module provides phase-type aware validation for intention anchors,
ensuring that phase-specific requirements are met.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

import yaml

logger = logging.getLogger(__name__)


@dataclass
class CustomPivot:
    """Definition of a custom pivot for a specific phase type."""

    name: str
    type: str  # e.g., "float", "string", "list", "int"
    default: Any = None
    description: str = ""


@dataclass
class PhaseTypePivots:
    """Defines pivot types for a phase type."""

    phase_type: str
    required_pivots: List[str] = field(default_factory=list)
    optional_pivots: List[str] = field(default_factory=list)
    custom_pivots: List[CustomPivot] = field(default_factory=list)

    def all_pivot_names(self) -> Set[str]:
        """Return all pivot names (universal + custom)."""
        universal = set(self.required_pivots) | set(self.optional_pivots)
        custom = {p.name for p in self.custom_pivots}
        return universal | custom


class PhaseTypeRegistry:
    """Registry of phase types and their pivot requirements.

    This registry maps phase types (e.g., 'build', 'test', 'tidy') to their
    pivot type requirements, enabling phase-aware validation of intention anchors.
    """

    # Universal pivots that apply to all phase types
    UNIVERSAL_PIVOTS = {
        "north_star",
        "safety_risk",
        "evidence_verification",
        "scope_boundaries",
        "budget_cost",
        "memory_continuity",
        "governance_review",
        "parallelism_isolation",
    }

    def __init__(self):
        """Initialize empty registry."""
        self._registry: Dict[str, PhaseTypePivots] = {}

    def load_from_config(self, config_path: str | Path) -> None:
        """Load phase type configurations from YAML.

        Args:
            config_path: Path to YAML configuration file

        Raises:
            FileNotFoundError: If config file doesn't exist
            yaml.YAMLError: If YAML parsing fails
        """
        config_path = Path(config_path)
        if not config_path.exists():
            logger.warning(f"Phase type config not found: {config_path}")
            return

        with open(config_path) as f:
            config = yaml.safe_load(f)

        if not config:
            logger.warning(f"Empty phase type config: {config_path}")
            return

        for phase_config in config.get("phase_types", []):
            phase_name = phase_config.get("name")
            if not phase_name:
                logger.warning("Phase type config missing 'name' field")
                continue

            # Parse custom pivots
            custom_pivots = []
            for custom_pivot_config in phase_config.get("custom_pivots", []):
                custom_pivots.append(
                    CustomPivot(
                        name=custom_pivot_config.get("name"),
                        type=custom_pivot_config.get("type", "string"),
                        default=custom_pivot_config.get("default"),
                        description=custom_pivot_config.get("description", ""),
                    )
                )

            pivots = PhaseTypePivots(
                phase_type=phase_name,
                required_pivots=phase_config.get("required_pivots", []),
                optional_pivots=phase_config.get("optional_pivots", []),
                custom_pivots=custom_pivots,
            )

            self._registry[phase_name] = pivots
            logger.info(
                f"Registered phase type '{phase_name}' with {len(custom_pivots)} custom pivots"
            )

    def get_pivots_for_phase(self, phase_type: str) -> PhaseTypePivots:
        """Get pivot configuration for a phase type.

        If phase type is not registered, returns default config with
        north_star and scope as required.

        Args:
            phase_type: The phase type name

        Returns:
            PhaseTypePivots configuration for the phase type
        """
        if phase_type in self._registry:
            return self._registry[phase_type]

        # Default: north_star and scope are required, others are optional
        logger.debug(f"Using default pivot configuration for phase type: {phase_type}")
        return PhaseTypePivots(
            phase_type=phase_type,
            required_pivots=["north_star", "scope_boundaries"],
            optional_pivots=list(self.UNIVERSAL_PIVOTS - {"north_star", "scope_boundaries"}),
            custom_pivots=[],
        )

    def validate_anchor_for_phase(self, anchor: Any, phase_type: str) -> Tuple[bool, List[str]]:
        """Validate anchor has required pivots for phase type.

        Args:
            anchor: IntentionAnchorV2 instance to validate
            phase_type: Phase type to validate against

        Returns:
            Tuple of (is_valid, error_messages)
        """
        pivots = self.get_pivots_for_phase(phase_type)
        errors = []

        # Check required universal pivots
        for required_pivot in pivots.required_pivots:
            if required_pivot in self.UNIVERSAL_PIVOTS:
                pivot_attr = self._pivot_name_to_attr(required_pivot)
                if not getattr(anchor.pivot_intentions, pivot_attr, None):
                    errors.append(
                        f"Phase '{phase_type}' requires universal pivot '{required_pivot}'"
                    )

        # Check required custom pivots
        custom_pivots_dict = getattr(anchor, "custom_pivots", {})
        for custom_pivot in pivots.custom_pivots:
            if custom_pivot.name not in custom_pivots_dict:
                if custom_pivot.default is None:
                    errors.append(
                        f"Phase '{phase_type}' requires custom pivot '{custom_pivot.name}'"
                    )

        return len(errors) == 0, errors

    @staticmethod
    def _pivot_name_to_attr(pivot_name: str) -> str:
        """Convert pivot name to IntentionAnchorV2 attribute name.

        Args:
            pivot_name: Pivot name (e.g., 'north_star')

        Returns:
            Attribute name (e.g., 'north_star')
        """
        # Map generic names to actual attribute names
        mapping = {
            "north_star": "north_star",
            "safety_risk": "safety_risk",
            "evidence": "evidence_verification",
            "evidence_verification": "evidence_verification",
            "scope": "scope_boundaries",
            "scope_boundaries": "scope_boundaries",
            "budget": "budget_cost",
            "budget_cost": "budget_cost",
            "memory": "memory_continuity",
            "memory_continuity": "memory_continuity",
            "governance": "governance_review",
            "governance_review": "governance_review",
            "parallelism": "parallelism_isolation",
            "parallelism_isolation": "parallelism_isolation",
        }
        return mapping.get(pivot_name, pivot_name)

    def list_phase_types(self) -> List[str]:
        """List all registered phase types.

        Returns:
            List of phase type names
        """
        return list(self._registry.keys())

    def get_registry(self) -> Dict[str, PhaseTypePivots]:
        """Get the entire registry.

        Returns:
            Dictionary mapping phase types to their pivot configurations
        """
        return dict(self._registry)
