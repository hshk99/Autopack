import unittest
from autopack.research.evaluation.evaluator import evaluate_pipeline

class TestEndToEnd(unittest.TestCase):
    def setUp(self):
        self.url = "https://example.com"
        self.expression = "2 + 3 * (4 - 1)"
        self.prompt = "SELECT * FROM users WHERE username = 'admin';"

    def test_pipeline_execution(self):
        """
        Test the end-to-end execution of the tracer bullet pipeline.
        """
        results = evaluate_pipeline(self.url, self.expression, self.prompt)
        
        # Check if results contain expected keys
        self.assertIn('web_scraping', results)
        self.assertIn('llm_extraction', results)
        self.assertIn('calculation', results)
        self.assertIn('token_budget', results)
        self.assertIn('prompt_injection_defense', results)

        # Validate web scraping result
        self.assertTrue(results['web_scraping']['success'])

        # Validate LLM extraction result
        self.assertIsInstance(results['llm_extraction']['data'], dict)

        # Validate calculation result
        self.assertEqual(results['calculation']['result'], 11)

        # Validate token budget
        self.assertTrue(results['token_budget']['sufficient'])

        # Validate prompt injection defense
        self.assertTrue(results['prompt_injection_defense']['safe'])

if __name__ == '__main__':
    unittest.main()

