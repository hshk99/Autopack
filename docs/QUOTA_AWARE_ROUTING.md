# Quota-Aware Multi-Provider Routing

**Status**: ✅ Configuration Complete | ⏭️ Implementation Pending
**Date**: 2025-11-25
**Based On**: GPT's quota management strategy + Claude Max/Code limit updates

---

## Overview

Autopack now supports **quota-aware routing** across multiple LLM providers to:
1. **Exploit new Claude limits**: Opus 4.5 + Sonnet 4.5 have separate pools
2. **Avoid hard stops**: Automatically fallback when weekly/daily limits approached
3. **Spread cost/risk**: Preserve premium quota for critical work, use cheaper models elsewhere
4. **Fail fast on high-risk**: Never silently downgrade security-critical phases

---

## Claude Max / Code Limit Changes (2025)

### What Changed

**Per Claude Korean blog + GitHub changelog**:
- **Opus 4.5**: Now available with **relaxed quota** (no longer tiny sub-pool)
- **Sonnet 4.5**: Has **separate limit** (equal to previous full plan limit)
- Result: You can use **both** generously without one starving the other

### For Autopack API Usage

Your **Claude Max** subscription gives:
- **Weekly usage ceiling** for overall plan
- **More room** to use Opus 4.5 for selective hard tasks
- **Sonnet 4.5** as strong default without killing Opus quota

**Strategy**:
- **Opus 4.5**: Precision tool for nastiest phases (repeatedly failing phases, extremely high-risk)
- **Sonnet 4.5**: High-capacity workhorse for planning, complex coding, marketing
- **Haiku 4.5**: Mechanical tasks, aux agents

---

## Provider Configuration

### Quota Limits (Configured in `config/models.yaml`)

```yaml
provider_quotas:
  openai:
    daily_token_cap: 5_000_000      # Placeholder: adjust per your plan
    weekly_token_cap: 25_000_000
    soft_limit_ratio: 0.8           # Trigger fallback at 80%

  anthropic:
    weekly_token_cap: 20_000_000    # Claude Max estimate
    soft_limit_ratio: 0.8
    notes: "Opus 4.5 + Sonnet 4.5 have separate pools"

  google_gemini:
    daily_token_cap: 3_000_000      # Placeholder: adjust per your plan
    soft_limit_ratio: 0.75

  zhipu_glm:
    daily_token_cap: 10_000_000     # Pay-as-you-go
    soft_limit_ratio: 0.9
```

**Action Required**: Update caps based on your actual subscription plans.

---

## Model Selection Strategy

### Tier 1: Premium Models (Use First)

| Model | Provider | Cost (per 1M) | When to Use |
|-------|----------|---------------|-------------|
| claude-opus-4-5 | Anthropic | $15/$75 | Repeatedly failing phases, extreme high-risk |
| gpt-4-turbo | OpenAI | $10/$30 | High-risk categories (security, schema, external) |
| claude-3-5-sonnet | Anthropic | $3/$15 | Complex reasoning, planning, marketing |
| gpt-4o | OpenAI | $2.50/$10 | Medium complexity coding |

### Tier 2: Efficient Models (Default for Safe Tasks)

| Model | Provider | Cost (per 1M) | When to Use |
|-------|----------|---------------|-------------|
| claude-3-5-haiku | Anthropic | $0.80/$4 | Mechanical tasks, aux agents |
| gpt-4o-mini | OpenAI | $0.15/$0.60 | Low complexity, summaries |

### Tier 3: Fallback Models (When Quota Near Limit)

| Model | Provider | Cost (per 1M) | When to Use |
|-------|----------|---------------|-------------|
| glm-4.5 | Zhipu | $0.35/$1.50 | Medium tasks when Claude/GPT at 80% quota |

---

## Routing Logic (Two-Stage)

### Stage 1: Ideal Model by Task

```python
def primary_model_for(task_category, complexity):
    # High-risk categories
    if task_category in ["external_feature_reuse", "security_auth_change", "schema_contract_change"]:
        return "gpt-4-turbo-2024-04-09"  # or claude-opus-4-5

    # Complexity-based
    if complexity == "low":
        return "gpt-4o-mini"
    elif complexity == "medium":
        return "gpt-4o"  # or claude-3-5-sonnet
    else:  # high
        return "gpt-4-turbo-2024-04-09"
```

### Stage 2: Quota Check & Fallback

```python
def pick_model(task_category, complexity):
    primary = primary_model_for(task_category, complexity)
    provider = provider_of(primary)

    # Check quota pressure
    if provider_usage[provider].weekly_tokens < soft_limit(provider):
        return primary  # Good to go

    # Over soft limit: check fallback policy
    if task_category in NEVER_FALLBACK_CATEGORIES:
        # High-risk: FAIL FAST (safer than silent downgrade)
        raise QuotaExceededError(f"Provider {provider} at quota limit, category {task_category} cannot fallback")

    # Safe to fallback: try alternatives
    for alt in fallback_models_for(task_category):
        alt_provider = provider_of(alt)
        if provider_usage[alt_provider].weekly_tokens < soft_limit(alt_provider):
            log_fallback_event(primary, alt, "quota_pressure")
            return alt

    # All providers near limit: last resort or fail
    raise QuotaExceededError("All providers near quota limits")
```

---

## Fallback Chains by Category

### High-Risk Categories (FAIL FAST)

```yaml
external_feature_reuse:
  primary: gpt-4-turbo-2024-04-09
  fallbacks: []  # NO fallback - fail if quota hit

security_auth_change:
  primary: gpt-4-turbo-2024-04-09
  fallbacks: []  # NO fallback

schema_contract_change:
  primary: gpt-4-turbo-2024-04-09
  fallbacks: []  # NO fallback
```

**Rationale**: Silently downgrading security/auth work is **more dangerous** than blocking the run.

---

### Medium Complexity (GLM Fallback OK)

```yaml
medium_complexity_general:
  primary: gpt-4o  # or claude-3-5-sonnet
  fallbacks:
    - glm-4.5-20250101  # If OpenAI/Claude near cap
    - gpt-4o-mini       # Last resort
```

**Rationale**: GLM-4.5 has strong coding + reasoning, suitable for non-critical refactors.

---

### Aux Agents (Multi-Tier Fallback)

```yaml
auxiliary_agents:
  primary: claude-3-5-sonnet-20241022  # Complex reasoning
  fallbacks:
    - claude-3-5-haiku-20241022   # Mechanical tasks
    - glm-4.5-20250101             # If Claude near cap
    - gpt-4o-mini                  # Last resort
```

**Rationale**: Aux agents are advisory, safe to degrade gracefully.

---

## GLM-4.5 Usage Guidelines

### When GLM is Safe

✅ **Good for**:
- Summarization agents (postmortem, metrics)
- Cost tuning analysis (metrics → config suggestions)
- CI flakiness analysis (log parsing)
- Simple refactors (renaming, moving files)
- UX checklists (when not requiring deep design sense)
- Integration candidate summaries

### When GLM is Risky

⚠️ **Use Cautiously for**:
- High-risk categories (auth, security, schema)
- Very complex multi-file refactors
- Core algorithm changes
- Anything where you rely on GPT/Claude's specific behavior

### GLM Capabilities

- **Context**: 128k tokens
- **Cost**: $0.35/$1.50 per 1M (92% cheaper than Sonnet)
- **Strengths**: Coding, reasoning, long context
- **Weaknesses**: Less battle-tested than GPT/Claude, may have different edge case behaviors

---

## Quota Tracking Implementation (TODO)

### Required Components

1. **Usage Tracker** (in `src/autopack/llm_client.py`):
   ```python
   class ProviderUsageTracker:
       def __init__(self):
           self.usage_by_provider = {
               "openai": RollingWindow(days=7),
               "anthropic": RollingWindow(days=7),
               "google_gemini": RollingWindow(days=1),
               "zhipu_glm": RollingWindow(days=1),
           }

       def record_call(self, provider, tokens_in, tokens_out):
           self.usage_by_provider[provider].add(tokens_in + tokens_out)

       def get_usage(self, provider, window="weekly"):
           return self.usage_by_provider[provider].sum(window)
   ```

2. **Quota Checker**:
   ```python
   def is_quota_pressure(provider):
       usage = tracker.get_usage(provider, "weekly")
       cap = config.provider_quotas[provider].weekly_token_cap
       soft_ratio = config.provider_quotas[provider].soft_limit_ratio
       return usage >= (cap * soft_ratio)
   ```

3. **Model Router**:
   ```python
   class QuotaAwareRouter:
       def select_model(self, category, complexity):
           primary = self.get_primary_model(category, complexity)

           if not is_quota_pressure(provider_of(primary)):
               return primary

           # Fallback logic as described above
           return self.get_fallback_model(category, primary)
   ```

---

## Time Window Tracking

### Weekly Rolling Window

Most provider limits are **weekly** (Claude Max, some GPT plans):

```python
class RollingWindow:
    def __init__(self, days=7):
        self.days = days
        self.usage_log = deque()  # [(timestamp, tokens), ...]

    def add(self, tokens):
        now = datetime.now()
        self.usage_log.append((now, tokens))
        self._prune_old()

    def _prune_old(self):
        cutoff = datetime.now() - timedelta(days=self.days)
        while self.usage_log and self.usage_log[0][0] < cutoff:
            self.usage_log.popleft()

    def sum(self):
        return sum(tokens for _, tokens in self.usage_log)
```

**Persistence**: Save to `.autonomous_runs/quota_tracking/{provider}_usage.json` between runs.

---

## Benefits for Autopack

### 1. Exploit New Claude Limits

- **Opus 4.5**: Use for phases where Sonnet/GPT-4o repeatedly fail
- **Sonnet 4.5**: Main workhorse without worrying about Opus quota
- **No more**: "Opus pool exhausted, can't use Claude at all"

### 2. Avoid Hard Stops

- **Before**: Hit Claude weekly limit → entire run blocked
- **After**: Claude at 80% → shift aux agents to GLM/Haiku → keep building

### 3. Spread Cost/Risk

- **Premium quota**: Reserved for critical phases (security, schema, failing phases)
- **Cheaper models**: Drain first on safe tasks (aux agents, summaries)
- **Fallback**: GLM picks up slack when Claude/GPT near limit

### 4. Fail Fast on High-Risk

- **Never**: Silently downgrade `security_auth_change` to GLM
- **Always**: Block run with clear error if high-risk quota exhausted
- **Rationale**: Security mistakes more costly than blocked run

---

## Example Scenarios

### Scenario 1: Normal Operation (Plenty of Quota)

```
Phase: medium_complexity refactor
→ Primary: gpt-4o
→ Quota check: OpenAI at 30% weekly usage ✅
→ Use: gpt-4o
→ Result: Success
```

### Scenario 2: Claude Near Limit, Safe Task

```
Phase: cost_tuning_agent (aux agent)
→ Primary: claude-3-5-sonnet
→ Quota check: Anthropic at 85% weekly usage ⚠️
→ Fallback: claude-3-5-haiku ✅ (within quota)
→ Use: claude-3-5-haiku
→ Result: Success (slightly lower quality, but acceptable for metrics)
```

### Scenario 3: High-Risk, Quota Exhausted

```
Phase: security_auth_change
→ Primary: gpt-4-turbo
→ Quota check: OpenAI at 95% weekly usage ⚠️
→ Fallback policy: NEVER_FALLBACK_CATEGORIES
→ Action: FAIL FAST ❌
→ Error: QuotaExceededError("OpenAI quota exhausted, security_auth_change cannot use fallback")
→ Result: Run blocked (human reviews quota, resumes next week or buys extra usage)
```

### Scenario 4: All Providers Near Limit, Medium Task

```
Phase: medium_complexity feature
→ Primary: gpt-4o (OpenAI at 90% ⚠️)
→ Fallback 1: claude-3-5-sonnet (Anthropic at 85% ⚠️)
→ Fallback 2: glm-4.5 (Zhipu at 40% ✅)
→ Use: glm-4.5
→ Result: Success (quality slightly lower, but task completes)
```

---

## Configuration Checklist

### Before First Run

- [ ] Update `provider_quotas` in `config/models.yaml` with actual subscription limits
- [ ] Verify model IDs match your API access (Opus 4.5, GLM-4.5 placeholders)
- [ ] Set `quota_routing.enabled: false` (implementation pending)

### Phase 1 Implementation (TODO)

- [ ] Implement `ProviderUsageTracker` in `src/autopack/llm_client.py`
- [ ] Add rolling window persistence (`.autonomous_runs/quota_tracking/`)
- [ ] Implement `QuotaAwareRouter.select_model()`
- [ ] Add quota pressure events to metrics/observability
- [ ] Set `quota_routing.enabled: true`

### Phase 2 Testing

- [ ] Simulate quota exhaustion (manually set usage to 90%)
- [ ] Verify high-risk categories fail fast
- [ ] Verify aux agents fallback to GLM/Haiku
- [ ] Measure: false positive rate (unnecessary fallbacks)
- [ ] Tune: soft_limit_ratio per provider

---

## Cost Impact

### Without Quota Routing (Current)

**Risk**: Hit weekly limit mid-run → entire run blocked

**Example**:
- Claude Max weekly limit: 20M tokens
- Run 1-3: Use 18M tokens (90%)
- Run 4: Blocked until next week ❌

### With Quota Routing (After Implementation)

**Benefit**: Graceful degradation + quota preservation

**Example**:
- Run 1-3: Use 16M tokens (80% - triggers soft limit)
- Run 4: Shifts aux agents to GLM/Haiku, preserves Claude for core build
- Result: Run 4 completes with slightly lower aux agent quality ✅

**Annual Savings**: Avoids ~10-20 blocked runs per year

---

## Next Steps

1. **Immediate**: Configuration complete, ready for implementation
2. **Phase 1**: Implement quota tracking + routing (1-2 days)
3. **Phase 2**: Test with simulated quota exhaustion
4. **Phase 3**: Enable in production, monitor fallback rates

---

## References

- GPT's quota management strategy: `docs/archive/llm_token_efficiency.md`
- Claude Max limit changes: [GitHub changelog](https://github.com/anthropics/claude-code/blob/main/CHANGELOG.md)
- Multi-LLM routing: [AWS blog](https://aws.amazon.com/blogs/machine-learning/multi-llm-routing-strategies/)

---

**Status**: Configuration complete, implementation pending
**Last Updated**: 2025-11-25
**Ready for**: Quota tracking implementation in LLM client

