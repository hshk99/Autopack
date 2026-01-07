"""
GitHub Settings Self-Audit (branch protections, required checks, merge constraints)

This is intentionally a *manual* audit tool by default (not CI-blocking), because
GitHub branch protection rules live outside the repo and often require admin rights.

Usage examples:
  # Uses GITHUB_REPO if set, otherwise infers from git remote origin.
  # Uses GITHUB_TOKEN if set (recommended).
  python scripts/ci/github_settings_self_audit.py

  python scripts/ci/github_settings_self_audit.py --repo hshk99/Autopack --branch main

  # Fail with exit code 1 if policy does not match (drift)
  python scripts/ci/github_settings_self_audit.py --check

Outputs:
  - Markdown (default) to stdout
  - JSON via --format json
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from typing import Any, Iterable, Optional

import requests


DEFAULT_RECOMMENDED_REQUIRED_CHECKS = [
    # These correspond to CI job names in .github/workflows/ci.yml.
    # Note: GitHub status check names may include workflow prefixes; matching is suffix-tolerant.
    "lint",
    "docs-sot-integrity",
    "test-core",
]


@dataclass(frozen=True)
class AuditPolicy:
    repo: str
    branch: str
    required_checks: list[str]
    require_prs: bool
    require_conversation_resolution: bool
    require_linear_history: bool
    disallow_force_pushes: bool
    disallow_deletions: bool


def _run(cmd: list[str]) -> str:
    return subprocess.check_output(cmd, stderr=subprocess.STDOUT, text=True).strip()


def infer_repo_from_git_remote() -> Optional[str]:
    """Infer owner/repo from git remote origin URL."""
    try:
        url = _run(["git", "config", "--get", "remote.origin.url"])
    except Exception:
        return None

    # https://github.com/owner/repo.git
    m = re.search(r"github\.com[:/](?P<owner>[^/]+)/(?P<repo>[^/.]+)(?:\.git)?$", url)
    if not m:
        return None
    return f"{m.group('owner')}/{m.group('repo')}"


def github_get_json(
    token: Optional[str], url: str, accept: str = "application/vnd.github+json"
) -> tuple[int, dict[str, Any] | list[Any] | None]:
    headers: dict[str, str] = {"Accept": accept, "User-Agent": "autopack-self-audit"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    r = requests.get(url, headers=headers, timeout=30)
    if r.status_code == 204:
        return r.status_code, None
    try:
        return r.status_code, r.json()
    except Exception:
        return r.status_code, None


def _as_list(x: Any) -> list[Any]:
    if x is None:
        return []
    if isinstance(x, list):
        return x
    return [x]


def _suffix_match_any(
    actual: Iterable[str], expected: Iterable[str]
) -> tuple[list[str], list[str]]:
    """
    Status check names in GitHub can appear as:
      - "lint"
      - "Autopack CI / lint"
    We treat expected checks as satisfied if any actual check equals OR endswith expected,
    OR endswith "/ <expected>".
    """
    actual_list = [a for a in actual if a]
    missing: list[str] = []
    matched: list[str] = []
    for exp in expected:
        ok = False
        for act in actual_list:
            if act == exp or act.endswith(exp) or act.endswith(f"/ {exp}"):
                ok = True
                break
        if ok:
            matched.append(exp)
        else:
            missing.append(exp)
    return matched, missing


def load_policy(repo: str, branch: str, policy_path: Optional[str]) -> AuditPolicy:
    if policy_path:
        data = json.loads(open(policy_path, "r", encoding="utf-8").read())
        return AuditPolicy(
            repo=repo,
            branch=branch,
            required_checks=list(data.get("required_checks") or []),
            require_prs=bool(data.get("require_prs", True)),
            require_conversation_resolution=bool(data.get("require_conversation_resolution", True)),
            require_linear_history=bool(data.get("require_linear_history", False)),
            disallow_force_pushes=bool(data.get("disallow_force_pushes", True)),
            disallow_deletions=bool(data.get("disallow_deletions", True)),
        )

    return AuditPolicy(
        repo=repo,
        branch=branch,
        required_checks=list(DEFAULT_RECOMMENDED_REQUIRED_CHECKS),
        require_prs=True,
        require_conversation_resolution=True,
        require_linear_history=False,
        disallow_force_pushes=True,
        disallow_deletions=True,
    )


def audit(policy: AuditPolicy, token: Optional[str]) -> dict[str, Any]:
    owner, repo = policy.repo.split("/", 1)

    base = f"https://api.github.com/repos/{owner}/{repo}"
    repo_status, repo_json = github_get_json(token, base)
    if repo_status != 200:
        raise RuntimeError(f"Failed to read repo metadata: HTTP {repo_status}")

    prot_url = f"{base}/branches/{policy.branch}/protection"
    prot_status, prot_json = github_get_json(token, prot_url)

    result: dict[str, Any] = {
        "repo": policy.repo,
        "branch": policy.branch,
        "repo_visibility": (
            (repo_json or {}).get("visibility") if isinstance(repo_json, dict) else None
        ),
        "default_branch": (
            (repo_json or {}).get("default_branch") if isinstance(repo_json, dict) else None
        ),
        "protection_status_code": prot_status,
        "findings": [],
        "raw": {"repo": repo_json, "branch_protection": prot_json},
        "policy": {
            "required_checks": policy.required_checks,
            "require_prs": policy.require_prs,
            "require_conversation_resolution": policy.require_conversation_resolution,
            "require_linear_history": policy.require_linear_history,
            "disallow_force_pushes": policy.disallow_force_pushes,
            "disallow_deletions": policy.disallow_deletions,
        },
    }

    if prot_status == 404:
        result["findings"].append(
            {
                "level": "fail",
                "area": "branch_protection",
                "message": "Branch protection is not enabled (API returned 404).",
            }
        )
        return result
    if prot_status == 401 and not token:
        result["findings"].append(
            {
                "level": "fail",
                "area": "branch_protection",
                "message": "Unauthorized (HTTP 401). Provide a token via GITHUB_TOKEN (or GH_TOKEN) to read branch protection settings.",
            }
        )
        return result
    if prot_status != 200 or not isinstance(prot_json, dict):
        result["findings"].append(
            {
                "level": "fail",
                "area": "branch_protection",
                "message": f"Unable to read branch protection (HTTP {prot_status}).",
            }
        )
        return result

    # Required status checks
    rsc = prot_json.get("required_status_checks") or {}
    contexts = _as_list(rsc.get("contexts"))
    # Newer API: "checks" can contain dicts like {"context": "...", ...}
    checks = [c.get("context") for c in _as_list(rsc.get("checks")) if isinstance(c, dict)]
    actual_checks = [c for c in (list(contexts) + list(checks)) if isinstance(c, str)]
    _, missing = _suffix_match_any(actual_checks, policy.required_checks)
    if policy.required_checks:
        if missing:
            result["findings"].append(
                {
                    "level": "fail",
                    "area": "required_status_checks",
                    "message": f"Missing required checks: {missing}",
                    "actual": sorted(set(actual_checks)),
                }
            )
        else:
            result["findings"].append(
                {
                    "level": "pass",
                    "area": "required_status_checks",
                    "message": "Required status checks include expected checks.",
                    "actual": sorted(set(actual_checks)),
                }
            )

    # PR requirements
    prr = prot_json.get("required_pull_request_reviews")
    if policy.require_prs:
        if not prr:
            result["findings"].append(
                {
                    "level": "fail",
                    "area": "pull_request_reviews",
                    "message": "PR review requirements not enabled.",
                }
            )
        else:
            result["findings"].append(
                {
                    "level": "pass",
                    "area": "pull_request_reviews",
                    "message": "PR review requirements enabled.",
                    "details": {
                        "required_approving_review_count": prr.get(
                            "required_approving_review_count"
                        ),
                        "dismiss_stale_reviews": prr.get("dismiss_stale_reviews"),
                        "require_code_owner_reviews": prr.get("require_code_owner_reviews"),
                    },
                }
            )

    # Conversation resolution
    rcr = prot_json.get("required_conversation_resolution") or {}
    enabled_rcr = bool(rcr.get("enabled"))
    if policy.require_conversation_resolution and not enabled_rcr:
        result["findings"].append(
            {
                "level": "fail",
                "area": "conversation_resolution",
                "message": "Require conversation resolution is not enabled.",
            }
        )
    else:
        result["findings"].append(
            {
                "level": "pass",
                "area": "conversation_resolution",
                "message": f"Require conversation resolution: {enabled_rcr}",
            }
        )

    # Linear history
    rlh = prot_json.get("required_linear_history") or {}
    enabled_rlh = bool(rlh.get("enabled"))
    if policy.require_linear_history and not enabled_rlh:
        result["findings"].append(
            {
                "level": "fail",
                "area": "linear_history",
                "message": "Require linear history is not enabled.",
            }
        )
    else:
        result["findings"].append(
            {
                "level": "pass",
                "area": "linear_history",
                "message": f"Require linear history: {enabled_rlh}",
            }
        )

    # Force push / deletions
    afp = prot_json.get("allow_force_pushes") or {}
    ad = prot_json.get("allow_deletions") or {}
    allow_force_pushes = bool(afp.get("enabled"))
    allow_deletions = bool(ad.get("enabled"))

    if policy.disallow_force_pushes and allow_force_pushes:
        result["findings"].append(
            {
                "level": "fail",
                "area": "force_pushes",
                "message": "Force pushes are allowed on protected branch.",
            }
        )
    else:
        result["findings"].append(
            {
                "level": "pass",
                "area": "force_pushes",
                "message": f"Allow force pushes: {allow_force_pushes}",
            }
        )

    if policy.disallow_deletions and allow_deletions:
        result["findings"].append(
            {
                "level": "fail",
                "area": "branch_deletions",
                "message": "Branch deletions are allowed on protected branch.",
            }
        )
    else:
        result["findings"].append(
            {
                "level": "pass",
                "area": "branch_deletions",
                "message": f"Allow deletions: {allow_deletions}",
            }
        )

    return result


def format_markdown(report: dict[str, Any]) -> str:
    findings = report.get("findings") or []
    fails = [f for f in findings if f.get("level") == "fail"]
    status = "FAIL" if fails else "PASS"

    lines: list[str] = []
    lines.append(f"# GitHub Settings Self-Audit ({status})")
    lines.append("")
    lines.append(f"- Repo: `{report.get('repo')}`")
    lines.append(f"- Branch: `{report.get('branch')}`")
    lines.append(f"- Default branch (GitHub): `{report.get('default_branch')}`")
    lines.append(f"- Branch protection API status: `{report.get('protection_status_code')}`")
    lines.append("")

    lines.append("## Findings")
    if not findings:
        lines.append("- (none)")
        return "\n".join(lines) + "\n"

    for f in findings:
        level = f.get("level", "info").upper()
        area = f.get("area", "unknown")
        msg = f.get("message", "")
        lines.append(f"- **{level}** `{area}`: {msg}")
        details = f.get("details")
        if isinstance(details, dict) and details:
            for k, v in details.items():
                lines.append(f"  - **{k}**: `{v}`")
        actual = f.get("actual")
        if isinstance(actual, list) and actual:
            lines.append(f"  - **actual**: {', '.join(f'`{a}`' for a in actual)}")

    lines.append("")
    return "\n".join(lines)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--repo", help="owner/repo (defaults to $GITHUB_REPO or inferred from git remote)"
    )
    p.add_argument("--branch", default="main", help="Branch to audit (default: main)")
    p.add_argument(
        "--policy",
        help="Optional JSON policy file to override defaults (required_checks, require_prs, etc.)",
    )
    p.add_argument("--format", choices=["md", "json"], default="md")
    p.add_argument("--out", help="Write report to a file instead of stdout")
    p.add_argument(
        "--check",
        action="store_true",
        help="Exit with code 1 if any FAIL findings exist (drift).",
    )
    args = p.parse_args()

    repo = args.repo or os.getenv("GITHUB_REPO") or infer_repo_from_git_remote()
    if not repo:
        print(
            "ERROR: Unable to determine repo slug. Provide --repo owner/repo or set GITHUB_REPO.",
            file=sys.stderr,
        )
        return 2

    token = os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN")
    policy = load_policy(repo=repo, branch=args.branch, policy_path=args.policy)

    try:
        report = audit(policy=policy, token=token)
    except Exception as e:
        print(f"ERROR: audit failed: {e}", file=sys.stderr)
        return 2

    output: str
    if args.format == "json":
        output = json.dumps(report, indent=2, sort_keys=True) + "\n"
    else:
        output = format_markdown(report)

    if args.out:
        with open(args.out, "w", encoding="utf-8", newline="\n") as f:
            f.write(output)
    else:
        print(output, end="")

    if args.check:
        findings = report.get("findings") or []
        if any(f.get("level") == "fail" for f in findings):
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
