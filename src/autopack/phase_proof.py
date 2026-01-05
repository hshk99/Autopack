"""
Proof-carrying phase outputs for intention-first autonomy.

Implements:
- Per-phase "proof" artifact (small JSON + short markdown)
- "What changed + what was verified" structure
- Bounded fields (no content dumps)
- Contract tests for presence and field limits

All phase outputs are measurable and auditable.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator

from autopack.file_layout import RunFileLayout


class PhaseVerification(BaseModel):
    """
    What was verified in this phase.

    Bounded to prevent content dumps.
    """

    model_config = ConfigDict(extra="forbid")

    tests_passed: int = Field(ge=0, description="Number of tests that passed")
    tests_failed: int = Field(ge=0, description="Number of tests that failed")
    probes_executed: list[str] = Field(
        default_factory=list,
        max_length=20,
        description="List of probes executed (max 20)",
    )
    contracts_verified: list[str] = Field(
        default_factory=list,
        max_length=20,
        description="List of contracts verified (max 20)",
    )
    verification_summary: str = Field(
        ..., max_length=500, description="Short summary of verification"
    )


class PhaseChange(BaseModel):
    """
    What changed in this phase.

    Bounded to prevent content dumps.
    """

    model_config = ConfigDict(extra="forbid")

    files_created: int = Field(ge=0, description="Number of files created")
    files_modified: int = Field(ge=0, description="Number of files modified")
    files_deleted: int = Field(ge=0, description="Number of files deleted")
    key_changes: list[str] = Field(
        default_factory=list,
        max_length=10,
        description="List of key changes (max 10 items, each max 200 chars)",
    )
    change_summary: str = Field(..., max_length=500, description="Short summary of changes")

    @field_validator("key_changes")
    @classmethod
    def _validate_key_changes_item_length(cls, v: list[str]) -> list[str]:
        for item in v:
            if len(item) > 200:
                raise ValueError("Each key_changes item must be <= 200 characters")
        return v


class PhaseProof(BaseModel):
    """
    Complete proof artifact for a phase.

    Intention: make progress measurable and auditable without content dumps.
    """

    model_config = ConfigDict(extra="forbid")

    proof_id: str
    run_id: str
    phase_id: str
    created_at: datetime
    completed_at: datetime
    duration_seconds: float = Field(ge=0.0, description="Phase duration in seconds")

    changes: PhaseChange
    verification: PhaseVerification

    success: bool
    error_summary: str | None = Field(
        None, max_length=500, description="Error summary if phase failed"
    )

    # Schema versioning and placeholder tracking (BUILD-161 Phase A)
    schema_version: str = Field(
        default="1.0", description="Proof schema version for forward compatibility"
    )
    metrics_placeholder: bool = Field(
        default=False,
        description="True if change/verification metrics are placeholders (not yet instrumented)",
    )


class PhaseProofStorage:
    """
    Persistence layer for phase proof artifacts.

    Stores proofs as run-local artifacts for auditability.
    """

    @staticmethod
    def get_proof_path(run_id: str, phase_id: str, project_id: str | None = None) -> Path:
        """
        Get canonical path for phase proof artifact.

        Uses the repo-standard run layout:
        `.autonomous_runs/<project>/runs/<family>/<run_id>/proofs/<phase_id>.json`
        """
        layout = RunFileLayout(run_id=run_id, project_id=project_id)
        safe_phase_id = phase_id.replace(" ", "_").replace("/", "_")
        return layout.base_dir / "proofs" / f"{safe_phase_id}.json"

    @staticmethod
    def get_proof_dir(run_id: str, project_id: str | None = None) -> Path:
        """Get directory for all proof artifacts in this run."""
        layout = RunFileLayout(run_id=run_id, project_id=project_id)
        return layout.base_dir / "proofs"

    @staticmethod
    def save_proof(proof: PhaseProof) -> None:
        """
        Save phase proof to run-local artifact.

        Args:
            proof: Phase proof to save
        """
        path = PhaseProofStorage.get_proof_path(proof.run_id, proof.phase_id)
        path.parent.mkdir(parents=True, exist_ok=True)

        # Atomic write (temp → replace)
        temp_path = path.with_suffix(".tmp")
        temp_path.write_text(proof.model_dump_json(indent=2, exclude_none=True), encoding="utf-8")
        temp_path.replace(path)

    @staticmethod
    def load_proof(run_id: str, phase_id: str) -> PhaseProof | None:
        """
        Load phase proof from run-local artifact.

        Args:
            run_id: Run ID
            phase_id: Phase ID

        Returns:
            PhaseProof if exists, else None
        """
        path = PhaseProofStorage.get_proof_path(run_id, phase_id)
        if not path.exists():
            return None

        data = json.loads(path.read_text(encoding="utf-8"))
        return PhaseProof(**data)

    @staticmethod
    def list_proofs(run_id: str) -> list[str]:
        """
        List all phase IDs with proofs in this run.

        Args:
            run_id: Run ID

        Returns:
            List of phase IDs
        """
        proof_dir = PhaseProofStorage.get_proof_dir(run_id)
        if not proof_dir.exists():
            return []

        return [p.stem for p in proof_dir.glob("*.json")]


def render_proof_as_markdown(proof: PhaseProof) -> str:
    """
    Render phase proof as human-readable markdown.

    Args:
        proof: Phase proof

    Returns:
        Markdown string
    """
    status = "✅ SUCCESS" if proof.success else "❌ FAILED"
    duration = f"{proof.duration_seconds:.1f}s"

    md = f"""# Phase Proof: {proof.phase_id}

**Status**: {status}
**Duration**: {duration}
**Completed**: {proof.completed_at.isoformat()}

## Changes

{proof.changes.change_summary}

- Files created: {proof.changes.files_created}
- Files modified: {proof.changes.files_modified}
- Files deleted: {proof.changes.files_deleted}

### Key Changes
"""

    for change in proof.changes.key_changes:
        md += f"- {change}\n"

    md += f"""
## Verification

{proof.verification.verification_summary}

- Tests passed: {proof.verification.tests_passed}
- Tests failed: {proof.verification.tests_failed}
- Probes executed: {len(proof.verification.probes_executed)}
- Contracts verified: {len(proof.verification.contracts_verified)}
"""

    if proof.verification.probes_executed:
        md += "\n### Probes Executed\n"
        for probe in proof.verification.probes_executed:
            md += f"- {probe}\n"

    if proof.verification.contracts_verified:
        md += "\n### Contracts Verified\n"
        for contract in proof.verification.contracts_verified:
            md += f"- {contract}\n"

    if not proof.success and proof.error_summary:
        md += f"\n## Error\n\n{proof.error_summary}\n"

    return md
