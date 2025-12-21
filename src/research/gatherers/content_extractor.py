"""
Content Extractor Module

This module is responsible for extracting and processing content from web pages.
It deduplicates content, categorizes it by type, and identifies gaps.
"""

from typing import List, Dict, Any
import re


class ContentExtractor:
    def __init__(self):
        self.content_store = []

    def extract_content(self, html: str) -> List[str]:
        """
        Extracts text content from HTML.

        :param html: The HTML content as a string.
        :return: A list of extracted text segments.
        """
        # Simple regex-based extraction for demonstration purposes
        text_segments = re.findall(r'>[^<]+<', html)
        return [segment.strip('<> ') for segment in text_segments]

    def deduplicate_content(self, contents: List[str]) -> List[str]:
        """
        Deduplicates the extracted content.

        :param contents: A list of content strings.
        :return: A list of unique content strings.
        """
        return list(set(contents))

    def categorize_content(self, contents: List[str]) -> Dict[str, List[str]]:
        """
        Categorizes content into predefined categories.

        :param contents: A list of content strings.
        :return: A dictionary with categories as keys and lists of content strings as values.
        """
        categories = {
            "news": [],
            "blog": [],
            "advertisement": [],
            "other": []
        }
        for content in contents:
            if "news" in content.lower():
                categories["news"].append(content)
            elif "blog" in content.lower():
                categories["blog"].append(content)
            elif "buy now" in content.lower() or "sale" in content.lower():
                categories["advertisement"].append(content)
            else:
                categories["other"].append(content)
        return categories

    def identify_gaps(self, categorized_content: Dict[str, List[str]]) -> List[str]:
        """
        Identifies gaps in the content based on predefined criteria.

        :param categorized_content: A dictionary of categorized content.
        :return: A list of identified gaps.
        """
        gaps = []
        if not categorized_content["news"]:
            gaps.append("Missing news content")
        if not categorized_content["blog"]:
            gaps.append("Missing blog content")
        return gaps

    def process_html(self, html: str) -> Dict[str, Any]:
        """
        Full processing of HTML content.

        :param html: The HTML content as a string.
        :return: A dictionary containing deduplicated, categorized content and identified gaps.
        """
        extracted = self.extract_content(html)
        deduplicated = self.deduplicate_content(extracted)
        categorized = self.categorize_content(deduplicated)
        gaps = self.identify_gaps(categorized)
        return {
            "deduplicated": deduplicated,
            "categorized": categorized,
            "gaps": gaps
        }
