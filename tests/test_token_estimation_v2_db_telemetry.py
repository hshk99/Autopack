import json

from sqlalchemy import create_engine
from sqlalchemy import event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


def test_token_estimation_v2_db_write_stores_ratio_semantics(monkeypatch):
    """
    Regression test:
    - Telemetry DB write is enabled via TELEMETRY_DB_ENABLED
    - waste_ratio is stored as a float ratio (predicted/actual), not a percent-int
    - smape_percent is stored as a float percent
    """
    # Enable feature flag
    monkeypatch.setenv("TELEMETRY_DB_ENABLED", "1")

    # Patch SessionLocal in the module under test to use an in-memory DB
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    # Ensure FK constraints are enforced in SQLite
    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    # Import Base + models after engine created
    from autopack.database import Base
    from autopack.models import Run, Tier, Phase, TokenEstimationV2Event
    import autopack.anthropic_clients as anthropic_clients
    import autopack.database as autopack_database

    Base.metadata.create_all(bind=engine)

    # Create minimal run/tier/phase row so the composite FK (run_id, phase_id) is satisfied
    session = TestingSessionLocal()
    try:
        run = Run(id="run-1")
        session.add(run)
        session.flush()

        tier = Tier(tier_id="T1", run_id="run-1", tier_index=0, name="Tier", description=None)
        session.add(tier)
        session.flush()

        phase = Phase(
            phase_id="P1",
            run_id="run-1",
            tier_id=tier.id,
            phase_index=0,
            name="Phase",
            description=None,
        )
        session.add(phase)
        session.commit()
    finally:
        session.close()

    # Monkeypatch the SessionLocal used by _write_token_estimation_v2_telemetry()
    # (it imports SessionLocal from autopack.database at call time)
    monkeypatch.setattr(autopack_database, "SessionLocal", TestingSessionLocal, raising=True)

    # Call helper
    anthropic_clients._write_token_estimation_v2_telemetry(
        run_id="run-1",
        phase_id="P1",
        category="implementation",
        complexity="maintenance",
        deliverables=["src/x.py"],
        predicted_output_tokens=250,
        actual_output_tokens=100,
        selected_budget=512,
        success=True,
        truncated=False,
        stop_reason=None,
        model="test-model",
    )

    # Assert DB row exists and semantics are correct
    session = TestingSessionLocal()
    try:
        rows = session.query(TokenEstimationV2Event).all()
        assert len(rows) == 1
        e = rows[0]
        assert json.loads(e.deliverables_json) == ["src/x.py"]
        assert e.waste_ratio == 2.5
        assert 85.0 < e.smape_percent < 90.0  # smape between 250 and 100 is 85.714...
    finally:
        session.close()


