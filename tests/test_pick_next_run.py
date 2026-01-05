from scripts.pick_next_run import infer_run_type


def test_infer_run_type_autopack_maintenance() -> None:
    assert infer_run_type("build112-completion") == "autopack_maintenance"
    assert infer_run_type("autopack-followups-v1") == "autopack_maintenance"
    assert infer_run_type("BUILD-129-something") == "autopack_maintenance"


def test_infer_run_type_project_build() -> None:
    assert infer_run_type("research-system-v26") == "project_build"
    assert infer_run_type("fileorg-backend-fixes-v4-20251130") == "project_build"
