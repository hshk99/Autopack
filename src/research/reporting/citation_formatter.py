"""
Citation Formatter

This module provides functionality to format citations for research reports.
"""


class CitationFormatter:
    """
    The CitationFormatter class formats citations in a specified style.
    """

    def __init__(self, style="APA"):
        self.style = style

    def format_citation(self, author, title, year, source):
        """
        Formats a citation based on the specified style.

        Args:
            author (str): The author of the source.
            title (str): The title of the source.
            year (int): The publication year.
            source (str): The source or publisher.

        Returns:
            str: The formatted citation.
        """
        if self.style == "APA":
            return f"{author} ({year}). {title}. {source}."
        elif self.style == "MLA":
            return f"{author}. \"{title}.\" {source}, {year}."
        else:
            raise ValueError(f"Unsupported citation style: {self.style}")


if __name__ == "__main__":
    formatter = CitationFormatter(style="APA")
    citation = formatter.format_citation(
        author="John Doe",
        title="Research Methods",
        year=2025,
        source="Science Publishing"
    )
    print("Formatted Citation:")
    print(citation)
