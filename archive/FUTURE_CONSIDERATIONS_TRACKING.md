# Future Considerations Tracking

**Date**: November 26, 2025
**Purpose**: Master list of items to be considered for future incorporation based on Autopack's runtime data

---

## Executive Summary

This document tracks all features, optimizations, and enhancements that were discussed but deferred pending real-world data from Autopack's operation. Each item includes:
- **What it is**: Brief description
- **Why deferred**: Reason for not implementing immediately
- **Data required**: What metrics/behavior we need to observe
- **Decision criteria**: When/why we would implement it
- **Review timeline**: When to revisit this decision

---

## Part 1: Deferred Features (Require Runtime Data)

### 1. Shadow Mode for Model Comparison

**What It Is**:
Run cheaper models (gpt-4o) in parallel with authoritative models (GPT-5, Opus) for high-risk phases, but only apply the authoritative model's output. Compare results to build confidence data.

**Why Deferred**:
- Doubles token cost for most expensive phases
- Adds no security benefit (authoritative model already decides)
- Only useful if planning future cost-cutting
- Current stance: "For security work, we pay for best models"

**Data Required**:
```
Monitor for 3-6 months:
1. GPT-5/Opus weekly spend on high-risk categories
2. Percentage of total budget consumed by high-risk work
3. Frequency of high-risk phases (currently expected <10%)

Specifically track:
- Weekly cost: security_auth_change
- Weekly cost: external_feature_reuse_remote
- Weekly cost: schema_contract_change_destructive
- Combined percentage of total weekly spend
```

**Decision Criteria**:
- ✅ **Implement shadow mode if**:
  - High-risk categories consume >40% of weekly budget, AND
  - This spend is causing budget pressure, AND
  - We're seriously considering downgrading security phases to cheaper models

- ❌ **Do NOT implement if**:
  - High-risk categories <30% of budget
  - Budget is comfortable
  - No plans to downgrade security phases

**Review Timeline**: After 3 months of operation (February 2026)

**Reference**: `docs/CLAUDE_FINAL_CONSENSUS_GPT_ROUND4.md` Part 2, `ref7.md` GPT2's response

---

### 2. Context Selector - JIT Context Loading

**What It Is**:
Intelligent context selection that loads only relevant files for each phase based on:
- Category-specific patterns (backend, frontend, database, api, tests, docs)
- Recently changed files
- Keyword matching from description
- Complexity-based heuristics

**Why Deferred**:
- Need baseline data on current context usage
- Need to measure actual context window exhaustion frequency
- Simple heuristics may be sufficient vs complex ML-based selection

**Data Required**:
```
Monitor for 2-4 weeks:
1. Average input tokens per phase (by category)
2. Frequency of context window exhaustion
3. Which file types consume most tokens
4. Correlation between phase complexity and context size

Specifically track:
- Phase ID → input tokens → files included → category
- Context window exhaustion incidents (>200k tokens)
- File type distribution (*.py, *.ts, *.md, etc.)
- Unused files (files included but not referenced in output)
```

**Decision Criteria**:
- ✅ **Implement context selector if**:
  - Context window exhaustion occurs >5 times/week, OR
  - Average input tokens >100k for any category, OR
  - Evidence that irrelevant files are frequently included

- ❌ **Do NOT implement if**:
  - Context exhaustion <1 time/week
  - Average input tokens <50k
  - Current "include everything" approach works fine

**Expected Impact**:
- 40-60% context reduction (estimated)
- Faster response times
- Lower input token costs

**Review Timeline**: After 50 phases run (or 2 weeks, whichever comes first)

**Reference**: Phase 1b implementation notes, GPT consensus on simple heuristics vs ML

---

### 3. Token Budget Enforcement (Hard Limits)

**What It Is**:
Enforce hard stops when weekly token budget is exceeded, rather than just logging warnings.

**Current Implementation**: Budget tracking with warnings only:
```python
# In LlmService
if weekly_usage > soft_limit:
    logger.warning(f"Approaching {provider} quota: {weekly_usage}/{cap}")
```

**Why Deferred**:
- Current quotas (50M OpenAI, 10M Anthropic weekly) are generous
- Need to see actual usage patterns first
- Hard stops could block legitimate work
- Prefer alerts + human override over automatic blocking (initially)

**Data Required**:
```
Monitor for 1-2 months:
1. Actual weekly token usage by provider
2. Usage patterns (spikes vs steady)
3. Highest usage week
4. Cost correlation with phase volume

Specifically track:
- Weekly usage: OpenAI (tokens)
- Weekly usage: Anthropic (tokens)
- Peak day within each week
- Cost per week (USD)
```

**Decision Criteria**:
- ✅ **Implement hard limits if**:
  - Actual weekly usage regularly exceeds 80% of quota, OR
  - Cost is becoming unsustainable, OR
  - Need enforceable limits for budget compliance

- ❌ **Keep warnings-only if**:
  - Actual usage <50% of quota
  - Budget is comfortable
  - Warnings are sufficient for monitoring

**Hybrid Approach** (likely outcome):
- Keep warnings for most categories
- Hard limits only for `never_fallback_categories` when quota truly exhausted
- Require manual override for high-risk phases if quota exceeded

**Review Timeline**: After 2 months of operation (January 2026)

**Reference**: `config/models.yaml` quota_enforcement section, `docs/CLAUDE_FINAL_ASSESSMENT_GPT_ROUND3.md`

---

### 4. Dynamic Escalation Threshold Tuning

**What It Is**:
Automatically adjust `after_attempts` thresholds based on observed success rates.

**Example**:
```yaml
# Current static config
external_feature_reuse_internal:
  strategy: progressive
  escalate_to:
    after_attempts: 2  # Fixed

# Proposed dynamic tuning
external_feature_reuse_internal:
  strategy: progressive
  escalate_to:
    after_attempts: auto  # Adjust based on success rate
```

**Why Deferred**:
- Need data on actual escalation success rates
- Static thresholds may be sufficient
- Dynamic tuning adds complexity

**Data Required**:
```
Monitor for 2-3 months:
1. Success rate by attempt number for each category
2. Wasted attempts (escalated but would have succeeded with more retries)
3. Premature escalations (escalated when primary model would have worked)

Specifically track per category:
- Attempt 1 success rate
- Attempt 2 success rate
- Attempt 3+ success rate
- Average attempts to success
- Percentage that required escalation
```

**Decision Criteria**:
- ✅ **Implement dynamic tuning if**:
  - Clear pattern emerges (e.g., 90% of failures happen on attempt 1), OR
  - Static thresholds are consistently suboptimal, OR
  - Significant cost savings possible from tuning

- ❌ **Keep static thresholds if**:
  - Success rates vary widely (no consistent pattern)
  - Static thresholds are working well
  - Cost savings would be minimal (<10%)

**Review Timeline**: After 100 phases per category (likely 2-3 months)

**Reference**: Progressive routing strategy discussion, GPT1's feedback on escalation logic

---

### 5. Dual Auditing for Non-Security Categories

**What It Is**:
Extend dual auditing (GPT-5 + Opus consensus) beyond the three high-risk categories to other important work.

**Current Implementation**:
Dual auditing ONLY for:
- `security_auth_change`
- `external_feature_reuse_remote`
- `schema_contract_change_destructive`

**Proposed Extension**:
Also dual audit for:
- `schema_contract_change_additive` (if failures occur)
- `core_backend_high` (for critical refactors)
- `external_feature_reuse_internal` (for internal supply chain)

**Why Deferred**:
- Dual auditing doubles auditor cost
- Need data on single auditor failure rate first
- May be overkill for non-security work

**Data Required**:
```
Monitor for 2-3 months:
1. Auditor rejection rate by category
2. Bugs discovered post-merge (slipped through auditor)
3. False negative rate (auditor approved bad code)

Specifically track:
- Category → auditor approval rate
- Category → post-merge bugs requiring rollback
- Auditor model → rejection accuracy (via manual review)
```

**Decision Criteria**:
- ✅ **Extend dual auditing if**:
  - Single auditor false negative rate >5% for any category, OR
  - Critical bugs slip through for non-security categories >2 times/month, OR
  - High-stakes refactors justify extra safety

- ❌ **Keep single auditing if**:
  - Single auditor false negative rate <2%
  - Post-merge bugs are rare and low-severity
  - Cost increase not justified by risk reduction

**Review Timeline**: After 3 months of operation (February 2026)

**Reference**: `docs/CLAUDE_ASSESSMENT_OF_GPT_FEEDBACK.md` dual auditing discussion

---

### 6. Category Auto-Splitting Based on Frequency

**What It Is**:
If certain categories become >20% of total phases, automatically recommend further splitting.

**Example**:
```
If core_backend_high becomes 40% of phases:
→ Suggest splitting into:
  - core_backend_high_security_sensitive
  - core_backend_high_performance_critical
  - core_backend_high_general
```

**Why Deferred**:
- Need actual category distribution data first
- Current 8 categories may be sufficient
- Over-splitting adds maintenance burden

**Data Required**:
```
Monitor for 2-3 months:
1. Category distribution (% of total phases)
2. Homogeneity within categories (are phases similar?)
3. Cost concentration (does one category dominate spend?)

Specifically track:
- Category → phase count → percentage
- Category → cost distribution
- Manual review: "Is this category too broad?"
```

**Decision Criteria**:
- ✅ **Split category if**:
  - Single category >30% of total phases, AND
  - Clear subcategories exist within it, AND
  - Splitting would enable better model routing

- ❌ **Keep current categories if**:
  - No single category >25% of phases
  - Categories are already well-defined
  - Splitting would add complexity without benefit

**Review Timeline**: After 200 total phases run (likely 2-3 months)

**Reference**: `docs/CLAUDE_FINAL_CONSENSUS_GPT_ROUND4.md` category splitting framework

---

### 7. Provider Quota Balancing

**What It Is**:
Dynamically shift load between OpenAI and Anthropic to balance quota usage.

**Current Implementation**:
Fixed model assignments per category:
```yaml
security_auth_change:
  builder_primary: gpt-5           # Always OpenAI
  auditor_primary: claude-opus-4-5  # Always Anthropic
```

**Proposed Enhancement**:
```yaml
security_auth_change:
  builder_primary: [gpt-5, claude-opus-4-5]  # Alternate based on quota
  auditor_primary: [claude-opus-4-5, gpt-5]
  quota_balancing: enabled
```

**Why Deferred**:
- Current quotas are sufficient
- Fixed assignments are simpler
- Need data on whether quota pressure is real

**Data Required**:
```
Monitor for 2-3 months:
1. Quota utilization by provider (% of weekly cap)
2. Quota exhaustion incidents
3. Provider availability/reliability

Specifically track:
- Weekly OpenAI usage vs 50M cap
- Weekly Anthropic usage vs 10M cap
- Quota incidents by provider
- Which provider hits soft limit first
```

**Decision Criteria**:
- ✅ **Implement quota balancing if**:
  - One provider regularly exceeds 80% quota while other is <50%, OR
  - Quota exhaustion incidents occur >2 times/month, OR
  - Provider outages require fallback capability

- ❌ **Keep fixed assignments if**:
  - Both providers stay <70% quota utilization
  - No quota incidents
  - Fixed assignments are working well

**Review Timeline**: After 3 months of operation (February 2026)

**Reference**: `config/models.yaml` provider_quotas section

---

## Part 2: Deferred Optimizations (Premature Without Data)

### 8. Learned Rules Refinement Based on Rejection Patterns

**What It Is**:
Analyze auditor rejection reasons to automatically generate new learned rules.

**Example**:
```
If auditor repeatedly rejects for "missing input validation":
→ Auto-generate learned rule:
  "Always add input validation for user-facing API endpoints"
```

**Why Deferred**:
- Need rejection data first
- Manual rule creation may be sufficient initially
- Auto-generation could produce low-quality rules

**Data Required**:
```
Monitor for 3-6 months:
1. Auditor rejection reasons (categorized)
2. Most common rejection types
3. Correlation between rejection reason and category

Collect:
- Rejection reason text (from auditor feedback)
- Category + complexity of rejected phases
- Whether same issue repeats across phases
```

**Decision Criteria**:
- ✅ **Implement auto-rule generation if**:
  - Same rejection reason appears >10 times, OR
  - Clear patterns emerge that could be codified, OR
  - Manual rule creation is becoming bottleneck

- ❌ **Keep manual rule creation if**:
  - Rejections are diverse (no clear patterns)
  - Manual rules cover most cases
  - Auto-generation quality is questionable

**Review Timeline**: After 6 months of operation (May 2026)

**Reference**: Phase 3 planning in earlier consensus documents

---

### 9. Primary Model Downgrading for Over-Powered Categories

**What It Is**:
If a category never escalates, downgrade the primary model to save cost.

**Example**:
```
If tests category has 0% escalation rate over 3 months:
→ Downgrade from claude-sonnet-4-5 to gpt-4o-mini
```

**Why Deferred**:
- Need escalation rate data first
- Risk of degrading quality for marginal savings
- Current models may be appropriately sized

**Data Required**:
```
Monitor for 3 months minimum:
1. Escalation rate by category
2. Quality metrics (bugs post-merge)
3. Cost per category

Track:
- Category → escalation rate → trend over time
- Cost savings if downgraded
- Quality impact estimate
```

**Decision Criteria**:
- ✅ **Downgrade primary model if**:
  - Escalation rate <5% for 3 consecutive months, AND
  - Quality remains high (no post-merge bugs), AND
  - Cost savings >15% for that category

- ❌ **Keep current primary model if**:
  - Escalation rate >10%
  - Any quality concerns
  - Cost savings <10%

**Important**: NEVER downgrade for `never_fallback_categories` (security, supply chain, destructive migrations)

**Review Timeline**: After 3 months of operation (February 2026)

**Reference**: Progressive routing strategy cost optimization goals

---

### 10. Complexity-Based Context Window Allocation

**What It Is**:
Allocate larger context windows for high-complexity phases, smaller for low-complexity.

**Current Approach**: Same context inclusion logic for all phases

**Proposed Enhancement**:
```python
if complexity == "high":
    max_files = 100
    max_tokens = 150000
elif complexity == "medium":
    max_files = 50
    max_tokens = 75000
else:  # low
    max_files = 20
    max_tokens = 30000
```

**Why Deferred**:
- Need data on context usage by complexity
- May be premature optimization
- Current approach may be sufficient

**Data Required**:
```
Monitor for 1-2 months:
1. Input tokens by complexity level
2. Context window exhaustion by complexity
3. Quality correlation with context size

Track:
- Complexity → average input tokens
- Complexity → context exhaustion incidents
- Complexity → phase success rate
```

**Decision Criteria**:
- ✅ **Implement variable context allocation if**:
  - Clear correlation between complexity and context needs, OR
  - Low-complexity phases waste tokens on unused context, OR
  - High-complexity phases run out of context frequently

- ❌ **Keep uniform context if**:
  - No clear correlation with complexity
  - Context exhaustion is rare (<1/week)
  - Simplicity preferred over optimization

**Review Timeline**: After 100 phases run (likely 1-2 months)

**Reference**: Context engineering discussion in earlier documents

---

## Part 3: Infrastructure Enhancements (Deferred to Phase 3+)

### 11. Real-Time Dashboard with Live Metrics

**What It Is**:
Live dashboard showing current phase status, model usage, costs, and alerts.

**Proposed Features**:
- Real-time phase progress
- Token usage gauges (OpenAI, Anthropic)
- Cost tracking (daily, weekly, monthly)
- Alert feed (quota incidents, failures)
- Category distribution charts
- Model performance metrics

**Why Deferred**:
- Weekly static reports may be sufficient initially
- Dashboard requires significant frontend work
- Need baseline data to know what to visualize

**Data Required**:
```
After 1-2 months of operation:
1. Which metrics are most valuable for decision-making?
2. How often do we check reports?
3. What alerts need immediate attention vs weekly review?
```

**Decision Criteria**:
- ✅ **Build live dashboard if**:
  - Weekly reports are insufficient (need real-time monitoring), OR
  - Managing multiple concurrent runs (requires live status), OR
  - Budget for frontend development available

- ❌ **Keep static reports if**:
  - Weekly reports meet needs
  - Run volume is low (single operator, <10 runs/week)
  - Frontend work not prioritized

**Review Timeline**: After 3 months of operation (February 2026)

**Reference**: Month 2 dashboard integration from implementation plan

---

### 12. Automated Rollback on Quality Gate Failures

**What It Is**:
Automatically revert merged changes if post-merge probes or CI fail.

**Current Approach**: Manual rollback if needed

**Proposed Enhancement**:
```yaml
# In .autopack/config.yaml
auto_rollback:
  enabled: true
  triggers:
    - probe_failure_threshold: 2  # Rollback if 2+ probes fail
    - ci_failure: true            # Rollback if CI fails
    - security_scan_critical: true # Rollback if critical vuln introduced
```

**Why Deferred**:
- Need data on failure rates first
- Manual rollback may be sufficient
- Risk of over-aggressive rollbacks

**Data Required**:
```
Monitor for 3-6 months:
1. Frequency of post-merge failures
2. Time to detect failures
3. Time to manual rollback
4. Impact of failures before rollback

Track:
- Post-merge probe failures
- Post-merge CI failures
- Security scan regressions
- Rollback frequency and reasons
```

**Decision Criteria**:
- ✅ **Implement auto-rollback if**:
  - Post-merge failures occur >2 times/month, OR
  - Manual rollback is time-consuming (>30 min), OR
  - Failures cause production issues

- ❌ **Keep manual rollback if**:
  - Post-merge failures are rare (<1/month)
  - Failures are non-critical
  - Manual review preferred before rollback

**Review Timeline**: After 6 months of operation (May 2026)

**Reference**: Quality gate framework from security assessment

---

### 13. Multi-Repo Support

**What It Is**:
Extend Autopack to manage changes across multiple repositories simultaneously.

**Current Limitation**: Single repo per run

**Proposed Enhancement**:
```yaml
# In phase spec
multi_repo:
  - repo: autopack-api
    changes: [src/auth/login.py]
  - repo: autopack-frontend
    changes: [components/LoginForm.tsx]
  - repo: autopack-shared
    changes: [types/User.ts]
```

**Why Deferred**:
- Single repo is sufficient for current project
- Multi-repo adds significant complexity
- Need to validate single-repo approach first

**Data Required**:
```
Monitor for 6+ months:
1. How often do changes span multiple repos?
2. What's the coordination overhead?
3. Are there clear use cases?
```

**Decision Criteria**:
- ✅ **Implement multi-repo if**:
  - Frequent need to coordinate changes across repos (>1/week), OR
  - Manual coordination is error-prone, OR
  - Expanding to larger system with multiple repos

- ❌ **Keep single-repo if**:
  - Rare need for multi-repo changes
  - Manual coordination is acceptable
  - Complexity not justified

**Review Timeline**: After 6+ months (May 2026 or later)

**Reference**: Not explicitly discussed, but logical future enhancement

---

## Part 4: Model Upgrades (Dependent on Model Availability)

### 14. GPT-5 Upgrade Path Validation

**What It Is**:
Validate that GPT-5 is actually better than gpt-4o for high-risk work in practice.

**Current Assumption**: GPT-5 has ~26% lower hallucination rate (benchmark data)

**Validation Needed**:
- Real-world performance on Autopack tasks
- Cost vs quality tradeoff
- Latency impact

**Data Required**:
```
Monitor for 3 months:
1. GPT-5 phase success rate vs gpt-4o historical baseline
2. GPT-5 auditor rejection rate vs gpt-4o
3. Quality of GPT-5 output (manual review sample)
4. Actual cost per phase with GPT-5

Compare:
- GPT-5 first-attempt success rate
- gpt-4o first-attempt success rate (if we have historical data)
- Quality metrics for both
```

**Decision Criteria**:
- ✅ **Keep GPT-5 if**:
  - Success rate >gpt-4o by >10%, OR
  - Quality improvement is noticeable, OR
  - Cost increase is justified by quality gains

- ⚠️ **Reconsider GPT-5 if**:
  - Success rate similar to gpt-4o (<5% difference), AND
  - Cost is significantly higher, AND
  - Quality improvement is marginal

**Review Timeline**: After 3 months of GPT-5 usage (February 2026)

**Reference**: Model selection rationale in security assessment

---

### 15. O3-Mini as Auditor Option

**What It Is**:
Evaluate whether o3-mini (if/when released) is suitable as auditor for specific categories.

**Current Decision**: NOT using o3 due to cost ($2150/M output tokens)

**Future Consideration**:
If o3-mini is released with:
- 10x lower cost ($215/M output tokens)
- Strong reasoning capabilities
- Suitable latency

Then evaluate for:
- Schema validation (logic-heavy auditing)
- Security review (reasoning about vulnerabilities)
- Complex refactor auditing

**Data Required**:
```
When o3-mini is available:
1. Benchmark on sample Autopack audit tasks
2. Cost comparison vs Claude Opus 4.5
3. Latency measurements
4. Quality assessment (does reasoning help?)
```

**Decision Criteria**:
- ✅ **Adopt o3-mini as auditor if**:
  - Quality ≥ Claude Opus 4.5 for audit tasks, AND
  - Cost ≤ 1.5x Claude Opus 4.5, AND
  - Latency acceptable (<30 sec for audits)

- ❌ **Stick with Claude Opus 4.5 if**:
  - o3-mini quality is worse
  - Cost is prohibitive
  - Latency is too high (reasoning overhead)

**Review Timeline**: When o3-mini is released (TBD - not yet available)

**Reference**: `docs/COMPREHENSIVE_SECURITY_AND_AUTOMATION_ASSESSMENT.md` o3 analysis

---

### 16. Claude Opus 5 Migration Plan

**What It Is**:
When Claude Opus 5 is released, evaluate as replacement for Opus 4.5.

**Current Best Auditor**: Claude Opus 4.5 (80.9% SWE-bench)

**Future Consideration**:
Opus 5 likely improvements:
- Higher SWE-bench score
- Better code understanding
- Potentially lower cost

**Data Required**:
```
When Opus 5 is available:
1. Benchmark on sample Autopack audit tasks
2. SWE-bench score comparison
3. Cost comparison
4. Side-by-side quality comparison (50 phases)
```

**Decision Criteria**:
- ✅ **Migrate to Opus 5 if**:
  - SWE-bench score >82%, OR
  - Noticeable quality improvement in audits, OR
  - Cost decrease with same/better quality

- ⏳ **Gradual rollout if**:
  - Quality slightly better but need validation
  - Start with progressive categories, then best_first

- ❌ **Keep Opus 4.5 if**:
  - Opus 5 quality is worse or same
  - Cost increase not justified

**Review Timeline**: When Claude Opus 5 is released (TBD - likely Q1-Q2 2026)

**Reference**: Model comparison table in security assessment

---

## Part 5: Configuration Tuning (Data-Driven)

### 17. Max Attempts Tuning by Category

**What It Is**:
Adjust `max_attempts` limits based on actual success rate data.

**Current Defaults**:
```yaml
# Most categories: no explicit max (inherits global)
# Destructive migrations: max_attempts: 2
```

**Proposed Data-Driven Tuning**:
```
If category success rate by attempt:
- Attempt 1: 70%
- Attempt 2: 90%
- Attempt 3: 95%
- Attempt 4+: 96%

Then max_attempts: 3 is optimal (diminishing returns after)
```

**Data Required**:
```
Monitor for 2-3 months per category:
1. Success rate by attempt number
2. Marginal success rate improvement per additional attempt
3. Cost per additional attempt

Track:
- Category → attempt number → success/failure
- Cost per attempt
- Time per attempt
```

**Decision Criteria**:
- ✅ **Set max_attempts: N if**:
  - Marginal improvement after N attempts <5%, OR
  - Cost of attempt N+1 exceeds value of success

- Example:
  - If 95% success by attempt 3, set max_attempts: 3
  - If 60% success by attempt 3, no max (keep trying)

**Review Timeline**: After 100 phases per category (likely 2-3 months)

**Reference**: Progressive routing strategy implementation

---

### 18. Rate Limiting Threshold Adjustment

**What It Is**:
Adjust rate limit from 10 runs/minute based on actual usage patterns.

**Current Setting**: `10/minute` (somewhat arbitrary)

**Data-Driven Adjustment**:
```
If legitimate usage patterns show:
- Most users: 1-3 runs/minute
- Power users: 5-8 runs/minute
- Abuse attempts: >15 runs/minute

Then: Keep 10/minute or increase to 15/minute
```

**Data Required**:
```
Monitor for 1-2 months:
1. Distribution of request rates
2. Legitimate burst patterns
3. False positives (legitimate users hit limit)

Track:
- Requests per minute per IP
- Rate limit hits by IP
- User feedback on rate limits
```

**Decision Criteria**:
- ✅ **Increase rate limit if**:
  - Legitimate users hit limit >1 time/week, OR
  - Usage patterns show higher burst needs, OR
  - Single operator doing rapid iteration

- ✅ **Decrease rate limit if**:
  - Abuse attempts are common, OR
  - Server load is high, OR
  - Need stricter throttling

- ✅ **Keep 10/minute if**:
  - No legitimate rate limit hits
  - Abuse is rare
  - Current limit is working well

**Review Timeline**: After 1 month of operation (December 2025)

**Reference**: `src/autopack/main.py` rate limiting implementation

---

## Part 6: Quality & Safety Enhancements (Validation Required)

### 19. Pre-Flight Validation for Destructive Operations

**What It Is**:
Extra validation step before running destructive migrations or schema changes.

**Example**:
```python
# Before running schema_contract_change_destructive:
pre_flight_checks = [
    "Confirm no active connections to affected tables",
    "Verify backup exists and is <1 hour old",
    "Check rollback plan is in place",
    "Require manual approval if affects >1000 rows"
]
```

**Why Deferred**:
- Need data on destructive operation failure rate
- May be overkill if LLM quality is high
- Adds latency and complexity

**Data Required**:
```
Monitor for 3-6 months:
1. Failure rate for schema_contract_change_destructive
2. Severity of failures (data loss vs minor issues)
3. Time to recovery from failures

Track:
- Destructive operation failures
- Post-merge rollbacks required
- Data loss incidents (should be zero)
```

**Decision Criteria**:
- ✅ **Implement pre-flight checks if**:
  - Any data loss incident occurs, OR
  - Destructive operation failure rate >10%, OR
  - Stakeholder concern about safety

- ❌ **Skip pre-flight checks if**:
  - Zero data loss incidents
  - Destructive operations are rare (<1/month)
  - LLM quality is sufficient

**Review Timeline**: After 6 months of operation (May 2026)

**Reference**: `schema_contract_change_destructive` best_first configuration

---

### 20. Supply Chain Vetting Process

**What It Is**:
Formal vetting process for external packages before `external_feature_reuse_remote` phases.

**Example**:
```
Before allowing Autopack to pull from NPM/PyPI:
1. Check package age (>6 months old)
2. Check download count (>10k/month)
3. Check known vulnerabilities (via Snyk/npm audit)
4. Check maintainer reputation
5. Require manual approval if any red flags
```

**Why Deferred**:
- Current policy: `allow_auto_apply: false` (requires human review)
- Need data on how often external reuse is attempted
- Formal vetting may be overkill if rare

**Data Required**:
```
Monitor for 3-6 months:
1. Frequency of external_feature_reuse_remote phases
2. Quality of packages selected by LLM
3. Security scan results for added packages

Track:
- How often external packages are suggested
- Which packages are most common
- Vulnerabilities discovered in added packages
```

**Decision Criteria**:
- ✅ **Implement formal vetting if**:
  - External reuse occurs >2 times/month, OR
  - LLM suggests low-quality packages, OR
  - Vulnerabilities are discovered in added packages

- ❌ **Keep manual review only if**:
  - External reuse is rare (<1/month)
  - LLM suggestions are high-quality
  - Manual review is sufficient

**Review Timeline**: After 6 months of operation (May 2026)

**Reference**: `external_feature_reuse_remote` configuration and GPT supply chain discussion

---

## Part 7: Items from Chatbot_Project Integration Analysis

**Source**: GPT1 + GPT2 consensus on chatbot_project integration, Phase 1b completion

### 21. Context Heuristics Validation (Token Savings Measurement)

**What It Is**:
Measure actual token savings from the context ranking heuristics we implemented in Phase 1b.

**Already Implemented**:
- `_relevance_score()` - keyword matching from description
- `_recency_score()` - recently changed files prioritized
- `_type_priority_score()` - critical files ranked higher

**Validation Required**:
```
Measure before/after metrics:
- Average context tokens per phase (before ranking)
- Average context tokens per phase (after ranking)
- Phase success rate (ensure no degradation)
- Token savings percentage
```

**Why This Matters**:
- GPT2 said: "Abort if there is no measurable reduction in average context tokens per call"
- Need to prove 30-50% claimed reduction is real
- If savings are <20%, may need to revisit approach

**Data Required**:
```
Monitor for 1-2 months:
1. tokens_per_llm_call by phase (input tokens specifically)
2. number_of_context_tokens per phase
3. files_included vs files_used (how many files were unnecessary?)
4. Phase success rate before/after ranking

Track per phase:
- Input tokens: before_ranking vs after_ranking
- Files included: before_ranking vs after_ranking
- Files referenced in output (measure relevance accuracy)
- Phase outcome (success/failure - ensure no quality degradation)
```

**Decision Criteria**:
- ✅ **Keep context ranking if**:
  - Token savings ≥30%, AND
  - Phase success rate unchanged or improved

- ⚠️ **Tune heuristics if**:
  - Token savings 15-30%, OR
  - Phase success rate decreased slightly (<5%)

- ❌ **Revert context ranking if**:
  - Token savings <15%, OR
  - Phase success rate decreased >5%

**Review Timeline**: After 50 phases run (or 2 weeks, whichever comes first)

**Reference**: `src/autopack/context_selector.py` implementation, GPT2 Phase 2 Medium priority

---

### 22. Risk Scorer Calibration with Incident History

**What It Is**:
Calibrate risk scorer thresholds using actual incident data from Autopack's operation.

**Already Implemented**:
```python
# In src/autopack/risk_scorer.py
def calculate_risk_score(phase_spec: Dict) -> Dict:
    score = 0
    score += loc_delta_score(phase_spec)         # Up to 40 points
    score += critical_path_score(phase_spec)      # Up to 30 points
    score += test_coverage_score(phase_spec)      # Up to 20 points
    score += hygiene_score(phase_spec)            # Up to 10 points
```

**Calibration Required**:
```
Current thresholds (arbitrary):
- Low risk: 0-30 points
- Medium risk: 31-60 points
- High risk: 61-100 points

Need to correlate with actual incidents:
- Which phases with score X actually caused issues?
- Which score ranges had 0% incident rate?
- Which score ranges had >10% incident rate?
```

**Why This Matters**:
- GPT1 said: "Calibrate using your own incident history before letting it veto anything"
- Current thresholds are not data-driven
- Risk of false positives (blocking safe phases) or false negatives (approving risky phases)

**Data Required**:
```
Monitor for 3-6 months:
1. Risk score for every phase
2. Which phases caused post-merge incidents (bugs, rollbacks, etc.)
3. Correlation between score and incident rate

Create dataset:
- Phase ID → risk score → incident? (yes/no)
- Calculate precision/recall for each threshold
- Find optimal threshold that maximizes detection while minimizing false positives
```

**Decision Criteria**:
- ✅ **Promote risk scorer to gate if**:
  - Clear correlation: high-risk scores predict >50% of incidents, AND
  - False positive rate <10%, AND
  - Confidence that gating would have prevented real issues

- ⚠️ **Keep as dashboard metadata only if**:
  - Weak correlation: high-risk scores don't predict incidents well, OR
  - High false positive rate (>20%), OR
  - Not enough incident data yet

**Calibration Method**:
```python
# After 6 months of data
def calibrate_risk_thresholds(incident_history: List[Dict]):
    """Find optimal thresholds using incident data."""

    # Sort phases by risk score
    phases = sorted(incident_history, key=lambda p: p["risk_score"])

    # Test different thresholds
    best_f1 = 0
    best_threshold = 60

    for threshold in range(0, 100, 5):
        predicted_high_risk = [p for p in phases if p["risk_score"] >= threshold]
        actual_incidents = [p for p in phases if p["had_incident"]]

        true_positives = len([p for p in predicted_high_risk if p["had_incident"]])
        false_positives = len([p for p in predicted_high_risk if not p["had_incident"]])
        false_negatives = len([p for p in actual_incidents if p["risk_score"] < threshold])

        precision = true_positives / (true_positives + false_positives) if true_positives + false_positives > 0 else 0
        recall = true_positives / (true_positives + false_negatives) if true_positives + false_negatives > 0 else 0
        f1 = 2 * (precision * recall) / (precision + recall) if precision + recall > 0 else 0

        if f1 > best_f1:
            best_f1 = f1
            best_threshold = threshold

    return best_threshold, best_f1
```

**Review Timeline**: After 6 months of operation (May 2026) - need significant incident data

**Reference**: GPT1 Tier 2 priority, risk scorer implementation in Phase 1b

---

### 23. Post-Run Replay Tooling

**What It Is**:
Allow operator to replay a tier with manual modifications, without re-running the entire run from scratch.

**Use Case**:
```
Scenario: Tier 3 failed due to unexpected test failure
Current: Re-run entire Tier 1→2→3
Proposed: "Replay Tier 3 with modifications" (fix test setup, re-run)
```

**Why Deferred**:
- Need data on how often tiers fail and require manual intervention
- Current approach (re-run everything) may be sufficient if failures are rare
- Adds complexity to run state management

**Implementation Concept**:
```python
# New endpoint
@app.post("/runs/{run_id}/replay-tier")
def replay_tier(
    run_id: str,
    tier_id: str,
    modifications: Dict,  # Manual changes to apply before replay
    db: Session = Depends(get_db)
):
    """Replay a specific tier with manual modifications."""

    # Load tier state from previous run
    tier_state = load_tier_state(run_id, tier_id)

    # Apply manual modifications
    for file_path, changes in modifications.items():
        apply_changes(file_path, changes)

    # Re-run tier from this state
    result = execute_tier(tier_state, db)

    return result
```

**Data Required**:
```
Monitor for 2-3 months:
1. How often do tiers fail?
2. How often are failures fixable with minor manual changes?
3. How much time is wasted re-running entire runs?

Track:
- Tier failure rate by tier number
- Failure reasons (test issues, environment issues, logic errors)
- Time spent on full re-runs when only last tier needed replay
```

**Decision Criteria**:
- ✅ **Implement replay tooling if**:
  - Tier failures occur >3 times/week, AND
  - >50% of failures would benefit from replay (vs full re-run), AND
  - Time savings would be significant (>30 min/week)

- ❌ **Keep full re-run approach if**:
  - Tier failures are rare (<1/week)
  - Most failures require re-running from scratch anyway
  - Time savings would be minimal

**Review Timeline**: After 3 months of operation (February 2026)

**Reference**: GPT2 Phase 2 Medium priority, "Still 'zero-intervention per run', gives operator first-class way to replay"

---

### 24. Multi-Signal Stall Detection (Logging Only)

**What It Is**:
Log advanced stall detection signals for analysis, WITHOUT gating on them yet.

**Signals to Log**:
```python
# In LlmService.call()
stall_signals = {
    "evidence_delta": calculate_evidence_delta(previous_attempt, current_attempt),
    "entropy": calculate_output_entropy(current_attempt),
    "loop_score": detect_repetition_patterns(current_attempt),
    "mean_time_until_success": get_mtus_for_category(category)
}

# Log to telemetry (do NOT gate)
telemetry.log_stall_signals(phase_id, attempt_num, stall_signals)
```

**Why Deferred**:
- GPT1 said: "Log advanced signals if you want; don't gate on them yet"
- Need data to validate whether these signals actually predict stalls
- Risk of false positives if used for gating without validation

**Data Required**:
```
Monitor for 6+ months:
1. Stall signal values for all phases
2. Which phases actually stalled (>5 attempts with no success)
3. Correlation between signal values and actual stalls

Build dataset:
- Phase ID → attempt_num → stall_signals → did_eventually_succeed?
- Identify which signals are most predictive
- Determine thresholds that would have caught stalls without false positives
```

**Decision Criteria**:
- ✅ **Promote to gating logic if**:
  - Clear correlation: signal predicts stalls with >80% accuracy, AND
  - False positive rate <5%, AND
  - Would have prevented significant wasted token spend

- ❌ **Keep as logging only if**:
  - Weak correlation with actual stalls
  - High false positive rate
  - Simple attempt-count limits are sufficient

**Review Timeline**: After 6+ months of operation (June 2026+)

**Reference**: GPT1 Tier 3 (low priority), multi-signal gates discussion

---

### 25. HiTL (Human-in-the-Loop) Emergency Override

**What It Is**:
Pause run and ask operator for intervention after catastrophic pattern detected.

**Proposed Triggers**:
```python
# Pause run and alert operator if:
catastrophic_patterns = [
    "5+ consecutive failures in security_auth_change category",
    "Quota exhausted for never_fallback_category",
    "10+ phases failed with same error pattern",
    "Risk score >90 AND auditor flagged critical issues"
]
```

**Why Deferred**:
- GPT1 said: "Consider later and only as emergency override, behind feature flag, off by default"
- Current philosophy: zero-intervention per run
- Need data on how often catastrophic patterns actually occur

**Data Required**:
```
Monitor for 6+ months:
1. How often do catastrophic patterns occur?
2. Would human intervention have helped?
3. Cost of false pauses vs cost of continuing bad runs

Track:
- Consecutive failure chains
- Same-error pattern repetitions
- Quota exhaustion incidents
- Operator would have paused manually? (retrospective review)
```

**Decision Criteria**:
- ✅ **Implement HiTL (behind flag, off by default) if**:
  - Catastrophic patterns occur >1 time/month, AND
  - Manual intervention would have prevented significant waste/damage, AND
  - Pattern detection is reliable (low false positive rate)

- ❌ **Reject HiTL if**:
  - Catastrophic patterns are rare (<1/quarter)
  - Automatic recovery mechanisms are sufficient
  - Prefer fully autonomous operation

**Review Timeline**: After 6+ months of operation (June 2026+), only if evidence warrants

**Reference**: GPT1 Tier 3 (low priority), explicit "off by default" recommendation

---

### 26. LangGraph / Qdrant Integration

**What It Is**:
- **LangGraph**: Graph-based orchestration for complex multi-agent workflows
- **Qdrant**: Vector database for semantic search over run history

**Why REJECTED for v1**:
- GPT1 + GPT2 consensus: "Current evidence: it doesn't need this"
- Autopack's orchestration is simple: linear tier progression
- Run history search via SQL is sufficient

**Future Consideration**:
```
Only revisit if Autopack v2 requires:
- Complex multi-agent orchestration (graph-based, not linear)
- Semantic search: "Find all runs similar to this description"
- Dynamic phase generation based on run history patterns
```

**Data Required**:
```
N/A - not monitoring for this.
Only reconsider if use case emerges:
- Users request: "Search past runs by natural language description"
- Orchestration becomes too complex for linear tier model
- Need agent-to-agent communication patterns
```

**Decision Criteria**:
- ✅ **Reconsider LangGraph/Qdrant if**:
  - Clear use case emerges that can't be solved with current architecture, AND
  - Complexity is justified by value, AND
  - Autopack v2 redesign is planned

- ❌ **Reject for foreseeable future if**:
  - Current linear tier model works fine
  - SQL search over runs is sufficient
  - No compelling use case emerges

**Review Timeline**: N/A - only if use case emerges organically

**Reference**: GPT1 Tier 3 explicit REJECT, GPT2 explicit REJECT, "NO Qdrant, NO embeddings, NO new infrastructure"

---

### 27. Agents, Reuse Index, Portfolio, User Feedback

**What It Is**:
Advanced features mentioned in MoAI-ADK architecture but not adopted for Autopack:
- **Agents**: 35 specialized agents (MoAI has this, Autopack has 2: Builder + Auditor)
- **Reuse Index**: Searchable index of reusable code patterns
- **Portfolio**: Track all past runs, projects, patterns
- **User Feedback**: Collect explicit feedback on Builder/Auditor quality

**Why Deferred/Rejected**:
- **Agents**: Autopack's 2-agent model is simpler and sufficient
- **Reuse Index**: Would require Qdrant (rejected for v1)
- **Portfolio**: Simple run history DB is sufficient initially
- **User Feedback**: Could be valuable but adds UX complexity

**Reconsideration Criteria**:

#### Reuse Index:
- ✅ **Implement if**:
  - Builder repeatedly recreates similar code patterns (>5 times), AND
  - Explicit reuse would save significant tokens/time, AND
  - Willing to add vector DB infrastructure

- **Data Required**: Track code similarity across phases, measure duplication

- **Review Timeline**: After 6+ months (June 2026+)

#### Portfolio Management:
- ✅ **Implement if**:
  - Managing >10 concurrent projects with Autopack, AND
  - Need cross-project insights, AND
  - Simple per-run history is insufficient

- **Data Required**: N/A - use case driven

- **Review Timeline**: Only if multi-project usage emerges

#### User Feedback:
- ✅ **Implement if**:
  - Operator frequently disagrees with Builder/Auditor decisions, AND
  - Feedback would improve model selection/routing, AND
  - UX budget available for feedback UI

- **Data Required**: Track manual overrides, rollbacks, operator dissatisfaction signals

- **Review Timeline**: After 3 months of operation (February 2026)

**Implementation Concept for User Feedback**:
```python
# Add to phase completion
@app.post("/phases/{phase_id}/feedback")
def submit_phase_feedback(
    phase_id: str,
    feedback: Dict,  # {quality: 1-5, comments: str, would_change: str}
    db: Session = Depends(get_db)
):
    """Collect operator feedback on phase quality."""

    # Store feedback
    db.add(PhaseFeedback(
        phase_id=phase_id,
        quality_rating=feedback["quality"],
        comments=feedback["comments"],
        suggested_changes=feedback["would_change"]
    ))

    # Use for model routing calibration
    if feedback["quality"] <= 2:
        log_model_failure(phase_id, "low_quality_feedback")
```

**Reference**: MoAI-ADK patterns, thin adoption strategy

---

### 28. Time Budget System (Simple Watchdog Only)

**What It Is**:
GPT1 + GPT2 consensus: Use simple `max_duration_minutes` watchdog, NOT full time budget system.

**Already Implemented**:
```python
# In time_watchdog.py
class TimeWatchdog:
    def __init__(self, max_duration_seconds=7200):
        self.max_duration_seconds = max_duration_seconds
```

**What We're NOT Building**:
```yaml
# REJECTED: Complex time budget system
time_budgets:
  soft_cap_minutes: 30
  hard_cap_minutes: 60
  tier_1_max: 10
  tier_2_max: 20
  tier_3_max: 30
```

**Why Simple Watchdog is Sufficient**:
- GPT1: "Add simple run-level max_duration_minutes and surface it in the dashboard. No heavy time-budget subsystem."
- GPT2: "Look for phases spending 10-20 minutes with <5k tokens" (to detect stalls, not for budget enforcement)
- Most phases complete quickly; watchdog prevents true runaways

**Monitoring Required**:
```
Track for 1-2 months:
1. Phase duration distribution
2. Phases that exceed 10 minutes
3. Correlation: long duration + low tokens = stall?

If we see phases routinely hitting watchdog:
→ Investigate whether it's stalls or legitimately complex work
→ Tune watchdog threshold if needed
→ Do NOT build complex budget system unless evidence demands it
```

**Decision Criteria**:
- ✅ **Keep simple watchdog if**:
  - <5% of phases exceed watchdog
  - Long phases are legitimately complex (not stalls)
  - No budget enforcement needed

- ⚠️ **Add phase-level duration logging if**:
  - Need better visibility into what's slow
  - Dashboard shows duration per phase

- ❌ **Do NOT build complex time budget system unless**:
  - Evidence of systemic time budget issues (not yet observed)

**Review Timeline**: After 1 month of operation (December 2025)

**Reference**: GPT1 Tier 1 consensus, GPT2 "no heavy time-budget subsystem"

---

### 29. Chatbot_Project Integration Strategy

**What It Is**:
Keep chatbot_project as **donor only**, do NOT merge codebases.

**Consensus** (GPT1 + GPT2 + Claude):
- ✅ Extract useful patterns from chatbot_project (context ranking, risk scoring, UI components)
- ❌ Do NOT attempt full merge or shared codebase
- ❌ Do NOT adopt LangGraph, Qdrant, or heavy infrastructure from chatbot_project

**What We've Already Extracted**:
1. ✅ Context ranking heuristics (`_relevance_score`, `_recency_score`, `_type_priority_score`)
2. ✅ Risk scorer implementation (LOC delta, critical paths, test coverage, hygiene)
3. ✅ UI components (BudgetBar, RiskBadge concepts for dashboard)
4. ✅ Time watchdog (simple wall-clock guardrail)

**What We're NOT Extracting**:
- ❌ 35-agent architecture (Autopack has 2 agents: Builder + Auditor)
- ❌ 135 skills (Autopack uses learned rules instead)
- ❌ EARS SPEC format (too verbose for Autopack's needs)
- ❌ Full TRUST-5 framework (Autopack has thin quality gate instead)
- ❌ Heavy hook system (deferred to Phase 3 if needed)
- ❌ LangGraph orchestration (rejected for v1)
- ❌ Qdrant vector DB (rejected for v1)

**Review Timeline**: N/A - decision is final, chatbot_project remains separate

**Reference**: GPT1 + GPT2 Tier 1 unanimous consensus, "Keep chatbot_project as donor only; do not merge"

---

## Part 8: Review Schedule Summary

### Monthly Reviews (First 6 Months)

**December 2025** (Month 1):
- ✅ Review: Implementation status (this document)
- ✅ Review: Category distribution (after 50 phases)
- ✅ Review: Rate limiting threshold (#18)
- ✅ Review: Context selector implementation (#2)
- ✅ Review: Complexity-based context allocation (#10)

**January 2026** (Month 2):
- ✅ Review: Escalation rates by category (#4, #9, #17)
- ✅ Review: Cost breakdown and trends (#5, #3)
- ✅ Review: Category detection accuracy (#7)
- ✅ Review: Token budget enforcement approach (#3)
- ✅ Review: Dashboard needs (#11)

**February 2026** (Month 3):
- ✅ Review: Provider quota balancing needs (#7)
- ✅ Review: GPT-5 performance validation (#14)
- ✅ Review: Dual auditing extension (#5)
- ✅ Review: Shadow mode consideration (#1)
- ✅ Review: Primary model downgrading opportunities (#9)

**March 2026** (Month 4):
- ✅ Review: Quarterly deep dive on all metrics
- ✅ Review: Category auto-splitting needs (#6)
- ✅ Review: Dynamic escalation threshold tuning (#4)
- ✅ Review: System evolution and major changes

**April-May 2026** (Months 5-6):
- ✅ Review: Learned rules refinement (#8)
- ✅ Review: Automated rollback consideration (#12)
- ✅ Review: Pre-flight validation for destructive ops (#19)
- ✅ Review: Supply chain vetting process (#20)
- ✅ Review: Multi-repo support needs (#13)

**June 2026+** (6+ Months):
- ✅ Review: All deferred items for re-evaluation
- ✅ Review: New model availability (Opus 5, o3-mini, etc.)
- ✅ Review: System redesign considerations

---

## Part 8: Data Collection Implementation

### Integration Points

All data collection will be implemented in **Phase 2** via:

1. **Telemetry Database** (`src/autopack/telemetry.py`):
   - `PhaseMetrics` table
   - `QuotaIncident` table
   - `AuthEvent` table
   - `RateLimitEvent` table
   - `SecurityScanResult` table

2. **Collection Hooks**:
   - `LlmService.call()` → log phase metrics
   - `ModelRouter.select_model()` → log routing decisions
   - `main.py.verify_api_key()` → log auth events
   - `main.py rate limiter` → log rate limit hits
   - GitHub Actions workflows → log security scan results

3. **Report Generation**:
   - `scripts/generate_weekly_report.py` → auto-run weekly
   - `scripts/generate_monthly_deep_dive.py` → auto-run monthly
   - Manual review spreadsheets as needed

### Storage Requirements

Estimated storage per month:
- PhaseMetrics: ~100 phases × 1 KB = 100 KB
- QuotaIncidents: ~10 incidents × 0.5 KB = 5 KB
- AuthEvents: ~5000 requests × 0.2 KB = 1 MB
- RateLimitEvents: ~50 hits × 0.2 KB = 10 KB
- SecurityScanResults: ~30 scans × 10 KB = 300 KB

**Total**: ~1.5 MB/month (negligible)

Retention: 12 months (delete older data)

---

## Summary

### Total Deferred Items: 29

**By Priority**:
- **High Priority** (review in 1-3 months): #2, #3, #4, #5, #7, #14, #17, #18, #21, #22, #28
- **Medium Priority** (review in 3-6 months): #1, #6, #8, #9, #11, #15, #16, #19, #20, #23, #27
- **Low Priority** (review in 6+ months): #10, #12, #13, #24, #25
- **REJECTED** (do not implement): #26 (LangGraph/Qdrant), #29 (confirmed strategy)

**By Category**:
- Features requiring runtime data: 7 items (#1-7)
- Optimizations premature without data: 3 items (#8-10)
- Infrastructure enhancements: 3 items (#11-13)
- Model upgrades: 3 items (#14-16)
- Configuration tuning: 2 items (#17-18)
- Quality & safety enhancements: 2 items (#19-20)
- Chatbot_project integration items: 9 items (#21-29)

**Next Actions**:
1. ✅ **This document created** - comprehensive tracking established
2. ⏳ **Phase 2 Week 1**: Implement telemetry database and collection hooks
3. ⏳ **Phase 2 Week 2**: Set up auto-report generation and GitHub Actions workflow
4. ⏳ **Month 1 (December 2025)**: First review cycle after 50 phases run
5. ⏳ **Ongoing**: Use `docs/WEEKLY_REPORT_LATEST.md` for decision-making

---

**End of Future Considerations Tracking**
