"""Tests for ROAD-B: Telemetry Analysis"""

import pytest
import sqlite3
import tempfile
from pathlib import Path
from datetime import datetime

from scripts.analyze_run_telemetry import TelemetryAnalyzer, write_analysis_report


@pytest.fixture
def temp_db():
    """Create temporary database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    # Create tables
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Create phase_outcome_events table
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS phase_outcome_events (
            id INTEGER PRIMARY KEY,
            phase_id TEXT NOT NULL,
            outcome TEXT NOT NULL,
            stop_reason TEXT,
            timestamp TEXT NOT NULL
        )
    """
    )

    # Create phases table
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS phases (
            id INTEGER PRIMARY KEY,
            phase_id TEXT NOT NULL,
            tokens_used INTEGER DEFAULT 0,
            created_at TEXT NOT NULL
        )
    """
    )

    conn.commit()
    conn.close()

    yield db_path

    # Cleanup
    Path(db_path).unlink(missing_ok=True)


class TestTelemetryAnalyzer:
    """Test telemetry analysis functionality."""

    def test_analyze_failures_empty(self, temp_db):
        """Test analyzing failures when no data exists."""
        with TelemetryAnalyzer(temp_db) as analyzer:
            failures = analyzer.analyze_failures()
            assert failures == []

    def test_analyze_failures_with_data(self, temp_db):
        """Test analyzing failures with sample data."""
        # Insert test data
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()

        now = datetime.now().isoformat()
        cursor.execute(
            """
            INSERT INTO phase_outcome_events
            (phase_id, outcome, stop_reason, timestamp)
            VALUES (?, ?, ?, ?)
        """,
            ("phase-001", "FAILED", "builder_crash", now),
        )

        cursor.execute(
            """
            INSERT INTO phase_outcome_events
            (phase_id, outcome, stop_reason, timestamp)
            VALUES (?, ?, ?, ?)
        """,
            ("phase-001", "FAILED", "builder_crash", now),
        )

        cursor.execute(
            """
            INSERT INTO phase_outcome_events
            (phase_id, outcome, stop_reason, timestamp)
            VALUES (?, ?, ?, ?)
        """,
            ("phase-002", "FAILED", "timeout", now),
        )

        conn.commit()
        conn.close()

        # Analyze
        with TelemetryAnalyzer(temp_db) as analyzer:
            failures = analyzer.analyze_failures()

        # Should have 2 failures (grouped by phase and reason)
        assert len(failures) > 0
        # First should be phase-001 with frequency 2
        first = failures[0]
        assert first["phase_id"] == "phase-001"
        assert first["frequency"] == 2

    def test_analyze_cost_sinks_empty(self, temp_db):
        """Test cost analysis with no data."""
        with TelemetryAnalyzer(temp_db) as analyzer:
            sinks = analyzer.analyze_cost_sinks()
            assert sinks == []

    def test_analyze_cost_sinks_with_data(self, temp_db):
        """Test cost analysis with sample data."""
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()

        now = datetime.now().isoformat()
        cursor.execute(
            """
            INSERT INTO phases (phase_id, tokens_used, created_at)
            VALUES (?, ?, ?)
        """,
            ("phase-001", 50000, now),
        )

        cursor.execute(
            """
            INSERT INTO phases (phase_id, tokens_used, created_at)
            VALUES (?, ?, ?)
        """,
            ("phase-001", 30000, now),
        )

        cursor.execute(
            """
            INSERT INTO phases (phase_id, tokens_used, created_at)
            VALUES (?, ?, ?)
        """,
            ("phase-002", 20000, now),
        )

        conn.commit()
        conn.close()

        # Analyze
        with TelemetryAnalyzer(temp_db) as analyzer:
            sinks = analyzer.analyze_cost_sinks()

        # phase-001 should be top cost sink
        assert len(sinks) > 0
        assert sinks[0]["phase_id"] == "phase-001"
        assert sinks[0]["total_tokens"] == 80000

    def test_generate_analysis_report(self, temp_db):
        """Test comprehensive report generation."""
        with TelemetryAnalyzer(temp_db) as analyzer:
            report = analyzer.generate_analysis_report(window_days=7, limit=10)

        assert "timestamp" in report
        assert "window_days" in report
        assert report["window_days"] == 7
        assert "top_failures" in report
        assert "top_cost_sinks" in report
        assert "top_retry_patterns" in report

    def test_write_analysis_report(self, temp_db):
        """Test report file writing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "analysis" / "report.md"

            with TelemetryAnalyzer(temp_db) as analyzer:
                report = analyzer.generate_analysis_report()

            write_analysis_report(report, output_path)

            # Check files were created
            assert output_path.exists()
            assert (output_path.with_suffix(".json")).exists()

            # Check markdown content
            content = output_path.read_text()
            assert "Telemetry Analysis Report" in content
            assert "Top Failure Modes" in content
            assert "Top Cost Sinks" in content


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
