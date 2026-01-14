"""
Universal Decision Engine

Makes strategic implementation decisions with full project context.
Works for any project by considering vision, market, domain, and constraints.
"""

import json
import os
from pathlib import Path
from typing import List, Dict
from datetime import datetime
import anthropic

from scripts.research.data_structures import (
    ProjectContext,
    ResearchGap,
    OpportunityAnalysis,
    ImplementationDecision,
    DecisionReport,
    DecisionType,
    Priority,
    Effort,
)


class DecisionEngine:
    """
    Makes strategic implementation decisions with full context.

    For each gap, decides:
    - IMPLEMENT_NOW: Add to active development
    - IMPLEMENT_LATER: Add to FUTURE_PLAN
    - REVIEW: Needs more research/discussion
    - REJECT: Not aligned with vision/constraints

    Considers:
    - Strategic alignment with vision
    - User impact
    - Competitive necessity
    - Dependencies and blockers
    - Resource fit (budget, timeline, team)
    - Opportunity cost
    """

    def __init__(self, project_id: str):
        self.project_id = project_id
        self.anthropic_client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    def decide(self, gaps: List[ResearchGap], context: ProjectContext) -> DecisionReport:
        """Make implementation decisions for all gaps"""
        print(f"\n{'=' * 60}")
        print(f"MAKING DECISIONS: {self.project_id}")
        print(f"{'=' * 60}\n")

        report = DecisionReport(project_id=self.project_id)

        # Process gaps by priority (critical first)
        critical_gaps = [g for g in gaps if g.priority == Priority.CRITICAL]
        high_gaps = [g for g in gaps if g.priority == Priority.HIGH]
        other_gaps = [g for g in gaps if g.priority not in [Priority.CRITICAL, Priority.HIGH]]

        print(f"Processing {len(critical_gaps)} critical gaps...")
        for gap in critical_gaps:
            decision = self._make_decision(gap, context)
            report.decisions.append(decision)

        print(f"Processing {len(high_gaps)} high-priority gaps...")
        for gap in high_gaps:
            decision = self._make_decision(gap, context)
            report.decisions.append(decision)

        print(f"Processing {len(other_gaps)} medium/low-priority gaps...")
        for gap in other_gaps:
            decision = self._make_decision(gap, context)
            report.decisions.append(decision)

        print(f"\n{'=' * 60}")
        print("DECISION MAKING COMPLETE")
        print(f"{'=' * 60}\n")
        self._print_summary(report)

        return report

    def _make_decision(self, gap: ResearchGap, context: ProjectContext) -> ImplementationDecision:
        """Make decision for a single gap using LLM with full context"""

        # Build comprehensive context for LLM
        decision_prompt = f"""Make a strategic implementation decision for this gap.

GAP DETAILS:
- Type: {gap.gap_type.value}
- Title: {gap.title}
- Description: {gap.description}
- Current State: {gap.current_state}
- Desired State: {gap.desired_state}
- Priority: {gap.priority.value}
- Effort: {gap.effort.value}
- Source Research: {", ".join(gap.source_research)}

PROJECT CONTEXT:
Vision: {context.vision_statement or "Not specified"}
Target Users: {", ".join(context.target_users[:5]) if context.target_users else "Not specified"}
Core Principles: {", ".join(context.core_principles[:5]) if context.core_principles else "Not specified"}

Market Position:
- Key Competitors: {", ".join(context.key_competitors[:3]) if context.key_competitors else "Not specified"}
- Competitive Advantages: {", ".join(context.competitive_advantages[:3]) if context.competitive_advantages else "Not specified"}

Domain Focus: {", ".join(context.domain_focus[:3]) if context.domain_focus else "General purpose"}

Technical Constraints:
- Tech Stack: {", ".join(context.tech_stack[:5]) if context.tech_stack else "Not specified"}
- Architecture Constraints: {len(context.architecture_constraints)} documented decisions
- Known Issues: {len(context.known_issues)} active issues

Current State:
- Implemented Features: {len(context.implemented_features)}
- Planned Features: {len(context.planned_features)}

Make a decision: IMPLEMENT_NOW, IMPLEMENT_LATER, REVIEW, or REJECT

Consider:
1. **Strategic Alignment**: Does this align with our vision and principles?
2. **User Impact**: How much value does this provide to target users?
3. **Competitive Impact**: Is this necessary for competitive positioning?
4. **Dependencies**: What needs to happen first?
5. **Resource Fit**: Do we have the capabilities and bandwidth?
6. **Opportunity Cost**: What are we NOT doing if we do this?

Return JSON:
{{
  "decision": "IMPLEMENT_NOW|IMPLEMENT_LATER|REVIEW|REJECT",
  "rationale": "Why this decision makes strategic sense...",
  "strategic_alignment": "How this aligns (or doesn't) with vision/strategy...",
  "user_impact": "Impact on target users...",
  "competitive_impact": "Impact on competitive position...",
  "prerequisites": ["What needs to happen first..."],
  "estimated_value": 7.5,  // 0-10 scale
  "estimated_effort": 5.0,  // 0-10 scale
  "roi_score": 1.5  // value/effort ratio
}}"""

        try:
            response = self.anthropic_client.messages.create(
                model="claude-3-5-sonnet-20241022",  # Use Sonnet for strategic decisions
                max_tokens=1500,
                messages=[{"role": "user", "content": decision_prompt}],
            )

            result = json.loads(response.content[0].text)

            decision = ImplementationDecision(
                decision_id=f"{gap.gap_id}_decision",
                gap=gap,
                decision=DecisionType[result["decision"]],
                rationale=result["rationale"],
                strategic_alignment=result["strategic_alignment"],
                user_impact=result["user_impact"],
                competitive_impact=result["competitive_impact"],
                prerequisites=result.get("prerequisites", []),
                estimated_value=result.get("estimated_value", 5.0),
                estimated_effort=result.get("estimated_effort", 5.0),
                roi_score=result.get("roi_score", 1.0),
            )

            print(f"  ✓ {gap.title[:50]}... → {decision.decision.value}")
            return decision

        except Exception as e:
            print(f"  ⚠️  Error making decision for {gap.title[:30]}: {e}")
            # Fallback: Default decision based on priority
            return self._default_decision(gap)

    def _default_decision(self, gap: ResearchGap) -> ImplementationDecision:
        """Fallback decision when LLM fails"""
        # Default heuristic based on priority and effort
        if gap.priority == Priority.CRITICAL:
            decision_type = DecisionType.IMPLEMENT_NOW
        elif gap.priority == Priority.HIGH and gap.effort in [Effort.LOW, Effort.MEDIUM]:
            decision_type = DecisionType.IMPLEMENT_NOW
        elif gap.priority in [Priority.HIGH, Priority.MEDIUM]:
            decision_type = DecisionType.IMPLEMENT_LATER
        else:
            decision_type = DecisionType.REVIEW

        return ImplementationDecision(
            decision_id=f"{gap.gap_id}_decision",
            gap=gap,
            decision=decision_type,
            rationale="Default decision based on priority and effort (LLM unavailable)",
            strategic_alignment="Unknown (requires manual review)",
            user_impact="Unknown (requires manual review)",
            competitive_impact="Unknown (requires manual review)",
            estimated_value=5.0,
            estimated_effort=5.0,
            roi_score=1.0,
        )

    def _print_summary(self, report: DecisionReport):
        """Print summary of decisions"""
        print("Summary:")
        print(f"  • Total decisions: {len(report.decisions)}")
        print(f"  • Implement now: {len(report.get_implement_now())}")
        print(f"  • Implement later: {len(report.get_implement_later())}")
        print(f"  • Review: {len(report.get_by_decision_type(DecisionType.REVIEW))}")
        print(f"  • Reject: {len(report.get_by_decision_type(DecisionType.REJECT))}")

        high_roi = report.get_high_roi(threshold=1.5)
        if high_roi:
            print(f"\nHigh ROI opportunities ({len(high_roi)}):")
            for decision in high_roi[:5]:
                print(f"  • {decision.gap.title[:50]} (ROI: {decision.roi_score:.1f})")


class DecisionRouter:
    """
    Routes decisions to appropriate locations in file system.

    - IMPLEMENT_NOW → .autonomous_runs/{project}/archive/research/active/
    - IMPLEMENT_LATER → docs/FUTURE_PLAN.md
    - REVIEW → .autonomous_runs/{project}/archive/research/reviewed/deferred/
    - REJECT → .autonomous_runs/{project}/archive/research/reviewed/rejected/
    """

    def __init__(self, project_id: str):
        self.project_id = project_id

    def route(self, report: DecisionReport) -> Dict:
        """Route decisions to appropriate locations"""
        print(f"\n{'=' * 60}")
        print(f"ROUTING DECISIONS: {self.project_id}")
        print(f"{'=' * 60}\n")

        routing_summary = {"implement_now": 0, "implement_later": 0, "review": 0, "reject": 0}

        # Route IMPLEMENT_NOW to active research
        implement_now = report.get_implement_now()
        if implement_now:
            self._route_to_active(implement_now)
            routing_summary["implement_now"] = len(implement_now)

        # Route IMPLEMENT_LATER to FUTURE_PLAN
        implement_later = report.get_implement_later()
        if implement_later:
            self._route_to_future_plan(implement_later)
            routing_summary["implement_later"] = len(implement_later)

        # Route REVIEW to deferred
        review = report.get_by_decision_type(DecisionType.REVIEW)
        if review:
            self._route_to_review(review)
            routing_summary["review"] = len(review)

        # Route REJECT to rejected
        reject = report.get_by_decision_type(DecisionType.REJECT)
        if reject:
            self._route_to_rejected(reject)
            routing_summary["reject"] = len(reject)

        print(f"\n{'=' * 60}")
        print("ROUTING COMPLETE")
        print(f"{'=' * 60}\n")
        print("Summary:")
        print(f"  • Active: {routing_summary['implement_now']}")
        print(f"  • Future plan: {routing_summary['implement_later']}")
        print(f"  • Review: {routing_summary['review']}")
        print(f"  • Rejected: {routing_summary['reject']}")

        return routing_summary

    def _route_to_active(self, decisions: List[ImplementationDecision]):
        """Route to active research directory"""
        active_dir = self._get_research_dir() / "active"
        active_dir.mkdir(parents=True, exist_ok=True)

        output_file = (
            active_dir / f"implementation_plan_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
        )

        content = "# Implementation Plan: Active Items\n\n"
        content += f"**Generated**: {datetime.now().isoformat()}\n"
        content += f"**Project**: {self.project_id}\n\n"

        for decision in decisions:
            content += f"\n## {decision.gap.title}\n\n"
            content += f"**Type**: {decision.gap.gap_type.value}\n"
            content += f"**Priority**: {decision.gap.priority.value}\n"
            content += f"**Effort**: {decision.gap.effort.value}\n"
            content += f"**ROI Score**: {decision.roi_score:.2f}\n\n"
            content += f"### Description\n{decision.gap.description}\n\n"
            content += f"### Current State\n{decision.gap.current_state}\n\n"
            content += f"### Desired State\n{decision.gap.desired_state}\n\n"
            content += f"### Rationale\n{decision.rationale}\n\n"
            content += f"### User Impact\n{decision.user_impact}\n\n"

            if decision.prerequisites:
                content += "### Prerequisites\n"
                for prereq in decision.prerequisites:
                    content += f"- {prereq}\n"
                content += "\n"

        output_file.write_text(content, encoding="utf-8")
        print(f"  ✓ Routed {len(decisions)} items to active: {output_file}")

    def _route_to_future_plan(self, decisions: List[ImplementationDecision]):
        """Append to FUTURE_PLAN.md"""
        future_plan_path = self._get_sot_file_path("FUTURE_PLAN.md")

        if not future_plan_path.exists():
            content = "# Future Plan\n\n"
        else:
            content = future_plan_path.read_text(encoding="utf-8")
            content += (
                f"\n\n## Research-Driven Features (Added {datetime.now().strftime('%Y-%m-%d')})\n\n"
            )

        for decision in decisions:
            content += f"\n### {decision.gap.title}\n\n"
            content += f"**Priority**: {decision.gap.priority.value} | "
            content += f"**Effort**: {decision.gap.effort.value} | "
            content += f"**ROI**: {decision.roi_score:.2f}\n\n"
            content += f"{decision.gap.description}\n\n"
            content += f"**Rationale**: {decision.rationale}\n\n"

        future_plan_path.write_text(content, encoding="utf-8")
        print(f"  ✓ Routed {len(decisions)} items to FUTURE_PLAN.md")

    def _route_to_review(self, decisions: List[ImplementationDecision]):
        """Route to review/deferred directory"""
        review_dir = self._get_research_dir() / "reviewed" / "deferred"
        review_dir.mkdir(parents=True, exist_ok=True)

        output_file = review_dir / f"for_review_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"

        content = "# Items for Review\n\n"
        content += f"**Generated**: {datetime.now().isoformat()}\n\n"

        for decision in decisions:
            content += f"\n## {decision.gap.title}\n\n"
            content += f"{decision.gap.description}\n\n"
            content += f"**Why deferred**: {decision.rationale}\n\n"

        output_file.write_text(content, encoding="utf-8")
        print(f"  ✓ Routed {len(decisions)} items to review: {output_file}")

    def _route_to_rejected(self, decisions: List[ImplementationDecision]):
        """Route to review/rejected directory"""
        reject_dir = self._get_research_dir() / "reviewed" / "rejected"
        reject_dir.mkdir(parents=True, exist_ok=True)

        output_file = reject_dir / f"rejected_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"

        content = "# Rejected Items\n\n"
        content += f"**Generated**: {datetime.now().isoformat()}\n\n"

        for decision in decisions:
            content += f"\n## {decision.gap.title}\n\n"
            content += f"{decision.gap.description}\n\n"
            content += f"**Why rejected**: {decision.rationale}\n\n"

        output_file.write_text(content, encoding="utf-8")
        print(f"  ✓ Routed {len(decisions)} items to rejected: {output_file}")

    def _get_sot_file_path(self, filename: str) -> Path:
        """Get path to SOT file"""
        if self.project_id == "autopack":
            return Path("docs") / filename
        else:
            return Path(".autonomous_runs") / self.project_id / "docs" / filename

    def _get_research_dir(self) -> Path:
        """Get research directory"""
        if self.project_id == "autopack":
            return Path("archive") / "research"
        else:
            return Path(".autonomous_runs") / self.project_id / "archive" / "research"


if __name__ == "__main__":
    import sys
    from scripts.research.context_assembler import ContextAssembler
    from scripts.research.research_analyzer import ResearchAnalyzer

    project_id = sys.argv[1] if len(sys.argv) > 1 else "file-organizer-app-v1"

    # Assemble context
    print("Assembling context...")
    assembler = ContextAssembler(project_id)
    context = assembler.assemble()

    # Analyze research
    print("\nAnalyzing research...")
    analyzer = ResearchAnalyzer(project_id)
    analysis = analyzer.analyze(context)

    # Make decisions
    print("\nMaking decisions...")
    engine = DecisionEngine(project_id)
    report = engine.decide(analysis.gaps, context)

    # Route decisions
    print("\nRouting decisions...")
    router = DecisionRouter(project_id)
    router.route(report)

    # Save decision report
    output_path = Path(f".autonomous_runs/{project_id}/decision_report.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    output_data = {
        "project_id": report.project_id,
        "decided_at": report.decided_at.isoformat(),
        "decisions": [
            {
                "decision_id": d.decision_id,
                "gap_title": d.gap.title,
                "gap_type": d.gap.gap_type.value,
                "decision": d.decision.value,
                "rationale": d.rationale,
                "strategic_alignment": d.strategic_alignment,
                "user_impact": d.user_impact,
                "competitive_impact": d.competitive_impact,
                "estimated_value": d.estimated_value,
                "estimated_effort": d.estimated_effort,
                "roi_score": d.roi_score,
            }
            for d in report.decisions
        ],
    }

    output_path.write_text(json.dumps(output_data, indent=2), encoding="utf-8")
    print(f"\n✓ Decision report saved to {output_path}")
