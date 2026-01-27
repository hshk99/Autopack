import json
import time
from pathlib import Path

from fastapi.testclient import TestClient

from autopack.config import settings
from autopack.dashboard.server import create_dashboard_app


class _StubUsageRecorder:
    def get_summary(self):
        return {"doctor_stats": {}}


def _client_with_runs(tmp_path: Path) -> TestClient:
    # Point autonomous_runs_dir at a temp location for the test
    settings.autonomous_runs_dir = str(tmp_path)
    return TestClient(create_dashboard_app(_StubUsageRecorder()))


def test_latest_diagnostics_returns_placeholder_when_empty(tmp_path: Path):
    client = _client_with_runs(tmp_path)
    resp = client.get("/api/diagnostics/latest")
    assert resp.status_code == 200
    data = resp.json()
    assert data["run_id"] is None
    assert data["ledger"] == "No diagnostics available"


def test_latest_diagnostics_returns_newest_summary(tmp_path: Path):
    client = _client_with_runs(tmp_path)
    run1 = tmp_path / "run1" / "diagnostics"
    run2 = tmp_path / "run2" / "diagnostics"
    run1.mkdir(parents=True)
    run2.mkdir(parents=True)

    summary1 = {
        "failure_class": "patch_apply_error",
        "phase_id": "p1",
        "ledger": "first",
        "probes": [{"name": "probe1", "commands": ["cmd1"], "resolved": False}],
        "timestamp": time.time() - 100,
    }
    summary2 = {
        "failure_class": "ci_fail",
        "phase_id": "p2",
        "ledger": "latest",
        "probes": [{"name": "probe2", "commands": ["cmd2"], "resolved": True}],
        "timestamp": time.time(),
    }
    (run1 / "diagnostic_summary.json").write_text(json.dumps(summary1))
    time.sleep(0.01)
    (run2 / "diagnostic_summary.json").write_text(json.dumps(summary2))

    resp = client.get("/api/diagnostics/latest")
    assert resp.status_code == 200
    data = resp.json()
    assert data["run_id"] == "run2"
    assert data["failure_class"] == "ci_fail"
    assert data["ledger"] == "latest"
    assert data["probes"][0]["name"] == "probe2"


def test_latest_diagnostics_handles_corrupt_json(tmp_path: Path):
    client = _client_with_runs(tmp_path)
    run = tmp_path / "run_bad" / "diagnostics"
    run.mkdir(parents=True)
    (run / "diagnostic_summary.json").write_text("{bad json")

    resp = client.get("/api/diagnostics/latest")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ledger"] == "Diagnostics summary unreadable"
