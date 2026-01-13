"""
Plan parser: convert markdown task lists into phase specs matching phase_spec_schema.

Heuristics:
- Top-level bullets ("- ") become phases.
- Inline tags override defaults: [complexity:low], [category:tests], [paths:src/,tests/]
- Acceptance criteria: child bullets starting with "- [ ]" or "- " under the task.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

DEFAULT_COMPLEXITY = "medium"
DEFAULT_CATEGORY = "feature"


@dataclass
class ParsedPhase:
    id: str
    description: str
    complexity: str = DEFAULT_COMPLEXITY
    task_category: str = DEFAULT_CATEGORY
    acceptance_criteria: List[str] = field(default_factory=list)
    scope_paths: List[str] = field(default_factory=list)
    read_only_context: List[str] = field(default_factory=list)


def _slug(text: str, max_len: int = 40) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "-", text.lower()).strip("-")
    if not cleaned:
        cleaned = "phase"
    if len(cleaned) <= max_len:
        return cleaned
    digest = hashlib.sha1(text.encode("utf-8", errors="ignore")).hexdigest()[:6]
    return f"{cleaned[: max_len - 7]}-{digest}"


def _parse_tagged_value(text: str, tag: str) -> Optional[str]:
    m = re.search(rf"\[{tag}:([^\]]+)\]", text)
    if m:
        return m.group(1).strip()
    return None


def _extract_paths(text: str, tag: str) -> List[str]:
    val = _parse_tagged_value(text, tag)
    if not val:
        return []
    return [p.strip() for p in val.split(",") if p.strip()]


def parse_markdown_plan(
    path: Path,
    default_complexity: str = DEFAULT_COMPLEXITY,
    default_category: str = DEFAULT_CATEGORY,
) -> List[ParsedPhase]:
    lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    phases: List[ParsedPhase] = []
    i = 0
    while i < len(lines):
        line = lines[i].rstrip()
        if line.startswith("- "):
            title = line[2:].strip()
            comp = _parse_tagged_value(line, "complexity") or default_complexity
            cat = _parse_tagged_value(line, "category") or default_category
            scope_paths = _extract_paths(line, "paths")
            roc = _extract_paths(line, "read_only")
            # Clean title without tags
            title_clean = re.sub(r"\[[^\]]+\]", "", title).strip()
            acc: List[str] = []
            i += 1
            while i < len(lines) and lines[i].startswith("  "):
                sub = lines[i].strip()
                if sub.startswith("- "):
                    text = sub[2:].strip()
                    text = re.sub(r"\[[^\]]+\]", "", text).strip()
                    if text:
                        acc.append(text)
                i += 1
            pid = _slug(title_clean or f"phase-{len(phases) + 1}")
            phases.append(
                ParsedPhase(
                    id=pid,
                    description=title_clean or title,
                    complexity=comp,
                    task_category=cat,
                    acceptance_criteria=acc,
                    scope_paths=scope_paths,
                    read_only_context=roc,
                )
            )
            continue
        i += 1
    return phases


def phases_to_plan(phases: List[ParsedPhase]) -> Dict[str, List[Dict]]:
    plan_phases: List[Dict] = []
    for p in phases:
        phase = {
            "id": p.id,
            "description": p.description,
            "complexity": p.complexity,
            "task_category": p.task_category,
            "acceptance_criteria": p.acceptance_criteria,
        }
        if p.scope_paths or p.read_only_context:
            phase["scope"] = {}
            if p.scope_paths:
                phase["scope"]["paths"] = p.scope_paths
            if p.read_only_context:
                phase["scope"]["read_only_context"] = p.read_only_context
        plan_phases.append(phase)
    return {"phases": plan_phases}
