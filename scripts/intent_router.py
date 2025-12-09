#!/usr/bin/env python3
"""
Natural-language intent router for Autopack.

Maps user intents to safe, predefined actions without typing raw commands:
- Refresh planning artifacts (ingest + embeddings)
- Run memory maintenance (TTL prune + tombstones)
- Show plan changes / decision log
- Query planning context (memory retrieval)
"""

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from autopack import models
from autopack.config import settings
from autopack.database import Base
from autopack.memory import MemoryService
from autopack.memory.maintenance import run_maintenance, _load_memory_config
from scripts import ingest_planning_artifacts


# ---------------------------------------------------------------------------
# Intent definitions
# ---------------------------------------------------------------------------

ActionResult = Tuple[str, bool]  # message, success
ActionFn = Callable[[str, argparse.Namespace], ActionResult]


@dataclass
class Intent:
    name: str
    keywords: List[str]
    action: ActionFn
    description: str


def _match_intent(text: str, intents: List[Intent]) -> Optional[Intent]:
    lowered = text.lower()
    for intent in intents:
        if any(k in lowered for k in intent.keywords):
            return intent
    return None


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------

def action_ingest(project_id: str, args: argparse.Namespace) -> ActionResult:
    repo_root = Path(args.repo_root or Path(__file__).resolve().parent.parent)
    ingest_planning_artifacts.run_ingest(
        project_id=project_id,
        repo_root=repo_root,
        author=args.author,
        reason=args.reason,
        extras=args.extra or [],
    )
    return ("Planning artifacts ingested and embedded.", True)


def action_maintenance(project_id: str, args: argparse.Namespace) -> ActionResult:
    cfg = _load_memory_config()
    ttl = args.ttl_days or cfg.get("ttl_days", 30)
    keep_versions = args.keep_versions or cfg.get("planning_keep_versions", 3)
    mem = MemoryService()
    stats = run_maintenance(mem.store, project_id, ttl_days=ttl, planning_keep_versions=keep_versions)
    return (f"Maintenance complete: {stats}", True)


def action_show_plan_changes(project_id: str, args: argparse.Namespace) -> ActionResult:
    engine = create_engine(settings.database_url)
    Session = sessionmaker(bind=engine)
    Base.metadata.create_all(bind=engine)
    session = Session()
    try:
        changes = (
            session.query(models.PlanChange)
            .filter(models.PlanChange.project_id == project_id)
            .order_by(models.PlanChange.timestamp.desc())
            .limit(args.limit)
            .all()
        )
        if not changes:
            return ("No plan changes found.", True)
        lines = []
        for c in changes:
            ts = c.timestamp.isoformat() if c.timestamp else "unknown"
            lines.append(f"{ts} :: {c.summary} :: {c.rationale}")
        return ("\n".join(lines), True)
    finally:
        session.close()


def action_show_decisions(project_id: str, args: argparse.Namespace) -> ActionResult:
    engine = create_engine(settings.database_url)
    Session = sessionmaker(bind=engine)
    Base.metadata.create_all(bind=engine)
    session = Session()
    try:
        decisions = (
            session.query(models.DecisionLog)
            .filter(models.DecisionLog.project_id == project_id)
            .order_by(models.DecisionLog.timestamp.desc())
            .limit(args.limit)
            .all()
        )
        if not decisions:
            return ("No decisions found.", True)
        lines = []
        for d in decisions:
            ts = d.timestamp.isoformat() if d.timestamp else "unknown"
            lines.append(f"{ts} :: {d.trigger} -> {d.choice} :: {d.rationale}")
        return ("\n".join(lines), True)
    finally:
        session.close()


def action_memory_query(project_id: str, args: argparse.Namespace) -> ActionResult:
    mem = MemoryService()
    retrieved = mem.retrieve_context(
        query=args.query,
        project_id=project_id,
        include_code=False,
        include_errors=False,
        include_hints=False,
        include_planning=True,
        include_plan_changes=True,
        include_decisions=True,
    )
    formatted = mem.format_retrieved_context(retrieved, max_chars=4000)
    return (formatted or "(no context)", True)


INTENTS: List[Intent] = [
    Intent(
        name="ingest_planning",
        keywords=["ingest", "refresh plan", "planning artifact", "reload plan", "update plan"],
        action=action_ingest,
        description="Refresh planning artifacts and embeddings",
    ),
    Intent(
        name="maintenance",
        keywords=["maintenance", "prune", "cleanup", "ttl", "tombstone"],
        action=action_maintenance,
        description="Run vector memory maintenance (TTL prune + tombstones)",
    ),
    Intent(
        name="show_plan_changes",
        keywords=["plan change", "plan changes", "show plan change", "plan log"],
        action=action_show_plan_changes,
        description="Show recent plan changes",
    ),
    Intent(
        name="show_decisions",
        keywords=["decision log", "decisions", "doctor decisions"],
        action=action_show_decisions,
        description="Show recent decision log entries",
    ),
    Intent(
        name="context_query",
        keywords=["context", "memory", "planning context", "what do we know", "retrieval"],
        action=action_memory_query,
        description="Query planning context from memory",
    ),
]


def main():
    parser = argparse.ArgumentParser(description="Natural-language intent router for Autopack")
    parser.add_argument("--project-id", default="autopack", help="Project scope")
    parser.add_argument("--query", required=True, help="User intent in natural language")
    parser.add_argument("--repo-root", default=None, type=Path, help="Repo root (for ingest)")
    parser.add_argument("--author", default="autopack-agent", help="Author for ingest logging")
    parser.add_argument("--reason", default="intent_router", help="Reason for ingest/version bump")
    parser.add_argument("--extra", nargs="*", default=[], help="Additional paths for ingest")
    parser.add_argument("--ttl-days", type=int, default=None, help="Override TTL days for maintenance")
    parser.add_argument("--keep-versions", type=int, default=None, help="Override planning keep_versions for maintenance")
    parser.add_argument("--limit", type=int, default=5, help="Max rows to show for plan changes/decisions")
    args = parser.parse_args()

    intent = _match_intent(args.query, INTENTS)
    if not intent:
        print("Intent not recognized. Supported intents:")
        for item in INTENTS:
            print(f"- {item.name}: {item.description}")
        raise SystemExit(1)

    message, ok = intent.action(args.project_id, args)
    status = "OK" if ok else "FAILED"
    print(f"[{status}] {intent.name}: {message}")


if __name__ == "__main__":
    main()

