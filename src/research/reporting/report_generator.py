"""
Report Generator

This module generates research reports based on synthesized findings and recommendations.
"""

from src.research.agents.meta_auditor import MetaAuditor
from src.research.reporting.citation_formatter import CitationFormatter


class ReportGenerator:
    """
    The ReportGenerator class generates research reports.
    """

    def __init__(self):
        self.meta_auditor = MetaAuditor()
        self.citation_formatter = CitationFormatter()

    def generate_report(self):
        """
        Generates a research report.

        Returns:
            str: The generated report as a string.
        """
        findings = self.meta_auditor.synthesize_findings()
        recommendations = self.meta_auditor.generate_recommendations(findings)

        report = self._format_report(findings, recommendations)
        return report

    def _format_report(self, findings, recommendations):
        """
        Formats the report content.

        Args:
            findings (dict): The synthesized findings.
            recommendations (list): The strategic recommendations.

        Returns:
            str: The formatted report.
        """
        report = "Research Report\n"
        report += "=" * 50 + "\n\n"
        report += "Findings:\n"
        for key, value in findings.items():
            report += f"{key.capitalize()}:\n"
            report += f"Score: {value['score']}\n"
            report += f"Details: {value['details']}\n\n"

        report += "Recommendations:\n"
        for recommendation in recommendations:
            report += f"- {recommendation}\n"

        report += "\nCitations:\n"
        report += self.citation_formatter.format_citation(
            author="John Doe",
            title="Research Methods",
            year=2025,
            source="Science Publishing"
        )

        return report


if __name__ == "__main__":
    generator = ReportGenerator()
    report = generator.generate_report()

    print(report)

    # Save report to a file
    with open("research_report.txt", "w") as file:
        file.write(report)
