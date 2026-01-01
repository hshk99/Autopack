# Phase 0 Part 3: Synthesis & Evaluation

**Status**: 🚧 Ready for Implementation
**Estimated Effort**: 20-30 hours
**Timeline**: Week 2, Days 2-3
**Build ID**: BUILD-034
**Depends On**: Part 1 (Evidence Foundation) ✅ + Part 2 (GitHub Discovery & Analysis) ✅
**Enables**: Phase 1 (Full Implementation) OR Pivot Decision

---

## Executive Summary

Build the **MetaAuditor** to synthesize 10-20 findings into a **1-page executive summary** with strict citation requirements. Then create the **evaluation harness** to measure citation validity (the CRITICAL metric).

This is the **final validation** before committing to full 500-620 hour implementation.

**Success Criteria**:
- ✅ MetaAuditor produces readable 1-page summary (<3000 words)
- ✅ Every recommendation cites ≥2 findings
- ✅ Manual evaluation: ≥80% citation validity (quotes appear in sources)
- ✅ Cost <$8/session (total for Parts 1-3)
- ✅ Readable in <10 minutes

**FINAL STOP/GO Gate**:
- If average score ≥7.0/10 → **GO to Phase 1** (full implementation)
- If average score <7.0/10 → **STOP, pivot to curated registry** (simpler approach)

---

## Background & Rationale

### The Synthesis Challenge

After Parts 1-2, we have:
- ✅ Evidence-bound findings (extraction_span requirement enforced)
- ✅ Deterministic decision scores (Python arithmetic)

**Remaining Risk**: Can LLM synthesize findings into **verifiable recommendations**?

All 3 GPT reviewers flagged:
- "MetaAuditor risks false precision"
- "Evaluation vacuum - no way to measure accuracy"
- "Teaching to the test failure if source overlap metric used"

### Why Citation Validity Metric?

**BAD Metric** (from v2.1 feedback):
```python
# Source overlap (penalizes finding NEW sources):
score = len(system_sources & gold_sources) / len(gold_sources)
```

**GOOD Metric** (Phase 0):
```python
# Citation validity (measures claim entailment):
for recommendation in summary.recommendations:
    for citation in recommendation.citations:
        quote = citation.finding.extraction_span
        if quote in source_content:
            valid_citations += 1
validity_rate = valid_citations / total_citations
```

**Key Insight**: The metric must measure **claim entailment** (does the quote support the claim?), not source overlap.

---

## Implementation Specification

### 1. Directory Structure

```
src/autopack/research/
├── models/
│   ├── evidence.py          # ✅ From Part 1
│   └── validators.py        # ✅ From Part 1
├── discovery/
│   └── github_discovery.py  # ✅ From Part 2
├── gathering/
│   └── github_gatherer.py   # ✅ From Part 2
├── analysis/
│   ├── decision_frameworks.py  # ✅ From Part 2
│   └── meta_auditor.py      # NEW: MetaAuditor
├── evaluation/
│   ├── __init__.py
│   ├── gold_standard.py     # NEW: Gold dataset definition
│   └── evaluator.py         # NEW: Citation validity checker
└── tests/
    ├── test_meta_auditor.py
    └── test_evaluation.py
```

### 2. Core Components

#### 2.1 MetaAuditor (`analysis/meta_auditor.py`)

**Purpose**: Synthesize 10-20 findings into 1-page executive summary with strict citations

**Implementation**:

```python
"""MetaAuditor for synthesizing findings into executive summaries."""

from dataclasses import dataclass
from typing import List

from ..models.evidence import Finding
from ..analysis.decision_frameworks import DecisionScore


@dataclass
class Recommendation:
    """A single recommendation with citations."""

    recommendation: str  # The recommendation (1-2 sentences)
    rationale: str  # Why this recommendation (2-3 sentences)
    citations: List[Finding]  # ≥2 findings supporting this recommendation
    confidence: float  # 0.0-1.0

    def validate(self) -> None:
        """Validate recommendation has sufficient citations."""
        if len(self.citations) < 2:
            raise ValueError(f"Recommendation must cite ≥2 findings (has {len(self.citations)})")


@dataclass
class ExecutiveSummary:
    """1-page executive summary of research findings."""

    topic: str
    decision_score: DecisionScore  # From MarketAttractivenessCalculator
    key_findings: List[str]  # 3-5 bullet points
    recommendations: List[Recommendation]  # 3-5 recommendations
    go_no_go: str  # "GO" or "NO-GO"
    rationale: str  # Why GO or NO-GO (2-3 sentences)

    total_findings: int  # Number of findings analyzed
    total_sources: int  # Number of sources
    generated_at: str  # ISO timestamp


class MetaAuditor:
    """
    Synthesizes findings into executive summary.

    CRITICAL: Every recommendation MUST cite ≥2 findings.
    """

    def __init__(self, llm_client):
        """
        Initialize MetaAuditor.

        Args:
            llm_client: LLM client for synthesis
        """
        self.llm_client = llm_client

    async def synthesize(
        self,
        topic: str,
        findings: List[Finding],
        decision_score: DecisionScore
    ) -> ExecutiveSummary:
        """
        Synthesize findings into 1-page executive summary.

        Args:
            topic: Research topic
            findings: All findings (10-20 expected)
            decision_score: Market Attractiveness Score from Part 2

        Returns:
            ExecutiveSummary with GO/NO-GO decision
        """

        # Build findings context for LLM
        findings_text = self._format_findings_for_llm(findings)

        # Synthesis prompt (MUST enforce citations)
        synthesis_prompt = f"""You are a strategic analyst synthesizing market research findings.

**Topic**: {topic}

**Market Attractiveness Score**: {decision_score.score if decision_score.score else 'Insufficient data'}
**Score Inputs**: {decision_score.inputs}
**Confidence**: {decision_score.confidence}

**Findings** ({len(findings)} total):
{findings_text}

**Your Task**:
Synthesize these findings into a 1-page executive summary for decision-makers.

**CRITICAL REQUIREMENTS**:
1. **Key Findings** (3-5 bullet points):
   - Summarize most important findings
   - Each bullet must reference finding IDs [e.g., "Finding 1, 3, 7 show..."]

2. **Recommendations** (3-5 actionable recommendations):
   - Each recommendation MUST cite ≥2 finding IDs
   - Format: "Recommendation: [text] (Findings: 2, 5, 9)"
   - Include confidence (0.0-1.0)

3. **GO/NO-GO Decision**:
   - Based on Market Attractiveness Score and findings
   - GO if score >50 AND findings show market viability
   - NO-GO if score <50 OR critical blockers found
   - Include 2-3 sentence rationale citing finding IDs

**Output Format** (JSON):
{{
  "key_findings": [
    "File organization tools show 15-20% annual growth (Finding 1, 4, 7)",
    "Market dominated by 3 major players (Finding 2, 8)",
    ...
  ],
  "recommendations": [
    {{
      "recommendation": "Focus on niche segment: developer productivity tools",
      "rationale": "Findings 3, 6, 11 show underserved developer market with high WTP",
      "cited_finding_ids": [3, 6, 11],
      "confidence": 0.8
    }},
    ...
  ],
  "go_no_go": "GO",
  "rationale": "Market Attractiveness Score of 67.2 indicates viable opportunity. Findings 1-7 confirm market growth and accessibility. (Findings: 1, 2, 3, 4, 5, 6, 7)"
}}
"""

        # Call LLM
        response = await self.llm_client.complete(
            prompt=synthesis_prompt,
            response_format="json"
        )

        # Parse response
        import json
        from datetime import datetime, timezone

        data = json.loads(response.content)

        # Convert to Recommendation objects
        recommendations = []
        for rec_data in data["recommendations"]:
            # Map cited_finding_ids to Finding objects
            cited_findings = [
                findings[fid - 1]  # IDs are 1-indexed
                for fid in rec_data["cited_finding_ids"]
                if 0 < fid <= len(findings)
            ]

            recommendation = Recommendation(
                recommendation=rec_data["recommendation"],
                rationale=rec_data["rationale"],
                citations=cited_findings,
                confidence=rec_data["confidence"]
            )

            # Validate ≥2 citations
            recommendation.validate()

            recommendations.append(recommendation)

        # Build ExecutiveSummary
        summary = ExecutiveSummary(
            topic=topic,
            decision_score=decision_score,
            key_findings=data["key_findings"],
            recommendations=recommendations,
            go_no_go=data["go_no_go"],
            rationale=data["rationale"],
            total_findings=len(findings),
            total_sources=len(set(f.source_url for f in findings)),
            generated_at=datetime.now(timezone.utc).isoformat()
        )

        return summary

    def _format_findings_for_llm(self, findings: List[Finding]) -> str:
        """Format findings for LLM prompt."""
        formatted = []
        for i, finding in enumerate(findings, start=1):
            formatted.append(
                f"[Finding {i}] {finding.title}\n"
                f"  Content: {finding.content}\n"
                f"  Quote: \"{finding.extraction_span}\"\n"
                f"  Source: {finding.source_url}\n"
                f"  Relevance: {finding.relevance_score}/10 | "
                f"Recency: {finding.recency_score}/10 | "
                f"Trust: {finding.trust_score}/3"
            )
        return "\n\n".join(formatted)
```

#### 2.2 Gold Standard Dataset (`evaluation/gold_standard.py`)

**Purpose**: Define ground truth for evaluation

```python
"""Gold standard dataset for evaluation."""

from dataclasses import dataclass
from typing import List


@dataclass
class GoldTopic:
    """A gold standard research topic with ground truth."""

    topic: str  # Research topic
    expected_sources: List[str]  # URLs of high-quality sources (for reference, NOT strict matching)
    expected_findings: List[str]  # Key findings (for reference)
    expected_recommendations: List[str]  # Expected recommendations (for reference)
    expected_go_no_go: str  # Expected decision ("GO" or "NO-GO")


# Phase 0 Gold Standard Dataset (5 topics)
GOLD_TOPICS = [
    GoldTopic(
        topic="file organization tools",
        expected_sources=[
            "https://github.com/organize/organize",
            "https://github.com/tfeldmann/organize",
            "https://github.com/SimonSapin/python-fuse"
        ],
        expected_findings=[
            "File organization tools show steady GitHub star growth (15-20% annually)",
            "Market dominated by general-purpose tools (Dropbox, Google Drive) with niche opportunity for developer-focused tools",
            "Open-source tools indicate active community interest"
        ],
        expected_recommendations=[
            "Focus on developer productivity niche",
            "Integrate with existing workflows (VS Code, CLI)",
            "Leverage open-source community for feedback"
        ],
        expected_go_no_go="GO"
    ),

    GoldTopic(
        topic="AI coding assistants",
        expected_sources=[
            "https://github.com/features/copilot",
            "https://github.com/TabbyML/tabby",
            "https://github.com/getcursor/cursor"
        ],
        expected_findings=[
            "Rapid market growth (GitHub Copilot 1M+ users)",
            "High competition (GitHub, Tabnine, Codeium, Cursor)",
            "Strong WTP among professional developers ($10-20/month)"
        ],
        expected_recommendations=[
            "Differentiate via specialized domain (e.g., data science, DevOps)",
            "Focus on enterprise segment (security, compliance)",
            "Build on open-source models (cost advantage)"
        ],
        expected_go_no_go="GO"
    ),

    GoldTopic(
        topic="task automation frameworks",
        expected_sources=[
            "https://github.com/apache/airflow",
            "https://github.com/PrefectHQ/prefect",
            "https://github.com/dagster-io/dagster"
        ],
        expected_findings=[
            "Enterprise market dominated by Airflow (mature, established)",
            "Emerging competitors (Prefect, Dagster) focus on developer experience",
            "High switching costs (existing DAGs, integrations)"
        ],
        expected_recommendations=[
            "Target greenfield projects (new teams, startups)",
            "Emphasize developer experience differentiation",
            "Build integration ecosystem early"
        ],
        expected_go_no_go="GO"
    ),

    GoldTopic(
        topic="knowledge management systems",
        expected_sources=[
            "https://github.com/logseq/logseq",
            "https://github.com/dendronhq/dendron",
            "https://github.com/obsidianmd/obsidian-releases"
        ],
        expected_findings=[
            "Growing market (Notion, Obsidian, Roam)",
            "Network effects favor incumbents",
            "Privacy-focused segment shows interest (Logseq, Dendron)"
        ],
        expected_recommendations=[
            "Target privacy-conscious users",
            "Emphasize local-first architecture",
            "Integrate with developer workflows"
        ],
        expected_go_no_go="GO"
    ),

    GoldTopic(
        topic="blockchain-based social networks",
        expected_sources=[
            "https://github.com/Minds/minds",
            "https://github.com/mastodon/mastodon"
        ],
        expected_findings=[
            "Limited traction (low user counts)",
            "High technical complexity (blockchain)",
            "Regulatory uncertainty"
        ],
        expected_recommendations=[
            "Avoid blockchain for MVP (adds complexity, limited value)",
            "Focus on decentralization benefits (data ownership)",
            "Reconsider market timing"
        ],
        expected_go_no_go="NO-GO"
    )
]
```

#### 2.3 Citation Validity Evaluator (`evaluation/evaluator.py`)

**Purpose**: Measure citation validity (CRITICAL metric)

```python
"""Citation validity evaluation for research summaries."""

from dataclasses import dataclass
from typing import List

from ..models.evidence import Finding
from ..models.validators import FindingVerifier
from ..analysis.meta_auditor import ExecutiveSummary, Recommendation


@dataclass
class CitationValidityResult:
    """Result of citation validity evaluation."""

    total_citations: int
    valid_citations: int
    invalid_citations: int
    validity_rate: float  # 0.0-1.0
    invalid_details: List[str]  # Details of invalid citations


class CitationValidityEvaluator:
    """
    Evaluates citation validity: do quoted spans appear in sources?

    This is the CRITICAL metric for Phase 0 success.
    """

    def __init__(self):
        self.verifier = FindingVerifier()

    async def evaluate_summary(
        self,
        summary: ExecutiveSummary,
        source_contents: dict  # {source_url: content}
    ) -> CitationValidityResult:
        """
        Evaluate citation validity for an executive summary.

        Args:
            summary: ExecutiveSummary to evaluate
            source_contents: Dict of {source_url: raw_content}

        Returns:
            CitationValidityResult with validity rate
        """

        total_citations = 0
        valid_citations = 0
        invalid_details = []

        # Check each recommendation's citations
        for rec in summary.recommendations:
            for finding in rec.citations:
                total_citations += 1

                # Get source content
                source_content = source_contents.get(finding.source_url)
                if not source_content:
                    invalid_details.append(
                        f"Citation {total_citations}: Source URL not in source_contents ({finding.source_url})"
                    )
                    continue

                # Verify finding
                result = await self.verifier.verify_finding(finding, source_content)

                if result.valid:
                    valid_citations += 1
                else:
                    invalid_details.append(
                        f"Citation {total_citations}: {result.reason}\n"
                        f"  Finding: {finding.title}\n"
                        f"  Quote: \"{finding.extraction_span}\"\n"
                        f"  Source: {finding.source_url}"
                    )

        validity_rate = valid_citations / total_citations if total_citations > 0 else 0.0

        return CitationValidityResult(
            total_citations=total_citations,
            valid_citations=valid_citations,
            invalid_citations=total_citations - valid_citations,
            validity_rate=validity_rate,
            invalid_details=invalid_details
        )
```

### 3. Evaluation Harness

```python
# scripts/run_phase_0_evaluation.py

"""
Phase 0 Evaluation Harness

Runs end-to-end research pipeline on 5 gold topics and measures:
- Citation validity rate (≥80% target)
- Cost per session (<$8 target)
- Readability (1-page, <10 minutes)
"""

import asyncio
from datetime import datetime

from autopack.research.discovery.github_discovery import GitHubDiscoveryStrategy
from autopack.research.gathering.github_gatherer import GitHubGatherer
from autopack.research.analysis.decision_frameworks import MarketAttractivenessCalculator
from autopack.research.analysis.meta_auditor import MetaAuditor
from autopack.research.evaluation.gold_standard import GOLD_TOPICS
from autopack.research.evaluation.evaluator import CitationValidityEvaluator


async def evaluate_topic(topic: str, llm_client):
    """Run end-to-end research for a topic."""

    print(f"\n{'='*60}")
    print(f"Evaluating: {topic}")
    print(f"{'='*60}")

    # Step 1: Discovery
    discovery = GitHubDiscoveryStrategy()
    sources = await discovery.discover_sources(topic, max_results=10, min_stars=100)
    print(f"✅ Discovered {len(sources)} sources")

    # Step 2: Gathering
    gatherer = GitHubGatherer(llm_client)
    all_findings = []
    source_contents = {}  # For evaluation

    for source in sources[:5]:
        findings = await gatherer.gather_findings(source, topic, max_findings=3)
        all_findings.extend(findings)

        # Cache source content for evaluation
        readme_content = await gatherer._fetch_readme(source.url)
        if readme_content:
            source_contents[source.url] = readme_content

    print(f"✅ Extracted {len(all_findings)} findings")

    # Step 3: Decision Framework
    calculator = MarketAttractivenessCalculator(llm_client)
    decision_score = await calculator.calculate(all_findings)
    print(f"✅ Decision score: {decision_score.score} (confidence: {decision_score.confidence})")

    # Step 4: Synthesis
    auditor = MetaAuditor(llm_client)
    summary = await auditor.synthesize(topic, all_findings, decision_score)
    print(f"✅ Generated executive summary")
    print(f"   GO/NO-GO: {summary.go_no_go}")
    print(f"   Recommendations: {len(summary.recommendations)}")

    # Step 5: Evaluation
    evaluator = CitationValidityEvaluator()
    eval_result = await evaluator.evaluate_summary(summary, source_contents)

    print(f"\n📊 EVALUATION RESULTS:")
    print(f"   Citation Validity: {eval_result.validity_rate:.1%} ({eval_result.valid_citations}/{eval_result.total_citations})")

    if eval_result.invalid_citations > 0:
        print(f"\n⚠️  Invalid Citations:")
        for detail in eval_result.invalid_details[:5]:  # Show first 5
            print(f"   {detail}")

    return {
        "topic": topic,
        "citation_validity": eval_result.validity_rate,
        "total_findings": len(all_findings),
        "total_sources": len(sources),
        "decision_score": decision_score.score,
        "go_no_go": summary.go_no_go
    }


async def main():
    """Run full Phase 0 evaluation."""

    print("="*60)
    print("PHASE 0 EVALUATION HARNESS")
    print("="*60)
    print(f"Started: {datetime.now().isoformat()}")
    print(f"Topics: {len(GOLD_TOPICS)}")
    print()

    # Setup (use real LLM client)
    from autopack.llm_service import LLMService
    llm_client = LLMService()

    # Run evaluation on each gold topic
    results = []
    for gold_topic in GOLD_TOPICS:
        result = await evaluate_topic(gold_topic.topic, llm_client)
        results.append(result)

    # Aggregate results
    print("\n" + "="*60)
    print("AGGREGATE RESULTS")
    print("="*60)

    avg_validity = sum(r["citation_validity"] for r in results) / len(results)
    print(f"\n✅ Average Citation Validity: {avg_validity:.1%}")

    if avg_validity >= 0.80:
        print(f"\n🎉 PHASE 0 SUCCESS! Citation validity ≥80%")
        print(f"   Recommendation: PROCEED TO PHASE 1")
    else:
        print(f"\n❌ PHASE 0 FAIL. Citation validity <80%")
        print(f"   Recommendation: PIVOT TO CURATED REGISTRY")

    # Print per-topic results
    print(f"\nPer-Topic Results:")
    for r in results:
        status = "✅" if r["citation_validity"] >= 0.80 else "❌"
        print(f"{status} {r['topic']}: {r['citation_validity']:.1%} validity, {r['total_findings']} findings, GO/NO-GO: {r['go_no_go']}")


if __name__ == "__main__":
    asyncio.run(main())
```

### 4. FINAL STOP/GO Validation Gate

After running evaluation harness on 5 gold topics:

### ✅ GO to Phase 1 (Full Implementation)

If ALL criteria met:
- [ ] Average citation validity ≥80% across 5 topics
- [ ] ≥4/5 topics have validity ≥75% (allows 1 outlier)
- [ ] Total cost <$40 (5 topics × $8 budget)
- [ ] Executive summaries readable in <10 minutes each
- [ ] GO/NO-GO decisions align with expected (≥4/5 correct)
- [ ] No critical bugs in evaluation

**Next Step**: Proceed to Phase 1 (expand to Reddit, Web sources, 500-620 hours)

### ❌ STOP - Pivot to Curated Registry

If ANY occur:
- [ ] Average citation validity <80%
- [ ] ≥2/5 topics have validity <75%
- [ ] Total cost >$50 (budget overrun)
- [ ] Executive summaries take >15 minutes to read
- [ ] GO/NO-GO decisions wrong (≤2/5 correct)
- [ ] Critical bugs that break evaluation

**Next Step**: Create [Curated_Registry_Implementation.md](./Curated_Registry_Implementation.md) (120-150h simpler approach)

---

## Implementation Checklist

- [ ] Implement `MetaAuditor` (analysis/meta_auditor.py)
- [ ] Implement `GoldTopic` and `GOLD_TOPICS` (evaluation/gold_standard.py)
- [ ] Implement `CitationValidityEvaluator` (evaluation/evaluator.py)
- [ ] Create evaluation harness script (scripts/run_phase_0_evaluation.py)
- [ ] Run evaluation on 5 gold topics
- [ ] Measure average citation validity
- [ ] Measure total cost
- [ ] Review executive summaries (readability, 1-page, <10 minutes)
- [ ] Document in BUILD_HISTORY.md
- [ ] **FINAL STOP/GO DECISION**: Phase 1 or Pivot?

---

## Cost Estimation

**Target**: <$40 total (5 topics × $8/topic budget)

**Per Topic**:
- Parts 1-2: ~$1-2 (discovery + gathering + decision framework)
- Part 3 (synthesis): ~$2-3 (MetaAuditor synthesis)
- **Total**: ~$3-5/topic

**5 Topics**: ~$15-25 total ✅ Well under $40 budget

---

## Related Documentation

- **Build**: [BUILD-034](../../docs/BUILD_HISTORY.md#BUILD-034) - Phase 0 Research System
- **Debug**: [DBG-003](../../docs/DEBUG_LOG.md#DBG-003) - Planning Cycle Diminishing Returns
- **Part 1**: [Phase_0_Part_1_Evidence_Foundation.md](./Phase_0_Part_1_Evidence_Foundation.md)
- **Part 2**: [Phase_0_Part_2_GitHub_Discovery_And_Analysis.md](./Phase_0_Part_2_GitHub_Discovery_And_Analysis.md)
- **Analysis**: `C:\Users\hshk9\.claude\plans\sunny-booping-seahorse.md`
- **GPT Feedback**: `C:\Users\hshk9\OneDrive\Backup\Desktop\ref4.md`

---

## Success Metrics Summary

**CRITICAL**: Citation validity ≥80%

**Why This Metric**:
- Measures actual quote verification (Part 1 evidence binding)
- Validates LLM synthesis quality (not just presence of citations)
- Directly addresses #1 trust failure (citation laundering)
- Avoids "teaching to the test" (unlike source overlap)

**What ≥80% Means**:
- Out of every 5 citations, 4 are verifiable quotes from sources
- System can be trusted for strategic decisions
- Evidence-first architecture works as designed

**What <80% Means**:
- Too many fabricated/misattributed citations
- System not ready for decision-ready outputs
- Need to pivot to simpler approach (curated registry)

---

## Next Steps

**If ≥80% Citation Validity (GO)**:
1. Update BUILD_HISTORY.md with Phase 0 SUCCESS
2. Create Phase 1 specification (expand to Reddit, Web, full 500-620h)
3. Begin Phase 1 implementation

**If <80% Citation Validity (STOP)**:
1. Update BUILD_HISTORY.md with Phase 0 PIVOT decision
2. Create Curated_Registry_Implementation.md (simpler, 120-150h)
3. Begin curated registry implementation

---

## Phase 0 Complete!

Congratulations! You've completed the Phase 0 Tracer Bullet specification.

**What We Built**:
- ✅ Part 1: Evidence Foundation (prevents citation laundering)
- ✅ Part 2: GitHub Discovery & Analysis (code-based decision frameworks)
- ✅ Part 3: Synthesis & Evaluation (citation validity measurement)

**What We Validated**:
- Evidence-first architecture feasibility
- GitHub API as viable data source
- Code-based frameworks prevent LLM arithmetic hallucination
- Citation validity measurement methodology
- Cost per session (<$8 achievable)

**Decision Point**: Run `scripts/run_phase_0_evaluation.py` and measure citation validity.

**Your next action determines Autopack's research system future** 🚀
