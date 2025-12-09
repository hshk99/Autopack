"""
Plan utilities: merging plan JSONs while respecting phase ids.
"""

from __future__ import annotations

from typing import Dict, List


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

