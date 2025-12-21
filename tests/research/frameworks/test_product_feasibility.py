import unittest
from src.autopack.research.frameworks.product_feasibility import ProductFeasibility

class TestProductFeasibility(unittest.TestCase):

    def setUp(self):
        self.parameters = ["parameter1", "parameter2", "parameter3"]
        self.framework = ProductFeasibility(self.parameters)

    def test_evaluate(self):
        data = {
            "parameter1": 8,
            "parameter2": 6,
            "parameter3": 7
        }
        result = self.framework.evaluate(data)
        self.assertEqual(result['feasibility'], 21)
        self.assertEqual(result['framework'], "Product Feasibility")

    def test_evaluate_with_missing_parameters(self):
        data = {
            "parameter1": 8,
            "parameter3": 7
        }
        result = self.framework.evaluate(data)
        self.assertEqual(result['feasibility'], 15)

    def test_evaluate_with_no_parameters(self):
        data = {}
        result = self.framework.evaluate(data)
        self.assertEqual(result['feasibility'], 0)

if __name__ == '__main__':
    unittest.main()

