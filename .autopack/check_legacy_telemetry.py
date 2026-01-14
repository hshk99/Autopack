#!/usr/bin/env python3
"""Quick script to check legacy database for telemetry data."""

import os
import sys
from pathlib import Path

os.environ["DATABASE_URL"] = "sqlite:///autopack_legacy.db"
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from autopack.database import SessionLocal
from autopack.usage_recorder import LlmUsageEvent

session = SessionLocal()
try:
    total_events = session.query(LlmUsageEvent).count()
    print(f"Legacy DB - Total LLM usage events: {total_events}")

    if total_events > 0:
        # Try to find events from successful phases
        sample = session.query(LlmUsageEvent).first()
        print("\nSample event:")
        print(f"  Phase: {sample.phase_id}")
        print(f"  Run: {sample.run_id}")
        print(f"  Estimated tokens: {sample.estimated_tokens}")
        print(f"  Actual output tokens: {sample.actual_output_tokens}")

        # Count events with both estimated and actual tokens
        usable_events = (
            session.query(LlmUsageEvent)
            .filter(
                LlmUsageEvent.estimated_tokens.isnot(None),
                LlmUsageEvent.actual_output_tokens.isnot(None),
            )
            .count()
        )
        print(f"\nUsable events (has estimated + actual tokens): {usable_events}")

finally:
    session.close()
