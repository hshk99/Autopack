"""Tests for UK-specific pack templates (tax and immigration)."""

import os
import pytest
import yaml
from pathlib import Path


class TestUKPackSchema:
    """Test that UK pack files conform to the required schema."""

    @pytest.fixture
    def packs_dir(self):
        """Get the packs directory path."""
        return Path(__file__).parent.parent / "packs"

    @pytest.fixture
    def tax_uk_pack(self, packs_dir):
        """Load the UK tax pack YAML."""
        pack_path = packs_dir / "tax_uk.yaml"
        assert pack_path.exists(), f"Tax UK pack not found at {pack_path}"
        with open(pack_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)

    @pytest.fixture
    def immigration_uk_pack(self, packs_dir):
        """Load the UK immigration pack YAML."""
        pack_path = packs_dir / "immigration_uk.yaml"
        assert pack_path.exists(), f"Immigration UK pack not found at {pack_path}"
        with open(pack_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)

    def test_tax_uk_required_fields(self, tax_uk_pack):
        """Test that tax_uk.yaml has all required top-level fields."""
        required_fields = ['name', 'description', 'version', 'country', 'domain', 
                          'categories', 'checklists', 'official_sources']
        for field in required_fields:
            assert field in tax_uk_pack, f"Missing required field: {field}"

    def test_immigration_uk_required_fields(self, immigration_uk_pack):
        """Test that immigration_uk.yaml has all required top-level fields."""
        required_fields = ['name', 'description', 'version', 'country', 'domain', 
                          'categories', 'checklists', 'official_sources']
        for field in required_fields:
            assert field in immigration_uk_pack, f"Missing required field: {field}"

    def test_tax_uk_country_and_domain(self, tax_uk_pack):
        """Test that tax pack has correct country and domain."""
        assert tax_uk_pack['country'] == 'UK', "Country should be 'UK'"
        assert tax_uk_pack['domain'] == 'tax', "Domain should be 'tax'"

    def test_immigration_uk_country_and_domain(self, immigration_uk_pack):
        """Test that immigration pack has correct country and domain."""
        assert immigration_uk_pack['country'] == 'UK', "Country should be 'UK'"
        assert immigration_uk_pack['domain'] == 'immigration', "Domain should be 'immigration'"

    def test_tax_uk_categories_structure(self, tax_uk_pack):
        """Test that tax pack categories have proper structure."""
        categories = tax_uk_pack['categories']
        assert isinstance(categories, list), "Categories should be a list"
        assert len(categories) > 0, "Categories list should not be empty"
        
        category_names = set()
        for category in categories:
            assert 'name' in category, "Category missing 'name' field"
            assert 'description' in category, "Category missing 'description' field"
            assert 'examples' in category, "Category missing 'examples' field"
            assert isinstance(category['examples'], list), "Examples should be a list"
            assert len(category['examples']) > 0, "Examples list should not be empty"
            
            # Check for duplicate category names
            assert category['name'] not in category_names, f"Duplicate category name: {category['name']}"
            category_names.add(category['name'])

    def test_immigration_uk_categories_structure(self, immigration_uk_pack):
        """Test that immigration pack categories have proper structure."""
        categories = immigration_uk_pack['categories']
        assert isinstance(categories, list), "Categories should be a list"
        assert len(categories) > 0, "Categories list should not be empty"
        
        category_names = set()
        for category in categories:
            assert 'name' in category, "Category missing 'name' field"
            assert 'description' in category, "Category missing 'description' field"
            assert 'examples' in category, "Category missing 'examples' field"
            assert isinstance(category['examples'], list), "Examples should be a list"
            assert len(category['examples']) > 0, "Examples list should not be empty"
            
            # Check for duplicate category names
            assert category['name'] not in category_names, f"Duplicate category name: {category['name']}"
            category_names.add(category['name'])

    def test_tax_uk_checklists_structure(self, tax_uk_pack):
        """Test that tax pack checklists have proper structure."""
        checklists = tax_uk_pack['checklists']
        assert isinstance(checklists, list), "Checklists should be a list"
        assert len(checklists) > 0, "Checklists list should not be empty"
        
        for checklist in checklists:
            assert 'name' in checklist, "Checklist missing 'name' field"
            assert 'required_documents' in checklist, "Checklist missing 'required_documents' field"
            assert isinstance(checklist['required_documents'], list), "Required documents should be a list"
            assert len(checklist['required_documents']) > 0, "Required documents list should not be empty"

    def test_immigration_uk_checklists_structure(self, immigration_uk_pack):
        """Test that immigration pack checklists have proper structure."""
        checklists = immigration_uk_pack['checklists']
        assert isinstance(checklists, list), "Checklists should be a list"
        assert len(checklists) > 0, "Checklists list should not be empty"
        
        for checklist in checklists:
            assert 'name' in checklist, "Checklist missing 'name' field"
            assert 'required_documents' in checklist, "Checklist missing 'required_documents' field"
            assert isinstance(checklist['required_documents'], list), "Required documents should be a list"
            assert len(checklist['required_documents']) > 0, "Required documents list should not be empty"

    def test_tax_uk_official_sources(self, tax_uk_pack):
        """Test that tax pack has valid official sources."""
        sources = tax_uk_pack['official_sources']
        assert isinstance(sources, list), "Official sources should be a list"
        assert len(sources) > 0, "Official sources list should not be empty"
        
        for source in sources:
            assert isinstance(source, str), "Each source should be a string"
            assert len(source) > 0, "Source should not be empty string"

    def test_immigration_uk_official_sources(self, immigration_uk_pack):
        """Test that immigration pack has valid official sources."""
        sources = immigration_uk_pack['official_sources']
        assert isinstance(sources, list), "Official sources should be a list"
        assert len(sources) > 0, "Official sources list should not be empty"
        
        for source in sources:
            assert isinstance(source, str), "Each source should be a string"
            assert len(source) > 0, "Source should not be empty string"

    def test_tax_uk_version_format(self, tax_uk_pack):
        """Test that tax pack version follows semantic versioning."""
        version = tax_uk_pack['version']
        assert isinstance(version, str), "Version should be a string"
        parts = version.split('.')
        assert len(parts) == 3, "Version should follow semantic versioning (X.Y.Z)"
        for part in parts:
            assert part.isdigit(), f"Version part '{part}' should be numeric"

    def test_immigration_uk_version_format(self, immigration_uk_pack):
        """Test that immigration pack version follows semantic versioning."""
        version = immigration_uk_pack['version']
        assert isinstance(version, str), "Version should be a string"
        parts = version.split('.')
        assert len(parts) == 3, "Version should follow semantic versioning (X.Y.Z)"
        for part in parts:
            assert part.isdigit(), f"Version part '{part}' should be numeric"


class TestUKPackContent:
    """Test the content quality and completeness of UK packs."""

    @pytest.fixture
    def packs_dir(self):
        """Get the packs directory path."""
        return Path(__file__).parent.parent / "packs"

    @pytest.fixture
    def tax_uk_pack(self, packs_dir):
        """Load the UK tax pack YAML."""
        with open(packs_dir / "tax_uk.yaml", 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)

    @pytest.fixture
    def immigration_uk_pack(self, packs_dir):
        """Load the UK immigration pack YAML."""
        with open(packs_dir / "immigration_uk.yaml", 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)

    def test_tax_uk_has_self_assessment_checklist(self, tax_uk_pack):
        """Test that tax pack includes Self Assessment checklist."""
        checklist_names = [c['name'] for c in tax_uk_pack['checklists']]
        assert any('Self Assessment' in name for name in checklist_names), \
            "Tax pack should include Self Assessment checklist"

    def test_tax_uk_has_vat_content(self, tax_uk_pack):
        """Test that tax pack includes VAT-related content."""
        all_text = str(tax_uk_pack).lower()
        assert 'vat' in all_text, "Tax pack should include VAT content"

    def test_immigration_uk_has_skilled_worker_content(self, immigration_uk_pack):
        """Test that immigration pack includes Skilled Worker visa content."""
        all_text = str(immigration_uk_pack).lower()
        assert 'skilled worker' in all_text, "Immigration pack should include Skilled Worker content"

    def test_immigration_uk_has_settlement_content(self, immigration_uk_pack):
        """Test that immigration pack includes settlement/ILR content."""
        all_text = str(immigration_uk_pack).lower()
        assert any(term in all_text for term in ['settlement', 'indefinite leave', 'ilr']), \
            "Immigration pack should include settlement content"

    def test_tax_uk_categories_count(self, tax_uk_pack):
        """Test that tax pack has reasonable number of categories."""
        categories = tax_uk_pack['categories']
        assert len(categories) >= 3, "Tax pack should have at least 3 categories"
        assert len(categories) <= 10, "Tax pack should not have more than 10 categories"

    def test_immigration_uk_categories_count(self, immigration_uk_pack):
        """Test that immigration pack has reasonable number of categories."""
        categories = immigration_uk_pack['categories']
        assert len(categories) >= 3, "Immigration pack should have at least 3 categories"
        assert len(categories) <= 10, "Immigration pack should not have more than 10 categories"

    def test_tax_uk_checklists_count(self, tax_uk_pack):
        """Test that tax pack has reasonable number of checklists."""
        checklists = tax_uk_pack['checklists']
        assert len(checklists) >= 3, "Tax pack should have at least 3 checklists"
        assert len(checklists) <= 15, "Tax pack should not have more than 15 checklists"

    def test_immigration_uk_checklists_count(self, immigration_uk_pack):
        """Test that immigration pack has reasonable number of checklists."""
        checklists = immigration_uk_pack['checklists']
        assert len(checklists) >= 3, "Immigration pack should have at least 3 checklists"
        assert len(checklists) <= 15, "Immigration pack should not have more than 15 checklists"

    def test_tax_uk_official_sources_are_gov_uk(self, tax_uk_pack):
        """Test that tax pack official sources include gov.uk links."""
        sources = tax_uk_pack['official_sources']
        gov_uk_sources = [s for s in sources if 'gov.uk' in s.lower()]
        assert len(gov_uk_sources) > 0, "Tax pack should include gov.uk official sources"

    def test_immigration_uk_official_sources_are_gov_uk(self, immigration_uk_pack):
        """Test that immigration pack official sources include gov.uk links."""
        sources = immigration_uk_pack['official_sources']
        gov_uk_sources = [s for s in sources if 'gov.uk' in s.lower()]
        assert len(gov_uk_sources) > 0, "Immigration pack should include gov.uk official sources"

    def test_tax_uk_description_not_empty(self, tax_uk_pack):
        """Test that tax pack has meaningful description."""
        description = tax_uk_pack['description']
        assert len(description) > 20, "Description should be meaningful (>20 chars)"

    def test_immigration_uk_description_not_empty(self, immigration_uk_pack):
        """Test that immigration pack has meaningful description."""
        description = immigration_uk_pack['description']
        assert len(description) > 20, "Description should be meaningful (>20 chars)"

    def test_tax_uk_examples_not_generic(self, tax_uk_pack):
        """Test that tax pack examples are specific, not generic placeholders."""
        for category in tax_uk_pack['categories']:
            for example in category['examples']:
                assert 'example' not in example.lower() or len(example) > 15, \
                    f"Example '{example}' appears to be a generic placeholder"

    def test_immigration_uk_examples_not_generic(self, immigration_uk_pack):
        """Test that immigration pack examples are specific, not generic placeholders."""
        for category in immigration_uk_pack['categories']:
            for example in category['examples']:
                assert 'example' not in example.lower() or len(example) > 15, \
                    f"Example '{example}' appears to be a generic placeholder"
