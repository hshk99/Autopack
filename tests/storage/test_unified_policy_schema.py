from pathlib import Path

import yaml

from autopack.storage_optimizer.policy import load_policy


def test_unified_policy_file_schema_has_required_sections():
    policy_path = Path("config/protection_and_retention_policy.yaml")
    assert policy_path.exists()

    data = yaml.safe_load(policy_path.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    assert "protected_paths" in data
    assert "categories" in data

    # node_modules should NOT be an absolute protection (it's a cleanup category)
    protected_paths = data.get("protected_paths") or {}
    for v in protected_paths.values():
        if isinstance(v, list):
            assert not any("node_modules" in str(x) for x in v)

    categories = data.get("categories") or {}
    for cat_name, cat_data in categories.items():
        assert "patterns" in cat_data, f"{cat_name} missing patterns"
        assert "allowed_actions" in cat_data, f"{cat_name} missing allowed_actions"


def test_storage_optimizer_load_policy_defaults_to_unified_policy():
    policy = load_policy()
    assert policy.version
    # Key categories expected by docs/architecture
    assert "dev_caches" in policy.categories
    assert "diagnostics_logs" in policy.categories
    assert "runs" in policy.categories
    assert "archive_buckets" in policy.categories

    # Ensure node_modules is treated as a cleanup candidate category, not protected
    assert any("node_modules" in p for p in policy.categories["dev_caches"].match_globs)
