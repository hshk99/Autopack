"""Tests for Canada tax and immigration pack YAML validation."""

import pytest
import yaml
from pathlib import Path


class TestCanadaTaxPack:
    """Tests for Canada tax pack YAML structure and content."""

    @pytest.fixture
    def tax_pack(self):
        """Load the Canada tax pack YAML."""
        pack_path = Path(__file__).parent.parent.parent.parent / "src" / "backend" / "packs" / "tax_canada.yaml"
        with open(pack_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    def test_required_top_level_keys(self, tax_pack):
        """Test that all required top-level keys are present."""
        required_keys = ["name", "description", "version", "country", "domain", "categories", "checklists", "official_sources"]
        for key in required_keys:
            assert key in tax_pack, f"Missing required key: {key}"

    def test_country_is_canada(self, tax_pack):
        """Test that country is set to CA."""
        assert tax_pack["country"] == "CA"

    def test_domain_is_tax(self, tax_pack):
        """Test that domain is set to tax."""
        assert tax_pack["domain"] == "tax"

    def test_categories_non_empty(self, tax_pack):
        """Test that categories list is non-empty."""
        assert len(tax_pack["categories"]) > 0

    def test_category_structure(self, tax_pack):
        """Test that each category has required fields."""
        for category in tax_pack["categories"]:
            assert "name" in category, "Category missing name"
            assert "description" in category, "Category missing description"
            assert "examples" in category, "Category missing examples"
            assert len(category["examples"]) > 0, f"Category {category['name']} has no examples"

    def test_no_duplicate_category_names(self, tax_pack):
        """Test that there are no duplicate category names."""
        names = [cat["name"] for cat in tax_pack["categories"]]
        assert len(names) == len(set(names)), "Duplicate category names found"

    def test_checklists_non_empty(self, tax_pack):
        """Test that checklists list is non-empty."""
        assert len(tax_pack["checklists"]) > 0

    def test_checklist_structure(self, tax_pack):
        """Test that each checklist has required fields."""
        for checklist in tax_pack["checklists"]:
            assert "name" in checklist, "Checklist missing name"
            assert "required_documents" in checklist, "Checklist missing required_documents"
            assert len(checklist["required_documents"]) > 0, f"Checklist {checklist['name']} has no required documents"

    def test_official_sources_non_empty(self, tax_pack):
        """Test that official_sources list is non-empty."""
        assert len(tax_pack["official_sources"]) > 0

    def test_official_sources_are_urls(self, tax_pack):
        """Test that official sources are valid URLs."""
        for source in tax_pack["official_sources"]:
            assert source.startswith("http"), f"Invalid URL: {source}"

    def test_cra_category_exists(self, tax_pack):
        """Test that CRA Tax Forms category exists."""
        category_names = [cat["name"] for cat in tax_pack["categories"]]
        assert "CRA Tax Forms" in category_names

    def test_version_format(self, tax_pack):
        """Test that version follows semantic versioning."""
        version = tax_pack["version"]
        parts = version.split(".")
        assert len(parts) == 3, "Version should be in X.Y.Z format"


class TestCanadaImmigrationPack:
    """Tests for Canada immigration pack YAML structure and content."""

    @pytest.fixture
    def immigration_pack(self):
        """Load the Canada immigration pack YAML."""
        pack_path = Path(__file__).parent.parent.parent.parent / "src" / "backend" / "packs" / "immigration_canada.yaml"
        with open(pack_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    def test_required_top_level_keys(self, immigration_pack):
        """Test that all required top-level keys are present."""
        required_keys = ["name", "description", "version", "country", "domain", "categories", "checklists", "official_sources"]
        for key in required_keys:
            assert key in immigration_pack, f"Missing required key: {key}"

    def test_country_is_canada(self, immigration_pack):
        """Test that country is set to CA."""
        assert immigration_pack["country"] == "CA"

    def test_domain_is_immigration(self, immigration_pack):
        """Test that domain is set to immigration."""
        assert immigration_pack["domain"] == "immigration"

    def test_categories_non_empty(self, immigration_pack):
        """Test that categories list is non-empty."""
        assert len(immigration_pack["categories"]) > 0

    def test_category_structure(self, immigration_pack):
        """Test that each category has required fields."""
        for category in immigration_pack["categories"]:
            assert "name" in category, "Category missing name"
            assert "description" in category, "Category missing description"
            assert "examples" in category, "Category missing examples"
            assert len(category["examples"]) > 0, f"Category {category['name']} has no examples"

    def test_no_duplicate_category_names(self, immigration_pack):
        """Test that there are no duplicate category names."""
        names = [cat["name"] for cat in immigration_pack["categories"]]
        assert len(names) == len(set(names)), "Duplicate category names found"

    def test_checklists_non_empty(self, immigration_pack):
        """Test that checklists list is non-empty."""
        assert len(immigration_pack["checklists"]) > 0

    def test_checklist_structure(self, immigration_pack):
        """Test that each checklist has required fields."""
        for checklist in immigration_pack["checklists"]:
            assert "name" in checklist, "Checklist missing name"
            assert "required_documents" in checklist, "Checklist missing required_documents"
            assert len(checklist["required_documents"]) > 0, f"Checklist {checklist['name']} has no required documents"

    def test_official_sources_non_empty(self, immigration_pack):
        """Test that official_sources list is non-empty."""
        assert len(immigration_pack["official_sources"]) > 0

    def test_official_sources_are_urls(self, immigration_pack):
        """Test that official sources are valid URLs."""
        for source in immigration_pack["official_sources"]:
            assert source.startswith("http"), f