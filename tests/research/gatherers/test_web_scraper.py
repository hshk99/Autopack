import unittest
from unittest.mock import patch

from autopack.research.gatherers.web_scraper import WebScraper


class TestWebScraper(unittest.TestCase):
    def setUp(self):
        self.scraper = WebScraper()

    @patch("autopack.research.gatherers.web_scraper.requests.get")
    def test_fetch_content(self, mock_get):
        mock_get.return_value.status_code = 200
        mock_get.return_value.text = "<html><body>Test content</body></html>"
        mock_get.return_value.headers = {"content-type": "text/html; charset=utf-8"}
        content = self.scraper.fetch_content("http://example.com")
        self.assertIn("Test content", content)

    @patch("autopack.research.gatherers.web_scraper.requests.get")
    def test_fetch_content_failure(self, mock_get):
        mock_get.return_value.status_code = 404
        with self.assertRaises(Exception):
            self.scraper.fetch_content("http://example.com")

    def test_parse_content(self):
        html_content = "<html><body><p>Test content</p></body></html>"
        parsed = self.scraper.parse_content(html_content)
        self.assertEqual(parsed, "Test content")

    def test_handle_invalid_url(self):
        with self.assertRaises(ValueError):
            self.scraper.fetch_content("not_a_url")

    def test_handle_empty_url(self):
        with self.assertRaises(ValueError):
            self.scraper.fetch_content("")

    def test_handle_invalid_scheme(self):
        with self.assertRaises(ValueError):
            self.scraper.fetch_content("ftp://example.com")

    @patch(
        "autopack.research.gatherers.web_scraper.WebScraper._allowed_by_robots", return_value=False
    )
    def test_robots_disallow_raises(self, _mock_allowed):
        with self.assertRaises(PermissionError):
            self.scraper.fetch_content("http://example.com")

    @patch("autopack.research.gatherers.web_scraper.requests.get")
    def test_unsupported_content_type(self, mock_get):
        mock_get.return_value.status_code = 200
        mock_get.return_value.text = "pdf bytes"
        mock_get.return_value.headers = {"content-type": "application/pdf"}
        with self.assertRaises(ValueError):
            self.scraper.fetch_content("http://example.com")

    @patch("autopack.research.gatherers.web_scraper.requests.get")
    def test_user_agent_header_sent(self, mock_get):
        mock_get.return_value.status_code = 200
        mock_get.return_value.text = "<html><body>Test</body></html>"
        mock_get.return_value.headers = {"content-type": "text/html"}

        self.scraper.fetch_content("http://example.com")
        _args, kwargs = mock_get.call_args
        self.assertIn("headers", kwargs)
        self.assertIn("User-Agent", kwargs["headers"])
        self.assertTrue(kwargs["headers"]["User-Agent"])

    @patch("autopack.research.gatherers.web_scraper.time.sleep")
    @patch("autopack.research.gatherers.web_scraper.time.time")
    def test_rate_limiting_sleeps(self, mock_time, mock_sleep):
        mock_time.side_effect = [100.0, 100.0, 100.0, 100.0]  # deterministic
        s = WebScraper(min_seconds_per_domain=1.0)
        # First request sets last_request_ts; second should sleep for 1s
        s._enforce_rate_limit("example.com")
        s._enforce_rate_limit("example.com")
        self.assertTrue(mock_sleep.called)


if __name__ == "__main__":
    unittest.main()
