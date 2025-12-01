#!/usr/bin/env python3
"""Reset phases to QUEUED status for re-testing"""

import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from autopack.db_setup import SessionLocal
from autopack.models import Phase

def reset_phases(run_id: str):
    """Reset all phases for a run to QUEUED status"""
    session = SessionLocal()
    try:
        updated = session.query(Phase).filter(Phase.run_id == run_id).update({'status': 'QUEUED'})
        session.commit()
        print(f'[OK] Reset {updated} phases to QUEUED for {run_id}')
    except Exception as e:
        session.rollback()
        print(f'[ERROR] Failed to reset phases: {e}')
        raise
    finally:
        session.close()

if __name__ == "__main__":
    run_id = sys.argv[1] if len(sys.argv) > 1 else "fileorg-phase2-final"
    reset_phases(run_id)
