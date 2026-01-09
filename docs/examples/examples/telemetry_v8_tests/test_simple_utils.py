"""Simple utility function tests for telemetry v8 examples.

This module contains minimal unit tests demonstrating basic pytest usage
for utility functions like string formatting, path normalization, and
list deduplication.
"""



def format_phase_name(phase_id: str, category: str) -> str:
    """Format a phase name from ID and category.
    
    Args:
        phase_id: The phase identifier (e.g., 'telemetry-v8-d1')
        category: The phase category (e.g., 'docs', 'tests')
    
    Returns:
        Formatted phase name string
    """
    return f"{phase_id}:{category}"


def normalize_path(path: str) -> str:
    """Normalize a file path to use forward slashes.
    
    Args:
        path: Input path with any separator style
    
    Returns:
        Normalized path with forward slashes
    """
    return path.replace("\\", "/").rstrip("/")


def deduplicate_list(items: list) -> list:
    """Remove duplicates from a list while preserving order.
    
    Args:
        items: Input list that may contain duplicates
    
    Returns:
        List with duplicates removed, order preserved
    """
    seen = set()
    result = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


# Test cases

def test_format_phase_name():
    """Test phase name formatting."""
    assert format_phase_name("telemetry-v8-d1", "docs") == "telemetry-v8-d1:docs"
    assert format_phase_name("phase-123", "tests") == "phase-123:tests"
    assert format_phase_name("", "category") == ":category"


def test_normalize_path():
    """Test path normalization."""
    assert normalize_path("examples\\telemetry_v8_tests") == "examples/telemetry_v8_tests"
    assert normalize_path("src/autopack/core.py") == "src/autopack/core.py"
    assert normalize_path("path/to/dir/") == "path/to/dir"
    assert normalize_path("mixed\\path/style\\") == "mixed/path/style"


def test_deduplicate_list():
    """Test list deduplication while preserving order."""
    assert deduplicate_list([1, 2, 3, 2, 1]) == [1, 2, 3]
    assert deduplicate_list(["a", "b", "a", "c"]) == ["a", "b", "c"]
    assert deduplicate_list([]) == []
    assert deduplicate_list([1, 1, 1]) == [1]
