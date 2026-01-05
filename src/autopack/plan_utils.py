"""
Plan utilities: merging plan JSONs while respecting phase ids + intention_refs validation.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


def merge_plans(base: Dict, new: Dict, allow_update: bool = False) -> Dict:
    merged = {"phases": []}
    base_phases = {p["id"]: p for p in base.get("phases", [])}
    for p in base.get("phases", []):
        merged["phases"].append(p)

    for p in new.get("phases", []):
        pid = p.get("id")
        if pid in base_phases:
            if allow_update:
                # Replace existing phase with new one
                merged["phases"] = [p if ph["id"] == pid else ph for ph in merged["phases"]]
            else:
                # Skip duplicate ids if not allowed to update
                continue
        else:
            merged["phases"].append(p)
    return merged


def validate_intention_refs(
    phase_id: str,
    intention_refs: Optional[Dict],
    anchor_data: Optional[Dict],
    *,
    strict_mode: bool = False,
) -> List[str]:
    """
    Validate that intention_refs indices are in-range of the anchor's lists.

    Intention behind it: catch broken references early (warn-first mode in M1,
    then block mode in later milestones).

    Args:
        phase_id: Phase identifier for logging
        intention_refs: The intention_refs dict from the phase (or None)
        anchor_data: The IntentionAnchor dict (or None if anchor doesn't exist)
        strict_mode: If True, missing refs/out-of-range → raise; if False, warn only

    Returns:
        List of warning/error messages (empty if valid)

    Raises:
        ValueError: If strict_mode=True and validation fails
    """
    warnings = []

    # If no refs provided, that's allowed in warn-first mode
    if intention_refs is None:
        if anchor_data is not None and not strict_mode:
            warnings.append(
                f"Phase {phase_id}: no intention_refs provided (warn-first mode: allowed)"
            )
        return warnings

    # If refs provided but no anchor exists, warn
    if anchor_data is None:
        msg = f"Phase {phase_id}: has intention_refs but no anchor found"
        warnings.append(msg)
        if strict_mode:
            raise ValueError(msg)
        return warnings

    # Validate indices are in-range
    def check_indices(field_name: str, indices: List[int], anchor_list: List) -> None:
        for idx in indices:
            if idx < 0 or idx >= len(anchor_list):
                msg = (
                    f"Phase {phase_id}: intention_refs.{field_name}[{idx}] "
                    f"out of range (anchor has {len(anchor_list)} items)"
                )
                warnings.append(msg)
                if strict_mode:
                    raise ValueError(msg)

    # Check success_criteria refs
    if "success_criteria" in intention_refs:
        anchor_criteria = anchor_data.get("success_criteria", [])
        check_indices("success_criteria", intention_refs["success_criteria"], anchor_criteria)

    # Check constraints.must refs
    if "constraints_must" in intention_refs:
        anchor_must = anchor_data.get("constraints", {}).get("must", [])
        check_indices("constraints_must", intention_refs["constraints_must"], anchor_must)

    # Check constraints.must_not refs
    if "constraints_must_not" in intention_refs:
        anchor_must_not = anchor_data.get("constraints", {}).get("must_not", [])
        check_indices(
            "constraints_must_not", intention_refs["constraints_must_not"], anchor_must_not
        )

    # Check constraints.preferences refs
    if "constraints_preferences" in intention_refs:
        anchor_prefs = anchor_data.get("constraints", {}).get("preferences", [])
        check_indices(
            "constraints_preferences", intention_refs["constraints_preferences"], anchor_prefs
        )

    # Log warnings if any
    for warning in warnings:
        logger.warning(warning)

    return warnings
