import unittest
from src.autopack.research.frameworks.competitive_intensity import CompetitiveIntensity

class TestCompetitiveIntensity(unittest.TestCase):

    def setUp(self):
        self.factors = ["factor1", "factor2", "factor3"]
        self.framework = CompetitiveIntensity(self.factors)

    def test_evaluate(self):
        data = {
            "factor1": 7,
            "factor2": 3,
            "factor3": 5
        }
        result = self.framework.evaluate(data)
        self.assertEqual(result['intensity'], 15)
        self.assertEqual(result['framework'], "Competitive Intensity")

    def test_evaluate_with_missing_factors(self):
        data = {
            "factor1": 7,
            "factor3": 5
        }
        result = self.framework.evaluate(data)
        self.assertEqual(result['intensity'], 12)

    def test_evaluate_with_no_factors(self):
        data = {}
        result = self.framework.evaluate(data)
        self.assertEqual(result['intensity'], 0)

if __name__ == '__main__':
    unittest.main()

