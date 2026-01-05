"""
Citation validity evaluator for research findings.

Evaluates the validity of citations in research findings by verifying
that quoted text can be found in the original source content.
"""

from typing import Dict, List

from autopack.research.models.validators import CitationValidator, Finding


class CitationValidityEvaluator:
    """
    Evaluates citation validity across a collection of research findings.

    Uses CitationValidator to verify each finding against its source content
    and aggregates results into summary statistics.

    Example:
        evaluator = CitationValidityEvaluator()
        results = evaluator.evaluate_summary(findings, source_map)
        print(f"Citation validity: {results['validity_percentage']:.1f}%")
    """

    def __init__(self) -> None:
        """Initialize the evaluator."""
        self._validator = CitationValidator()

    def evaluate_summary(self, findings: List[Finding], source_content_map: Dict[str, str]) -> Dict:
        """
        Evaluate citation validity for a list of findings.

        Args:
            findings: List of Finding objects to validate.
            source_content_map: Mapping from source identifier (repo name or
                source_hash) to the full source content text.

        Returns:
            Dictionary containing:
                - total_findings: Total number of findings evaluated
                - valid_citations: Count of valid citations
                - invalid_citations: Count of invalid citations
                - validity_percentage: Percentage of valid citations (0-100)
                - failure_breakdown: Dict mapping failure reasons to counts
        """
        total_findings = len(findings)
        valid_citations = 0
        invalid_citations = 0
        failure_breakdown: Dict[str, int] = {}

        for finding in findings:
            # Get source identifier from finding metadata
            source_key = self._get_source_key(finding)
            source_text = source_content_map.get(source_key, "")
            source_hash = finding.source_hash if hasattr(finding, "source_hash") else source_key

            # Verify the citation
            result = self._validator.verify(finding, source_text, source_hash)

            if result.valid:
                valid_citations += 1
            else:
                invalid_citations += 1
                # Track failure reason
                reason = result.reason or "unknown"
                failure_breakdown[reason] = failure_breakdown.get(reason, 0) + 1

        # Calculate validity percentage
        validity_percentage = (
            (valid_citations / total_findings * 100) if total_findings > 0 else 0.0
        )

        return {
            "total_findings": total_findings,
            "valid_citations": valid_citations,
            "invalid_citations": invalid_citations,
            "validity_percentage": validity_percentage,
            "failure_breakdown": failure_breakdown,
        }

    def _get_source_key(self, finding: Finding) -> str:
        """
        Extract the source key from a finding for lookup in source_content_map.

        Args:
            finding: The Finding object to extract source key from.

        Returns:
            Source key string (repo name, source_hash, or empty string).
        """
        # Try to get repo name from metadata first
        if hasattr(finding, "metadata") and finding.metadata:
            if "repo_name" in finding.metadata:
                return finding.metadata["repo_name"]
            if "repo" in finding.metadata:
                return finding.metadata["repo"]

        # Fall back to source_hash
        if hasattr(finding, "source_hash") and finding.source_hash:
            return finding.source_hash

        return ""
