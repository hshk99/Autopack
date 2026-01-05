"""Gatherer module for the tracer bullet pipeline."""

import requests
from bs4 import BeautifulSoup


def fetch_web_content(url: str) -> str:
    """
    Fetches the content of a web page.

    Args:
        url (str): The URL of the web page to fetch.

    Returns:
        str: The content of the web page.

    Raises:
        requests.HTTPError: If the HTTP request fails.
    """
    try:
        response = requests.get(url)
        response.raise_for_status()
        return response.text
    except requests.RequestException as e:
        raise requests.HTTPError(f"Failed to fetch {url}: {e}")


def parse_html_content(html_content: str) -> list:
    """
    Parses HTML content and extracts structured data.

    Args:
        html_content (str): The HTML content to parse.

    Returns:
        list: A list of extracted data.
    """
    soup = BeautifulSoup(html_content, "html.parser")
    data = []
    for item in soup.find_all("p"):  # Example: Extract all paragraphs
        data.append(item.get_text())
    return data


if __name__ == "__main__":
    # Example usage
    url = "https://example.com"
    try:
        content = fetch_web_content(url)
        data = parse_html_content(content)
        print(f"Extracted data: {data}")
    except requests.HTTPError as e:
        print(f"Error: {e}")
