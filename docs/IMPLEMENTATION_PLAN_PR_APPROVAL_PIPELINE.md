## Implementation Plan: PR Approval Pipeline (Run-Local Proposal → Telegram Buttons → Local PR Create)

**Status**: Design locked (single direction; safe-by-default)

### Direction (chosen; aligned to `README.md` ideal state)

Implement a **post-run** PR approval pipeline that preserves Autopack’s core guarantees:

- **Executor stays pure**: the autonomous executor loop remains free of network-side effects (no GitHub/Telegram calls from executor code).
- **CI stays read-only**: CI validates but never writes/merges.
- **Artifacts-first**: PR intent is captured as **run-local artifacts** under `RunFileLayout`.
- **Explicit human gating**: PR creation requires **Telegram inline button approval** (✅ Approve / ❌ Reject).
- **Never auto-merge by default**: merge remains manual (or a separate, future approval action with its own guardrails).

This plan chooses one path: **PR creation is a post-run command**, not a phase inside the executor.

---

### Ambiguities (resolved)

- **A1) When does PR approval trigger?**
  - **Decision**: Only after **Builder + Auditor + Quality Gate converge** and **local tests are green** (i.e., “PR-ready”).
  - The post-run command must require an explicit `--pr-ready` (or equivalent) flag or a verified “ready” marker written as a run-local artifact.

- **A2) Where does `gh pr create` run?**
  - **Decision**: Only on the **local machine** running the post-run command, with `gh` already authenticated.
  - CI does not run `gh`, and the executor does not run `gh`.

- **A3) How do Telegram button callbacks identify the approval request?**
  - **Decision**: Use the **database `approval_id`** (integer primary key), not `phase_id`.
  - This avoids collisions, allows idempotency, and makes auditing reliable.

- **A4) Where are proposal / result artifacts stored?**
  - **Decision**: Under canonical run directory from `RunFileLayout`:
    - `<run_base>/pr/proposal.json`
    - `<run_base>/pr/proposal.md`
    - `<run_base>/pr/result.json`
  - Never write to SOT (`docs/*`) from runtime.

- **A5) What is “approval” authorizing?**
  - **Decision**: Approval authorizes **PR creation only**, not merge.
  - A future merge gate (if ever added) must be a distinct action type and a second approval.

---

### Existing building blocks to reuse (do not reinvent)

- **Telegram inline buttons** are already implemented in `src/autopack/notifications/telegram_notifier.py` via `callback_data`.
- **Webhook callback processing** exists in `src/autopack/main.py` at `POST /telegram/webhook`.
- **Approval DB lifecycle** exists in `src/autopack/main.py` via:
  - `POST /approval/request`
  - `GET /approval/status/{approval_id}`
  - background timeout cleanup task

This plan extends these mechanisms; it does not replace them.

---

## Contract: “Run-local proposal → Telegram approval → Local PR create”

### Step 1) Generate PR proposal artifacts (run-local)

**Goal**: Create a bounded, auditable proposal describing what will be PR’d.

**Inputs** (minimum):
- `run_id`, `project_id` (optional)
- `branch`, `base_branch`
- `diff stats` (files changed, added/removed)
- `risk score` (reuse existing risk scorer if available; otherwise pass-through from caller)
- links to run-local proofs (phase proofs, routing snapshot)

**Outputs**:
- `proposal.json` (machine-readable)
- `proposal.md` (human-readable body for PR)

**Acceptance criteria**:
- Proposal generation is deterministic given the same inputs (no network calls).
- Proposal artifact paths are canonical under `RunFileLayout`.
- Proposal is self-contained enough that a human can approve without reading terminal logs.

---

### Step 2) Request PR-create approval via Telegram inline buttons

**Goal**: Get explicit user consent using **buttons**, not free-text replies.

**Action**: Create a new approval request through existing `POST /approval/request`:

- `decision_info.type = "PR_CREATE"`
- `decision_info` includes:
  - `branch`, `base_branch`, `title`
  - `proposal_paths` (json + md)
  - summary fields: `files_count`, `risk_score`, `risk_level`, `loc_added`, `loc_removed`

**Telegram message**:
- Must include:
  - run id (and “PR_CREATE”)
  - branch name
  - risk summary
  - net deletion / added / removed
  - top files (bounded)
  - checklist reminder: “CI must be green before merge”

**Telegram callback_data** (new; id-based):
- `pr_approve:{approval_id}`
- `pr_reject:{approval_id}`

**Acceptance criteria**:
- Pressing buttons updates the correct approval row (by `approval_id`).
- Idempotent: pressing twice does not create inconsistent state (second press is acknowledged but no-op).

---

### Step 3) On approval, create PR locally via `gh`

**Goal**: Create the PR only after approval; record outcome as run-local artifact.

**Process**:
- Poll `GET /approval/status/{approval_id}` until terminal:
  - `approved`, `rejected`, or `timeout`
- If `approved`:
  - Confirm branch exists + working tree clean + commits present.
  - Check idempotency: does a PR already exist for this branch?
    - `gh pr list --head <branch> --json number,url,state`
    - If exists: record as result and exit success.
  - Else create:
    - `gh pr create --title <title> --body-file <proposal.md> --base <base_branch> --head <branch>`
- Write `<run_base>/pr/result.json` containing:
  - approval id, status, PR URL/number, head sha, timestamp

**Acceptance criteria**:
- No PR creation occurs without explicit approval.
- “PR already exists” is handled cleanly and recorded.
- Fail-safe: if `gh` fails, no retries thrash; write result artifact with error and stop.

---

## Implementation tasks (exact; minimal surface area)

### 1) Add proposal artifact module

**File**: `src/autopack/pr/proposal_artifacts.py`

Skeleton:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from autopack.file_layout import RunFileLayout


@dataclass(frozen=True)
class PrProposal:
    run_id: str
    project_id: str | None
    branch: str
    base_branch: str
    title: str
    files_changed: list[str]
    loc_added: int
    loc_removed: int
    risk_score: int
    risk_level: str
    checklist: list[str]
    summary_md: str
    metadata: dict[str, Any]


class PrProposalStorage:
    @staticmethod
    def proposal_paths(*, run_id: str, project_id: str | None) -> tuple[str, str]:
        layout = RunFileLayout(project_id=project_id, run_id=run_id)
        base = layout.run_dir()
        return (str(base / "pr" / "proposal.json"), str(base / "pr" / "proposal.md"))

    @staticmethod
    def save(*, proposal: PrProposal) -> tuple[str, str]:
        # Create directories, then atomically write JSON + MD
        # Return (json_path, md_path)
        raise NotImplementedError
```

---

### 2) Add git inspection helpers (local-only)

**File**: `src/autopack/pr/git_inspection.py`

Skeleton:

```python
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DiffStats:
    files: list[str]
    added: int
    removed: int


def get_diff_stats(*, base_ref: str) -> DiffStats:
    # Use `git diff --numstat <base_ref>...HEAD` and parse deterministically
    raise NotImplementedError


def ensure_branch(*, branch: str) -> None:
    # Create or checkout branch deterministically; no network
    raise NotImplementedError


def commit_all(*, message: str) -> str:
    # Stage + commit; return commit sha
    raise NotImplementedError
```

---

### 3) Extend Telegram notifier with PR-specific buttons

**File**: `src/autopack/notifications/telegram_notifier.py`

Add a method (do not change existing deletion approval flow):

```python
def send_pr_approval_request(
    self,
    *,
    approval_id: int,
    run_id: str,
    branch: str,
    risk_level: str,
    risk_score: int,
    loc_removed: int,
    loc_added: int,
    files: list[str],
    checklist: list[str],
) -> bool:
    # sendMessage with inline_keyboard buttons:
    #   callback_data: f"pr_approve:{approval_id}" and f"pr_reject:{approval_id}"
    raise NotImplementedError
```

Message should visually match the existing “Approval Needed” style (risk line, net deletion, top files, timestamp).

---

### 4) Extend webhook handler to handle PR callbacks by approval_id

**File**: `src/autopack/main.py`

In `POST /telegram/webhook`:
- After storage callback handling, add PR callback handling:
  - Recognize `callback_data.startswith("pr_approve:")` and `pr_reject:`
  - Parse `approval_id`
  - Load `models.ApprovalRequest` by `id` where `status=="pending"`
  - Set `status="approved"` or `"rejected"`, `response_method="telegram"`, `responded_at=now`
  - Acknowledge callback (optional: implement `answer_telegram_callback` helper for core notifier too; storage already has this helper)

**Hard requirement**: Do not use `phase_id` for PR callbacks.

---

### 5) Add post-run script: propose + approve + create PR

**File**: `scripts/pr/propose_and_create_pr.py` (new directory `scripts/pr/`)

Skeleton contract:

```python
from __future__ import annotations

import os
import time
import subprocess

import requests

from autopack.pr.proposal_artifacts import PrProposal, PrProposalStorage
from autopack.pr.git_inspection import ensure_branch, commit_all, get_diff_stats


def main() -> int:
    # Guardrails
    if os.getenv("AUTOPACK_ENABLE_PR_APPROVAL", "false").lower() != "true":
        print("PR approval pipeline disabled (AUTOPACK_ENABLE_PR_APPROVAL != true).")
        return 2

    # Inputs: run_id, project_id, branch, base_branch, title, api_url
    # 1) ensure branch + commit
    # 2) compute diff stats
    # 3) write proposal artifacts
    # 4) POST /approval/request (decision_info.type=PR_CREATE) → approval_id
    # 5) poll /approval/status/{approval_id}
    # 6) if approved → gh pr list/idempotency → gh pr create
    # 7) write result artifact
    return 0
```

**Environment**:
- `AUTOPACK_ENABLE_PR_APPROVAL=true` (required)
- `AUTOPACK_API_URL` (default `http://localhost:8001` in existing approval test scripts)
- `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` configured on the API server side (existing)

---

## Idempotency rules (must implement)

- **Approval request**:
  - If the script is re-run for the same run/branch, it may create a new approval request. That is acceptable.
  - However, if the approval is already terminal, the script must not re-open PR creation without a new approval id.

- **PR existence**:
  - Must check `gh pr list --head <branch>` before creating.
  - If PR exists: write `result.json` with that PR info and exit success.

---

## Security / safety rules (must implement)

- **No secrets in artifacts**: proposal/result artifacts must not include tokens.
- **No auto-merge**: there is no “merge” action in this pipeline.
- **No CI usage**: CI workflows must not call these scripts.

---

## Tests (minimal, high-signal)

Add tests that don’t require network or `gh`:

- **`tests/autopack/test_pr_proposal_artifacts.py`**
  - proposal paths are under `RunFileLayout`
  - writing proposal creates both files and is stable

- **`tests/autopack/test_telegram_webhook_pr_callbacks.py`**
  - PR callbacks update `ApprovalRequest` by id
  - second callback press is no-op but acknowledged

Mock `requests`/`subprocess` for the post-run script tests if you add them; otherwise keep script untested and rely on unit tests around helpers.

---

## Handoff checklist (what “done” looks like)

- Telegram message shows **✅ Approve / ❌ Reject** buttons for PR approval.
- Pressing buttons transitions the correct approval row to `approved/rejected`.
- Post-run script:
  - writes run-local proposal artifacts
  - requests approval
  - on approval creates PR (or detects existing PR)
  - writes run-local result artifact
- Executor remains unchanged (no new network calls).
