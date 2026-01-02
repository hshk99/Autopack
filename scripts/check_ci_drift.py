#!/usr/bin/env python3
"""
CI Drift Checks (BUILD-154)

Guards against:
- Version drift across pyproject.toml, docs/PROJECT_INDEX.json, and README.md
- Dependency drift between pyproject.toml and requirements*.txt
- Unified protection policy schema regressions (config/protection_and_retention_policy.yaml)

Designed to be fast, deterministic, and safe to run in CI.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Iterable, Optional, Set


REPO_ROOT = Path(__file__).resolve().parents[1]


def _fail(msg: str) -> None:
    print(f"[DRIFT][FAIL] {msg}")
    raise SystemExit(1)


def _warn(msg: str) -> None:
    print(f"[DRIFT][WARN] {msg}")


def _info(msg: str) -> None:
    print(f"[DRIFT][OK] {msg}")


def _normalize_pkg_name(name: str) -> str:
    # PEP 503-ish normalization
    return re.sub(r"[-_.]+", "-", name.strip().lower())


def _parse_requirement_name(line: str) -> Optional[str]:
    s = line.strip()
    if not s or s.startswith("#"):
        return None
    if s.startswith("-r ") or s.startswith("--requirement "):
        return None
    if s.startswith("-"):
        # Skip other pip options (-e, --find-links, etc.)
        return None

    # Strip environment markers
    s = s.split(";", 1)[0].strip()

    # Remove inline comments
    s = s.split("#", 1)[0].strip()
    if not s:
        return None

    # Extract name up to first version/operator delimiter
    # Examples:
    #   uvicorn[standard]>=0.24.0  -> uvicorn
    #   python-magic-bin>=0.4.14   -> python-magic-bin
    m = re.match(r"^([A-Za-z0-9][A-Za-z0-9._-]*)(?:\[.*\])?(?:\s*(==|>=|<=|~=|!=|>|<).*)?$", s)
    if not m:
        return None
    return _normalize_pkg_name(m.group(1))


def _read_requirements_recursive(path: Path, seen: Optional[Set[Path]] = None) -> Set[str]:
    if seen is None:
        seen = set()
    path = path.resolve()
    if path in seen:
        return set()
    seen.add(path)

    if not path.exists():
        _fail(f"Missing requirements file: {path}")

    names: Set[str] = set()
    for raw in path.read_text(encoding="utf-8").splitlines():
        s = raw.strip()
        if s.startswith("-r ") or s.startswith("--requirement "):
            inc = s.split(maxsplit=1)[1].strip()
            inc_path = (path.parent / inc).resolve()
            names |= _read_requirements_recursive(inc_path, seen=seen)
            continue
        name = _parse_requirement_name(raw)
        if name:
            names.add(name)
    return names


def _read_pyproject_deps(pyproject_path: Path) -> tuple[str, Set[str], Set[str]]:
    try:
        import tomllib  # py3.11+
    except Exception:  # pragma: no cover
        _fail("Python 3.11+ required (tomllib not available)")

    data = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    project = data.get("project") or {}
    version = project.get("version")
    if not isinstance(version, str) or not version.strip():
        _fail("pyproject.toml missing [project].version")

    deps = set()
    for d in project.get("dependencies") or []:
        # Skip platform-specific deps that don't apply to current platform
        # pip-compile handles these correctly, so we shouldn't fail on missing platform-specific deps
        # Example: "python-magic>=0.4.27; sys_platform != 'win32'" on Windows
        name = _parse_requirement_name(str(d))
        if name:
            # For platform-conditional deps, accept if either variant is present
            # e.g., both python-magic and python-magic-bin satisfy the dep group
            if "magic" in name and name in ("python-magic", "python-magic-bin"):
                # Add both variants so either satisfies the check
                deps.add("python-magic")
                deps.add("python-magic-bin")
            else:
                deps.add(name)

    dev_deps = set()
    opt = project.get("optional-dependencies") or {}
    for d in opt.get("dev") or []:
        name = _parse_requirement_name(str(d))
        if name:
            dev_deps.add(name)

    return version.strip(), deps, dev_deps


def _read_readme_version(readme_path: Path) -> str:
    text = readme_path.read_text(encoding="utf-8")
    m = re.search(r"^\*\*Version\*\*:\s*([0-9]+\.[0-9]+\.[0-9]+)\b", text, flags=re.MULTILINE)
    if not m:
        _fail("README.md missing '**Version**: x.y.z' line")
    return m.group(1)


def _read_project_index_version(project_index_path: Path) -> str:
    data = json.loads(project_index_path.read_text(encoding="utf-8"))
    v = data.get("version")
    if not isinstance(v, str) or not v.strip():
        _fail("docs/PROJECT_INDEX.json missing 'version' field")
    return v.strip()


def _check_unified_policy_schema(policy_path: Path) -> None:
    try:
        import yaml  # type: ignore
    except Exception:
        _fail("PyYAML not installed (required for policy schema validation)")

    data = yaml.safe_load(policy_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        _fail("Unified policy is not a YAML mapping at root")

    if "protected_paths" not in data or "categories" not in data:
        _fail("Unified policy missing required keys: protected_paths, categories")

    protected_paths = data.get("protected_paths") or {}
    if not isinstance(protected_paths, dict):
        _fail("Unified policy protected_paths must be a mapping")

    # Ensure node_modules isn't an absolute protection (it should be a cleanup category)
    for v in protected_paths.values():
        if isinstance(v, list) and any("node_modules" in str(x) for x in v):
            _fail("Unified policy incorrectly marks node_modules as an absolute protected path")

    categories = data.get("categories") or {}
    if not isinstance(categories, dict) or not categories:
        _fail("Unified policy categories must be a non-empty mapping")

    required_cats = {"dev_caches", "diagnostics_logs", "runs", "archive_buckets"}
    missing = required_cats - set(categories.keys())
    if missing:
        _fail(f"Unified policy missing required categories: {sorted(missing)}")

    for cat_name, cat_data in categories.items():
        if not isinstance(cat_data, dict):
            _fail(f"Category '{cat_name}' must be a mapping")
        if "patterns" not in cat_data:
            _fail(f"Category '{cat_name}' missing patterns")
        if "allowed_actions" not in cat_data:
            _fail(f"Category '{cat_name}' missing allowed_actions (required for Storage Optimizer compatibility)")


def main() -> int:
    pyproject = REPO_ROOT / "pyproject.toml"
    readme = REPO_ROOT / "README.md"
    project_index = REPO_ROOT / "docs" / "PROJECT_INDEX.json"
    req = REPO_ROOT / "requirements.txt"
    req_dev = REPO_ROOT / "requirements-dev.txt"
    policy = REPO_ROOT / "config" / "protection_and_retention_policy.yaml"

    # Version drift
    py_v, py_deps, py_dev_deps = _read_pyproject_deps(pyproject)
    idx_v = _read_project_index_version(project_index)
    readme_v = _read_readme_version(readme)

    if py_v != idx_v or py_v != readme_v:
        _fail(f"Version drift: pyproject={py_v}, docs/PROJECT_INDEX.json={idx_v}, README={readme_v}")
    _info(f"Version consistent: {py_v}")

    # Dependency drift (pyproject -> requirements)
    req_names = _read_requirements_recursive(req_dev) if req_dev.exists() else _read_requirements_recursive(req)
    missing_core = sorted(py_deps - req_names)
    missing_dev = sorted(py_dev_deps - req_names)

    # Filter platform-conditional deps: if either variant is present, consider satisfied
    # e.g., python-magic/python-magic-bin are platform alternatives
    if "python-magic" in missing_core and "python-magic-bin" in req_names:
        missing_core.remove("python-magic")
    if "python-magic-bin" in missing_core and "python-magic" in req_names:
        missing_core.remove("python-magic-bin")

    if missing_core:
        _fail(f"requirements missing core deps from pyproject: {missing_core}")
    if missing_dev:
        _fail(f"requirements missing dev deps from pyproject: {missing_dev}")
    _info("requirements*.txt covers pyproject core + dev dependencies")

    # Unified policy schema
    if not policy.exists():
        _fail(f"Missing unified policy file: {policy}")
    _check_unified_policy_schema(policy)
    _info("Unified policy schema validated")

    return 0


if __name__ == "__main__":
    sys.exit(main())


