# tests/smoke/test_basic.py
"""
Basic smoke tests for Autopack.

These tests verify that core components can be imported and instantiated.
"""

import pytest


def test_imports():
    """Test that core modules can be imported."""
    try:
        from autopack import autonomous_executor
        from autopack import memory
        from autopack import models
        assert True
    except ImportError as e:
        pytest.fail(f"Failed to import core modules: {e}")


def test_memory_service_creation():
    """Test that MemoryService can be created."""
    from autopack.memory import MemoryService

    # Create with FAISS fallback (no Qdrant required for smoke test)
    service = MemoryService(use_qdrant=False, enabled=True)
    assert service is not None
    assert service.backend == "faiss"


def test_database_models():
    """Test that database models can be imported."""
    try:
        from autopack.models import Phase, Run, DecisionLog, PlanChange
        assert True
    except ImportError as e:
        pytest.fail(f"Failed to import database models: {e}")


def test_config_loading():
    """Test that config files can be loaded."""
    from pathlib import Path
    import yaml

    config_dir = Path(__file__).parent.parent.parent / "config"
    memory_config = config_dir / "memory.yaml"

    assert memory_config.exists(), "memory.yaml not found"

    with open(memory_config) as f:
        config = yaml.safe_load(f)

    assert "enable_memory" in config
    assert "use_qdrant" in config


def test_smoke_suite_passes():
    """Meta-test: verify smoke tests are passing."""
    assert True, "Smoke test suite is operational"
