import socket
import unittest
import urllib.error
from unittest.mock import MagicMock, patch

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

    # Tests for robots.txt error handling (IMP-REL-006)

    @patch("autopack.research.gatherers.web_scraper.urllib.robotparser.RobotFileParser")
    def test_robots_txt_network_error_allows_request(self, mock_robot_parser):
        """Test that network errors when fetching robots.txt allow the request."""
        scraper = WebScraper()
        mock_instance = MagicMock()
        mock_robot_parser.return_value = mock_instance
        mock_instance.read.side_effect = urllib.error.URLError("Connection failed")

        # Should allow request when robots.txt fetch fails with network error
        result = scraper._allowed_by_robots("http://example.com/page")
        self.assertTrue(result)

    @patch("autopack.research.gatherers.web_scraper.urllib.robotparser.RobotFileParser")
    def test_robots_txt_timeout_allows_request(self, mock_robot_parser):
        """Test that timeout errors when fetching robots.txt allow the request."""
        scraper = WebScraper()
        mock_instance = MagicMock()
        mock_robot_parser.return_value = mock_instance
        mock_instance.read.side_effect = socket.timeout("Read timed out")

        # Should allow request when robots.txt fetch times out
        result = scraper._allowed_by_robots("http://example.com/page")
        self.assertTrue(result)

    @patch("autopack.research.gatherers.web_scraper.urllib.robotparser.RobotFileParser")
    def test_robots_txt_parse_error_denies_request(self, mock_robot_parser):
        """Test that parse errors when reading robots.txt deny the request."""
        scraper = WebScraper()
        mock_instance = MagicMock()
        mock_robot_parser.return_value = mock_instance
        mock_instance.read.side_effect = ValueError("Invalid robots.txt format")

        # Should deny request when robots.txt parse error occurs
        result = scraper._allowed_by_robots("http://example.com/page")
        self.assertFalse(result)

    @patch("autopack.research.gatherers.web_scraper.urllib.robotparser.RobotFileParser")
    def test_robots_txt_unexpected_error_raises(self, mock_robot_parser):
        """Test that unexpected errors when reading robots.txt are re-raised."""
        scraper = WebScraper()
        mock_instance = MagicMock()
        mock_robot_parser.return_value = mock_instance
        mock_instance.read.side_effect = RuntimeError("Unexpected error")

        # Should raise when unexpected error occurs
        with self.assertRaises(RuntimeError):
            scraper._allowed_by_robots("http://example.com/page")

    @patch("autopack.research.gatherers.web_scraper.urllib.robotparser.RobotFileParser")
    def test_robots_check_network_error_allows_request(self, mock_robot_parser):
        """Test that network errors when checking robots rules allow the request."""
        scraper = WebScraper()
        mock_instance = MagicMock()
        mock_robot_parser.return_value = mock_instance
        mock_instance.read.return_value = None  # Read succeeds
        mock_instance.can_fetch.side_effect = urllib.error.URLError("Connection failed")

        # Should allow request when can_fetch fails with network error
        result = scraper._allowed_by_robots("http://example.com/page")
        self.assertTrue(result)

    @patch("autopack.research.gatherers.web_scraper.urllib.robotparser.RobotFileParser")
    def test_robots_check_timeout_allows_request(self, mock_robot_parser):
        """Test that timeout errors when checking robots rules allow the request."""
        scraper = WebScraper()
        mock_instance = MagicMock()
        mock_robot_parser.return_value = mock_instance
        mock_instance.read.return_value = None  # Read succeeds
        mock_instance.can_fetch.side_effect = socket.timeout("Read timed out")

        # Should allow request when can_fetch times out
        result = scraper._allowed_by_robots("http://example.com/page")
        self.assertTrue(result)

    @patch("autopack.research.gatherers.web_scraper.urllib.robotparser.RobotFileParser")
    def test_robots_check_parse_error_denies_request(self, mock_robot_parser):
        """Test that parse errors when checking robots rules deny the request."""
        scraper = WebScraper()
        mock_instance = MagicMock()
        mock_robot_parser.return_value = mock_instance
        mock_instance.read.return_value = None  # Read succeeds
        mock_instance.can_fetch.side_effect = ValueError("Invalid robots.txt check")

        # Should deny request when can_fetch parse error occurs
        result = scraper._allowed_by_robots("http://example.com/page")
        self.assertFalse(result)

    @patch("autopack.research.gatherers.web_scraper.urllib.robotparser.RobotFileParser")
    def test_robots_check_unexpected_error_raises(self, mock_robot_parser):
        """Test that unexpected errors when checking robots rules are re-raised."""
        scraper = WebScraper()
        mock_instance = MagicMock()
        mock_robot_parser.return_value = mock_instance
        mock_instance.read.return_value = None  # Read succeeds
        mock_instance.can_fetch.side_effect = RuntimeError("Unexpected error")

        # Should raise when unexpected error occurs
        with self.assertRaises(RuntimeError):
            scraper._allowed_by_robots("http://example.com/page")

    @patch("autopack.research.gatherers.web_scraper.urllib.robotparser.RobotFileParser")
    @patch("autopack.research.gatherers.web_scraper.requests.get")
    def test_robots_cache_persists_after_error(self, mock_get, mock_robot_parser):
        """Test that robots parser is cached even after network errors."""
        scraper = WebScraper()
        mock_instance = MagicMock()
        mock_robot_parser.return_value = mock_instance
        mock_instance.read.side_effect = urllib.error.URLError("Connection failed")

        # First call
        result1 = scraper._allowed_by_robots("http://example.com/page1")
        self.assertTrue(result1)

        # Second call should use cached parser and raise same error again
        mock_instance.read.side_effect = urllib.error.URLError("Connection failed again")
        result2 = scraper._allowed_by_robots("http://example.com/page2")
        self.assertTrue(result2)

        # Verify that read() was only called once (caching works)
        self.assertEqual(mock_instance.read.call_count, 1)


if __name__ == "__main__":
    unittest.main()
