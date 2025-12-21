"""
Test Suite for Content Sanitizer

This module contains unit tests for the ContentSanitizer class.
"""

import unittest
from src.autopack.research.security.content_sanitizer import ContentSanitizer

class TestContentSanitizer(unittest.TestCase):

    def setUp(self):
        """
        Set up the test case environment.
        """
        self.content_sanitizer = ContentSanitizer()

    def test_sanitize_basic(self):
        """
        Test basic content sanitization.
        """
        content = "This is a phishing attempt."
        sanitized_content = self.content_sanitizer.sanitize(content)
        self.assertNotIn("phishing", sanitized_content)
        self.assertIn("[REDACTED]", sanitized_content)

    def test_is_safe(self):
        """
        Test checking if content is safe.
        """
        content = "This is a safe content."
        self.assertTrue(self.content_sanitizer.is_safe(content))
        content = "This contains malware."
        self.assertFalse(self.content_sanitizer.is_safe(content))

    # Additional tests for more complex scenarios can be added here

if __name__ == '__main__':
    unittest.main()
