"""
Smoke test for tidy module imports.

Prevents regression of relative vs absolute import issues.
Ensures all tidy modules can be imported as tidy_up.py does.
"""

import sys
from pathlib import Path


def test_tidy_imports():
    """Test that all tidy modules can be imported as tidy_up.py does."""
    repo = Path(__file__).resolve().parents[2]
    tidy_dir = repo / "scripts" / "tidy"

    # Add to path exactly as tidy_up.py does
    original_path = sys.path.copy()
    sys.path.insert(0, str(tidy_dir))

    try:
        # Import core tidy modules (these should not raise ImportError)
        import autonomous_runs_cleaner  # noqa: F401
        import io_utils  # noqa: F401
        import lease  # noqa: F401
        import pending_moves  # noqa: F401

        # Verify key classes/functions exist
        assert hasattr(pending_moves, "PendingMovesQueue"), "PendingMovesQueue class missing"
        assert hasattr(pending_moves, "retry_pending_moves"), "retry_pending_moves function missing"
        assert hasattr(io_utils, "atomic_write_json"), "atomic_write_json function missing"
        assert hasattr(lease, "Lease"), "Lease class missing"
        assert hasattr(autonomous_runs_cleaner, "cleanup_autonomous_runs"), (
            "cleanup_autonomous_runs function missing"
        )

    finally:
        # Clean up sys.path
        sys.path = original_path


def test_tidy_cross_module_imports():
    """Test that tidy modules can import from each other correctly."""
    repo = Path(__file__).resolve().parents[2]
    tidy_dir = repo / "scripts" / "tidy"

    original_path = sys.path.copy()
    sys.path.insert(0, str(tidy_dir))

    try:
        # Import pending_moves which depends on io_utils
        import tempfile

        import pending_moves

        # Verify that pending_moves successfully imported io_utils
        # (if import failed, PendingMovesQueue would not be usable)
        with tempfile.TemporaryDirectory() as tmpdir:
            queue_file = Path(tmpdir) / "queue.json"
            workspace = Path(tmpdir) / "workspace"
            queue = pending_moves.PendingMovesQueue(queue_file=queue_file, workspace_root=workspace)
            assert queue is not None, (
                "PendingMovesQueue instantiation failed (cross-module import issue)"
            )

    finally:
        sys.path = original_path


def test_no_relative_imports_in_tidy():
    """Test that tidy modules don't use relative imports that break when run as scripts."""
    repo = Path(__file__).resolve().parents[2]
    tidy_dir = repo / "scripts" / "tidy"

    # Check pending_moves.py for relative imports
    pending_moves_path = tidy_dir / "pending_moves.py"
    content = pending_moves_path.read_text(encoding="utf-8")

    # Should not contain "from .io_utils import"
    assert "from .io_utils import" not in content, (
        "pending_moves.py contains relative import (from .io_utils) - use 'from io_utils import' instead"
    )

    # Check other critical modules
    for module_name in ["io_utils.py", "lease.py"]:
        module_path = tidy_dir / module_name
        if module_path.exists():
            module_content = module_path.read_text(encoding="utf-8")
            # Check for relative imports pattern: "from ."
            relative_import_pattern = "from ."
            assert relative_import_pattern not in module_content, (
                f"{module_name} contains relative import - use absolute imports instead"
            )
