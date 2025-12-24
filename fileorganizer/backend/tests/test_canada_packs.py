"""Tests for Canada-specific pack templates (tax and immigration)."""

import os
import pytest
import yaml
from pathlib import Path


class TestCanadaPackSchema:
    """Test that Canada pack files conform to the required schema."""

    @pytest.fixture
    def packs_dir(self):
        """Get the packs directory path."""
        return Path(__file__).parent.parent / "packs"

    @pytest.fixture
    def tax_canada_pack(self, packs_dir):
        """Load the Canada tax pack YAML."""
        pack_path = packs_dir / "tax_canada.yaml"
        assert pack_path.exists(), f"Tax Canada pack not found at {pack_path}"
        with open(pack_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)

    @pytest.fixture
    def immigration_canada_pack(self, packs_dir):
        """Load the Canada immigration pack YAML."""
        pack_path = packs_dir / "immigration_canada.yaml"
        assert pack_path.exists(), f"Immigration Canada pack not found at {pack_path}"
        with open(pack_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)

    def test_tax_canada_required_fields(self, tax_canada_pack):
        """Test that tax_canada.yaml has all required top-level fields."""
        required_fields = ['name', 'description', 'version', 'country', 'domain', 
                          'categories', 'checklists', 'official_sources']
        for field in required_fields:
            assert field in tax_canada_pack, f"Missing required field: {field}"

    def test_immigration_canada_required_fields(self, immigration_canada_pack):
        """Test that immigration_canada.yaml has all required top-level fields."""
        required_fields = ['name', 'description', 'version', 'country', 'domain', 
                          'categories', 'checklists', 'official_sources']
        for field in required_fields:
            assert field in immigration_canada_pack, f"Missing required field: {field}"

    def test_tax_canada_country_and_domain(self, tax_canada_pack):
        """Test that tax pack has correct country and domain."""
        assert tax_canada_pack['country'] == 'Canada', "Country should be 'Canada'"
        assert tax_canada_pack['domain'] == 'tax', "Domain should be 'tax'"

    def test_immigration_canada_country_and_domain(self, immigration_canada_pack):
        """Test that immigration pack has correct country and domain."""
        assert immigration_canada_pack['country'] == 'Canada', "Country should be 'Canada'"
        assert immigration_canada_pack['domain'] == 'immigration', "Domain should be 'immigration'"

    def test_tax_canada_categories_structure(self, tax_canada_pack):
        """Test that tax pack categories have proper structure."""
        categories = tax_canada_pack['categories']
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

    def test_immigration_canada_categories_structure(self, immigration_canada_pack):
        """Test that immigration pack categories have proper structure."""
        categories = immigration_canada_pack['categories']
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

    def test_tax_canada_checklists_structure(self, tax_canada_pack):
        """Test that tax pack checklists have proper structure."""
        checklists = tax_canada_pack['checklists']
        assert isinstance(checklists, list), "Checklists should be a list"
        assert len(checklists) > 0, "Checklists list should not be empty"
        
        for checklist in checklists:
            assert 'name' in checklist, "Checklist missing 'name' field"
            assert 'required_documents' in checklist, "Checklist missing 'required_documents' field"
            assert isinstance(checklist['required_documents'], list), "Required documents should be a list"
            assert len(checklist['required_documents']) > 0, "Required documents list should not be empty"

    def test_immigration_canada_checklists_structure(self, immigration_canada_pack):
        """Test that immigration pack checklists have proper structure."""
        checklists = immigration_canada_pack['checklists']
        assert isinstance(checklists, list), "Checklists should be a list"
        assert len(checklists) > 0, "Checklists list should not be empty"
        
        for checklist in checklists:
            assert 'name' in checklist, "Checklist missing 'name' field"
            assert 'required_documents' in checklist, "Checklist missing 'required_documents' field"
            assert isinstance(checklist['required_documents'], list), "Required documents should be a list"
            assert len(checklist['required_documents']) > 0, "Required documents list should not be empty"

    def test_tax_canada_official_sources(self, tax_canada_pack):
        """Test that tax pack has valid official sources."""
        sources = tax_canada_pack['official_sources']
        assert isinstance(sources, list), "Official sources should be a list"
        assert len(sources) > 0, "Official sources list should not be empty"
        
        for source in sources:
            assert isinstance(source, str), "Each source should be a string"
            assert len(source) > 0, "Source should not be empty string"

    def test_immigration_canada_official_sources(self, immigration_canada_pack):
        """Test that immigration pack has valid official sources."""
        sources = immigration_canada_pack['official_sources']
        assert isinstance(sources, list), "Official sources should be a list"
        assert len(sources) > 0, "Official sources list should not be empty"
        
        for source in sources:
            assert isinstance(source, str), "Each source should be a string"
            assert len(source) > 0, "Source should not be empty string"

    def test_tax_canada_version_format(self, tax_canada_pack):
        """Test that tax pack version follows semantic versioning."""
        version = tax_canada_pack['version']
        assert isinstance(version, str), "Version should be a string"
        parts = version.split('.')
        assert len(parts) == 3, "Version should follow semantic versioning (X.Y.Z)"
        for part in parts:
            assert part.isdigit(), f"Version part '{part}' should be numeric"

    def test_immigration_canada_version_format(self, immigration_canada_pack):
        """Test that immigration pack version follows semantic versioning."""
        version = immigration_canada_pack['version']
        assert isinstance(version, str), "Version should be a string"
        parts = version.split('.')
        assert len(parts) == 3, "Version should follow semantic versioning (X.Y.Z)"
        for part in parts:
            assert part.isdigit(), f"Version part '{part}' should be numeric"


class TestCanadaPackContent:
    """Test the content quality and completeness of Canada packs."""

    @pytest.fixture
    def packs_dir(self):
        """Get the packs directory path."""
        return Path(__file__).parent.parent / "packs"

    @pytest.fixture
    def tax_canada_pack(self, packs_dir):
        """Load the Canada tax pack YAML."""
        with open(packs_dir / "tax_canada.yaml", 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)

    @pytest.fixture
    def immigration_canada_pack(self, packs_dir):
        """Load the Canada immigration pack YAML."""
        with open(packs_dir / "immigration_canada.yaml", 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)

    def test_tax_canada_has_t1_content(self, tax_canada_pack):
        """Test that tax pack includes T1 income tax return content."""
        all_text = str(tax_canada_pack).lower()
        assert 't1' in all_text, "Tax pack should include T1 content"

    def test_tax_canada_has_gst_hst_content(self, tax_canada_pack):
        """Test that tax pack includes GST/HST content."""
        all_text = str(tax_canada_pack).lower()
        assert 'gst' in all_text or 'hst' in all_text, "Tax pack should include GST/HST content"

    def test_tax_canada_has_rrsp_content(self, tax_canada_pack):
        """Test that tax pack includes RRSP content."""
        all_text = str(tax_canada_pack).lower()
        assert 'rrsp' in all_text, "Tax pack should include RRSP content"

    def test_immigration_canada_has_express_entry_content(self, immigration_canada_pack):
        """Test that immigration pack includes Express Entry content."""
        all_text = str(immigration_canada_pack).lower()
        assert 'express entry' in all_text, "Immigration pack should include Express Entry content"

    def test_immigration_canada_has_study_permit_content(self, immigration_canada_pack):
        """Test that immigration pack includes study permit content."""
        all_text = str(immigration_canada_pack).lower()
        assert 'study permit' in all_text, "Immigration pack should include study permit content"

    def test_immigration_canada_has_sponsorship_content(self, immigration_canada_pack):
        """Test that immigration pack includes family sponsorship content."""
        all_text = str(immigration_canada_pack).lower()
        assert 'sponsorship' in all_text, "Immigration pack should include sponsorship content"

    def test_tax_canada_categories_count(self, tax_canada_pack):
        """Test that tax pack has reasonable number of categories."""
        categories = tax_canada_pack['categories']
        assert len(categories) >= 3, "Tax pack should have at least 3 categories"
        assert len(categories) <= 10, "Tax pack should not have more than 10 categories"

    def test_immigration_canada_categories_count(self, immigration_canada_pack):
        """Test that immigration pack has reasonable number of categories."""
        categories = immigration_canada_pack['categories']
        assert len(categories) >= 3, "Immigration pack should have at least 3 categories"
        assert len(categories) <= 10, "Immigration pack should not have more than 10 categories"

    def test_tax_canada_checklists_count(self, tax_canada_pack):
        """Test that tax pack has reasonable number of checklists."""
        checklists = tax_canada_pack['checklists']
        assert len(checklists) >= 3, "Tax pack should have at least 3 checklists"
        assert len(checklists) <= 15, "Tax pack should not have more than 15 checklists"

    def test_immigration_canada_checklists_count(self, immigration_canada_pack):
        """Test that immigration pack has reasonable number of checklists."""
        checklists = immigration_canada_pack['checklists']
        assert len(checklists) >= 3, "Immigration pack should have at least 3 checklists"
        assert len(checklists) <= 15, "Immigration pack should not have more than 15 checklists"

    def test_tax_canada_official_sources_are_canada_ca(self, tax_canada_pack):
        """Test that tax pack official sources include canada.ca links."""
        sources = tax_canada_pack['official_sources']
        canada_ca_sources = [s for s in sources if 'canada.ca' in s.lower()]
        assert len(canada_ca_sources) > 0, "Tax pack should include canada.ca official sources"

    def test_immigration_canada_official_sources_are_canada_ca(self, immigration_canada_pack):
        """Test that immigration pack official sources include canada.ca links."""
        sources = immigration_canada_pack['official_sources']
        canada_ca_sources = [s for s in sources if 'canada.ca' in s.lower()]
        assert len(canada_ca_sources) > 0, "Immigration pack should include canada.ca official sources"

    def test_tax_canada_description_not_empty(self, tax_canada_pack):
        """Test that tax pack has meaningful description."""
        description = tax_canada_pack['description']
        assert len(description) > 20, "Description should be meaningful (>20 chars)"

    def test_immigration_canada_description_not_empty(self, immigration_canada_pack):
        """Test that immigration pack has meaningful description."""
        description = immigration_canada_pack['description']
        assert len(description) > 20, "Description should be meaningful (>20 chars)"

    def test_tax_canada_examples_not_generic(self, tax_canada_pack):
        """Test that tax pack examples are specific, not generic placeholders."""
        for category in tax_canada_pack['categories']:
            for example in category['examples']:
                assert 'example' not in example.lower() or len(example) > 15, \
                    f"Example '{example}' appears to be a generic placeholder"

    def test_immigration_canada_examples_not_generic(self, immigration_canada_pack):
        """Test that immigration pack examples are specific, not generic placeholders."""
        for category in immigration_canada_pack['categories']:
            for example in category['examples']:
                assert 'example' not in example.lower() or len(example) > 15, \
                    f"Example '{example}' appears to be a generic placeholder"

    def test_tax_canada_has_cra_references(self, tax_canada_pack):
        """Test that tax pack references CRA (Canada Revenue Agency)."""
        all_text = str(tax_canada_pack).lower()
        assert 'cra' in all_text or 'revenue agency' in all_text, \
            "Tax pack should reference CRA"

    def test_immigration_canada_has_ircc_references(self, immigration_canada_pack):
        """Test that immigration pack references IRCC."""
        sources_text = ' '.join(immigration_canada_pack['official_sources']).lower()
        assert 'immigration-refugees-citizenship' in sources_text, \
            "Immigration pack should reference IRCC in official sources"

    def test_tax_canada_has_t4_content(self, tax_canada_pack):
        """Test that tax pack includes T4 employment slip content."""
        all_text = str(tax_canada_pack).lower()
        assert 't4' in all_text, "Tax pack should include T4 content"

    def test_immigration_canada_has_lmia_content(self, immigration_canada_pack):
        """Test that immigration pack includes LMIA content for work permits."""
        all_text = str(immigration_canada_pack).lower()
        assert 'lmia' in all_text, "Immigration pack should include LMIA content"
