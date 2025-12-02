"""Dashboard server for Autopack metrics visualization."""

import logging
from pathlib import Path
from typing import Optional

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from autopack.usage_recorder import UsageRecorder

logger = logging.getLogger(__name__)


def create_dashboard_app(usage_recorder: UsageRecorder) -> FastAPI:
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
    
    return app
