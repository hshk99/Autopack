"""
Research System Preflight Analyzer

Purpose
-------
Provide a lightweight, operator-friendly preflight that catches deterministic
convergence blockers *before* running chunks, especially:
- Deliverables path/root inconsistencies across chunk YAMLs
- Deliverables that would be blocked by governed apply (protected-path policy)
- Missing Python dependencies referenced by chunk YAMLs
- Missing API credential environment variables for external gatherers

Usage (PowerShell)
-----------------
python -m autopack.research.preflight_analyzer ^
  --requirements-dir .autonomous_runs/file-organizer-app-v1/archive/research/active/requirements
"""

from __future__ import annotations

import argparse
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple


def _load_yaml(path: Path) -> Dict[str, Any]:
    try:
        import yaml  # type: ignore
    except Exception as e:  # pragma: no cover
        raise RuntimeError(
            "PyYAML is required for preflight. Install it (e.g. `pip install PyYAML`)."
        ) from e

    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Expected mapping YAML at {path}, got {type(data).__name__}")
    return data


def _iter_yaml_files(requirements_dir: Path) -> List[Path]:
    return sorted([p for p in requirements_dir.glob("chunk*.yaml") if p.is_file()])


def _normalize_req_name(raw: str) -> str:
    """
    Very small normalizer that extracts the package name from a requirements.txt line.
    Examples:
      "uvicorn[standard]>=0.24.0" -> "uvicorn"
      "python-magic-bin>=0.4.14; sys_platform == 'win32'" -> "python-magic-bin"
    """
    s = raw.strip()
    if not s or s.startswith("#") or s.startswith("-r"):
        return ""
    # strip markers
    s = s.split(";", 1)[0].strip()
    # strip version spec
    s = re.split(r"[<>=!~]=?", s, maxsplit=1)[0].strip()
    # strip extras
    s = s.split("[", 1)[0].strip()
    return s


def _read_requirements_txt(req_path: Path) -> Set[str]:
    if not req_path.exists():
        return set()
    pkgs: Set[str] = set()
    for line in req_path.read_text(encoding="utf-8").splitlines():
        name = _normalize_req_name(line)
        if name:
            pkgs.add(name.lower())
    return pkgs


def _read_pyproject_deps(pyproject_path: Path) -> Set[str]:
    if not pyproject_path.exists():
        return set()
    try:
        import tomllib  # py311+
    except Exception:  # pragma: no cover
        return set()
    data = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    deps = data.get("project", {}).get("dependencies", []) or []
    pkgs: Set[str] = set()
    if isinstance(deps, list):
        for s in deps:
            if not isinstance(s, str):
                continue
            name = _normalize_req_name(s)
            if name:
                pkgs.add(name.lower())
    return pkgs


def _read_pyproject_optional_dev_deps(pyproject_path: Path) -> Set[str]:
    if not pyproject_path.exists():
        return set()
    try:
        import tomllib  # py311+
    except Exception:  # pragma: no cover
        return set()
    data = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    deps = data.get("project", {}).get("optional-dependencies", {}).get("dev", []) or []
    pkgs: Set[str] = set()
    if isinstance(deps, list):
        for s in deps:
            if not isinstance(s, str):
                continue
            name = _normalize_req_name(s)
            if name:
                pkgs.add(name.lower())
    return pkgs


def _extract_deliverables(y: Dict[str, Any]) -> List[str]:
    d = y.get("deliverables") or {}
    if not isinstance(d, dict):
        return []
    code = d.get("code") or []
    if not isinstance(code, list):
        return []
    return [str(x) for x in code]


def _extract_libraries(y: Dict[str, Any]) -> List[str]:
    deps = y.get("dependencies") or {}
    if not isinstance(deps, dict):
        return []
    libs = deps.get("libraries") or []
    if not isinstance(libs, list):
        return []
    out: List[str] = []
    for item in libs:
        if not isinstance(item, str):
            continue
        # "beautifulsoup4 (HTML parsing)" -> "beautifulsoup4"
        out.append(item.split("(", 1)[0].strip())
    return [x for x in out if x]


def _extract_external_apis(y: Dict[str, Any]) -> List[str]:
    deps = y.get("dependencies") or {}
    if not isinstance(deps, dict):
        return []
    apis = deps.get("external_apis") or []
    if not isinstance(apis, list):
        return []
    return [str(x) for x in apis if isinstance(x, str)]


@dataclass(frozen=True)
class PreflightIssue:
    severity: str  # "ERROR" | "WARN" | "INFO"
    message: str
    file: Optional[str] = None


def _governed_apply_check(paths: Sequence[str]) -> List[PreflightIssue]:
    """
    Determine whether deliverable paths would be blocked by governed apply in project runs.
    """
    issues: List[PreflightIssue] = []
    try:
        from autopack.governed_apply import GovernedApplyPath
    except Exception:
        # If import fails, skip (this tool is best-effort and should not crash a run)
        return [
            PreflightIssue(
                severity="WARN",
                message="Could not import autopack.governed_apply; skipping protected-path feasibility checks.",
            )
        ]

    g = GovernedApplyPath(workspace=Path("."))  # uses default protected/allowed paths
    protected = tuple(p.replace("\\", "/") for p in g.protected_paths)
    allowed = tuple(p.replace("\\", "/") for p in g.allowed_paths)

    for p in paths:
        norm = p.replace("\\", "/")
        in_protected = any(norm.startswith(pr) for pr in protected)
        if not in_protected:
            continue
        is_allowed = any(norm.startswith(al) for al in allowed)
        if not is_allowed:
            issues.append(
                PreflightIssue(
                    severity="ERROR",
                    message=f"Deliverable '{norm}' is under a protected path and is NOT allowlisted; governed apply would reject it in project runs.",
                )
            )
    return issues


def _path_root_check(all_deliverables: Sequence[Tuple[str, str]]) -> List[PreflightIssue]:
    """
    Ensure deliverables don't mix incompatible roots (src/research vs src/autopack/research).
    """
    issues: List[PreflightIssue] = []
    roots: Set[str] = set()
    for file_path, chunk_file in all_deliverables:
        p = file_path.replace("\\", "/")
        if p.startswith("src/research/"):
            roots.add("src/research/")
        if p.startswith("src/autopack/research/"):
            roots.add("src/autopack/research/")

        if p.startswith("src/research/"):
            issues.append(
                PreflightIssue(
                    severity="ERROR",
                    file=chunk_file,
                    message=f"Deliverable root uses deprecated 'src/research/*': {p} (expected 'src/autopack/research/*')",
                )
            )

    if len(roots) > 1:
        issues.append(
            PreflightIssue(
                severity="WARN",
                message=f"Multiple deliverable roots detected across chunks: {sorted(roots)}",
            )
        )
    return issues


def _dependency_check(
    required_libraries: Sequence[Tuple[str, str]],
    requirements_pkgs: Set[str],
    pyproject_pkgs: Set[str],
) -> List[PreflightIssue]:
    issues: List[PreflightIssue] = []
    for lib, chunk_file in required_libraries:
        pkg = lib.lower()
        # pragmatic aliases / normalization
        alias = {
            "pyyaml": "pyyaml",
            "beautifulsoup4": "beautifulsoup4",
            "bs4": "beautifulsoup4",
        }.get(pkg, pkg)

        # Windows note: reppy is often problematic to build; allow stdlib fallback.
        if alias == "reppy" and os.name == "nt":
            issues.append(
                PreflightIssue(
                    severity="INFO",
                    file=chunk_file,
                    message="Chunk lists 'reppy' for robots.txt parsing; on Windows prefer stdlib 'urllib.robotparser' if reppy is unavailable.",
                )
            )
            continue

        if alias not in requirements_pkgs and alias not in pyproject_pkgs:
            issues.append(
                PreflightIssue(
                    severity="WARN",
                    file=chunk_file,
                    message=f"Dependency '{lib}' is referenced in chunk YAML but not found in requirements/pyproject dependencies.",
                )
            )
    return issues


def _api_env_check(external_apis: Sequence[Tuple[str, str]]) -> List[PreflightIssue]:
    issues: List[PreflightIssue] = []
    # Minimal env var conventions; repo may implement its own config later.
    api_env_expectations = {
        "GitHub API": ["GITHUB_TOKEN"],
        "Reddit API": ["REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET", "REDDIT_USER_AGENT"],
    }

    for api, chunk_file in external_apis:
        # normalize: "GitHub API (with authentication)" -> "GitHub API"
        key = api.split("(", 1)[0].strip()
        needed = api_env_expectations.get(key)
        if not needed:
            continue
        missing = [k for k in needed if not os.environ.get(k)]
        if missing:
            issues.append(
                PreflightIssue(
                    severity="INFO",
                    file=chunk_file,
                    message=f"{key} credentials not set in environment: missing {missing}",
                )
            )
    return issues


def run_preflight(requirements_dir: Path) -> Tuple[int, List[PreflightIssue]]:
    issues: List[PreflightIssue] = []

    yaml_files = _iter_yaml_files(requirements_dir)
    if not yaml_files:
        return 2, [PreflightIssue("ERROR", f"No chunk YAMLs found under {requirements_dir}")]

    all_deliverables: List[Tuple[str, str]] = []
    all_libs: List[Tuple[str, str]] = []
    all_apis: List[Tuple[str, str]] = []

    for f in yaml_files:
        y = _load_yaml(f)
        for d in _extract_deliverables(y):
            all_deliverables.append((d, str(f)))
        for lib in _extract_libraries(y):
            all_libs.append((lib, str(f)))
        for api in _extract_external_apis(y):
            all_apis.append((api, str(f)))

    # Checks
    issues.extend(_path_root_check(all_deliverables))
    issues.extend(_governed_apply_check([p for p, _ in all_deliverables]))

    repo_root = Path(__file__).parent.parent.parent.parent
    requirements_pkgs = _read_requirements_txt(repo_root / "requirements.txt")
    requirements_dev_pkgs = _read_requirements_txt(repo_root / "requirements-dev.txt")
    pyproject_pkgs = _read_pyproject_deps(repo_root / "pyproject.toml")
    pyproject_dev_pkgs = _read_pyproject_optional_dev_deps(repo_root / "pyproject.toml")

    declared_pkgs = set().union(
        requirements_pkgs, requirements_dev_pkgs, pyproject_pkgs, pyproject_dev_pkgs
    )
    issues.extend(_dependency_check(all_libs, declared_pkgs, declared_pkgs))
    issues.extend(_api_env_check(all_apis))

    errors = [i for i in issues if i.severity == "ERROR"]
    exit_code = 1 if errors else 0
    return exit_code, issues


def _print_issues(issues: Sequence[PreflightIssue]) -> None:
    def key(i: PreflightIssue) -> Tuple[int, str]:
        order = {"ERROR": 0, "WARN": 1, "INFO": 2}
        return (order.get(i.severity, 99), i.file or "")

    for i in sorted(issues, key=key):
        loc = f"{i.file}: " if i.file else ""
        print(f"[{i.severity}] {loc}{i.message}")


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Research System Preflight Analyzer")
    parser.add_argument(
        "--requirements-dir",
        type=str,
        required=True,
        help="Directory containing chunk*.yaml requirement files",
    )
    args = parser.parse_args(argv)
    requirements_dir = Path(args.requirements_dir)
    code, issues = run_preflight(requirements_dir=requirements_dir)
    _print_issues(issues)
    if code == 0:
        print("[OK] Preflight passed (no ERRORs).")
    else:
        print(f"[FAIL] Preflight found blocking issues (exit_code={code}).")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
