import unittest
from autopack.research.reporting.citation_formatter import CitationFormatter

class TestCitationFormatter(unittest.TestCase):

    def setUp(self):
        self.formatter = CitationFormatter()

    def test_format_apa(self):
        citation_data = {
            "author": "Doe, J.",
            "year": "2023",
            "title": "Research on Market Trends"
        }
        formatted = self.formatter.format(citation_data)
        expected = "Doe, J. (2023). Research on Market Trends."
        self.assertEqual(formatted, expected)

    def test_format_with_missing_data(self):
        citation_data = {
            "author": "Doe, J.",
            "year": "2023"
        }
        formatted = self.formatter.format(citation_data)
        expected = "Doe, J. (2023). ."
        self.assertEqual(formatted, expected)

    def test_format_with_empty_data(self):
        citation_data = {}
        formatted = self.formatter.format(citation_data)
        expected = ". (). ."
        self.assertEqual(formatted, expected)

if __name__ == '__main__':
    unittest.main()

