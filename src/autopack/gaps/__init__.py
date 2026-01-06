"""Gap detection module - deterministic gap scanning for autonomy loop.

Public API exports:
    - GapReportV1: gap report schema
    - GapScanner: deterministic gap scanner
    - scan_workspace: scan workspace for gaps
"""

from .models import GapReportV1, Gap, GapEvidence, SafeRemediation, GapSummary
from .scanner import GapScanner, scan_workspace

__all__ = [
    # Models
    "GapReportV1",
    "Gap",
    "GapEvidence",
    "SafeRemediation",
    "GapSummary",
    # Scanner
    "GapScanner",
    "scan_workspace",
]
