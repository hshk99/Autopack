#!/usr/bin/env python3
"""
Reset v2.2 restoration phases and re-run as v2.3 with BUILD-040
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from autopack.data_layer import DataLayer

def main():
    # Initialize data layer
    dl = DataLayer()

    # Get the v2.2 run
    run_id = "research-system-restore-and-evaluate-v2"
    run = dl.get_run(run_id)

    if not run:
        print(f"Run {run_id} not found")
        return 1

    print(f"Found run: {run_id}, status: {run['status']}")

    # Get all phases
    phases = dl.get_phases(run_id)
    print(f"Found {len(phases)} phases")

    # Reset all phases to QUEUED
    for phase in phases:
        phase_id = phase['phase_id']
        current_status = phase['status']

        if current_status in ['COMPLETE', 'FAILED']:
            dl.update_phase_status(run_id, phase_id, 'QUEUED')
            print(f"Reset phase {phase_id}: {current_status} -> QUEUED")

    # Reset run status to IN_PROGRESS
    dl.update_run_status(run_id, 'IN_PROGRESS')
    print("Reset run status to IN_PROGRESS")

    print("\nPhases have been reset. You can now re-run the autonomous_executor.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
