import os


def test_memory_service_falls_back_to_faiss_when_qdrant_unreachable(monkeypatch):
    """
    If Qdrant is configured/available but unreachable, MemoryService should not crash the executor.
    It should fall back to FAISS (or other local backend) when configured to do so.
    """
    from autopack.memory import memory_service as ms

    # Force "Qdrant available" path and then make QdrantStore init fail.
    monkeypatch.setattr(ms, "QDRANT_AVAILABLE", True, raising=False)

    class BoomQdrantStore:
        def __init__(self, *args, **kwargs):
            raise ConnectionError("simulated connection failure")

    monkeypatch.setattr(ms, "QdrantStore", BoomQdrantStore, raising=True)

    # Ensure config doesn't disable memory.
    monkeypatch.delenv("AUTOPACK_ENABLE_MEMORY", raising=False)
    monkeypatch.delenv("AUTOPACK_USE_QDRANT", raising=False)

    service = ms.MemoryService(use_qdrant=True)
    assert service.enabled is True
    assert service.backend == "faiss"

    # Core API should remain safe even if store ops fail.
    assert service.search_code("x", project_id="p") == []


def test_memory_service_disabled_env(monkeypatch):
    from autopack.memory import memory_service as ms

    monkeypatch.setenv("AUTOPACK_ENABLE_MEMORY", "0")
    service = ms.MemoryService()
    assert service.enabled is False
    assert service.backend == "disabled"

    # Calls should be no-ops
    assert service.search_code("x", project_id="p") == []


def test_memory_service_autostarts_qdrant_then_uses_it(monkeypatch):
    """
    If autostart is enabled and Qdrant is localhost/unreachable, MemoryService should
    attempt autostart and then proceed with Qdrant when it becomes reachable.
    """
    from autopack.memory import memory_service as ms

    # Use Qdrant path
    monkeypatch.setattr(ms, "QDRANT_AVAILABLE", True, raising=False)

    # Enable autostart via env to avoid depending on config file values.
    monkeypatch.setenv("AUTOPACK_QDRANT_AUTOSTART", "1")
    monkeypatch.setenv("AUTOPACK_QDRANT_HOST", "localhost")
    monkeypatch.setenv("AUTOPACK_QDRANT_PORT", "6333")

    calls = {"n": 0}

    class FlakyQdrantStore:
        def __init__(self, *args, **kwargs):
            calls["n"] += 1
            # First attempt fails, second succeeds
            if calls["n"] == 1:
                raise ConnectionError("not running yet")

        def ensure_collection(self, name: str, size: int = 1536) -> None:  # noqa: ARG002
            return None

    monkeypatch.setattr(ms, "QdrantStore", FlakyQdrantStore, raising=True)

    # Pretend autostart succeeded
    monkeypatch.setattr(ms, "_autostart_qdrant_if_needed", lambda **kwargs: True, raising=True)

    service = ms.MemoryService(use_qdrant=True)
    assert service.backend == "qdrant"


