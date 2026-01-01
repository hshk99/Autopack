"""
Migration: Add Storage Optimizer Intelligence Features (BUILD-151 Phase 4)

Adds learned_rules table and extends cleanup_candidates for auto-learning.
"""

from sqlalchemy import text
from autopack.database import SessionLocal, engine


def migrate():
    """Add storage intelligence tables and columns."""

    print("BUILD-151 Phase 4: Adding storage intelligence features...")

    # Check if learned_rules table already exists
    with engine.connect() as conn:
        try:
            conn.execute(text("SELECT 1 FROM learned_rules LIMIT 1"))
            print("✓ learned_rules table already exists, skipping creation")
            return
        except Exception:
            pass  # Table doesn't exist, continue

    # Detect database type
    is_sqlite = 'sqlite' in str(engine.url)

    # Create learned_rules table
    print("Creating learned_rules table...")
    with engine.connect() as conn:
        if is_sqlite:
            # SQLite version
            conn.execute(text("""
                CREATE TABLE learned_rules (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    pattern_type VARCHAR(50) NOT NULL,
                    pattern_value TEXT NOT NULL,
                    suggested_category VARCHAR(50) NOT NULL,
                    confidence_score DECIMAL(5, 2) NOT NULL CHECK (confidence_score >= 0 AND confidence_score <= 1),
                    based_on_approvals INTEGER NOT NULL DEFAULT 0,
                    based_on_rejections INTEGER NOT NULL DEFAULT 0,
                    sample_paths TEXT,
                    status VARCHAR(20) DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'rejected', 'applied')),
                    reviewed_by VARCHAR(100),
                    reviewed_at TIMESTAMP,
                    applied_to_policy_version VARCHAR(50),
                    description TEXT,
                    notes TEXT
                )
            """))
            conn.execute(text("CREATE INDEX idx_learned_rules_status ON learned_rules(status)"))
            conn.execute(text("CREATE INDEX idx_learned_rules_confidence ON learned_rules(confidence_score DESC)"))
            conn.execute(text("CREATE INDEX idx_learned_rules_created_at ON learned_rules(created_at DESC)"))
        else:
            # PostgreSQL version
            conn.execute(text("""
                CREATE TABLE learned_rules (
                    id SERIAL PRIMARY KEY,
                    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                    pattern_type VARCHAR(50) NOT NULL,
                    pattern_value TEXT NOT NULL,
                    suggested_category VARCHAR(50) NOT NULL,
                    confidence_score DECIMAL(5, 2) NOT NULL CHECK (confidence_score >= 0 AND confidence_score <= 1),
                    based_on_approvals INTEGER NOT NULL DEFAULT 0,
                    based_on_rejections INTEGER NOT NULL DEFAULT 0,
                    sample_paths TEXT[],
                    status VARCHAR(20) DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'rejected', 'applied')),
                    reviewed_by VARCHAR(100),
                    reviewed_at TIMESTAMP,
                    applied_to_policy_version VARCHAR(50),
                    description TEXT,
                    notes TEXT
                )
            """))
            conn.execute(text("CREATE INDEX idx_learned_rules_status ON learned_rules(status)"))
            conn.execute(text("CREATE INDEX idx_learned_rules_confidence ON learned_rules(confidence_score DESC)"))
            conn.execute(text("CREATE INDEX idx_learned_rules_created_at ON learned_rules(created_at DESC)"))

        conn.commit()

    print("✓ Created learned_rules table")

    # Extend cleanup_candidates table
    print("Extending cleanup_candidates table...")
    with engine.connect() as conn:
        try:
            conn.execute(text("ALTER TABLE cleanup_candidates ADD COLUMN user_feedback TEXT"))
            print("✓ Added user_feedback column")
        except Exception as e:
            if "duplicate column" in str(e).lower() or "already exists" in str(e).lower():
                print("✓ user_feedback column already exists")
            else:
                print(f"Warning: {e}")

        try:
            conn.execute(text("ALTER TABLE cleanup_candidates ADD COLUMN learned_rule_id INTEGER REFERENCES learned_rules(id)"))
            print("✓ Added learned_rule_id column")
        except Exception as e:
            if "duplicate column" in str(e).lower() or "already exists" in str(e).lower():
                print("✓ learned_rule_id column already exists")
            else:
                print(f"Warning: {e}")

        try:
            conn.execute(text("CREATE INDEX idx_cleanup_candidates_learned_rule ON cleanup_candidates(learned_rule_id)"))
            print("✓ Created index on learned_rule_id")
        except Exception as e:
            if "already exists" in str(e).lower():
                print("✓ Index already exists")
            else:
                print(f"Warning: {e}")

        conn.commit()

    print("✅ BUILD-151 Phase 4 migration complete!")


def rollback():
    """Rollback migration (for testing)."""
    print("Rolling back BUILD-151 Phase 4 migration...")

    with engine.connect() as conn:
        # Drop index
        try:
            conn.execute(text("DROP INDEX IF EXISTS idx_cleanup_candidates_learned_rule"))
        except Exception:
            pass

        # Drop columns (PostgreSQL only - SQLite doesn't support DROP COLUMN easily)
        is_sqlite = 'sqlite' in str(engine.url)
        if not is_sqlite:
            try:
                conn.execute(text("ALTER TABLE cleanup_candidates DROP COLUMN IF EXISTS learned_rule_id"))
                conn.execute(text("ALTER TABLE cleanup_candidates DROP COLUMN IF EXISTS user_feedback"))
            except Exception:
                pass

        # Drop indexes on learned_rules
        try:
            conn.execute(text("DROP INDEX IF EXISTS idx_learned_rules_created_at"))
            conn.execute(text("DROP INDEX IF EXISTS idx_learned_rules_confidence"))
            conn.execute(text("DROP INDEX IF EXISTS idx_learned_rules_status"))
        except Exception:
            pass

        # Drop table
        try:
            conn.execute(text("DROP TABLE IF EXISTS learned_rules CASCADE"))
        except Exception:
            pass

        conn.commit()

    print("✓ Rollback complete")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--rollback":
        rollback()
    else:
        migrate()
