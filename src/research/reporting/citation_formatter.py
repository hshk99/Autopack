"""Citation Formatter

This module provides citation formatting utilities for research reports,
supporting multiple citation styles.
"""

from typing import Dict, Any, List, Optional
from datetime import datetime


class Citation:
    """Represents a single citation.
    
    Attributes:
        authors: List of author names
        title: Publication title
        year: Publication year
        source: Source (journal, website, etc.)
        url: Optional URL
        access_date: Optional access date for web sources
    """
    
    def __init__(self, authors: List[str], title: str, year: int,
                 source: str, url: Optional[str] = None,
                 access_date: Optional[datetime] = None):
        """Initialize a citation.
        
        Args:
            authors: List of author names
            title: Publication title
            year: Publication year
            source: Source name
            url: Optional URL
            access_date: Optional access date
        """
        self.authors = authors
        self.title = title
        self.year = year
        self.source = source
        self.url = url
        self.access_date = access_date or datetime.now()
    
    def format_authors_apa(self) -> str:
        """Format authors in APA style.
        
        Returns:
            Formatted author string
        """
        if not self.authors:
            return "Unknown Author"
        
        if len(self.authors) == 1:
            return self.authors[0]
        elif len(self.authors) == 2:
            return f"{self.authors[0]} & {self.authors[1]}"
        else:
            return f"{self.authors[0]} et al."
    
    def format_authors_mla(self) -> str:
        """Format authors in MLA style.
        
        Returns:
            Formatted author string
        """
        if not self.authors:
            return "Unknown Author"
        
        if len(self.authors) == 1:
            return self.authors[0]
        else:
            return f"{self.authors[0]}, et al."
    
    def to_apa(self) -> str:
        """Format citation in APA style.
        
        Returns:
            APA-formatted citation string
        """
        citation = f"{self.format_authors_apa()} ({self.year}). {self.title}. "
        citation += f"{self.source}."
        
        if self.url:
            citation += f" Retrieved from {self.url}"
        
        return citation
    
    def to_mla(self) -> str:
        """Format citation in MLA style.
        
        Returns:
            MLA-formatted citation string
        """
        citation = f"{self.format_authors_mla()}. \"{self.title}.\" "
        citation += f"{self.source}, {self.year}."
        
        if self.url:
            citation += f" {self.url}. "
            citation += f"Accessed {self.access_date.strftime('%d %b. %Y')}."
        
        return citation
    
    def to_chicago(self) -> str:
        """Format citation in Chicago style.
        
        Returns:
            Chicago-formatted citation string
        """
        if not self.authors:
            author_str = "Unknown Author"
        elif len(self.authors) == 1:
            author_str = self.authors[0]
        else:
            author_str = f"{self.authors[0]} et al."
        
        citation = f"{author_str}. \"{self.title}.\" "
        citation += f"{self.source} ({self.year})."
        
        if self.url:
            citation += f" {self.url}."
        
        return citation


class CitationFormatter:
    """Manages and formats citations for research reports."""
    
    def __init__(self, style: str = 'apa'):
        """Initialize the citation formatter.
        
        Args:
            style: Citation style ('apa', 'mla', 'chicago')
            
        Raises:
            ValueError: If style is not supported
        """
        valid_styles = ['apa', 'mla', 'chicago']
        if style.lower() not in valid_styles:
            raise ValueError(f"Style must be one of {valid_styles}")
        
        self.style = style.lower()
        self.citations: List[Citation] = []
    
    def add_citation(self, citation: Citation) -> None:
        """Add a citation to the formatter.
        
        Args:
            citation: Citation instance to add
        """
        self.citations.append(citation)
    
    def add_from_dict(self, data: Dict[str, Any]) -> None:
        """Add a citation from dictionary data.
        
        Args:
            data: Dictionary with citation data
        """
        citation = Citation(
            authors=data.get('authors', []),
            title=data.get('title', 'Untitled'),
            year=data.get('year', datetime.now().year),
            source=data.get('source', 'Unknown Source'),
            url=data.get('url'),
            access_date=data.get('access_date')
        )
        self.add_citation(citation)
    
    def format_citation(self, citation: Citation) -> str:
        """Format a single citation in the current style.
        
        Args:
            citation: Citation to format
            
        Returns:
            Formatted citation string
        """
        if self.style == 'apa':
            return citation.to_apa()
        elif self.style == 'mla':
            return citation.to_mla()
        elif self.style == 'chicago':
            return citation.to_chicago()
        else:
            return str(citation.__dict__)
    
    def format_all(self) -> List[str]:
        """Format all citations in the current style.
        
        Returns:
            List of formatted citation strings
        """
        return [self.format_citation(c) for c in self.citations]
    
    def generate_bibliography(self) -> str:
        """Generate a formatted bibliography.
        
        Returns:
            Bibliography string with all citations
        """
        if not self.citations:
            return "No citations available."
        
        # Sort citations by author last name
        sorted_citations = sorted(self.citations, 
                                 key=lambda c: c.authors[0] if c.authors else 'ZZZ')
        
        lines = []
        
        if self.style == 'apa':
            lines.append("References\n")
        elif self.style == 'mla':
            lines.append("Works Cited\n")
        else:
            lines.append("Bibliography\n")
        
        for citation in sorted_citations:
            lines.append(self.format_citation(citation))
        
        return '\n'.join(lines)
    
    def generate_inline_citation(self, citation: Citation) -> str:
        """Generate an inline citation reference.
        
        Args:
            citation: Citation to reference
            
        Returns:
            Inline citation string
        """
        if self.style == 'apa':
            return f"({citation.format_authors_apa()}, {citation.year})"
        elif self.style == 'mla':
            return f"({citation.format_authors_mla()})"
        elif self.style == 'chicago':
            author = citation.authors[0] if citation.authors else "Unknown"
            return f"({author} {citation.year})"
        else:
            return f"[{citation.year}]"
    
    def export_to_bibtex(self) -> str:
        """Export citations to BibTeX format.
        
        Returns:
            BibTeX-formatted string
        """
        entries = []
        
        for i, citation in enumerate(self.citations, 1):
            entry = f"@article{{ref{i},\n"
            entry += f"  author = {{{' and '.join(citation.authors)}}},\n"
            entry += f"  title = {{{citation.title}}},\n"
            entry += f"  journal = {{{citation.source}}},\n"
            entry += f"  year = {{{citation.year}}}"
            
            if citation.url:
                entry += f",\n  url = {{{citation.url}}}"
            
            entry += "\n}"
            entries.append(entry)
        
        return '\n\n'.join(entries)
