"""Dashboard server for Autopack metrics visualization."""

import json
import logging
import os
from pathlib import Path
from typing import Optional, Tuple, Protocol

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from autopack.config import settings

logger = logging.getLogger(__name__)


class _UsageRecorderProto(Protocol):
    def get_summary(self):
        ...


def _find_latest_diagnostic_summary(base_dir: Path) -> Optional[Tuple[Path, float]]:
    """Return path and mtime of the latest diagnostic_summary.json under .autonomous_runs."""
    if not base_dir.exists():
        return None
    newest: Optional[Tuple[Path, float]] = None
    for run_dir in base_dir.iterdir():
        diag_path = run_dir / "diagnostics" / "diagnostic_summary.json"
        if diag_path.exists():
            mtime = diag_path.stat().st_mtime
            if newest is None or mtime > newest[1]:
                newest = (diag_path, mtime)
    return newest


def create_dashboard_app(usage_recorder: _UsageRecorderProto) -> FastAPI:
    """
    Create FastAPI application with dashboard endpoints.
    
    Args:
        usage_recorder: UsageRecorder instance for metrics
        
    Returns:
        FastAPI application with dashboard routes
    """
    app = FastAPI(title="Autopack Dashboard", version="1.0.0")
    
    # API endpoint for Doctor statistics
    @app.get("/api/doctor-stats")
    async def get_doctor_stats():
        """Get Doctor usage statistics."""
        stats = usage_recorder.get_summary()
        doctor_stats = stats.get("doctor_stats", {})
        
        total_calls = doctor_stats.get("total_calls", 0)
        
        return {
            "total_calls": total_calls,
            "cheap_calls": doctor_stats.get("cheap_calls", 0),
            "strong_calls": doctor_stats.get("strong_calls", 0),
            "escalations": doctor_stats.get("escalations", 0),
            "actions": doctor_stats.get("actions", {})
        }
    
    @app.get("/api/diagnostics/latest")
    async def get_latest_diagnostics():
        """
        Return the most recent diagnostic_summary.json for read-only visibility.
        """
        base_dir = Path(settings.autonomous_runs_dir)
        latest = _find_latest_diagnostic_summary(base_dir)
        if not latest:
            return {
                "run_id": None,
                "phase_id": None,
                "failure_class": None,
                "mode": None,
                "ledger": "No diagnostics available",
                "probes": [],
                "timestamp": None,
            }

        diag_path, mtime = latest
        try:
            with diag_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            run_id = diag_path.parent.parent.name
            return {
                "run_id": run_id,
                "phase_id": data.get("phase_id"),
                "failure_class": data.get("failure_class"),
            "mode": data.get("mode"),
                "ledger": data.get("ledger"),
                "probes": data.get("probes", []),
                "timestamp": data.get("timestamp"),
                "path": str(diag_path),
            }
        except Exception as e:
            logger.warning(f"Failed to read diagnostic summary at {diag_path}: {e}")
            return {
                "run_id": None,
                "phase_id": None,
                "failure_class": None,
                "mode": None,
                "ledger": "Diagnostics summary unreadable",
                "probes": [],
                "timestamp": None,
            }
    
    return app
