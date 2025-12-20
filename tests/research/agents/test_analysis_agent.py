import unittest
from autopack.research.agents.analysis_agent import AnalysisAgent


class TestAnalysisAgent(unittest.TestCase):

    def setUp(self):
        self.agent = AnalysisAgent()

    def test_aggregate_findings(self):
        findings = [
            {"type": "article", "content": "Content A"},
            {"type": "blog", "content": "Content B"},
            {"type": "article", "content": "Content C"},
        ]
        aggregated = self.agent.aggregate_findings(findings)
        self.assertEqual(len(aggregated), 2)
        self.assertIn("article", aggregated)
        self.assertIn("blog", aggregated)

    def test_deduplicate_content(self):
        contents = [
            "Content A",
            "Content B",
            "Content A",  # Duplicate
        ]
        deduplicated = self.agent.deduplicate_content(contents)
        self.assertEqual(len(deduplicated), 2)
        self.assertIn("Content A", deduplicated)
        self.assertIn("Content B", deduplicated)

    def test_identify_gaps(self):
        findings = [
            {"type": "article", "content": "Content A"},
            {"type": "blog", "content": "Content B"},
        ]
        gaps = self.agent.identify_gaps(findings, ["article", "blog", "report"])
        self.assertIn("report", gaps)

    def test_analyze_confidence_full(self):
        categorized = {
            "technical": [{"content": "x"}],
            "ux": [{"content": "x"}],
            "market": [{"content": "x"}],
            "competition": [{"content": "x"}],
        }
        result = self.agent.analyze(categorized)
        self.assertEqual(result["gaps"], [])
        self.assertEqual(result["confidence"], 1.0)

    def test_analyze_confidence_partial(self):
        categorized = {"technical": [{"content": "x"}], "ux": [], "market": [], "competition": []}
        result = self.agent.analyze(categorized)
        self.assertIn("ux", result["gaps"])
        self.assertLess(result["confidence"], 1.0)

if __name__ == '__main__':
    unittest.main()
