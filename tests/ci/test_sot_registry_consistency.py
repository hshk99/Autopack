import json
from pathlib import Path


def test_sot_registry_exists_and_has_required_fields():
    repo_root = Path(__file__).resolve().parent.parent.parent
    registry_path = repo_root / "config" / "sot_registry.json"
    assert registry_path.exists(), "config/sot_registry.json must exist"

    data = json.loads(registry_path.read_text(encoding="utf-8"))
    assert data.get("version") == 1
    assert "docs_sot_files" in data
    assert "protected_paths" in data


def test_sot_registry_docs_sot_files_matches_tidy():
    repo_root = Path(__file__).resolve().parent.parent.parent
    data = json.loads((repo_root / "config" / "sot_registry.json").read_text(encoding="utf-8"))
    registry_docs_sot = set(data["docs_sot_files"])

    from scripts.tidy.tidy_up import DOCS_SOT_FILES

    assert set(DOCS_SOT_FILES) == registry_docs_sot


def test_sot_registry_protected_paths_contains_all_docs_sot_files_plus_readme():
    repo_root = Path(__file__).resolve().parent.parent.parent
    data = json.loads((repo_root / "config" / "sot_registry.json").read_text(encoding="utf-8"))

    protected_paths = set(data["protected_paths"])
    assert "README.md" in protected_paths

    for sot_name in data["docs_sot_files"]:
        expected = f"docs/{sot_name}"
        assert expected in protected_paths, f"Missing protected SOT path: {expected}"
