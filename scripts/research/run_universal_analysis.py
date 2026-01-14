"""
Universal Research Analysis Pipeline

Orchestrates the complete research analysis workflow for any project.

Workflow:
1. Context Assembly: Build comprehensive project context (SOT + research)
2. Research Analysis: Find gaps between current state and research
3. Decision Making: Make strategic implementation decisions
4. Decision Routing: Route decisions to appropriate locations

Usage:
    python scripts/research/run_universal_analysis.py [project_id]

Examples:
    python scripts/research/run_universal_analysis.py file-organizer-app-v1
    python scripts/research/run_universal_analysis.py autopack
"""

import sys
import json
import os
from pathlib import Path
from datetime import datetime
import argparse

from scripts.research.context_assembler import ContextAssembler
from scripts.research.research_analyzer import ResearchAnalyzer
from scripts.research.decision_engine import DecisionEngine, DecisionRouter


class UniversalResearchAnalysisPipeline:
    """
    Universal research analysis pipeline that works for any project.

    This pipeline:
    - Works for ANY project (Autopack, file-organizer, or future projects)
    - Supports both initial planning AND ongoing improvement
    - Has comprehensive context (current state, vision, market, domain, constraints)
    - Makes strategic decisions with full context awareness
    """

    def __init__(self, project_id: str):
        self.project_id = project_id
        self.start_time = datetime.now()

    def run(self) -> dict:
        """Run the complete universal analysis pipeline"""
        print(f"\n{'=' * 70}")
        print("UNIVERSAL RESEARCH ANALYSIS PIPELINE")
        print(f"{'=' * 70}")
        print(f"Project: {self.project_id}")
        print(f"Started: {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'=' * 70}\n")

        results = {
            "project_id": self.project_id,
            "started_at": self.start_time.isoformat(),
            "phases": {},
        }

        # Phase 1: Context Assembly
        print(f"\n{'#' * 70}")
        print("PHASE 1: CONTEXT ASSEMBLY")
        print(f"{'#' * 70}\n")
        print("Building comprehensive project context from:")
        print("  • SOT files (BUILD_HISTORY, ARCHITECTURE_DECISIONS, DEBUG_LOG, etc.)")
        print("  • Research files (product vision, market research, domain requirements)")
        print("  • Database (PostgreSQL + Qdrant semantic search)\n")

        try:
            assembler = ContextAssembler(self.project_id)
            context = assembler.assemble()
            results["phases"]["context_assembly"] = {
                "status": "success",
                "features": len(context.implemented_features),
                "constraints": len(context.architecture_constraints),
                "issues": len(context.known_issues),
                "vision": bool(context.vision_statement),
            }

            # Save context
            self._save_context(context)
            print("\n✓ Phase 1 complete: Context assembled")

        except Exception as e:
            print(f"\n✗ Phase 1 failed: {e}")
            results["phases"]["context_assembly"] = {"status": "failed", "error": str(e)}
            return results

        # Phase 2: Research Analysis
        print(f"\n{'#' * 70}")
        print("PHASE 2: RESEARCH ANALYSIS")
        print(f"{'#' * 70}\n")
        print("Analyzing research to find gaps:")
        print("  • Feature gaps (market/user research vs implemented)")
        print("  • Compliance gaps (regulatory requirements vs current)")
        print("  • Competitive gaps (competitors vs our features)")
        print("  • Vision alignment gaps (vision vs current state)\n")

        try:
            analyzer = ResearchAnalyzer(self.project_id)
            analysis = analyzer.analyze(context)
            results["phases"]["research_analysis"] = {
                "status": "success",
                "total_gaps": len(analysis.gaps),
                "critical_gaps": len(analysis.get_critical_gaps()),
                "strategic_insights": len(analysis.strategic_insights),
            }

            # Save analysis
            self._save_analysis(analysis)
            print(f"\n✓ Phase 2 complete: {len(analysis.gaps)} gaps identified")

        except Exception as e:
            print(f"\n✗ Phase 2 failed: {e}")
            results["phases"]["research_analysis"] = {"status": "failed", "error": str(e)}
            return results

        # Phase 3: Decision Making
        print(f"\n{'#' * 70}")
        print("PHASE 3: DECISION MAKING")
        print(f"{'#' * 70}\n")
        print("Making strategic implementation decisions:")
        print("  • IMPLEMENT_NOW: Add to active development")
        print("  • IMPLEMENT_LATER: Add to FUTURE_PLAN")
        print("  • REVIEW: Needs more research/discussion")
        print("  • REJECT: Not aligned with vision/constraints\n")
        print("Considering:")
        print("  • Strategic alignment with vision")
        print("  • User impact")
        print("  • Competitive necessity")
        print("  • Dependencies and blockers")
        print("  • Resource fit (budget, timeline, team)")
        print("  • Opportunity cost\n")

        try:
            engine = DecisionEngine(self.project_id)
            report = engine.decide(analysis.gaps, context)
            results["phases"]["decision_making"] = {
                "status": "success",
                "total_decisions": len(report.decisions),
                "implement_now": len(report.get_implement_now()),
                "implement_later": len(report.get_implement_later()),
                "review": (
                    len(report.get_by_decision_type(report.decisions[0].decision.__class__.REVIEW))
                    if report.decisions
                    else 0
                ),
                "reject": (
                    len(report.get_by_decision_type(report.decisions[0].decision.__class__.REJECT))
                    if report.decisions
                    else 0
                ),
            }

            # Save decisions
            self._save_decisions(report)
            print(f"\n✓ Phase 3 complete: {len(report.decisions)} decisions made")

        except Exception as e:
            print(f"\n✗ Phase 3 failed: {e}")
            results["phases"]["decision_making"] = {"status": "failed", "error": str(e)}
            return results

        # Phase 4: Decision Routing
        print(f"\n{'#' * 70}")
        print("PHASE 4: DECISION ROUTING")
        print(f"{'#' * 70}\n")
        print("Routing decisions to appropriate locations:")
        print("  • IMPLEMENT_NOW → archive/research/active/")
        print("  • IMPLEMENT_LATER → docs/FUTURE_PLAN.md")
        print("  • REVIEW → archive/research/reviewed/deferred/")
        print("  • REJECT → archive/research/reviewed/rejected/\n")

        try:
            router = DecisionRouter(self.project_id)
            routing_summary = router.route(report)
            results["phases"]["decision_routing"] = {"status": "success", **routing_summary}

            print("\n✓ Phase 4 complete: Decisions routed")

        except Exception as e:
            print(f"\n✗ Phase 4 failed: {e}")
            results["phases"]["decision_routing"] = {"status": "failed", "error": str(e)}
            return results

        # Final summary
        end_time = datetime.now()
        duration = (end_time - self.start_time).total_seconds()
        results["completed_at"] = end_time.isoformat()
        results["duration_seconds"] = duration

        self._print_final_summary(results, analysis, report)

        # Save pipeline results
        self._save_results(results)

        return results

    def _save_context(self, context):
        """Save context to JSON"""
        output_dir = Path(f".autonomous_runs/{self.project_id}")
        output_dir.mkdir(parents=True, exist_ok=True)
        output_file = output_dir / "context.json"
        output_file.write_text(json.dumps(context.to_dict(), indent=2), encoding="utf-8")
        print(f"  → Context saved: {output_file}")

    def _save_analysis(self, analysis):
        """Save analysis to JSON"""
        output_dir = Path(f".autonomous_runs/{self.project_id}")
        output_dir.mkdir(parents=True, exist_ok=True)
        output_file = output_dir / "opportunity_analysis.json"

        data = {
            "project_id": analysis.project_id,
            "analyzed_at": analysis.analyzed_at.isoformat(),
            "gaps": [
                {
                    "gap_id": g.gap_id,
                    "gap_type": g.gap_type.value,
                    "title": g.title,
                    "description": g.description,
                    "current_state": g.current_state,
                    "desired_state": g.desired_state,
                    "priority": g.priority.value,
                    "effort": g.effort.value,
                    "source_research": g.source_research,
                }
                for g in analysis.gaps
            ],
            "strategic_insights": analysis.strategic_insights,
        }

        output_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
        print(f"  → Analysis saved: {output_file}")

    def _save_decisions(self, report):
        """Save decisions to JSON"""
        output_dir = Path(f".autonomous_runs/{self.project_id}")
        output_dir.mkdir(parents=True, exist_ok=True)
        output_file = output_dir / "decision_report.json"

        data = {
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

        output_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
        print(f"  → Decisions saved: {output_file}")

    def _save_results(self, results):
        """Save pipeline results"""
        output_dir = Path(f".autonomous_runs/{self.project_id}")
        output_dir.mkdir(parents=True, exist_ok=True)
        output_file = (
            output_dir / f"pipeline_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        )
        output_file.write_text(json.dumps(results, indent=2), encoding="utf-8")
        print(f"\n  → Pipeline results saved: {output_file}")

    def _print_final_summary(self, results, analysis, report):
        """Print final summary"""
        print(f"\n{'=' * 70}")
        print("PIPELINE COMPLETE")
        print(f"{'=' * 70}\n")

        print(f"Duration: {results['duration_seconds']:.1f} seconds\n")

        print("Context Assembly:")
        ctx = results["phases"]["context_assembly"]
        print(f"  • Implemented features: {ctx.get('features', 0)}")
        print(f"  • Architecture constraints: {ctx.get('constraints', 0)}")
        print(f"  • Known issues: {ctx.get('issues', 0)}")
        print(f"  • Vision defined: {'Yes' if ctx.get('vision') else 'No'}\n")

        print("Research Analysis:")
        ra = results["phases"]["research_analysis"]
        print(f"  • Total gaps: {ra.get('total_gaps', 0)}")
        print(f"  • Critical gaps: {ra.get('critical_gaps', 0)}")
        print(f"  • Strategic insights: {ra.get('strategic_insights', 0)}\n")

        print("Decisions:")
        dm = results["phases"]["decision_making"]
        print(f"  • Implement now: {dm.get('implement_now', 0)}")
        print(f"  • Implement later: {dm.get('implement_later', 0)}")
        print(f"  • Review: {dm.get('review', 0)}")
        print(f"  • Reject: {dm.get('reject', 0)}\n")

        if analysis.strategic_insights:
            print("Key Strategic Insights:")
            for i, insight in enumerate(analysis.strategic_insights[:3], 1):
                print(f"  {i}. {insight}\n")

        high_roi = report.get_high_roi(threshold=1.5)
        if high_roi:
            print(f"High ROI Opportunities ({len(high_roi)}):")
            for decision in high_roi[:5]:
                print(f"  • {decision.gap.title} (ROI: {decision.roi_score:.1f})")
            print()

        print(f"{'=' * 70}\n")


def main():
    parser = argparse.ArgumentParser(
        description="Universal Research Analysis Pipeline - Works for any project"
    )
    parser.add_argument(
        "project_id",
        nargs="?",
        default="file-organizer-app-v1",
        help="Project ID (e.g., file-organizer-app-v1, autopack)",
    )

    args = parser.parse_args()

    # Verify environment
    if not os.getenv("ANTHROPIC_API_KEY"):
        print("ERROR: ANTHROPIC_API_KEY not set")
        sys.exit(1)

    # Run pipeline
    pipeline = UniversalResearchAnalysisPipeline(args.project_id)
    results = pipeline.run()

    # Exit code based on success
    all_success = all(phase.get("status") == "success" for phase in results["phases"].values())
    sys.exit(0 if all_success else 1)


if __name__ == "__main__":
    main()
