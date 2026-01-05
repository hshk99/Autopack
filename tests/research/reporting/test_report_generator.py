import unittest
from autopack.research.reporting.report_generator import ReportGenerator
from autopack.research.reporting.citation_formatter import CitationFormatter


class TestReportGenerator(unittest.TestCase):

    def setUp(self):
        self.formatter = CitationFormatter()
        self.generator = ReportGenerator(self.formatter)

    def test_generate(self):
        analysis_results = [
            {
                "framework": "Market Attractiveness",
                "score": 75,
                "details": "Evaluated against 5 indicators",
            },
            {
                "framework": "Product Feasibility",
                "score": 80,
                "details": "Evaluated against 3 parameters",
            },
        ]
        report = self.generator.generate(analysis_results)
        self.assertIn("Market Attractiveness", report)
        self.assertIn("Product Feasibility", report)

    def test_generate_with_empty_results(self):
        analysis_results = []
        report = self.generator.generate(analysis_results)
        self.assertEqual(report, "Research Report\n\n")


if __name__ == "__main__":
    unittest.main()
