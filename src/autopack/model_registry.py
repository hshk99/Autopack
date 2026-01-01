"""Central model registry helpers.

Purpose:
- Provide a single source of truth for tool-specific model defaults (e.g., tidy)
  and common aliases without having to grep the codebase for hardcoded strings.
- Read from `config/models.yaml` (primary).

This intentionally stays lightweight (no DB required) so scripts can import it.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

import yaml


@dataclass(frozen=True)
class ModelsConfig:
    raw: Dict[str, Any]

    @property
    def model_aliases(self) -> Dict[str, str]:
        return dict(self.raw.get("model_aliases", {}) or {})

    @property
    def tool_models(self) -> Dict[str, str]:
        return dict(self.raw.get("tool_models", {}) or {})


def _repo_root() -> Path:
    # src/autopack/model_registry.py -> src/autopack -> src -> repo root
    return Path(__file__).resolve().parents[2]


def load_models_config(config_path: str = "config/models.yaml") -> ModelsConfig:
    path = Path(config_path)
    if not path.is_absolute():
        path = _repo_root() / path
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        data = {}
    return ModelsConfig(raw=data)


def resolve_model_alias(model: str, *, config_path: str = "config/models.yaml") -> str:
    cfg = load_models_config(config_path=config_path)
    aliases = cfg.model_aliases
    return aliases.get(model, model)


def get_tool_model(
    key: str,
    *,
    default: Optional[str] = None,
    config_path: str = "config/models.yaml",
) -> Optional[str]:
    cfg = load_models_config(config_path=config_path)
    if key in cfg.tool_models:
        return cfg.tool_models[key]
    return default


