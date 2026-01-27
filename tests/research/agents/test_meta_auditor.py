import unittest

from autopack.research.agents.meta_auditor import MetaAuditor


class MockFramework:
    def __init__(self, name, score):
        self.name = name
        self.score = score

    def evaluate(self, data):
        return {
            "framework": self.name,
            "score": self.score,
            "details": f"Evaluated with score {self.score}",
        }


class TestMetaAuditor(unittest.TestCase):
    def setUp(self):
        self.frameworks = [MockFramework("Framework A", 85), MockFramework("Framework B", 90)]
        self.meta_auditor = MetaAuditor(self.frameworks)

    def test_audit(self):
        data = {"key": "value"}
        recommendations = self.meta_auditor.audit(data)
        self.assertEqual(len(recommendations["details"]), 2)

    def test_synthesize(self):
        recommendations = [
            {"framework": "Framework A", "score": 85, "details": "Details A"},
            {"framework": "Framework B", "score": 90, "details": "Details B"},
        ]
        synthesized = self.meta_auditor.synthesize(recommendations)
        self.assertIn("Combined strategic insights", synthesized["summary"])


if __name__ == "__main__":
    unittest.main()
