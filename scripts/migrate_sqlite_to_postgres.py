"""
Migrate data from SQLite to PostgreSQL
"""
import sys
from pathlib import Path

# Set UTF-8 encoding for Windows console
if sys.platform == "win32":
    import codecs
    sys.stdout = codecs.getwriter("utf-8")(sys.stdout.detach())
    sys.stderr = codecs.getwriter("utf-8")(sys.stderr.detach())

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from autopack.models import DecisionLog, Run, Tier, Phase, PlanningArtifact, PlanChange
from autopack.usage_recorder import LlmUsageEvent, DoctorUsageStats

def migrate():
    """Migrate all data from SQLite to PostgreSQL"""

    # Connect to SQLite source
    sqlite_url = "sqlite:///autopack.db"
    sqlite_engine = create_engine(sqlite_url)
    SQLiteSession = sessionmaker(bind=sqlite_engine)
    sqlite_session = SQLiteSession()

    # Connect to PostgreSQL target (using default DATABASE_URL)
    from autopack.database import SessionLocal
    pg_session = SessionLocal()

    try:
        # Migrate DecisionLog entries
        decision_logs = sqlite_session.query(DecisionLog).all()
        print(f"Migrating {len(decision_logs)} DecisionLog entries...")
        for entry in decision_logs:
            # Check if already exists (by id or unique constraint)
            existing = pg_session.query(DecisionLog).filter_by(id=entry.id).first()
            if not existing:
                pg_session.merge(entry)
        pg_session.commit()
        print(f"✅ Migrated {len(decision_logs)} DecisionLog entries")

        # Migrate Runs
        runs = sqlite_session.query(Run).all()
        print(f"Migrating {len(runs)} Run entries...")
        for run in runs:
            existing = pg_session.query(Run).filter_by(id=run.id).first()
            if not existing:
                pg_session.merge(run)
        pg_session.commit()
        print(f"✅ Migrated {len(runs)} Run entries")

        # Migrate Tiers
        try:
            tiers = sqlite_session.query(Tier).all()
            print(f"Migrating {len(tiers)} Tier entries...")
            for tier in tiers:
                existing = pg_session.query(Tier).filter_by(id=tier.id).first()
                if not existing:
                    pg_session.merge(tier)
            pg_session.commit()
            print(f"✅ Migrated {len(tiers)} Tier entries")
        except Exception as e:
            print(f"⚠️ Tier table not found or error: {e}")

        # Migrate Phases
        try:
            phases = sqlite_session.query(Phase).all()
            print(f"Migrating {len(phases)} Phase entries...")
            for phase in phases:
                existing = pg_session.query(Phase).filter_by(id=phase.id).first()
                if not existing:
                    pg_session.merge(phase)
            pg_session.commit()
            print(f"✅ Migrated {len(phases)} Phase entries")
        except Exception as e:
            print(f"⚠️ Phase table not found or error: {e}")

        # Migrate PlanningArtifacts
        try:
            artifacts = sqlite_session.query(PlanningArtifact).all()
            print(f"Migrating {len(artifacts)} PlanningArtifact entries...")
            for artifact in artifacts:
                existing = pg_session.query(PlanningArtifact).filter_by(id=artifact.id).first()
                if not existing:
                    pg_session.merge(artifact)
            pg_session.commit()
            print(f"✅ Migrated {len(artifacts)} PlanningArtifact entries")
        except Exception as e:
            print(f"⚠️ PlanningArtifact table not found or error: {e}")

        # Migrate PlanChanges
        try:
            plan_changes = sqlite_session.query(PlanChange).all()
            print(f"Migrating {len(plan_changes)} PlanChange entries...")
            for change in plan_changes:
                existing = pg_session.query(PlanChange).filter_by(id=change.id).first()
                if not existing:
                    pg_session.merge(change)
            pg_session.commit()
            print(f"✅ Migrated {len(plan_changes)} PlanChange entries")
        except Exception as e:
            print(f"⚠️ PlanChange table not found or error: {e}")

        # Migrate LlmUsageEvent entries
        try:
            usage_events = sqlite_session.query(LlmUsageEvent).all()
            print(f"Migrating {len(usage_events)} LlmUsageEvent entries...")
            for event in usage_events:
                existing = pg_session.query(LlmUsageEvent).filter_by(id=event.id).first()
                if not existing:
                    pg_session.merge(event)
            pg_session.commit()
            print(f"✅ Migrated {len(usage_events)} LlmUsageEvent entries")
        except Exception as e:
            print(f"⚠️ LlmUsageEvent table not found or error: {e}")

        # Migrate DoctorUsageStats
        try:
            doctor_stats = sqlite_session.query(DoctorUsageStats).all()
            print(f"Migrating {len(doctor_stats)} DoctorUsageStats entries...")
            for stat in doctor_stats:
                existing = pg_session.query(DoctorUsageStats).filter_by(id=stat.id).first()
                if not existing:
                    pg_session.merge(stat)
            pg_session.commit()
            print(f"✅ Migrated {len(doctor_stats)} DoctorUsageStats entries")
        except Exception as e:
            print(f"⚠️ DoctorUsageStats table not found or error: {e}")

        # Verify migration
        print("\n📊 PostgreSQL counts after migration:")
        print(f"  DecisionLog: {pg_session.query(DecisionLog).count()}")
        print(f"  Run: {pg_session.query(Run).count()}")
        try:
            print(f"  Tier: {pg_session.query(Tier).count()}")
        except:
            pass
        try:
            print(f"  Phase: {pg_session.query(Phase).count()}")
        except:
            pass
        try:
            print(f"  PlanningArtifact: {pg_session.query(PlanningArtifact).count()}")
        except:
            pass
        try:
            print(f"  PlanChange: {pg_session.query(PlanChange).count()}")
        except:
            pass
        try:
            print(f"  LlmUsageEvent: {pg_session.query(LlmUsageEvent).count()}")
        except:
            pass
        try:
            print(f"  DoctorUsageStats: {pg_session.query(DoctorUsageStats).count()}")
        except:
            pass

    except Exception as e:
        print(f"❌ Migration failed: {e}")
        pg_session.rollback()
        raise
    finally:
        sqlite_session.close()
        pg_session.close()

if __name__ == "__main__":
    migrate()
