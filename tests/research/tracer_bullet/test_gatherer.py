import unittest
from tracer_bullet.gatherer import gather_data

class TestGatherer(unittest.TestCase):
    def setUp(self):
        self.url = "https://example.com"

    def test_gather_data_success(self):
        """
        Test successful data gathering from a URL.
        """
        result = gather_data(self.url)
        self.assertTrue(result['success'])
        self.assertIn('content', result)

    def test_gather_data_failure(self):
        """
        Test data gathering failure due to invalid URL.
        """
        invalid_url = "https://invalid-url.com"
        result = gather_data(invalid_url)
        self.assertFalse(result['success'])
        self.assertIn('error', result)

    def test_respect_robots_txt(self):
        """
        Test that the gatherer respects robots.txt.
        """
        result = gather_data(self.url)
        self.assertTrue(result['robots_respected'])

if __name__ == '__main__':
    unittest.main()

