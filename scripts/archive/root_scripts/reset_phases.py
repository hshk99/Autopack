"""Reset FileOrg Phase 2 phases to QUEUED state for BUILD-047 validation."""
import psycopg2

# Connect to database
DATABASE_URL = "postgresql://autopack:autopack@localhost:5432/autopack"
conn = psycopg2.connect(DATABASE_URL)
cursor = conn.cursor()

# Restore COMPLETE phases that were running (restore from QUEUED to COMPLETE)
# Only keep FAILED phases as QUEUED
cursor.execute("""
    UPDATE phases
    SET
        state = 'COMPLETE',
        quality_level = 'NEEDS_REVIEW'
    WHERE run_id = 'fileorg-phase2-beta-release'
    AND state = 'QUEUED'
    AND phase_id != 'fileorg-p2-advanced-search'
""")

# Ensure the FAILED phase stays QUEUED
cursor.execute("""
    UPDATE phases
    SET
        state = 'QUEUED',
        attempts_used = 0,
        last_failure_reason = NULL
    WHERE run_id = 'fileorg-phase2-beta-release'
    AND phase_id = 'fileorg-p2-advanced-search'
""")

conn.commit()

print("Restored 14 COMPLETE phases, kept 1 FAILED phase as QUEUED")

# Show updated phase states
cursor.execute("""
    SELECT phase_id, state, attempts_used, max_attempts
    FROM phases
    WHERE run_id = 'fileorg-phase2-beta-release'
    ORDER BY tier_id, phase_index
""")

phases = cursor.fetchall()
for phase in phases:
    print(f"{phase[0]:<40} state={phase[1]:<12} attempts={phase[2]}/{phase[3]}")

conn.close()
