"""
Export TokenEstimationV2 telemetry from database to NDJSON for analysis.

Usage:
    PYTHONUTF8=1 PYTHONPATH=src python scripts/export_token_estimation_telemetry.py > telemetry_export.ndjson
"""

import json
import sys
from autopack.database import SessionLocal
from autopack.models import TokenEstimationV2Event


def main():
    session = SessionLocal()
    try:
        events = (
            session.query(TokenEstimationV2Event)
            .order_by(TokenEstimationV2Event.timestamp.desc())
            .all()
        )

        print("# TokenEstimationV2 Telemetry Export", file=sys.stderr)
        print(f"# Total events: {len(events)}", file=sys.stderr)
        print(file=sys.stderr)

        for event in events:
            deliverables = []
            if event.deliverables_json:
                try:
                    deliverables = json.loads(event.deliverables_json)
                except Exception:
                    # Keep export resilient even if old/bad rows exist
                    deliverables = []
            record = {
                "run_id": event.run_id,
                "phase_id": event.phase_id,
                "timestamp": event.timestamp.isoformat(),
                "category": event.category,
                "complexity": event.complexity,
                "deliverable_count": event.deliverable_count,
                "deliverables": deliverables,
                "predicted_output_tokens": event.predicted_output_tokens,
                "actual_output_tokens": event.actual_output_tokens,
                "selected_budget": event.selected_budget,
                "success": event.success,
                "truncated": event.truncated,
                "stop_reason": event.stop_reason,
                "model": event.model,
                "smape_percent": event.smape_percent,
                # DB now stores waste_ratio as predicted/actual (float ratio)
                "waste_ratio": float(event.waste_ratio) if event.waste_ratio is not None else None,
                "underestimated": event.underestimated,
            }
            print(json.dumps(record))
    finally:
        session.close()


if __name__ == "__main__":
    main()
