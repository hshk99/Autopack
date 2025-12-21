import unittest
from src.autopack.research.frameworks.market_attractiveness import MarketAttractiveness

class TestMarketAttractiveness(unittest.TestCase):

    def setUp(self):
        self.indicators = ["indicator1", "indicator2", "indicator3"]
        self.framework = MarketAttractiveness(self.indicators)

    def test_evaluate(self):
        data = {
            "indicator1": 9,
            "indicator2": 4,
            "indicator3": 6
        }
        result = self.framework.evaluate(data)
        self.assertEqual(result['attractiveness'], 19)
        self.assertEqual(result['framework'], "Market Attractiveness")

    def test_evaluate_with_missing_indicators(self):
        data = {
            "indicator1": 9,
            "indicator3": 6
        }
        result = self.framework.evaluate(data)
        self.assertEqual(result['attractiveness'], 15)

    def test_evaluate_with_no_indicators(self):
        data = {}
        result = self.framework.evaluate(data)
        self.assertEqual(result['attractiveness'], 0)

if __name__ == '__main__':
    unittest.main()

