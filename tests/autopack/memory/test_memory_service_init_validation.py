import pytest


def test_memory_service_rejects_index_dir_that_is_a_file(tmp_path, monkeypatch):
    """
    MemoryService passes index_dir through to FaissStore, which will mkdir() the path.
    If the path already exists as a file, mkdir() should fail deterministically.
    """
    monkeypatch.setenv("AUTOPACK_ENABLE_MEMORY", "true")
    monkeypatch.setenv("AUTOPACK_USE_QDRANT", "false")

    bad_path = tmp_path / "not_a_directory"
    bad_path.write_text("I am a file, not a directory", encoding="utf-8")

    from autopack.memory.memory_service import MemoryService

    with pytest.raises((FileExistsError, NotADirectoryError, OSError)):
        MemoryService(index_dir=str(bad_path), use_qdrant=False, enabled=True)


