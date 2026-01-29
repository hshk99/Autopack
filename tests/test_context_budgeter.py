from autopack.context_budgeter import (get_embedding_stats,
                                       reset_embedding_cache,
                                       select_files_for_context,
                                       set_cache_persistence)


def test_budgeter_pins_deliverables_and_respects_budget():
    files = {
        "src/db.py": "def connect_db():\n    pass\n" * 200,  # large-ish
        "src/ui.tsx": "export const UI = () => null\n" * 200,
        "docs/huge.md": "lorem ipsum\n" * 5000,
    }
    scope_metadata = {
        "src/db.py": {"category": "modifiable"},
        "src/ui.tsx": {"category": "modifiable"},
        "docs/huge.md": {"category": "read_only"},
    }
    deliverables = ["src/db.py"]
    query = "database connection sqlite sqlalchemy"

    sel = select_files_for_context(
        files=files,
        scope_metadata=scope_metadata,
        deliverables=deliverables,
        query=query,
        budget_tokens=2000,  # too small for everything
        semantic=False,  # deterministic lexical mode in tests
    )

    assert "src/db.py" in sel.kept  # deliverable pinned
    assert sel.used_tokens_est <= sel.budget_tokens
    assert sel.mode == "lexical"


def test_budgeter_prefers_relevant_file_in_lexical_mode():
    files = {
        "src/db.py": "import sqlite3\n\ndef connect_db():\n    return sqlite3.connect(':memory:')\n",
        "src/ui.tsx": "export const Button = () => <button>OK</button>\n",
    }
    scope_metadata = {
        "src/db.py": {"category": "modifiable"},
        "src/ui.tsx": {"category": "modifiable"},
    }
    deliverables = []
    query = "sqlite database connect"

    sel = select_files_for_context(
        files=files,
        scope_metadata=scope_metadata,
        deliverables=deliverables,
        query=query,
        budget_tokens=20,  # force single-file selection
        semantic=False,
    )

    assert "src/db.py" in sel.kept
    assert "src/ui.tsx" not in sel.kept


def test_cache_persists_across_phases_when_enabled():
    """Verify embedding cache persists across phases when persistence is enabled."""
    # Ensure persistence is enabled (default)
    set_cache_persistence(True)

    # Reset cache
    reset_embedding_cache()

    # Phase 1: Select files (in lexical mode to avoid embedding API calls in tests)
    files1 = {
        "src/module1.py": "def func1():\n    pass\n" * 10,
    }
    select_files_for_context(
        files=files1,
        scope_metadata={},
        deliverables=[],
        query="function",
        budget_tokens=500,
        semantic=False,  # Use lexical mode to avoid API calls in tests
    )

    stats1 = get_embedding_stats()
    cache_size_after_phase1 = stats1["cache_size"]

    # Phase 2: Reset cache (should preserve cache when persistence is enabled)
    reset_embedding_cache()

    stats2 = get_embedding_stats()
    # Cache should be preserved
    assert stats2["cache_size"] == cache_size_after_phase1
    assert stats2["persist_cache"] is True

    # Cleanup: reset persistence to default
    set_cache_persistence(True)


def test_cache_reset_when_persistence_disabled():
    """Verify embedding cache is reset when persistence is disabled."""
    # Disable persistence
    set_cache_persistence(False)

    # Reset cache
    reset_embedding_cache()

    stats1 = get_embedding_stats()
    assert stats1["persist_cache"] is False

    # Phase 1: Select files (lexical mode)
    files1 = {
        "src/module1.py": "def func1():\n    pass\n" * 10,
    }
    select_files_for_context(
        files=files1,
        scope_metadata={},
        deliverables=[],
        query="function",
        budget_tokens=500,
        semantic=False,
    )

    # Phase 2: Reset cache (should clear cache when persistence is disabled)
    reset_embedding_cache()

    stats2 = get_embedding_stats()
    # Cache should be cleared
    assert stats2["cache_size"] == 0

    # Cleanup: reset persistence to default
    set_cache_persistence(True)


def test_cache_persistence_can_be_toggled():
    """Verify cache persistence can be toggled on and off."""
    # Start with persistence enabled
    set_cache_persistence(True)
    reset_embedding_cache()

    stats = get_embedding_stats()
    assert stats["persist_cache"] is True

    # Toggle to disabled
    set_cache_persistence(False)
    stats = get_embedding_stats()
    assert stats["persist_cache"] is False

    # Toggle back to enabled
    set_cache_persistence(True)
    stats = get_embedding_stats()
    assert stats["persist_cache"] is True
