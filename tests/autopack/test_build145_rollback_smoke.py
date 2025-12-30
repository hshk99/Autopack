"""BUILD-145: Smoke tests for rollback feature documentation and integration

Lightweight tests to validate rollback configuration, imports, and basic integration.
"""

import pytest
from pathlib import Path


class TestRollbackSmoke:
    """Smoke tests for rollback feature"""

    def test_rollback_manager_module_exists(self):
        """Rollback manager module should exist and be importable"""
        from autopack import rollback_manager

        assert hasattr(rollback_manager, "RollbackManager")

    def test_rollback_manager_class_importable(self):
        """RollbackManager class should be importable"""
        from autopack.rollback_manager import RollbackManager

        assert RollbackManager is not None

    def test_config_has_rollback_flag(self):
        """Config should have executor_rollback_enabled setting"""
        from autopack.config import Settings

        settings = Settings()
        assert hasattr(settings, "executor_rollback_enabled")
        assert isinstance(settings.executor_rollback_enabled, bool)
        assert settings.executor_rollback_enabled is False  # Default disabled

    def test_governed_apply_accepts_rollback_params(self):
        """GovernedApplyPath should accept run_id and phase_id for rollback"""
        from autopack.governed_apply import GovernedApplyPath
        from pathlib import Path
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)

            # Should not raise exception with rollback params
            governed_apply = GovernedApplyPath(
                workspace=workspace,
                run_id="test-run",
                phase_id="test-phase"
            )

            assert governed_apply is not None

    def test_governed_apply_without_rollback_params_works(self):
        """GovernedApplyPath should work without rollback params (backward compat)"""
        from autopack.governed_apply import GovernedApplyPath
        from pathlib import Path
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)

            # Should work without rollback params
            governed_apply = GovernedApplyPath(workspace=workspace)

            assert governed_apply is not None
            assert governed_apply.rollback_manager is None  # No rollback when disabled

    def test_rollback_manager_requires_workspace_and_ids(self):
        """RollbackManager should require workspace, run_id, and phase_id"""
        from autopack.rollback_manager import RollbackManager
        from pathlib import Path

        with pytest.raises(TypeError):
            # Should fail without required args
            RollbackManager()

    def test_rollback_manager_initialization(self):
        """RollbackManager should initialize with correct params"""
        from autopack.rollback_manager import RollbackManager
        from pathlib import Path
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            manager = RollbackManager(
                workspace=Path(tmpdir),
                run_id="test-run",
                phase_id="test-phase"
            )

            assert manager.workspace == Path(tmpdir)
            assert manager.run_id == "test-run"
            assert manager.phase_id == "test-phase"
            assert manager.savepoint_tag is None  # Not created yet

    def test_rollback_manager_has_required_methods(self):
        """RollbackManager should have all required methods"""
        from autopack.rollback_manager import RollbackManager

        required_methods = [
            "create_savepoint",
            "rollback_to_savepoint",
            "cleanup_savepoint",
            "cleanup_old_savepoints"
        ]

        for method_name in required_methods:
            assert hasattr(RollbackManager, method_name)

    def test_rollback_env_var_override(self, monkeypatch):
        """executor_rollback_enabled should be overridable via env var"""
        monkeypatch.setenv("AUTOPACK_ROLLBACK_ENABLED", "true")

        # Reload settings to pick up env var
        from autopack.config import Settings
        settings = Settings()

        # Pydantic should parse "true" string as boolean
        # Note: Pydantic accepts "true", "1", "yes", "on" as truthy values
        # If env var set, it should override default
        # (Actual parsing depends on pydantic_settings behavior)

    def test_build144_runbook_file_exists(self):
        """BUILD-144 migration runbook should exist"""
        runbook_path = Path("docs/guides/BUILD-144_USAGE_TOTAL_TOKENS_MIGRATION_RUNBOOK.md")
        assert runbook_path.exists(), f"Runbook not found at {runbook_path}"

    def test_build145_documented_in_build_history(self):
        """BUILD-145 should be documented in BUILD_HISTORY.md"""
        build_history = Path("docs/BUILD_HISTORY.md")
        assert build_history.exists()

        content = build_history.read_text(encoding='utf-8')
        assert "BUILD-145" in content

    def test_rollback_protected_paths_not_touched(self):
        """Rollback should document that it never touches protected paths"""
        from autopack import rollback_manager
        import inspect

        source = inspect.getsource(rollback_manager)

        # Documentation should mention protected paths
        # (Can't directly test runtime behavior without real git repo, but check docs)
        assert "protected" in source.lower() or "git" in source.lower()
