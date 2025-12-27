"""Report Generator

This module generates formatted research reports from framework analyses and
meta-auditor synthesis.
"""

from typing import Dict, Any, List, Optional
from datetime import datetime


class ReportGenerator:
    """Generates formatted research reports.
    
    Supports multiple output formats including markdown, HTML, and structured JSON.
    """
    
    def __init__(self, title: str, author: Optional[str] = None):
        """Initialize the report generator.
        
        Args:
            title: Report title
            author: Report author name
        """
        self.title = title
        self.author = author or "Research System"
        self.timestamp = datetime.now()
        self.sections: List[Dict[str, Any]] = []
    
    def add_section(self, title: str, content: str, level: int = 2) -> None:
        """Add a section to the report.
        
        Args:
            title: Section title
            content: Section content
            level: Heading level (1-6)
        """
        self.sections.append({
            'title': title,
            'content': content,
            'level': level
        })
    
    def add_framework_analysis(self, framework_name: str, framework: Any) -> None:
        """Add framework analysis section.
        
        Args:
            framework_name: Name of the framework
            framework: Framework instance with results
        """
        breakdown = framework.get_detailed_breakdown()
        
        # Build content
        content = f"""**Overall Score:** {breakdown.get('overall_score', breakdown.get('base_score', 'N/A'))}/10\n"""
        
        if 'interpretation' in breakdown:
            content += f"**Assessment:** {breakdown['interpretation']}\n\n"
        
        # Add criteria breakdown
        if 'criteria' in breakdown:
            content += "### Criteria Breakdown\n\n"
            for criterion in breakdown['criteria']:
                content += f"- **{criterion['name'].replace('_', ' ').title()}**: "
                content += f"{criterion['score']}/10 (weight: {criterion['weight']:.0%})\n"
                if criterion.get('evidence'):
                    content += f"  - Evidence: {criterion['evidence']}\n"
        
        # Add recommendations
        if hasattr(framework, 'get_recommendations'):
            recs = framework.get_recommendations()
            if recs:
                content += "\n### Recommendations\n\n"
                for rec in recs:
                    content += f"- {rec}\n"
        
        self.add_section(framework_name.replace('_', ' ').title(), content, level=2)
    
    def add_meta_analysis(self, meta_auditor: Any) -> None:
        """Add meta-auditor synthesis section.
        
        Args:
            meta_auditor: MetaAuditor instance with synthesis
        """
        synthesis = meta_auditor.synthesize_findings()
        
        # Overall viability
        content = f"""**Overall Viability Score:** {synthesis['overall_viability']['score']}/10\n"""
        content += f"**Assessment:** {synthesis['overall_viability']['interpretation']}\n\n"
        
        # Framework scores summary
        content += "### Framework Scores\n\n"
        for name, data in synthesis['framework_scores'].items():
            content += f"- **{name.replace('_', ' ').title()}**: {data['score']}/10 ({data['interpretation']})\n"
        
        # Critical risks
        if synthesis['critical_risks']:
            content += "\n### Critical Risks\n\n"
            for risk in synthesis['critical_risks']:
                content += f"- **[{risk['severity'].upper()}]** {risk['description']}\n"
                content += f"  - Impact: {risk['impact']}\n"
                if risk.get('mitigation'):
                    content += f"  - Mitigation: {risk['mitigation']}\n"
        
        # Key opportunities
        if synthesis['key_opportunities']:
            content += "\n### Key Opportunities\n\n"
            for opp in synthesis['key_opportunities']:
                content += f"- **{opp['category']}**: {opp['description']}\n"
                content += f"  - Action: {opp['action']}\n"
        
        self.add_section("Meta-Analysis & Strategic Synthesis", content, level=2)
        
        # Strategic recommendations
        if synthesis['strategic_recommendations']:
            rec_content = ""
            
            # Group by priority
            by_priority = {}
            for rec in synthesis['strategic_recommendations']:
                priority = rec['priority']
                if priority not in by_priority:
                    by_priority[priority] = []
                by_priority[priority].append(rec)
            
            for priority in ['critical', 'high', 'medium', 'low']:
                if priority in by_priority:
                    rec_content += f"\n#### {priority.title()} Priority\n\n"
                    for rec in by_priority[priority]:
                        rec_content += f"- **{rec['recommendation']}**\n"
                        rec_content += f"  - Category: {rec['category']}\n"
                        rec_content += f"  - Rationale: {rec['rationale']}\n"
                        rec_content += f"  - Timeline: {rec['timeline']}\n"
            
            self.add_section("Strategic Recommendations", rec_content, level=2)
    
    def generate_markdown(self) -> str:
        """Generate report in Markdown format.
        
        Returns:
            Markdown-formatted report string
        """
        lines = []
        
        # Header
        lines.append(f"# {self.title}\n")
        lines.append(f"**Author:** {self.author}\n")
        lines.append(f"**Date:** {self.timestamp.strftime('%Y-%m-%d %H:%M:%S')}\n")
        lines.append("---\n")
        
        # Sections
        for section in self.sections:
            heading = '#' * section['level']
            lines.append(f"{heading} {section['title']}\n")
            lines.append(f"{section['content']}\n")
        
        return '\n'.join(lines)
    
    def generate_html(self) -> str:
        """Generate report in HTML format.
        
        Returns:
            HTML-formatted report string
        """
        lines = []
        
        # HTML header
        lines.append("<!DOCTYPE html>")
        lines.append("<html>")
        lines.append("<head>")
        lines.append(f"<title>{self.title}</title>")
        lines.append("<style>")
        lines.append("body { font-family: Arial, sans-serif; max-width: 900px; margin: 0 auto; padding: 20px; }")
        lines.append("h1 { color: #333; border-bottom: 2px solid #333; }")
        lines.append("h2 { color: #555; margin-top: 30px; }")
        lines.append("h3 { color: #777; }")
        lines.append(".metadata { color: #888; font-style: italic; }")
        lines.append("</style>")
        lines.append("</head>")
        lines.append("<body>")
        
        # Content
        lines.append(f"<h1>{self.title}</h1>")
        lines.append(f"<p class='metadata'>Author: {self.author}</p>")
        lines.append(f"<p class='metadata'>Date: {self.timestamp.strftime('%Y-%m-%d %H:%M:%S')}</p>")
        lines.append("<hr>")
        
        for section in self.sections:
            lines.append(f"<h{section['level']}>{section['title']}</h{section['level']}>")
            # Convert markdown-style content to HTML
            content_html = section['content'].replace('\n', '<br>\n')
            content_html = content_html.replace('**', '<strong>').replace('**', '</strong>')
            lines.append(f"<div>{content_html}</div>")
        
        lines.append("</body>")
        lines.append("</html>")
        
        return '\n'.join(lines)
    
    def generate_json(self) -> Dict[str, Any]:
        """Generate report in structured JSON format.
        
        Returns:
            Dictionary with structured report data
        """
        return {
            'title': self.title,
            'author': self.author,
            'timestamp': self.timestamp.isoformat(),
            'sections': self.sections
        }
