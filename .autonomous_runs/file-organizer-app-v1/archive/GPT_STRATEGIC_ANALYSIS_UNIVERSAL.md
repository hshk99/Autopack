# GPT Strategic Analysis Template (Universal, uses RIGOROUS Market Research)

**Goal**: Given a rigorous market research document for a specific product, provide a brutally honest strategic assessment, GO/NO‑GO decision, and a focused execution plan that maximises profitability and reduces wasted effort.

This template assumes that:
- You have access to a **RIGOROUS market research document** produced using something like `MARKET_RESEARCH_RIGOROUS_*` for the current product.
- That document already contains: TAM/SAM/SOM, segment analysis, competitor landscape, pricing ideas, unit economics, technical risks, etc.

Your job is not to repeat the research, but to **interpret, challenge, and compress it into decisive guidance for the founder.**

When you see placeholders like `[PROJECT]`, replace them with the actual project name from context.

---

## 1. GO / NO‑GO Validation

### 1.1 Overall score and decision

- Assign a single **overall score (1–10)** to the project.
  - 8–10: Strong GO.
  - 6–7.5: Conditional GO (execution‑ and wedge‑dependent).
  - 4–5.5: Likely NO‑GO unless major pivots.
  - 1–3.5: Clear NO‑GO.

- State **explicitly**: GO, CONDITIONAL GO, or NO‑GO.

- In 3–5 bullet points, explain **why** you chose that score, referencing:
  - Market size and growth.
  - Competitive intensity and moat.
  - Segment economics (LTV/CAC, WTP).
  - Technical and regulatory feasibility.

### 1.2 Top 3 risks to mitigate (if GO/CONDITIONAL GO)

List the **three highest‑leverage risks** that must be addressed early, typically including:

- Failure to achieve a real 10x outcome vs the baseline.
- Weak moat and copycat risk.
- Segment confusion or overly broad scope.

For each risk, add 2–3 lines on *how* to mitigate or test it quickly.

If you conclude **NO‑GO**, instead list the 3–5 **deal‑breaking issues**.

---

## 2. Strategic Imperatives

Based on the research, define **three strategic imperatives** that should drive all decisions for the first 12–24 months. Typical imperatives:

1. **Commit to a narrow wedge**  
   - Choose a single primary segment + job‑to‑be‑done with the best combination of pain and economics (LTV/CAC), not necessarily the largest headcount.

2. **Deliver a measured 10x outcome**  
   - Specify the primary outcome (e.g., time saved, cost saved, risk reduced) and target improvement (e.g., “reduce from 10 hours to 2 hours for X task”).

3. **Keep v1 ruthlessly small, but end‑to‑end**  
   - Prioritise a thin, coherent workflow over a long list of features; aim for something that can plausibly be shipped within 6–9 months by a small team.

Tailor these to the actual project; do not just copy the generic wording. Make them as concrete as possible.

---

## 3. Segment Prioritisation

### 3.1 Interpret the segment economics

Using the market research document:

- Summarise the main candidate segments with their:
  - Size.
  - Pain level.
  - WTP / ARPU.
  - CAC and LTV estimates.
  - LTV/CAC ratios.

### 3.2 Recommend a primary wedge

- Choose **one primary segment** as the wedge. Justify based on:
  - Clear “must‑have” pain.
  - Strong or at least promising LTV/CAC.
  - Manageable switching costs.
  - Reasonable access to the segment with limited capital.

- Identify **secondary segments** to treat as:
  - Either “later expansions”, or
  - “Side‑effects” of building the core, not primary design targets.

If you think the research’s implied priority is wrong, **say so and correct it**.

### 3.3 Articulate the wedge thesis

Write a short wedge statement such as:

> “For [segment] who need to [critical job], [PROJECT] will [concrete 10x outcome] by [mechanism], starting with [initial workflow scope].”

---

## 4. 10x Differentiation

### 4.1 Is there a real 10x opportunity?

Based on the research:

- Describe the current **baseline workflow** for the primary wedge (manual processes + current tools).
- Quantify, where possible:
  - Time taken.
  - Costs.
  - Risk/error rates.
  - Cognitive load.

Then answer plainly:

- Is [PROJECT] realistically able to deliver:
  - 5–10x time reduction, or
  - 2–3x cost reduction *with* strong UX/privacy advantages, or
  - A clear reduction in high‑stakes risk?

If not, say: “This looks like a 2–3x, not 10x, improvement,” and call that out as a major risk.

### 4.2 Differentiation statement

Craft a **short positioning statement** that focuses on outcomes, not technology, e.g.:

> “For [segment] drowning in [problem], [PROJECT] is a [category] that turns [inputs] into [valuable output] in [timeframe], without [big downside that alternatives have].”

Avoid buzzwords. Make it concrete and grounded in the market research.

---

## 5. Pricing & Packaging Validation

Using the pricing ideas in the research:

- Evaluate whether proposed **tiers** and **price points** make sense given:
  - Competitor benchmarks.
  - Segment WTP.
  - API and infra cost structure.

- Comment on:
  - Whether the **free / starter** tier is too generous or too weak.
  - Whether the mid‑tier is under‑ or over‑priced relative to the value delivered.
  - How high‑ARPU segments (if any) should be packaged and priced.

- Suggest adjustments if needed, e.g.:
  - Restricting expensive features to paid tiers.
  - Raising prices for high‑value workflows.
  - Offering annual discounts to pull forward cash and improve retention.

---

## 6. MVP Scope & Roadmap

### 6.1 MVP definition

Define a realistic **MVP** that:

- Delivers a **thin, end‑to‑end workflow** for the primary wedge’s core job.
- Can plausibly be built and tested within **6–9 months** by a small team.
- Includes only the **minimum feature set** that is needed for users to experience the 10x outcome.

For clarity, split features into:

- **Must‑have for MVP**.
- **Nice‑to‑have for v1.1+** (later).
- **Out of scope for now** (explicitly parked).

### 6.2 Phased roadmap

Sketch a phased roadmap:

- **MVP (Phase 1)**: core workflow, basic UX, basic safety/rollback, minimal integrations.
- **Phase 2 (v1.1 / v1.2)**: 2–4 high‑leverage differentiating features *proven by MVP feedback*.
- **Phase 3 (v2+)**: expansions to secondary segments, richer workflows/packs, deeper integrations.

The point is to **avoid bloated v1** and feature creep.

---

## 7. Architecture & Technology (High‑Level)

You do **not** need to write detailed implementation plans, but you should:

- Sanity‑check the proposed stack from the research (e.g., local vs cloud, frameworks, dependencies).
- Highlight any **profit‑sensitive** choices, such as:
  - Heavy dependence on expensive APIs (LLMs, OCR, data sources).
  - Platforms that introduce high QA or support burden.
- Suggest high‑level architectural principles, e.g.:
  - Keep core logic modular so the same “engine” can power multiple workflows/packs.
  - Design for safe automation (logging, rollback, staging areas).

If the research proposes obviously fragile or over‑complex tech for the problem, say so and suggest a simpler alternative.

---

## 8. Financial Viability & Sensitivity

### 8.1 Validate unit economics

Cross‑check the research’s unit economics:

- Do the **CAC** assumptions look plausible given the channels and audience?
- Are the **LTV** and retention assumptions realistic for this category?
- Does the resulting **LTV/CAC** ratio look robust (e.g., >3) or fragile?

Summarise in a few bullets:

- “If CAC rises to X or retention drops to Y, this becomes marginal / still OK.”
- “High‑ARPU segment Z is where most of the economics come from.”

### 8.2 Validate revenue projections

Look at the Year 1 / 3 / 5 projections and answer:

- Are the user and revenue targets **plausible**, **optimistic**, or **very aggressive**?
- Which assumptions (conversion, churn, ACV, CAC) would most likely break?

If the projections look too rosy, explicitly downgrade them and explain.

---

## 9. Risk Matrix (Top 10) & Mitigation

From the research, construct or refine a **top‑10 risk list** with:

- Risk description.
- Likelihood (1–10).
- Impact (1–10).
- Priority (L × I).
- A short note on **mitigation** or **early test**.

Make sure to include:

- 10x value / PMF risk.
- Moat / copycat risk.
- Capital / runway risk.
- Technical feasibility of the core promise.
- Regulatory / compliance risk (if relevant).

Highlight the **top 3** by priority and restate them clearly for the founder.

---

## 10. Pivot & Kill Triggers

Based on the analysis:

- Define **specific, measurable triggers** for:
  - Pivoting segment focus (e.g., if segment A conversion <X% but segment B conversion >Y%).
  - Changing tech approach (e.g., local → cloud) if quality or performance targets aren’t met.
  - Abandoning or radically changing the idea if core assumptions fail.

Examples:

- “If after 6–9 months there are <N paying users and no measured 2–3x outcome on the core workflow, strongly consider shutting down or pivoting.”
- “If CAC exceeds [$] with no sign of improvement while LTV is capped at [$], this becomes non‑viable.”

These triggers should be **practical** and anchored in the previously discussed metrics.

---

## 11. Final Recommendation & Actionable Summary

### 11.1 One‑page founder brief

Compress everything into a **short, founder‑readable brief**:

- Decision: GO / CONDITIONAL GO / NO‑GO.
- Overall score (1–10).
- Primary wedge segment and wedge thesis.
- Summary of the 10x promise (baseline → target).
- Most important moat / defensibility considerations.
- MVP scope in one paragraph.
- 3 key financial takeaways (unit economics, capital, timelines).
- Top 3 risks and how to test them early.
- 5–10 **concrete next actions** for the next ~90 days.

### 11.2 Tone

- Be direct, not euphemistic.
- Optimise for **clear decision‑making**, not for making the founder feel good.
- Where research is weak or assumptions are shaky, call that out plainly.

---

## Output Format

Return a single Markdown document structured with the headings above:

1. GO / NO‑GO Validation  
2. Strategic Imperatives  
3. Segment Prioritisation  
4. 10x Differentiation  
5. Pricing & Packaging Validation  
6. MVP Scope & Roadmap  
7. Architecture & Technology (High‑Level)  
8. Financial Viability & Sensitivity  
9. Risk Matrix (Top 10) & Mitigation  
10. Pivot & Kill Triggers  
11. Final Recommendation & Actionable Summary

Adapt section lengths to the complexity of the project, but keep the overall document readable. Focus on clarity, explicit trade‑offs, and profitability.
