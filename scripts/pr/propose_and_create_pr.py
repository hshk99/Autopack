"""Post-run PR creation script with Telegram approval.

Usage:
    AUTOPACK_ENABLE_PR_APPROVAL=true python scripts/pr/propose_and_create_pr.py \\
        --run-id build123-feature \\
        --branch feat/my-feature \\
        --title "Add new feature" \\
        --base-branch main \\
        --api-url http://localhost:8000

Per IMPLEMENTATION_PLAN_PR_APPROVAL_PIPELINE.md:
- Requires AUTOPACK_ENABLE_PR_APPROVAL=true
- Writes run-local proposal artifacts
- Requests approval via POST /approval/request
- Polls /approval/status/{approval_id}
- On approval: runs gh pr create (after checking for duplicates)
- Writes <run_base>/pr/result.json
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import requests

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from autopack.pr.proposal_artifacts import PrProposal, PrProposalStorage
from autopack.pr.git_inspection import (
    get_diff_stats,
    get_current_branch,
    get_commit_sha,
)
from autopack.file_layout import RunFileLayout


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Create PR with approval workflow")
    parser.add_argument("--run-id", required=True, help="Run identifier")
    parser.add_argument("--branch", required=True, help="Branch name for PR")
    parser.add_argument("--title", required=True, help="PR title")
    parser.add_argument("--base-branch", default="main", help="Base branch (default: main)")
    parser.add_argument("--project-id", help="Project identifier (optional)")
    parser.add_argument("--api-url", default="http://localhost:8000", help="API URL")
    parser.add_argument("--summary", default="", help="PR summary (markdown)")
    parser.add_argument("--risk-score", type=int, default=0, help="Risk score 0-100")
    parser.add_argument("--timeout", type=int, default=900, help="Approval timeout (seconds)")

    args = parser.parse_args()

    # Guardrail: Require opt-in
    if os.getenv("AUTOPACK_ENABLE_PR_APPROVAL", "false").lower() != "true":
        print("❌ PR approval pipeline disabled (AUTOPACK_ENABLE_PR_APPROVAL != true).")
        print("   To enable: export AUTOPACK_ENABLE_PR_APPROVAL=true")
        return 2

    print(f"🔀 PR Approval Pipeline for run_id={args.run_id}")

    # Step 1: Compute diff stats
    print("\n[1/5] Computing diff stats...")
    try:
        diff_stats = get_diff_stats(args.base_branch)
        print(f"  ✓ {len(diff_stats.files)} files changed (+{diff_stats.added}/-{diff_stats.removed})")
    except subprocess.CalledProcessError as e:
        print(f"  ❌ Git diff failed: {e}")
        return 1

    # Step 2: Create proposal artifact
    print("\n[2/5] Creating PR proposal artifact...")
    current_branch = get_current_branch()
    commit_sha = get_commit_sha()

    proposal = PrProposal(
        run_id=args.run_id,
        phase_set=[],  # Caller can populate via --phase-set if needed (future enhancement)
        branch=args.branch,
        base_branch=args.base_branch,
        title=args.title,
        summary_md=args.summary or f"Automated changes from run {args.run_id}",
        files_changed=diff_stats.files,
        loc_added=diff_stats.added,
        loc_removed=diff_stats.removed,
        risk_score=args.risk_score,
        checklist=["CI must be green", "Review diff before merging"],
        metadata={
            "commit_sha": commit_sha,
            "current_branch": current_branch,
        },
    )

    json_path, md_path = PrProposalStorage.save(proposal, project_id=args.project_id)
    print("  ✓ Proposal saved:")
    print(f"    - {json_path}")
    print(f"    - {md_path}")

    # Step 3: Request approval via API
    print("\n[3/5] Requesting approval via Telegram...")
    try:
        approval_id = request_pr_approval(
            api_url=args.api_url,
            run_id=args.run_id,
            proposal=proposal,
            timeout_seconds=args.timeout,
        )
        print(f"  ✓ Approval request created: approval_id={approval_id}")
    except Exception as e:
        print(f"  ❌ Failed to request approval: {e}")
        _write_result(args.run_id, args.project_id, status="error", error=str(e))
        return 1

    # Step 4: Poll for approval
    print(f"\n[4/5] Waiting for approval (timeout: {args.timeout}s)...")
    try:
        status = wait_for_approval(
            api_url=args.api_url,
            approval_id=approval_id,
            timeout_seconds=args.timeout,
            poll_interval=10,
        )
        print(f"  ✓ Approval status: {status}")
    except Exception as e:
        print(f"  ❌ Error polling approval: {e}")
        _write_result(args.run_id, args.project_id, status="error", error=str(e))
        return 1

    if status != "approved":
        print(f"\n❌ PR creation {status}. Exiting.")
        _write_result(args.run_id, args.project_id, status=status)
        return 1

    # Step 5: Create PR via gh CLI
    print("\n[5/5] Creating PR via gh CLI...")
    try:
        pr_url = create_pr_via_gh(
            branch=args.branch,
            base_branch=args.base_branch,
            title=args.title,
            body_file=md_path,
        )
        print(f"  ✓ PR created: {pr_url}")
        _write_result(args.run_id, args.project_id, status="created", pr_url=pr_url)
        return 0
    except Exception as e:
        print(f"  ❌ gh pr create failed: {e}")
        _write_result(args.run_id, args.project_id, status="error", error=str(e))
        return 1


def request_pr_approval(
    *,
    api_url: str,
    run_id: str,
    proposal: PrProposal,
    timeout_seconds: int,
) -> int:
    """Request PR creation approval via POST /approval/request.

    Returns:
        approval_id
    """
    payload = {
        "run_id": run_id,
        "phase_id": f"pr-create-{run_id}",  # Placeholder phase_id
        "context": "PR_CREATE",
        "decision_info": {
            "type": "PR_CREATE",
            "branch": proposal.branch,
            "base_branch": proposal.base_branch,
            "title": proposal.title,
            "summary": proposal.summary_md[:200],  # Truncate
            "files_changed": len(proposal.files_changed),
            "loc_added": proposal.loc_added,
            "loc_removed": proposal.loc_removed,
            "risk_score": proposal.risk_score,
        },
    }

    response = requests.post(
        f"{api_url}/approval/request",
        json=payload,
        timeout=30,
    )
    response.raise_for_status()

    data = response.json()
    approval_id = data.get("approval_id")
    if not approval_id:
        raise ValueError(f"No approval_id in response: {data}")

    return approval_id


def wait_for_approval(
    *,
    api_url: str,
    approval_id: int,
    timeout_seconds: int,
    poll_interval: int = 10,
) -> str:
    """Poll GET /approval/status/{approval_id} until decided or timeout.

    Returns:
        "approved" | "rejected" | "timeout" | "error"
    """
    start_time = time.time()

    while True:
        elapsed = time.time() - start_time
        if elapsed > timeout_seconds:
            return "timeout"

        response = requests.get(
            f"{api_url}/approval/status/{approval_id}",
            timeout=10,
        )

        if response.status_code != 200:
            raise Exception(f"API error: {response.status_code} {response.text}")

        data = response.json()
        status = data.get("status", "pending")

        if status in ["approved", "rejected", "timeout", "error"]:
            return status

        # Still pending, keep polling
        time.sleep(poll_interval)


def create_pr_via_gh(
    *,
    branch: str,
    base_branch: str,
    title: str,
    body_file: Path,
) -> str:
    """Create PR via gh CLI.

    Idempotent: checks if PR already exists for branch before creating.

    Returns:
        PR URL

    Raises:
        subprocess.CalledProcessError: If gh command fails
    """
    # Check if PR already exists for this branch
    result = subprocess.run(
        ["gh", "pr", "list", "--head", branch, "--json", "url"],
        capture_output=True,
        text=True,
        check=True,
    )

    existing_prs = json.loads(result.stdout)
    if existing_prs:
        pr_url = existing_prs[0]["url"]
        print(f"  ⚠️  PR already exists for branch {branch}: {pr_url}")
        return pr_url

    # Create new PR
    result = subprocess.run(
        [
            "gh",
            "pr",
            "create",
            "--title",
            title,
            "--body-file",
            str(body_file),
            "--head",
            branch,
            "--base",
            base_branch,
        ],
        capture_output=True,
        text=True,
        check=True,
    )

    # Extract PR URL from output
    pr_url = result.stdout.strip()
    return pr_url


def _write_result(
    run_id: str,
    project_id: str | None,
    *,
    status: str,
    pr_url: str | None = None,
    error: str | None = None,
) -> None:
    """Write result.json to <run_base>/pr/result.json."""
    layout = RunFileLayout(run_id=run_id, project_id=project_id)
    result_path = layout.base_dir / "pr" / "result.json"
    result_path.parent.mkdir(parents=True, exist_ok=True)

    result = {
        "status": status,
        "pr_url": pr_url,
        "error": error,
    }

    result_path.write_text(json.dumps(result, indent=2), encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
