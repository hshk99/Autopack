"""Citation Formatter

This module formats citations and references for research reports.
"""

from typing import Any, Dict, List, Optional


class CitationFormatter:
    """Formats citations in various academic styles.

    Attributes:
        style: Citation style (APA, MLA, Chicago, IEEE)
        citations: List of citation dictionaries
    """

    SUPPORTED_STYLES = ["APA", "MLA", "Chicago", "IEEE"]

    def __init__(self, style: str = "APA"):
        """Initialize the citation formatter.

        Args:
            style: Citation style to use

        Raises:
            ValueError: If style is not supported
        """
        if style not in self.SUPPORTED_STYLES:
            raise ValueError(f"Style must be one of {self.SUPPORTED_STYLES}")
        self.style = style
        self.citations: List[Dict[str, Any]] = []

    def add_citation(self, citation_type: str, **kwargs) -> str:
        """Add a citation and return formatted reference.

        Args:
            citation_type: Type of citation (article, book, website, report)
            **kwargs: Citation details (author, title, year, etc.)

        Returns:
            Citation ID for in-text references
        """
        citation_id = f"ref{len(self.citations) + 1}"
        citation = {"id": citation_id, "type": citation_type, **kwargs}
        self.citations.append(citation)
        return citation_id

    def format_in_text(self, citation_id: str, page: Optional[str] = None) -> str:
        """Format in-text citation.

        Args:
            citation_id: Citation ID
            page: Optional page number

        Returns:
            Formatted in-text citation
        """
        citation = self._get_citation(citation_id)
        if not citation:
            return f"[{citation_id}]"

        if self.style == "APA":
            return self._format_apa_in_text(citation, page)
        elif self.style == "MLA":
            return self._format_mla_in_text(citation, page)
        elif self.style == "Chicago":
            return self._format_chicago_in_text(citation, page)
        else:  # IEEE
            return self._format_ieee_in_text(citation, page)

    def format_reference_list(self) -> str:
        """Format complete reference list.

        Returns:
            Formatted reference list
        """
        if not self.citations:
            return "No references."

        # Sort citations
        sorted_citations = self._sort_citations()

        # Format header
        if self.style == "APA":
            header = "References\n\n"
        elif self.style == "MLA":
            header = "Works Cited\n\n"
        elif self.style == "Chicago":
            header = "Bibliography\n\n"
        else:  # IEEE
            header = "References\n\n"

        # Format each citation
        references = []
        for i, citation in enumerate(sorted_citations, 1):
            if self.style == "APA":
                ref = self._format_apa_reference(citation)
            elif self.style == "MLA":
                ref = self._format_mla_reference(citation)
            elif self.style == "Chicago":
                ref = self._format_chicago_reference(citation)
            else:  # IEEE
                ref = f"[{i}] {self._format_ieee_reference(citation)}"
            references.append(ref)

        return header + "\n".join(references)

    def _get_citation(self, citation_id: str) -> Optional[Dict[str, Any]]:
        """Get citation by ID."""
        for citation in self.citations:
            if citation["id"] == citation_id:
                return citation
        return None

    def _sort_citations(self) -> List[Dict[str, Any]]:
        """Sort citations according to style."""
        if self.style == "IEEE":
            # IEEE uses order of appearance
            return self.citations.copy()
        else:
            # Alphabetical by author
            return sorted(self.citations, key=lambda x: x.get("author", x.get("title", "")))

    # APA Style Formatting
    def _format_apa_in_text(self, citation: Dict[str, Any], page: Optional[str]) -> str:
        """Format APA in-text citation."""
        author = citation.get("author", "Unknown")
        year = citation.get("year", "n.d.")

        # Extract last name if full name provided
        if "," in author:
            author = author.split(",")[0]
        elif " " in author:
            author = author.split()[-1]

        if page:
            return f"({author}, {year}, p. {page})"
        return f"({author}, {year})"

    def _format_apa_reference(self, citation: Dict[str, Any]) -> str:
        """Format APA reference."""
        ctype = citation.get("type", "article")

        if ctype == "article":
            return self._format_apa_article(citation)
        elif ctype == "book":
            return self._format_apa_book(citation)
        elif ctype == "website":
            return self._format_apa_website(citation)
        else:
            return self._format_apa_report(citation)

    def _format_apa_article(self, citation: Dict[str, Any]) -> str:
        """Format APA journal article."""
        author = citation.get("author", "Unknown")
        year = citation.get("year", "n.d.")
        title = citation.get("title", "Untitled")
        journal = citation.get("journal", "")
        volume = citation.get("volume", "")
        pages = citation.get("pages", "")
        doi = citation.get("doi", "")

        ref = f"{author} ({year}). {title}. "
        if journal:
            ref += f"*{journal}*"
        if volume:
            ref += f", *{volume}*"
        if pages:
            ref += f", {pages}"
        if doi:
            ref += f". https://doi.org/{doi}"

        return ref

    def _format_apa_book(self, citation: Dict[str, Any]) -> str:
        """Format APA book."""
        author = citation.get("author", "Unknown")
        year = citation.get("year", "n.d.")
        title = citation.get("title", "Untitled")
        publisher = citation.get("publisher", "")

        ref = f"{author} ({year}). *{title}*"
        if publisher:
            ref += f". {publisher}"

        return ref

    def _format_apa_website(self, citation: Dict[str, Any]) -> str:
        """Format APA website."""
        author = citation.get("author", citation.get("organization", "Unknown"))
        year = citation.get("year", "n.d.")
        title = citation.get("title", "Untitled")
        url = citation.get("url", "")
        access_date = citation.get("access_date", "")

        ref = f"{author} ({year}). *{title}*"
        if url:
            ref += f". Retrieved from {url}"
        if access_date:
            ref += f" (accessed {access_date})"

        return ref

    def _format_apa_report(self, citation: Dict[str, Any]) -> str:
        """Format APA report."""
        author = citation.get("author", citation.get("organization", "Unknown"))
        year = citation.get("year", "n.d.")
        title = citation.get("title", "Untitled")
        report_number = citation.get("report_number", "")
        publisher = citation.get("publisher", "")

        ref = f"{author} ({year}). *{title}*"
        if report_number:
            ref += f" (Report No. {report_number})"
        if publisher:
            ref += f". {publisher}"

        return ref

    # MLA Style Formatting
    def _format_mla_in_text(self, citation: Dict[str, Any], page: Optional[str]) -> str:
        """Format MLA in-text citation."""
        author = citation.get("author", "Unknown")

        # Extract last name
        if "," in author:
            author = author.split(",")[0]
        elif " " in author:
            author = author.split()[-1]

        if page:
            return f"({author} {page})"
        return f"({author})"

    def _format_mla_reference(self, citation: Dict[str, Any]) -> str:
        """Format MLA reference."""
        author = citation.get("author", "Unknown")
        title = citation.get("title", "Untitled")
        year = citation.get("year", "n.d.")

        return f'{author}. "{title}." {year}.'

    # Chicago Style Formatting
    def _format_chicago_in_text(self, citation: Dict[str, Any], page: Optional[str]) -> str:
        """Format Chicago in-text citation (notes style)."""
        # Chicago uses footnotes, return superscript number
        index = self.citations.index(citation) + 1
        return f"[{index}]"

    def _format_chicago_reference(self, citation: Dict[str, Any]) -> str:
        """Format Chicago reference."""
        author = citation.get("author", "Unknown")
        title = citation.get("title", "Untitled")
        year = citation.get("year", "n.d.")

        return f"{author}. *{title}*. {year}."

    # IEEE Style Formatting
    def _format_ieee_in_text(self, citation: Dict[str, Any], page: Optional[str]) -> str:
        """Format IEEE in-text citation."""
        index = self.citations.index(citation) + 1
        if page:
            return f"[{index}, p. {page}]"
        return f"[{index}]"

    def _format_ieee_reference(self, citation: Dict[str, Any]) -> str:
        """Format IEEE reference."""
        author = citation.get("author", "Unknown")
        title = citation.get("title", "Untitled")
        year = citation.get("year", "n.d.")

        return f'{author}, "{title}," {year}.'

    def clear_citations(self) -> None:
        """Clear all citations."""
        self.citations.clear()

    def get_citation_count(self) -> int:
        """Get number of citations.

        Returns:
            Number of citations
        """
        return len(self.citations)
