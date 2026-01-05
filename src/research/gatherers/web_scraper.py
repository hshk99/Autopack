"""
Web Scraper Module

This module is responsible for scraping web content and interfacing with the content extractor.
"""

import requests
from bs4 import BeautifulSoup
from typing import List, Dict
from src.research.gatherers.content_extractor import ContentExtractor


class WebScraper:
    def __init__(self):
        self.extractor = ContentExtractor()

    def fetch_html(self, url: str) -> str:
        """
        Fetches HTML content from a given URL.

        :param url: The URL to fetch content from.
        :return: The HTML content as a string.
        """
        try:
            response = requests.get(url)
            response.raise_for_status()
            return response.text
        except requests.RequestException as e:
            print(f"Error fetching {url}: {e}")
            return ""

    def scrape_and_process(self, url: str) -> Dict[str, List[str]]:
        """
        Scrapes a URL and processes the content.

        :param url: The URL to scrape.
        :return: A dictionary containing deduplicated, categorized content and identified gaps.
        """
        html = self.fetch_html(url)
        if not html:
            return {"error": "Failed to fetch content"}

        soup = BeautifulSoup(html, "html.parser")
        text_content = soup.get_text()
        processed_content = self.extractor.process_html(text_content)
        return processed_content

    def scrape_multiple(self, urls: List[str]) -> List[Dict[str, List[str]]]:
        """
        Scrapes multiple URLs and processes their content.

        :param urls: A list of URLs to scrape.
        :return: A list of dictionaries containing processed content for each URL.
        """
        results = []
        for url in urls:
            result = self.scrape_and_process(url)
            results.append(result)
        return results

    def aggregate_results(self, results: List[Dict[str, List[str]]]) -> Dict[str, List[str]]:
        """
        Aggregates results from multiple scrapes.

        :param results: A list of processed content dictionaries.
        :return: A single dictionary aggregating all deduplicated and categorized content.
        """
        aggregated = {
            "deduplicated": [],
            "categorized": {"news": [], "blog": [], "advertisement": [], "other": []},
            "gaps": [],
        }
        for result in results:
            aggregated["deduplicated"].extend(result.get("deduplicated", []))
            for category, items in result.get("categorized", {}).items():
                aggregated["categorized"][category].extend(items)
            aggregated["gaps"].extend(result.get("gaps", []))

        # Deduplicate aggregated content
        aggregated["deduplicated"] = list(set(aggregated["deduplicated"]))
        for category in aggregated["categorized"]:
            aggregated["categorized"][category] = list(set(aggregated["categorized"][category]))
        aggregated["gaps"] = list(set(aggregated["gaps"]))

        return aggregated

    def run(self, urls: List[str]) -> Dict[str, List[str]]:
        """
        Runs the web scraper on a list of URLs and aggregates the results.

        :param urls: A list of URLs to scrape.
        :return: Aggregated results from all URLs.
        """
        results = self.scrape_multiple(urls)
        aggregated_results = self.aggregate_results(results)
        return aggregated_results
