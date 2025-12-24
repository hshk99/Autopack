from autopack.context_budgeter import select_files_for_context


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


