import unittest
from unittest.mock import patch
from autopack.research.agents.compilation_agent import CompilationAgent


class TestCompilationAgent(unittest.TestCase):

    def setUp(self):
        self.agent = CompilationAgent()

    def test_compile_report(self):
        findings = [
            {"type": "article", "content": "Content A"},
            {"type": "blog", "content": "Content B"},
        ]
        report = self.agent.compile_report(findings)
        self.assertIn("Content A", report)
        self.assertIn("Content B", report)

    def test_categorize_by_type(self):
        findings = [
            {"type": "article", "content": "Content A"},
            {"type": "blog", "content": "Content B"},
            {"type": "article", "content": "Content C"},
        ]
        categorized = self.agent.categorize_by_type(findings)
        self.assertEqual(len(categorized["article"]), 2)
        self.assertEqual(len(categorized["blog"]), 1)

    def test_generate_summary(self):
        findings = [
            {"type": "article", "content": "Content A"},
            {"type": "blog", "content": "Content B"},
        ]
        summary = self.agent.generate_summary(findings)
        self.assertIn("Summary of findings", summary)

    def test_deduplicate_findings_exact_fallback(self):
        findings = [
            {"type": "article", "content": "Same"},
            {"type": "article", "content": "Same"},
            {"type": "article", "content": "Different"},
        ]
        deduped = self.agent.deduplicate_findings(findings, threshold=100)
        self.assertEqual(len(deduped), 2)

    def test_deduplicate_preserves_source_url(self):
        findings = [
            {"type": "article", "content": "Hello world", "source_url": None},
            {"type": "article", "content": "Hello world", "source_url": "https://example.com"},
        ]
        deduped = self.agent.deduplicate_findings(findings, threshold=100)
        self.assertEqual(len(deduped), 1)
        self.assertEqual(deduped[0].get("source_url"), "https://example.com")

    def test_categorize_buckets_present(self):
        findings = [
            {"type": "web", "content": "API latency and database scalability"},
            {"type": "web", "content": "UI onboarding and user experience improvements"},
            {"type": "web", "content": "market pricing demand signals"},
            {"type": "web", "content": "competitors exist in the space"},
        ]
        buckets = self.agent.categorize(findings)
        self.assertIn("technical", buckets)
        self.assertIn("ux", buckets)
        self.assertIn("market", buckets)
        self.assertIn("competition", buckets)
        self.assertEqual(len(buckets["technical"]), 1)
        self.assertEqual(len(buckets["ux"]), 1)
        self.assertEqual(len(buckets["market"]), 1)
        self.assertEqual(len(buckets["competition"]), 1)

    @patch(
        "autopack.research.agents.compilation_agent.WebScraper.fetch_content",
        return_value="Some page",
    )
    def test_compile_content_uses_scraper(self, _mock_fetch):
        result = self.agent.compile_content(["https://example.com/a"])
        self.assertIn("findings", result)
        self.assertEqual(result["findings"][0]["source_url"], "https://example.com/a")


if __name__ == "__main__":
    unittest.main()
