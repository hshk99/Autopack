import unittest
from src.autopack.research.frameworks.adoption_readiness import AdoptionReadiness

class TestAdoptionReadiness(unittest.TestCase):

    def setUp(self):
        self.criteria = ["criterion1", "criterion2", "criterion3"]
        self.framework = AdoptionReadiness(self.criteria)

    def test_evaluate(self):
        data = {
            "criterion1": 10,
            "criterion2": 5,
            "criterion3": 8
        }
        result = self.framework.evaluate(data)
        self.assertEqual(result['score'], 23)
        self.assertEqual(result['framework'], "Adoption Readiness")

    def test_evaluate_with_missing_criteria(self):
        data = {
            "criterion1": 10,
            "criterion3": 8
        }
        result = self.framework.evaluate(data)
        self.assertEqual(result['score'], 18)

    def test_evaluate_with_no_criteria(self):
        data = {}
        result = self.framework.evaluate(data)
        self.assertEqual(result['score'], 0)

if __name__ == '__main__':
    unittest.main()

