from autopack.schemas import PhaseResponse


def test_phase_response_normalizes_plain_string_scope() -> None:
    phase = PhaseResponse.model_validate(
        {
            "id": 1,
            "phase_id": "P1",
            "run_id": "r1",
            "tier_id": 1,
            "name": "Phase",
            "description": None,
            "state": "QUEUED",
            "task_category": None,
            "complexity": None,
            "builder_mode": None,
            "phase_index": 0,
            "scope": "legacy scope text",
        }
    )
    assert phase.scope == {"_legacy_text": "legacy scope text"}


def test_phase_response_normalizes_json_string_scope() -> None:
    phase = PhaseResponse.model_validate(
        {
            "id": 1,
            "phase_id": "P1",
            "run_id": "r1",
            "tier_id": 1,
            "name": "Phase",
            "description": None,
            "state": "QUEUED",
            "task_category": None,
            "complexity": None,
            "builder_mode": None,
            "phase_index": 0,
            "scope": "{\"paths\": [\"README.md\"]}",
        }
    )
    assert phase.scope == {"paths": ["README.md"]}


