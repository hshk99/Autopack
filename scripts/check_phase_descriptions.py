#!/usr/bin/env python3
"""Check phase descriptions in database"""

import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from autopack.db_setup import SessionLocal
from autopack.models import Phase

def check_phases(run_id):
    """Check all phases for a run"""
    session = SessionLocal()
    try:
        phases = session.query(Phase).filter(Phase.run_id == run_id).all()
        print(f'Found {len(phases)} phases for run {run_id}')
        for p in phases:
            desc_len = len(p.description or "")
            print(f'  Phase {p.phase_id}: description_length={desc_len}')
            if desc_len == 0:
                print(f'    WARNING: Empty description!')
            elif desc_len < 50:
                print(f'    Description: "{p.description}"')
    except Exception as e:
        print(f'[ERROR] Failed to check phases: {e}')
        raise
    finally:
        session.close()

if __name__ == "__main__":
    run_id = sys.argv[1] if len(sys.argv) > 1 else "fileorg-phase2-final"
    check_phases(run_id)
