import unittest
from autopack.research.gatherers.content_extractor import ContentExtractor


class TestContentExtractor(unittest.TestCase):

    def setUp(self):
        self.extractor = ContentExtractor()

    def test_extract_from_html(self):
        html_content = "<html><body><p>Test content</p></body></html>"
        extracted = self.extractor.extract_from_html(html_content)
        self.assertEqual(extracted, "Test content")

    def test_extract_from_html_none_raises(self):
        with self.assertRaises(ValueError):
            self.extractor.extract_from_html(None)  # type: ignore[arg-type]

    def test_extract_from_html_non_string_raises(self):
        with self.assertRaises(ValueError):
            self.extractor.extract_from_html(123)  # type: ignore[arg-type]

    def test_extract_from_html_strips_script(self):
        html = "<html><body><script>alert('x')</script><p>Keep</p></body></html>"
        extracted = self.extractor.extract_from_html(html)
        self.assertEqual(extracted, "Keep")

    def test_extract_from_json(self):
        json_content = '{"key": "value", "content": "Test content"}'
        extracted = self.extractor.extract_from_json(json_content)
        self.assertEqual(extracted, "Test content")

    def test_extract_from_json_first_string_value(self):
        json_content = '{"k1": 1, "k2": "hello"}'
        extracted = self.extractor.extract_from_json(json_content)
        self.assertEqual(extracted, "hello")

    def test_extract_from_text(self):
        text_content = "This is a test content."
        extracted = self.extractor.extract_from_text(text_content)
        self.assertEqual(extracted, "This is a test content.")

    def test_extract_from_text_none_raises(self):
        with self.assertRaises(ValueError):
            self.extractor.extract_from_text(None)  # type: ignore[arg-type]

    def test_handle_empty_content(self):
        empty_content = ""
        extracted = self.extractor.extract_from_text(empty_content)
        self.assertEqual(extracted, "")

    def test_handle_invalid_format(self):
        invalid_content = "<html><body><p>Test content</p></body>"
        with self.assertRaises(ValueError):
            self.extractor.extract_from_html(invalid_content)

    def test_extract_links_from_html(self):
        html = (
            "<html><body><a href='https://example.com/a'>a</a><a href='/rel'>rel</a></body></html>"
        )
        links = self.extractor.extract_links(html)
        self.assertEqual(links, ["https://example.com/a"])

    def test_extract_links_from_text(self):
        text = "See https://example.com/a and https://example.com/b"
        links = self.extractor.extract_links(text)
        self.assertEqual(links, ["https://example.com/a", "https://example.com/b"])

    def test_extract_links_non_string_raises(self):
        with self.assertRaises(ValueError):
            self.extractor.extract_links(123)  # type: ignore[arg-type]

    def test_extract_code_blocks(self):
        html = "<html><body><code>print('hi')</code><p>x</p></body></html>"
        blocks = self.extractor.extract_code_blocks(html)
        self.assertEqual(blocks, ["print('hi')"])

    def test_extract_code_blocks_plain_text_empty(self):
        blocks = self.extractor.extract_code_blocks("no html here")
        self.assertEqual(blocks, [])

    def test_extract_from_invalid_json_raises(self):
        with self.assertRaises(ValueError):
            self.extractor.extract_from_json("{'not': 'json'}")

    def test_extract_returns_structured_content(self):
        html = "<html><body><a href='https://example.com'>x</a><code>print(1)</code><p>Hello</p></body></html>"
        extracted = self.extractor.extract(html, source_url="https://example.com")
        self.assertIn("Hello", extracted.text)
        self.assertEqual(extracted.links, ["https://example.com"])
        self.assertEqual(extracted.code_blocks, ["print(1)"])


if __name__ == "__main__":
    unittest.main()
