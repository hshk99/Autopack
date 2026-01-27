"""Gap detection module - deterministic gap scanning for autonomy loop.

Public API exports:
    - GapReportV1: gap report schema
    - GapScanner: deterministic gap scanner
    - scan_workspace: scan workspace for gaps
    - scan_gaps: library façade for CLI/programmatic use (BUILD-179)
    - GapScanResult: result type for scan_gaps
"""

from .api import GapScanResult, scan_gaps
from .models import Gap, GapEvidence, GapReportV1, GapSummary, SafeRemediation
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
    # Library API (BUILD-179)
    "scan_gaps",
    "GapScanResult",
]
