#!/usr/bin/env python3
"""
Natural-language intent router for Autopack.

Maps user intents to safe, predefined actions without typing raw commands:
- Refresh planning artifacts (ingest + embeddings)
- Run memory maintenance (TTL prune + tombstones)
- Show plan changes / decision log
- Query planning context (memory retrieval)
- Check publication readiness (pre-publish checklist)
"""

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

# Set UTF-8 encoding for Windows console
if sys.platform == "win32":
    import codecs
    sys.stdout = codecs.getwriter("utf-8")(sys.stdout.detach())
    sys.stderr = codecs.getwriter("utf-8")(sys.stderr.detach())

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from autopack import models
from autopack.config import settings
from autopack.database import Base
from autopack.memory import MemoryService
from autopack.memory.maintenance import run_maintenance, _load_memory_config
from autopack.diagnostics import DiagnosticsAgent

# Import ingest script dynamically to avoid circular import issues
def _get_ingest_module():
    import importlib.util
    script_path = Path(__file__).parent / "ingest_planning_artifacts.py"
    spec = importlib.util.spec_from_file_location("ingest_planning_artifacts", script_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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
    ingest_module = _get_ingest_module()
    ingest_module.run_ingest(
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


def _run_manual_diagnostics(failure_class: str, project_id: str, args: argparse.Namespace) -> ActionResult:
    """Fire a governed diagnostics run from the CLI intent router."""
    workspace = Path(args.repo_root or Path.cwd())
    run_id = args.run_id or f"{project_id}-manual"
    diagnostics_dir = workspace / settings.autonomous_runs_dir / run_id / "diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)

    agent = DiagnosticsAgent(
        run_id=run_id,
        workspace=workspace,
        memory_service=MemoryService(),
        decision_logger=None,  # CLI usage is read-only; DB decision log is executor-owned
        diagnostics_dir=diagnostics_dir,
        max_probes=5,
        max_seconds=180,
    )
    context: Dict = {}
    if args.target:
        context["test_target"] = args.target

    outcome = agent.run_diagnostics(failure_class=failure_class, context=context)
    return (outcome.ledger_summary, True)


def action_diagnose_patch(project_id: str, args: argparse.Namespace) -> ActionResult:
    return _run_manual_diagnostics("patch_apply_error", project_id, args)


def action_diagnose_ci(project_id: str, args: argparse.Namespace) -> ActionResult:
    return _run_manual_diagnostics("ci_fail", project_id, args)


def action_check_publication_readiness(project_id: str, args: argparse.Namespace) -> ActionResult:
    """
    Run pre-publication checklist on a project.

    Verifies project has all necessary artifacts for public release:
    - README, LICENSE, CHANGELOG
    - Package metadata and dependencies
    - Documentation and tests
    - No secrets or PII
    - Proper versioning and git tags
    """
    # Determine project path
    if args.project_path:
        project_path = Path(args.project_path)
    else:
        # Default to .autonomous_runs/<project_id>
        workspace = Path(args.repo_root or Path.cwd())
        project_path = workspace / settings.autonomous_runs_dir / project_id

    if not project_path.exists():
        return (f"Project path does not exist: {project_path}", False)

    # Run pre_publish_checklist.py
    script_path = Path(__file__).parent / "pre_publish_checklist.py"
    cmd = [sys.executable, str(script_path), "--project-path", str(project_path)]

    if args.strict:
        cmd.append("--strict")

    if args.output:
        cmd.extend(["--output", str(args.output)])

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
            encoding="utf-8",
        )

        # Format output
        output = result.stdout
        if result.returncode == 0:
            status = "✓ READY FOR PUBLICATION"
            success = True
        else:
            status = "✗ NOT READY FOR PUBLICATION"
            success = False

        message = f"{status}\n\n{output}"

        # If JSON output requested, also print location
        if args.output:
            message += f"\n\nJSON results saved to: {args.output}"

        return (message, success)

    except Exception as e:
        return (f"Error running pre-publication checklist: {e}", False)


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
    Intent(
        name="diagnose_patch_failure",
        keywords=["diagnose patch", "patch failure", "apply failed", "patch failed"],
        action=action_diagnose_patch,
        description="Run governed diagnostics for patch/apply failures",
    ),
    Intent(
        name="diagnose_ci_failure",
        keywords=["diagnose ci", "ci failed", "tests failed", "why did ci fail"],
        action=action_diagnose_ci,
        description="Run governed diagnostics for CI/test failures",
    ),
    Intent(
        name="check_publication_readiness",
        keywords=[
            "check publication",
            "ready to publish",
            "ready for release",
            "publication checklist",
            "release checklist",
            "can i publish",
            "verify publication",
            "pre-publish",
            "prepublish",
        ],
        action=action_check_publication_readiness,
        description="Check if project is ready for public release (npm, PyPI, Docker Hub, GitHub)",
    ),
]


def main():
    parser = argparse.ArgumentParser(description="Natural-language intent router for Autopack")
    parser.add_argument("--project-id", default="autopack", help="Project scope")
    parser.add_argument("--query", required=True, help="User intent in natural language")
    parser.add_argument("--repo-root", default=None, type=Path, help="Repo root (for ingest)")
    parser.add_argument("--run-id", default=None, help="Run identifier for diagnostics")
    parser.add_argument("--target", default=None, help="Target selector for diagnostics (e.g., pytest -k pattern)")
    parser.add_argument("--author", default="autopack-agent", help="Author for ingest logging")
    parser.add_argument("--reason", default="intent_router", help="Reason for ingest/version bump")
    parser.add_argument("--extra", nargs="*", default=[], help="Additional paths for ingest")
    parser.add_argument("--ttl-days", type=int, default=None, help="Override TTL days for maintenance")
    parser.add_argument("--keep-versions", type=int, default=None, help="Override planning keep_versions for maintenance")
    parser.add_argument("--limit", type=int, default=5, help="Max rows to show for plan changes/decisions")
    parser.add_argument("--project-path", default=None, type=Path, help="Explicit project path for publication check (overrides project-id)")
    parser.add_argument("--strict", action="store_true", help="Strict mode for publication check (warnings = errors)")
    parser.add_argument("--output", default=None, type=Path, help="JSON output file for publication check results")
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

