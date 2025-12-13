"""
Universal Research Analyzer

Analyzes research files to find gaps between current state and research findings.
Works for any project by comparing ProjectContext against research catalog.
"""

import json
import os
from pathlib import Path
from typing import List, Dict
from datetime import datetime
import anthropic

from scripts.research.data_structures import (
    ProjectContext, ResearchGap, OpportunityAnalysis,
    GapType, Priority, Effort
)


class ResearchAnalyzer:
    """
    Analyzes research to find implementation opportunities.

    Compares current project state (from ProjectContext) against research
    findings to identify:
    - Feature gaps (market/user research vs implemented features)
    - Compliance gaps (regulatory requirements vs current state)
    - Competitive gaps (competitors vs our features)
    - Vision alignment gaps (vision vs current state)
    """

    def __init__(self, project_id: str):
        self.project_id = project_id
        self.anthropic_client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    def analyze(self, context: ProjectContext) -> OpportunityAnalysis:
        """Analyze research against context to find gaps"""
        print(f"\n{'='*60}")
        print(f"ANALYZING RESEARCH: {self.project_id}")
        print(f"{'='*60}\n")

        analysis = OpportunityAnalysis(project_id=self.project_id)

        # Phase 1: Find feature gaps (market/competitive research vs implemented)
        print("Phase 1: Finding feature gaps...")
        feature_gaps = self._find_feature_gaps(context)
        analysis.gaps.extend(feature_gaps)

        # Phase 2: Find compliance gaps (regulatory requirements vs current)
        print("\nPhase 2: Finding compliance gaps...")
        compliance_gaps = self._find_compliance_gaps(context)
        analysis.gaps.extend(compliance_gaps)

        # Phase 3: Find competitive gaps (competitors vs our features)
        print("\nPhase 3: Finding competitive gaps...")
        competitive_gaps = self._find_competitive_gaps(context)
        analysis.gaps.extend(competitive_gaps)

        # Phase 4: Find vision alignment gaps (vision vs current state)
        print("\nPhase 4: Finding vision alignment gaps...")
        vision_gaps = self._find_vision_gaps(context)
        analysis.gaps.extend(vision_gaps)

        # Phase 5: Extract strategic insights (cross-cutting themes)
        print("\nPhase 5: Extracting strategic insights...")
        analysis.strategic_insights = self._extract_strategic_insights(context, analysis.gaps)

        print(f"\n{'='*60}")
        print(f"RESEARCH ANALYSIS COMPLETE")
        print(f"{'='*60}\n")
        self._print_summary(analysis)

        return analysis

    def _find_feature_gaps(self, context: ProjectContext) -> List[ResearchGap]:
        """Find gaps between market opportunities and implemented features"""
        if not context.market_opportunities:
            print("  ⚠️  No market opportunities found")
            return []

        # Get list of implemented feature titles
        implemented = [f['title'] for f in context.implemented_features]
        planned = [f['title'] for f in context.planned_features]

        # Use LLM to identify which opportunities are NOT addressed
        prompt = f"""Analyze market opportunities against implemented and planned features.

MARKET OPPORTUNITIES:
{json.dumps(context.market_opportunities, indent=2)}

IMPLEMENTED FEATURES:
{json.dumps(implemented[:20], indent=2)}

PLANNED FEATURES:
{json.dumps(planned[:20], indent=2)}

Identify market opportunities that are NOT adequately addressed by implemented or planned features.

For each gap, provide:
1. Title (concise, actionable)
2. Description (what's missing)
3. Current state (what we have now)
4. Desired state (what we should have)
5. Priority (critical/high/medium/low)
6. Effort (low/medium/high)

Return JSON array:
[
  {{
    "title": "...",
    "description": "...",
    "current_state": "...",
    "desired_state": "...",
    "priority": "high",
    "effort": "medium"
  }}
]"""

        try:
            response = self.anthropic_client.messages.create(
                model="claude-3-5-haiku-20241022",
                max_tokens=2000,
                messages=[{"role": "user", "content": prompt}]
            )

            gaps_data = json.loads(response.content[0].text)
            gaps = []

            for i, gap_data in enumerate(gaps_data):
                gap = ResearchGap(
                    gap_id=f"feature_gap_{i+1}",
                    gap_type=GapType.FEATURE_GAP,
                    title=gap_data['title'],
                    description=gap_data['description'],
                    current_state=gap_data['current_state'],
                    desired_state=gap_data['desired_state'],
                    source_research=['market_research'],
                    priority=Priority[gap_data['priority'].upper()],
                    effort=Effort[gap_data['effort'].upper()]
                )
                gaps.append(gap)

            print(f"  ✓ Found {len(gaps)} feature gaps")
            return gaps

        except Exception as e:
            print(f"  ⚠️  Error finding feature gaps: {e}")
            return []

    def _find_compliance_gaps(self, context: ProjectContext) -> List[ResearchGap]:
        """Find gaps between regulatory requirements and current state"""
        if not context.regulatory_requirements:
            print("  ⚠️  No regulatory requirements found")
            return []

        # Use LLM to identify compliance gaps
        prompt = f"""Analyze regulatory/compliance requirements against current implementation.

REGULATORY REQUIREMENTS:
{json.dumps(context.regulatory_requirements, indent=2)}

IMPLEMENTED FEATURES:
{json.dumps([f['title'] for f in context.implemented_features[:20]], indent=2)}

KNOWN ISSUES:
{json.dumps([i['title'] for i in context.known_issues[:10]], indent=2)}

Identify regulatory requirements that are NOT adequately addressed.

For each compliance gap, provide:
1. Title
2. Description
3. Current state
4. Desired state
5. Priority (critical for legal requirements)
6. Effort estimate

Return JSON array:
[
  {{
    "title": "...",
    "description": "...",
    "current_state": "...",
    "desired_state": "...",
    "priority": "critical",
    "effort": "high"
  }}
]"""

        try:
            response = self.anthropic_client.messages.create(
                model="claude-3-5-haiku-20241022",
                max_tokens=2000,
                messages=[{"role": "user", "content": prompt}]
            )

            gaps_data = json.loads(response.content[0].text)
            gaps = []

            for i, gap_data in enumerate(gaps_data):
                gap = ResearchGap(
                    gap_id=f"compliance_gap_{i+1}",
                    gap_type=GapType.COMPLIANCE_GAP,
                    title=gap_data['title'],
                    description=gap_data['description'],
                    current_state=gap_data['current_state'],
                    desired_state=gap_data['desired_state'],
                    source_research=['regulatory_requirements'],
                    priority=Priority[gap_data['priority'].upper()],
                    effort=Effort[gap_data['effort'].upper()]
                )
                gaps.append(gap)

            print(f"  ✓ Found {len(gaps)} compliance gaps")
            return gaps

        except Exception as e:
            print(f"  ⚠️  Error finding compliance gaps: {e}")
            return []

    def _find_competitive_gaps(self, context: ProjectContext) -> List[ResearchGap]:
        """Find gaps between competitors' features and our features"""
        if not context.competitive_gaps:
            print("  ⚠️  No competitive gaps identified")
            return []

        # Use LLM to prioritize competitive gaps
        prompt = f"""Analyze competitive gaps against product vision and implemented features.

COMPETITIVE GAPS (features competitors have):
{json.dumps(context.competitive_gaps, indent=2)}

OUR VISION:
{context.vision_statement or "Not specified"}

OUR IMPLEMENTED FEATURES:
{json.dumps([f['title'] for f in context.implemented_features[:20]], indent=2)}

OUR PLANNED FEATURES:
{json.dumps([f['title'] for f in context.planned_features[:20]], indent=2)}

Identify which competitive gaps are worth addressing based on:
- Strategic alignment with our vision
- User value (not just feature parity)
- Competitive necessity

For each gap worth addressing:
1. Title
2. Description
3. Current state
4. Desired state
5. Priority
6. Effort

Return JSON array (only include gaps worth addressing):
[
  {{
    "title": "...",
    "description": "...",
    "current_state": "...",
    "desired_state": "...",
    "priority": "high",
    "effort": "medium"
  }}
]"""

        try:
            response = self.anthropic_client.messages.create(
                model="claude-3-5-haiku-20241022",
                max_tokens=2000,
                messages=[{"role": "user", "content": prompt}]
            )

            gaps_data = json.loads(response.content[0].text)
            gaps = []

            for i, gap_data in enumerate(gaps_data):
                gap = ResearchGap(
                    gap_id=f"competitive_gap_{i+1}",
                    gap_type=GapType.MARKET_GAP,
                    title=gap_data['title'],
                    description=gap_data['description'],
                    current_state=gap_data['current_state'],
                    desired_state=gap_data['desired_state'],
                    source_research=['competitive_analysis'],
                    priority=Priority[gap_data['priority'].upper()],
                    effort=Effort[gap_data['effort'].upper()]
                )
                gaps.append(gap)

            print(f"  ✓ Found {len(gaps)} competitive gaps worth addressing")
            return gaps

        except Exception as e:
            print(f"  ⚠️  Error finding competitive gaps: {e}")
            return []

    def _find_vision_gaps(self, context: ProjectContext) -> List[ResearchGap]:
        """Find gaps between product vision and current implementation"""
        if not context.vision_statement:
            print("  ⚠️  No product vision found")
            return []

        # Use LLM to identify vision alignment gaps
        prompt = f"""Analyze alignment between product vision and current implementation.

PRODUCT VISION:
{context.vision_statement}

TARGET USERS:
{json.dumps(context.target_users, indent=2)}

CORE PRINCIPLES:
{json.dumps(context.core_principles, indent=2)}

IMPLEMENTED FEATURES:
{json.dumps([f['title'] for f in context.implemented_features[:20]], indent=2)}

ARCHITECTURE CONSTRAINTS:
{json.dumps([a['title'] for a in context.architecture_constraints[:10]], indent=2)}

Identify areas where current implementation does NOT align with vision/principles.

For each vision gap:
1. Title
2. Description
3. Current state
4. Desired state (aligned with vision)
5. Priority
6. Effort

Return JSON array:
[
  {{
    "title": "...",
    "description": "...",
    "current_state": "...",
    "desired_state": "...",
    "priority": "high",
    "effort": "medium"
  }}
]"""

        try:
            response = self.anthropic_client.messages.create(
                model="claude-3-5-haiku-20241022",
                max_tokens=2000,
                messages=[{"role": "user", "content": prompt}]
            )

            gaps_data = json.loads(response.content[0].text)
            gaps = []

            for i, gap_data in enumerate(gaps_data):
                gap = ResearchGap(
                    gap_id=f"vision_gap_{i+1}",
                    gap_type=GapType.VISION_GAP,
                    title=gap_data['title'],
                    description=gap_data['description'],
                    current_state=gap_data['current_state'],
                    desired_state=gap_data['desired_state'],
                    source_research=['product_vision'],
                    priority=Priority[gap_data['priority'].upper()],
                    effort=Effort[gap_data['effort'].upper()]
                )
                gaps.append(gap)

            print(f"  ✓ Found {len(gaps)} vision alignment gaps")
            return gaps

        except Exception as e:
            print(f"  ⚠️  Error finding vision gaps: {e}")
            return []

    def _extract_strategic_insights(self, context: ProjectContext, gaps: List[ResearchGap]) -> List[str]:
        """Extract cross-cutting strategic insights from all gaps"""
        if not gaps:
            return []

        # Use LLM to identify strategic themes
        gaps_summary = []
        for gap in gaps[:20]:  # Max 20 gaps
            gaps_summary.append({
                'type': gap.gap_type.value,
                'title': gap.title,
                'priority': gap.priority.value
            })

        prompt = f"""Analyze these gaps to identify strategic themes and insights.

GAPS:
{json.dumps(gaps_summary, indent=2)}

PRODUCT VISION:
{context.vision_statement or "Not specified"}

MARKET OPPORTUNITIES:
{json.dumps(context.market_opportunities[:5], indent=2) if context.market_opportunities else "None"}

Identify 3-5 strategic insights that emerge from these gaps. Look for:
- Common themes across multiple gaps
- Strategic direction suggested by gaps
- Priority areas for investment
- Risks if gaps are not addressed

Return JSON array of strings:
[
  "Insight 1...",
  "Insight 2...",
  "Insight 3..."
]"""

        try:
            response = self.anthropic_client.messages.create(
                model="claude-3-5-haiku-20241022",
                max_tokens=1000,
                messages=[{"role": "user", "content": prompt}]
            )

            insights = json.loads(response.content[0].text)
            print(f"  ✓ Extracted {len(insights)} strategic insights")
            return insights

        except Exception as e:
            print(f"  ⚠️  Error extracting insights: {e}")
            return []

    def _print_summary(self, analysis: OpportunityAnalysis):
        """Print summary of analysis"""
        print(f"Summary:")
        print(f"  • Total gaps: {len(analysis.gaps)}")
        print(f"  • Critical: {len(analysis.get_by_priority(Priority.CRITICAL))}")
        print(f"  • High: {len(analysis.get_by_priority(Priority.HIGH))}")
        print(f"  • Medium: {len(analysis.get_by_priority(Priority.MEDIUM))}")
        print(f"  • Low: {len(analysis.get_by_priority(Priority.LOW))}")
        print(f"\nGaps by type:")
        for gap_type in GapType:
            count = len(analysis.get_by_type(gap_type))
            if count > 0:
                print(f"  • {gap_type.value}: {count}")
        print(f"\nStrategic insights: {len(analysis.strategic_insights)}")


if __name__ == "__main__":
    import sys
    from scripts.research.context_assembler import ContextAssembler

    project_id = sys.argv[1] if len(sys.argv) > 1 else "file-organizer-app-v1"

    # First assemble context
    print("Assembling context...")
    assembler = ContextAssembler(project_id)
    context = assembler.assemble()

    # Then analyze research
    analyzer = ResearchAnalyzer(project_id)
    analysis = analyzer.analyze(context)

    # Save to JSON
    output_path = Path(f".autonomous_runs/{project_id}/opportunity_analysis.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    output_data = {
        'project_id': analysis.project_id,
        'analyzed_at': analysis.analyzed_at.isoformat(),
        'gaps': [
            {
                'gap_id': g.gap_id,
                'gap_type': g.gap_type.value,
                'title': g.title,
                'description': g.description,
                'current_state': g.current_state,
                'desired_state': g.desired_state,
                'priority': g.priority.value,
                'effort': g.effort.value,
                'source_research': g.source_research
            }
            for g in analysis.gaps
        ],
        'strategic_insights': analysis.strategic_insights
    }

    output_path.write_text(json.dumps(output_data, indent=2), encoding='utf-8')
    print(f"\n✓ Analysis saved to {output_path}")
