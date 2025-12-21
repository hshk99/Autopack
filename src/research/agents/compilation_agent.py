"""
Compilation Agent Module

This module is responsible for compiling and organizing web content data.
It aggregates, deduplicates, categorizes, and identifies gaps in the content.
"""

from typing import List, Dict, Any
from src.research.gatherers.web_scraper import WebScraper


class CompilationAgent:
    def __init__(self):
        self.scraper = WebScraper()

    def compile_content(self, urls: List[str]) -> Dict[str, Any]:
        """
        Compiles content from a list of URLs.

        :param urls: A list of URLs to scrape and compile content from.
        :return: A dictionary containing aggregated, deduplicated, categorized content and identified gaps.
        """
        aggregated_results = self.scraper.run(urls)
        return aggregated_results

    def deduplicate_content(self, content: List[str]) -> List[str]:
        """
        Deduplicates the given content list.

        :param content: A list of content strings.
        :return: A list of unique content strings.
        """
        return list(set(content))

    def categorize_content(self, content: List[str]) -> Dict[str, List[str]]:
        """
        Categorizes the given content into predefined categories.

        :param content: A list of content strings.
        :return: A dictionary with categories as keys and lists of content strings as values.
        """
        categories = {
            "news": [],
            "blog": [],
            "advertisement": [],
            "other": []
        }
        for item in content:
            if "news" in item.lower():
                categories["news"].append(item)
            elif "blog" in item.lower():
                categories["blog"].append(item)
            elif "buy now" in item.lower() or "sale" in item.lower():
                categories["advertisement"].append(item)
            else:
                categories["other"].append(item)
        return categories

    def identify_gaps(self, categorized_content: Dict[str, List[str]]) -> List[str]:
        """
        Identifies gaps in the categorized content.

        :param categorized_content: A dictionary of categorized content.
        :return: A list of identified gaps.
        """
        gaps = []
        if not categorized_content["news"]:
            gaps.append("Missing news content")
        if not categorized_content["blog"]:
            gaps.append("Missing blog content")
        return gaps

