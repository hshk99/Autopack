"""Report Generator

This module generates formatted research reports from meta-auditor synthesis.
"""

from datetime import datetime
from typing import Any, Dict, Optional


class ReportGenerator:
    """Generates formatted research reports.

    Attributes:
        synthesis: Meta-auditor synthesis data
        report_config: Report configuration options
    """

    def __init__(self, synthesis: Dict[str, Any], report_config: Optional[Dict[str, Any]] = None):
        """Initialize the report generator.

        Args:
            synthesis: Meta-auditor synthesis dictionary
            report_config: Optional report configuration
        """
        self.synthesis = synthesis
        self.report_config = report_config or self._default_config()

    def _default_config(self) -> Dict[str, Any]:
        """Get default report configuration."""
        return {
            "include_executive_summary": True,
            "include_framework_details": True,
            "include_risk_analysis": True,
            "include_recommendations": True,
            "include_next_steps": True,
            "format": "markdown",
        }

    def generate_report(self) -> str:
        """Generate complete research report.

        Returns:
            Formatted report string
        """
        report_format = self.report_config.get("format", "markdown")

        if report_format == "markdown":
            return self._generate_markdown_report()
        elif report_format == "html":
            return self._generate_html_report()
        else:
            return self._generate_text_report()

    def _generate_markdown_report(self) -> str:
        """Generate Markdown formatted report."""
        sections = []

        # Header
        sections.append(self._generate_header())

        # Executive Summary
        if self.report_config.get("include_executive_summary", True):
            sections.append(self._generate_executive_summary())

        # Overall Assessment
        sections.append(self._generate_overall_assessment())

        # Framework Analyses
        if self.report_config.get("include_framework_details", True):
            sections.append(self._generate_framework_analyses())

        # Risk Analysis
        if self.report_config.get("include_risk_analysis", True):
            sections.append(self._generate_risk_analysis())

        # Recommendations
        if self.report_config.get("include_recommendations", True):
            sections.append(self._generate_recommendations())

        # Next Steps
        if self.report_config.get("include_next_steps", True):
            sections.append(self._generate_next_steps())

        # Footer
        sections.append(self._generate_footer())

        return "\n\n".join(sections)

    def _generate_header(self) -> str:
        """Generate report header."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return f"""# Strategic Research Analysis Report

**Generated:** {timestamp}
**Confidence Level:** {self.synthesis.get("confidence_level", "Unknown")}
"""

    def _generate_executive_summary(self) -> str:
        """Generate executive summary section."""
        decision = self.synthesis.get("decision_recommendation", "Unknown")
        score = self.synthesis.get("overall_score", 0)

        summary = f"""## Executive Summary

**Overall Assessment Score:** {score}/10
**Strategic Recommendation:** {decision}

### Key Highlights
"""

        # Critical success factors
        csf = self.synthesis.get("critical_success_factors", [])
        if csf:
            summary += "\n**Critical Success Factors:**\n"
            for factor in csf[:3]:
                summary += f"- {factor}\n"

        # Top risks
        risks = self.synthesis.get("key_risks", [])
        if risks:
            summary += "\n**Key Risks:**\n"
            for risk in risks[:3]:
                summary += f"- [{risk['severity'].upper()}] {risk['description']}\n"

        return summary

    def _generate_overall_assessment(self) -> str:
        """Generate overall assessment section."""
        score = self.synthesis.get("overall_score", 0)
        decision = self.synthesis.get("decision_recommendation", "Unknown")
        confidence = self.synthesis.get("confidence_level", "Unknown")

        # Interpretation
        if score >= 7.5:
            interpretation = "Strong opportunity with high potential for success"
        elif score >= 6.0:
            interpretation = "Viable opportunity with manageable risks"
        elif score >= 4.0:
            interpretation = "Marginal opportunity requiring significant improvements"
        else:
            interpretation = "Weak opportunity with substantial challenges"

        return f"""## Overall Assessment

**Score:** {score}/10
**Interpretation:** {interpretation}
**Decision:** {decision}
**Confidence:** {confidence}

### Score Breakdown

The overall score is calculated from four key frameworks:
- Market Attractiveness (30% weight)
- Product Feasibility (30% weight)
- Competitive Position (20% weight)
- Adoption Readiness (20% weight)
"""

    def _generate_framework_analyses(self) -> str:
        """Generate detailed framework analyses section."""
        section = "## Framework Analyses\n\n"

        framework_analyses = self.synthesis.get("framework_analyses", {})

        # Market Attractiveness
        if "market_attractiveness" in framework_analyses:
            section += self._format_market_analysis(framework_analyses["market_attractiveness"])

        # Product Feasibility
        if "product_feasibility" in framework_analyses:
            section += self._format_feasibility_analysis(framework_analyses["product_feasibility"])

        # Competitive Intensity
        if "competitive_intensity" in framework_analyses:
            section += self._format_competition_analysis(
                framework_analyses["competitive_intensity"]
            )

        # Adoption Readiness
        if "adoption_readiness" in framework_analyses:
            section += self._format_adoption_analysis(framework_analyses["adoption_readiness"])

        return section

    def _format_market_analysis(self, analysis: Dict[str, Any]) -> str:
        """Format market attractiveness analysis."""
        score = analysis.get("total_score", 0)
        interpretation = analysis.get("interpretation", "Unknown")

        section = f"""### Market Attractiveness

**Score:** {score}/10
**Assessment:** {interpretation}

**Key Factors:**
"""

        scores = analysis.get("scores", {})
        for criterion, value in scores.items():
            section += f"- {criterion.replace('_', ' ').title()}: {value}/10\n"

        return section + "\n"

    def _format_feasibility_analysis(self, analysis: Dict[str, Any]) -> str:
        """Format product feasibility analysis."""
        base_score = analysis.get("base_score", 0)
        adjusted_score = analysis.get("risk_adjusted_score", 0)
        interpretation = analysis.get("interpretation", "Unknown")

        section = f"""### Product Feasibility

**Base Score:** {base_score}/10
**Risk-Adjusted Score:** {adjusted_score}/10
**Assessment:** {interpretation}

**Key Factors:**
"""

        scores = analysis.get("scores", {})
        for criterion, value in scores.items():
            section += f"- {criterion.replace('_', ' ').title()}: {value}/10\n"

        # Risk factors
        risk_factors = analysis.get("risk_factors", [])
        if risk_factors:
            section += "\n**Risk Factors:**\n"
            for risk in risk_factors:
                section += f"- [{risk['severity'].upper()}] {risk['name']}\n"

        return section + "\n"

    def _format_competition_analysis(self, analysis: Dict[str, Any]) -> str:
        """Format competitive intensity analysis."""
        score = analysis.get("total_score", 0)
        interpretation = analysis.get("interpretation", "Unknown")

        section = f"""### Competitive Intensity

**Score:** {score}/10
**Assessment:** {interpretation}

**Key Forces:**
"""

        scores = analysis.get("scores", {})
        for criterion, value in scores.items():
            section += f"- {criterion.replace('_', ' ').title()}: {value}/10\n"

        # Market concentration
        concentration = analysis.get("market_concentration", {})
        if concentration:
            section += "\n**Market Concentration:**\n"
            section += f"- Level: {concentration.get('concentration_level', 'Unknown')}\n"
            section += f"- HHI: {concentration.get('herfindahl_index', 0)}\n"

        return section + "\n"

    def _format_adoption_analysis(self, analysis: Dict[str, Any]) -> str:
        """Format adoption readiness analysis."""
        base_score = analysis.get("base_score", 0)
        adjusted_score = analysis.get("barrier_adjusted_score", 0)
        interpretation = analysis.get("interpretation", "Unknown")
        timeline = analysis.get("adoption_timeline", "Unknown")

        section = f"""### Adoption Readiness

**Base Score:** {base_score}/10
**Barrier-Adjusted Score:** {adjusted_score}/10
**Assessment:** {interpretation}
**Timeline:** {timeline}

**Key Factors:**
"""

        scores = analysis.get("scores", {})
        for criterion, value in scores.items():
            section += f"- {criterion.replace('_', ' ').title()}: {value}/10\n"

        # Barriers
        barriers = analysis.get("barriers", [])
        if barriers:
            section += "\n**Adoption Barriers:**\n"
            for barrier in barriers:
                section += f"- [{barrier['impact'].upper()}] {barrier['name']}\n"

        return section + "\n"

    def _generate_risk_analysis(self) -> str:
        """Generate risk analysis section."""
        section = "## Risk Analysis\n\n"

        risks = self.synthesis.get("key_risks", [])
        if not risks:
            return section + "No significant risks identified.\n"

        # Group by severity
        critical_risks = [r for r in risks if r["severity"] == "critical"]
        high_risks = [r for r in risks if r["severity"] == "high"]
        medium_risks = [r for r in risks if r["severity"] == "medium"]

        if critical_risks:
            section += "### Critical Risks\n\n"
            for risk in critical_risks:
                section += f"**{risk['description']}**\n"
                section += f"- Category: {risk['category']}\n"
                section += f"- Mitigation: {risk['mitigation']}\n\n"

        if high_risks:
            section += "### High Risks\n\n"
            for risk in high_risks:
                section += f"**{risk['description']}**\n"
                section += f"- Category: {risk['category']}\n"
                section += f"- Mitigation: {risk['mitigation']}\n\n"

        if medium_risks:
            section += "### Medium Risks\n\n"
            for risk in medium_risks[:5]:  # Limit to top 5
                section += f"- {risk['description']} ({risk['category']})\n"

        return section

    def _generate_recommendations(self) -> str:
        """Generate recommendations section."""
        section = "## Strategic Recommendations\n\n"

        recommendations = self.synthesis.get("strategic_recommendations", [])
        if not recommendations:
            return section + "No specific recommendations available.\n"

        for i, rec in enumerate(recommendations, 1):
            section += f"{i}. {rec}\n"

        return section

    def _generate_next_steps(self) -> str:
        """Generate next steps section."""
        section = "## Next Steps\n\n"

        next_steps = self.synthesis.get("next_steps", [])
        if not next_steps:
            return section + "No specific next steps defined.\n"

        for i, step in enumerate(next_steps, 1):
            section += f"{i}. {step}\n"

        return section

    def _generate_footer(self) -> str:
        """Generate report footer."""
        return """---

*This report was generated by the Meta-Auditor Agent using systematic decision frameworks.*
*All scores and recommendations are based on the input data provided to the analysis frameworks.*
"""

    def _generate_html_report(self) -> str:
        """Generate HTML formatted report."""
        # Convert markdown to basic HTML
        markdown_report = self._generate_markdown_report()

        # Simple markdown to HTML conversion
        html = "<html><head><style>body{font-family:Arial,sans-serif;max-width:800px;margin:0 auto;padding:20px;}</style></head><body>"

        # Convert headers
        lines = markdown_report.split("\n")
        for line in lines:
            if line.startswith("# "):
                html += f"<h1>{line[2:]}</h1>"
            elif line.startswith("## "):
                html += f"<h2>{line[3:]}</h2>"
            elif line.startswith("### "):
                html += f"<h3>{line[4:]}</h3>"
            elif line.startswith("- "):
                html += f"<li>{line[2:]}</li>"
            elif line.strip():
                html += f"<p>{line}</p>"

        html += "</body></html>"
        return html

    def _generate_text_report(self) -> str:
        """Generate plain text report."""
        # Remove markdown formatting
        markdown_report = self._generate_markdown_report()
        text = markdown_report.replace("#", "").replace("**", "")
        return text

    def export_to_file(self, filepath: str) -> None:
        """Export report to file.

        Args:
            filepath: Path to output file
        """
        report = self.generate_report()
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(report)
