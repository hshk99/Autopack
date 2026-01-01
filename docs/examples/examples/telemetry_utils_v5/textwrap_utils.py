"""Text wrapping utility functions for text formatting.

This module provides common text wrapping and formatting utilities including:
- wrap_text: Wrap text to a specified width
- indent_text: Add indentation to text lines
- dedent_text: Remove common leading whitespace from text
- fill_text: Wrap and join text into a single string
"""

import textwrap
from typing import List, Optional


def wrap_text(text: str, width: int = 70, break_long_words: bool = True, 
              break_on_hyphens: bool = True) -> List[str]:
    """Wrap text to a specified width.
    
    Breaks text into lines of at most 'width' characters. Returns a list
    of wrapped lines without trailing newlines.
    
    Args:
        text: The input text to wrap
        width: Maximum line width (default: 70)
        break_long_words: If True, break words longer than width (default: True)
        break_on_hyphens: If True, break on hyphens in compound words (default: True)
        
    Returns:
        A list of wrapped text lines
        
    Examples:
        >>> wrap_text("This is a long line of text that needs to be wrapped", width=20)
        ['This is a long line', 'of text that needs', 'to be wrapped']
        >>> wrap_text("Short text", width=50)
        ['Short text']
        >>> wrap_text("Word" * 20, width=15, break_long_words=False)
        ['WordWordWordWordWordWordWordWordWordWordWordWordWordWordWordWordWordWordWordWord']
        >>> wrap_text("", width=70)
        []
    """
    if not text:
        return []
    
    wrapper = textwrap.TextWrapper(
        width=width,
        break_long_words=break_long_words,
        break_on_hyphens=break_on_hyphens
    )
    
    return wrapper.wrap(text)


def indent_text(text: str, prefix: str = "    ", predicate: Optional[callable] = None) -> str:
    """Add indentation to text lines.
    
    Adds the specified prefix to each line in the text. If a predicate function
    is provided, only lines for which predicate(line) returns True are indented.
    
    Args:
        text: The input text to indent
        prefix: String to prepend to each line (default: four spaces)
        predicate: Optional function to determine which lines to indent
        
    Returns:
        The indented text as a single string
        
    Examples:
        >>> indent_text("Line 1\nLine 2\nLine 3")
        '    Line 1\n    Line 2\n    Line 3'
        >>> indent_text("Hello\nWorld", prefix=">> ")
        '>> Hello\n>> World'
        >>> indent_text("A\nB\nC", prefix="  ", predicate=lambda line: line != "B")
        '  A\nB\n  C'
        >>> indent_text("", prefix="  ")
        ''
    """
    return textwrap.indent(text, prefix, predicate=predicate)


def dedent_text(text: str) -> str:
    """Remove common leading whitespace from text.
    
    Removes any common leading whitespace from every line in the text.
    This is useful for cleaning up indented text blocks while preserving
    relative indentation.
    
    Args:
        text: The input text to dedent
        
    Returns:
        The dedented text
        
    Examples:
        >>> dedent_text("    Line 1\n    Line 2\n    Line 3")
        'Line 1\nLine 2\nLine 3'
        >>> dedent_text("  Hello\n    World\n  !")
        'Hello\n  World\n!'
        >>> dedent_text("No indent\nHere")
        'No indent\nHere'
        >>> dedent_text("")
        ''
    """
    return textwrap.dedent(text)


def fill_text(text: str, width: int = 70, initial_indent: str = "", 
              subsequent_indent: str = "", break_long_words: bool = True) -> str:
    """Wrap and join text into a single string.
    
    Similar to wrap_text, but returns a single string with lines joined by
    newlines. Supports custom indentation for the first line and subsequent lines.
    
    Args:
        text: The input text to fill
        width: Maximum line width (default: 70)
        initial_indent: String to prepend to the first line (default: "")
        subsequent_indent: String to prepend to subsequent lines (default: "")
        break_long_words: If True, break words longer than width (default: True)
        
    Returns:
        The wrapped text as a single string with newlines
        
    Examples:
        >>> fill_text("This is a long line of text that needs to be wrapped", width=20)
        'This is a long line\nof text that needs\nto be wrapped'
        >>> fill_text("Hello World", width=50, initial_indent="* ")
        '* Hello World'
        >>> fill_text("A B C D E F", width=10, initial_indent="> ", subsequent_indent="  ")
        '> A B C D\n  E F'
        >>> fill_text("", width=70)
        ''
    """
    if not text:
        return ""
    
    wrapper = textwrap.TextWrapper(
        width=width,
        initial_indent=initial_indent,
        subsequent_indent=subsequent_indent,
        break_long_words=break_long_words
    )
    
    return wrapper.fill(text)
