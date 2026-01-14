#!/usr/bin/env python3
"""
Ingest planning artifacts into SQLite + vector memory (Phase 2).

Reads core planning files (templates/prompts/phase plans) and:
- Inserts/versions rows in planning_artifacts table
- Embeds summaries + content into MemoryService planning collection
- Tombstones previous versions in vector memory
"""

import argparse
import hashlib
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Tuple

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from autopack import models
from autopack.config import settings
from autopack.database import Base
from autopack.memory import MemoryService


DEFAULT_ARTIFACT_PATHS = [
    "templates/hardening_phases.json",
    "templates/phase_defaults.json",
    "planning/kickoff_prompt.md",
    "prompts/claude/planner_prompt.md",
    "autopack_phase_plan.json",
]


def read_text(path: Path) -> str:
    """Read text with utf-8 fallback."""
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="latin-1")


def summarize(text: str, limit: int = 400) -> str:
    """Very small heuristic summary (no LLM dependency)."""
    compact = " ".join(text.split())
    return compact[:limit]


def ensure_version_and_embed(
    session,
    memory: MemoryService,
    project_id: str,
    path: str,
    content: str,
    author: str,
    reason: str,
) -> Tuple[int, str]:
    """Create new version if hash changed, embed, and tombstone prior vector."""
    content_hash = hashlib.sha256(content.encode("utf-8", errors="ignore")).hexdigest()
    latest = (
        session.query(models.PlanningArtifact)
        .filter(
            models.PlanningArtifact.path == path, models.PlanningArtifact.project_id == project_id
        )
        .order_by(models.PlanningArtifact.version.desc())
        .first()
    )

    if latest and latest.hash == content_hash:
        return latest.version, latest.vector_id or ""

    next_version = 1 if not latest else (latest.version + 1)
    timestamp = datetime.now(timezone.utc).isoformat()
    summary_text = summarize(content)

    vector_id = memory.write_planning_artifact(
        path=path,
        content=content,
        project_id=project_id,
        version=next_version,
        author=author,
        reason=reason,
        summary=summary_text,
        timestamp=timestamp,
    )

    artifact = models.PlanningArtifact(
        path=path,
        version=next_version,
        project_id=project_id,
        timestamp=datetime.fromisoformat(timestamp),
        hash=content_hash,
        author=author,
        reason=reason,
        status="active",
        replaced_by=None,
        vector_id=vector_id,
    )
    session.add(artifact)

    # Supersede previous version
    if latest:
        latest.status = "superseded"
        latest.replaced_by = next_version
        session.add(latest)
        if latest.vector_id:
            memory.tombstone_entry(
                memory.planning_collection,
                latest.vector_id,
                replaced_by=vector_id,
                reason="superseded",
            )

    session.commit()
    return next_version, vector_id


def resolve_paths(repo_root: Path, extras: List[str]) -> List[Path]:
    paths = []
    for rel in DEFAULT_ARTIFACT_PATHS + extras:
        candidate = (repo_root / rel).resolve()
        if candidate.exists():
            paths.append(candidate)
        else:
            print(f"[WARN] Missing artifact: {rel}", file=sys.stderr)
    # Optional run-specific plan snapshot
    run_plan = repo_root / ".autonomous_runs" / "file-organizer-app-v1" / "autopack_phase_plan.json"
    if run_plan.exists():
        paths.append(run_plan.resolve())
    return paths


def run_ingest(
    project_id: str = "autopack",
    repo_root: Path = Path(__file__).resolve().parent.parent,
    author: str = "autopack-agent",
    reason: str = "initial_ingest",
    extras: Optional[List[str]] = None,
) -> None:
    """Programmatic entry to ingest planning artifacts (used by intent router)."""
    extras = extras or []
    memory = MemoryService()

    engine = create_engine(settings.database_url)
    Session = sessionmaker(bind=engine)
    Base.metadata.create_all(bind=engine)
    session = Session()

    try:
        for path_obj in resolve_paths(repo_root, extras):
            rel_path = str(path_obj.relative_to(repo_root))
            content = read_text(path_obj)
            version, vector_id = ensure_version_and_embed(
                session,
                memory,
                project_id=project_id,
                path=rel_path,
                content=content,
                author=author,
                reason=reason,
            )
            print(f"[OK] {rel_path} -> v{version} (vector_id={vector_id})")
    finally:
        session.close()


def main():
    parser = argparse.ArgumentParser(
        description="Ingest planning artifacts into DB + vector memory"
    )
    parser.add_argument(
        "--project-id", default="autopack", help="Project identifier for scoping embeddings"
    )
    parser.add_argument(
        "--repo-root", default=Path(__file__).resolve().parent.parent, type=Path, help="Repo root"
    )
    parser.add_argument("--author", default="autopack-agent", help="Author/agent string to record")
    parser.add_argument(
        "--reason", default="initial_ingest", help="Reason for ingestion/version bump"
    )
    parser.add_argument(
        "--extra", nargs="*", default=[], help="Additional relative paths to ingest"
    )
    args = parser.parse_args()
    run_ingest(
        project_id=args.project_id,
        repo_root=args.repo_root,
        author=args.author,
        reason=args.reason,
        extras=args.extra,
    )


if __name__ == "__main__":
    main()
