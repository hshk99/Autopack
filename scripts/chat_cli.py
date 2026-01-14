#!/usr/bin/env python3
"""
Lightweight chat/CLI router for memory queries (read-only).

Usage:
    python scripts/chat_cli.py --query "how do we plan phases?" --project-id autopack
"""

import argparse
from textwrap import indent

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from autopack import models
from autopack.config import settings
from autopack.database import Base
from autopack.memory import MemoryService


def format_results(results: dict) -> str:
    lines = []

    for key in ("plan_changes", "planning", "summaries", "errors", "hints", "decisions"):
        items = results.get(key) or []
        if not items:
            continue
        lines.append(f"{key.upper()}:")
        for item in items[:3]:
            payload = item.get("payload", {})
            preview = (
                payload.get("summary")
                or payload.get("hint")
                or payload.get("error_text")
                or payload.get("choice")
                or str(payload)[:200]
            )
            lines.append(f"  - {preview}")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Read-only memory chat/CLI router")
    parser.add_argument("--project-id", default="autopack", help="Project scope for retrieval")
    parser.add_argument("--query", required=True, help="Natural language query")
    parser.add_argument(
        "--show-plan-changes", action="store_true", help="Also print latest plan changes from DB"
    )
    args = parser.parse_args()

    mem = MemoryService()
    retrieved = mem.retrieve_context(
        query=args.query,
        project_id=args.project_id,
        include_code=False,
        include_errors=False,
        include_hints=False,
        include_planning=True,
        include_plan_changes=True,
        include_decisions=True,
    )
    formatted = mem.format_retrieved_context(retrieved, max_chars=4000)
    print("=== Retrieved Context ===")
    print(formatted or "(no context)")

    if args.show_plan_changes:
        engine = create_engine(settings.database_url)
        Session = sessionmaker(bind=engine)
        Base.metadata.create_all(bind=engine)
        session = Session()
        try:
            changes = (
                session.query(models.PlanChange)
                .filter(models.PlanChange.project_id == args.project_id)
                .order_by(models.PlanChange.timestamp.desc())
                .limit(5)
                .all()
            )
            print("\n=== Plan Changes (DB) ===")
            if not changes:
                print("(none)")
            else:
                for change in changes:
                    ts = change.timestamp.isoformat() if change.timestamp else "unknown"
                    print(indent(f"{ts} :: {change.summary} :: {change.rationale}", "  "))
        finally:
            session.close()


if __name__ == "__main__":
    main()
