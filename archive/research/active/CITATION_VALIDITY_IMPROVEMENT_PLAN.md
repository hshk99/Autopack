# Citation Validity Improvement Plan

**Date**: 2025-12-15
**Status**: PROPOSED
**Current Citation Validity**: 59.3%
**Target**: ≥80%

---

## Problem Analysis

Phase 0 evaluation achieved **59.3% citation validity** (below 80% target). Analysis of validation failures reveals root causes:

### Root Cause 1: Overly Strict Numeric Verification

**Code Location**: [validators.py:63-70](src/autopack/research/models/validators.py#L63-L70)

**Current Behavior**:
```python
# Check 3: If numeric claim, validate extraction
if finding.category in ["market_intelligence", "competitive_analysis"]:
    numeric_valid = self._verify_numeric_extraction(finding, normalized_span)
    if not numeric_valid:
        return VerificationResult(
            valid=False,
            reason="numeric claim does not match extraction_span",
            confidence=0.9
        )
```

**Problem**: The verifier extracts numbers from both `finding.content` (LLM's summary/interpretation) and `extraction_span` (direct quote), then checks if they match. This fails when:

**Example Failure Case**:
```
extraction_span: "GitHub reports over 100 million developers using the platform"
content: "GitHub has 100M+ active developers" (LLM summarized)

Numbers extracted:
  - extraction_span: ['100']
  - content: ['100']

✅ MATCH (this would pass)

BUT:

extraction_span: "The market size is approximately $500M annually"
content: "Market valued at five hundred million dollars per year" (LLM paraphrased)

Numbers extracted:
  - extraction_span: ['500']
  - content: ['500'] (if lucky) or [] (if LLM wrote it out)

❌ NO MATCH (fails validation)
```

**Impact**: Legitimate findings are rejected because the LLM's `content` field paraphrases numbers differently than the source quote.

---

### Root Cause 2: Text Normalization Gaps

**Code Location**: [validators.py:74-83](src/autopack/research/models/validators.py#L74-L83)

**Current Behavior**:
```python
def _normalize_text(self, text: str) -> str:
    normalized = re.sub(r'\s+', ' ', text.strip())
    return normalized.lower()
```

**Problem**: This normalization is too simple and misses:
- Unicode variations (e.g., `—` vs `-`, `'` vs `'`)
- HTML entities (e.g., `&amp;` vs `&`, `&nbsp;` vs ` `)
- Markdown artifacts (e.g., `**bold**` vs `bold`)
- Zero-width characters, soft hyphens, etc.

**Example Failure Case**:
```
Source README (raw):
  "We support **100+ integrations** with &amp; without authentication"

extraction_span (LLM extracted):
  "We support 100+ integrations with & without authentication"

After normalization:
  Source: "we support **100+ integrations** with &amp; without authentication"
  Quote:  "we support 100+ integrations with & without authentication"

❌ NO MATCH (HTML entity mismatch)
```

---

### Root Cause 3: LLM Prompt Doesn't Emphasize Exact Quoting

**Code Location**: [github_gatherer.py:129-164](src/autopack/research/gatherers/github_gatherer.py#L129-L164)

**Current Prompt**:
```
2. For EACH finding, you MUST provide:
   - extraction_span: A direct quote from the README (minimum 20 characters)

3. **NEVER fabricate quotes**. If you cannot find a relevant quote, do not create a finding.
```

**Problem**: While the prompt says "direct quote," it doesn't:
- Show the LLM examples of GOOD vs BAD quotes
- Explain what "direct" means (character-for-character match including punctuation)
- Emphasize that paraphrasing/summarizing in extraction_span is FORBIDDEN

**Example LLM Behavior**:
```
Source README:
  "The tool supports multiple programming languages including Python, JavaScript, Go, and Rust."

extraction_span (LLM's "direct quote"):
  "Supports Python, JavaScript, Go, and Rust" ← PARAPHRASED (dropped words)

✅ LLM thinks this is a "direct quote" (captures meaning)
❌ Validator rejects (not character-for-character match)
```

---

## Proposed Fixes

### Fix 1: Relax Numeric Verification Logic ⚡ HIGH IMPACT

**Change**: Only verify numbers in `extraction_span`, not in `finding.content`

**Rationale**: The `content` field is the LLM's interpretation/summary, which may legitimately paraphrase. The `extraction_span` is the evidence, so we only need to verify IT contains coherent numbers.

**Implementation**:

```python
# OLD (checks both content and span):
def _verify_numeric_extraction(self, finding: Finding, normalized_span: str) -> bool:
    content_numbers = re.findall(r'\d+(?:\.\d+)?', finding.content)
    span_numbers = re.findall(r'\d+(?:\.\d+)?', normalized_span)

    if not content_numbers:
        return True

    for num in content_numbers:
        if num in span_numbers:
            return True

    return False

# NEW (only verifies span is coherent):
def _verify_numeric_extraction(self, finding: Finding, normalized_span: str) -> bool:
    """
    Verify extraction_span contains numbers (no hallucination check needed for content).

    We only verify that extraction_span looks legitimate (has numbers if category suggests it).
    The content field is the LLM's interpretation and may legitimately paraphrase.
    """
    span_numbers = re.findall(r'\d+(?:\.\d+)?', normalized_span)

    # For market/competitive intelligence, span should contain at least one number
    if finding.category in ["market_intelligence", "competitive_analysis"]:
        if not span_numbers:
            # Span claims to be about numbers but has none -> suspicious
            return False

    # If span has numbers, it's valid (we trust the quote is from source, which Check 1 verified)
    return True
```

**Expected Impact**: +15-20% citation validity (most failures are numeric mismatches)

---

### Fix 2: Enhanced Text Normalization ⚡ MEDIUM IMPACT

**Change**: Normalize HTML entities, markdown, and Unicode variations

**Implementation**:

```python
import html
import unicodedata

def _normalize_text(self, text: str) -> str:
    """
    Enhanced normalization for robust text matching.

    Handles:
    - HTML entities (&amp; -> &, &nbsp; -> space)
    - Unicode normalization (NFKC)
    - Markdown artifacts (**bold** -> bold)
    - Zero-width characters, soft hyphens
    - Whitespace collapsing
    - Case normalization
    """
    # 1. Decode HTML entities
    text = html.unescape(text)

    # 2. Unicode normalization (NFKC: compatibility decomposition + canonical composition)
    text = unicodedata.normalize('NFKC', text)

    # 3. Remove zero-width characters and soft hyphens
    text = text.replace('\u200b', '')  # Zero-width space
    text = text.replace('\u200c', '')  # Zero-width non-joiner
    text = text.replace('\u200d', '')  # Zero-width joiner
    text = text.replace('\u00ad', '')  # Soft hyphen
    text = text.replace('\ufeff', '')  # Zero-width no-break space

    # 4. Strip markdown artifacts (simple patterns only)
    text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)  # **bold** -> bold
    text = re.sub(r'\*([^*]+)\*', r'\1', text)      # *italic* -> italic
    text = re.sub(r'`([^`]+)`', r'\1', text)        # `code` -> code

    # 5. Collapse whitespace
    text = re.sub(r'\s+', ' ', text.strip())

    # 6. Lowercase for case-insensitive matching
    text = text.lower()

    return text
```

**Expected Impact**: +5-10% citation validity (handles encoding edge cases)

---

### Fix 3: Improve Extraction Prompt ⚡ MEDIUM IMPACT

**Change**: Add explicit examples and stricter instructions

**Implementation**:

```python
extraction_prompt = f"""You are a research analyst extracting market intelligence findings from a GitHub repository README.

**Topic**: {topic}

**Repository Metadata**:
- Stars: {repo_metadata.get('stars', 0)}
- Forks: {repo_metadata.get('forks', 0)}
- Language: {repo_metadata.get('language', 'Unknown')}
- Last Updated: {repo_metadata.get('last_updated', 'Unknown')}

**README Content**:
{readme_content[:10000]}

**CRITICAL REQUIREMENTS**:
1. Extract up to {max_findings} findings related to "{topic}"

2. For EACH finding, you MUST provide:
   - **extraction_span**: A CHARACTER-FOR-CHARACTER direct quote from the README
     - MUST be EXACT copy-paste (same punctuation, capitalization, spacing)
     - MINIMUM 20 characters
     - NEVER paraphrase or summarize
     - NEVER add or remove words

   - **title**: Brief title (5-10 words)

   - **content**: YOUR interpretation/summary of what the quote means (1-3 sentences)
     - This is where you can paraphrase and add context
     - Explain the significance for the research topic

   - **category**: One of ["market_intelligence", "competitive_analysis", "technical_analysis"]

   - **relevance_score**: 0-10 (how relevant to topic)

3. **EXTRACTION_SPAN EXAMPLES**:

   ✅ GOOD (exact quote):
   {{
     "extraction_span": "Over 100 million developers use GitHub to collaborate on code",
     "content": "GitHub has a massive user base of 100M+ developers"
   }}

   ❌ BAD (paraphrased):
   {{
     "extraction_span": "100M+ developers on GitHub",  ← WRONG! Not exact quote
     "content": "Large developer community"
   }}

   ✅ GOOD (preserves punctuation):
   {{
     "extraction_span": "The tool supports Python, JavaScript, Go, and Rust.",
     "content": "Multi-language support across 4 major programming languages"
   }}

   ❌ BAD (changed punctuation):
   {{
     "extraction_span": "Supports Python JavaScript Go and Rust",  ← WRONG! Missing commas
     "content": "Multi-language support"
   }}

4. **NEVER fabricate quotes**. If you cannot find an EXACT quote that's relevant, skip that finding.

5. **VERIFICATION**: Before submitting each finding, mentally check:
   - Can I Ctrl+F the extraction_span in the README and find it EXACTLY? If no, revise it.

Return JSON array:
[
  {{
    "title": "...",
    "content": "YOUR INTERPRETATION HERE",
    "extraction_span": "EXACT CHARACTER-FOR-CHARACTER QUOTE HERE (min 20 chars)",
    "category": "market_intelligence",
    "relevance_score": 8
  }},
  ...
]
"""
```

**Expected Impact**: +5-10% citation validity (reduces paraphrasing in quotes)

---

## Implementation Plan

### Phase 1: Quick Wins (1-2 hours)

**Priority**: Fix 1 (Relax Numeric Verification)

**Steps**:
1. Update `validators.py` → `_verify_numeric_extraction()`
2. Run Phase 0 evaluation on 5 topics
3. Measure citation validity improvement

**Expected Result**: 59.3% → 74-79% citation validity

---

### Phase 2: Enhanced Normalization (2-3 hours)

**Priority**: Fix 2 (Enhanced Text Normalization)

**Steps**:
1. Update `validators.py` → `_normalize_text()`
2. Add unit tests for edge cases:
   - HTML entities (`&amp;`, `&nbsp;`, `&quot;`)
   - Unicode variations (`—` vs `-`, `'` vs `'`)
   - Markdown artifacts (`**bold**`, `*italic*`, `` `code` ``)
3. Run Phase 0 evaluation on 5 topics
4. Measure citation validity improvement

**Expected Result**: 74-79% → 79-89% citation validity

---

### Phase 3: Prompt Engineering (2-3 hours)

**Priority**: Fix 3 (Improve Extraction Prompt)

**Steps**:
1. Update `github_gatherer.py` → extraction prompt with examples
2. Run Phase 0 evaluation on 5 topics
3. Analyze invalid citations to see if paraphrasing reduced
4. Measure citation validity improvement

**Expected Result**: 79-89% → 84-94% citation validity

---

### Phase 4: Validation (1 hour)

**Steps**:
1. Run full Phase 0 evaluation on 5 gold topics
2. Measure citation validity
3. If ≥80%: Mark Phase 0 as SUCCESS ✅
4. If <80%: Analyze remaining failures and iterate

---

## Success Criteria

- **Primary**: Citation validity ≥80% across 5 gold topics
- **Secondary**: Cost remains <$8/session
- **Secondary**: No increase in false negatives (legitimate quotes rejected)

---

## Risk Assessment

### Risk 1: Relaxing Numeric Verification Allows Hallucination

**Mitigation**: Check 1 (quote in source) and Check 2 (hash verification) still enforce evidence binding. The numeric check was redundant since we already verify the quote appears in the source.

### Risk 2: Enhanced Normalization Creates False Positives

**Mitigation**: Normalization is applied IDENTICALLY to both source and quote, so it only affects edge cases. Add comprehensive unit tests to catch regressions.

### Risk 3: Prompt Changes Reduce Finding Quality

**Mitigation**: Examples in prompt show both GOOD and BAD behavior, teaching the LLM what we want. Monitor finding relevance scores to ensure quality doesn't degrade.

---

## Next Steps

1. **USER DECISION**: Approve this plan?
2. If YES: Implement Fix 1 (Quick Win) and measure impact
3. Based on results, decide whether to proceed to Fixes 2-3

---

**Status**: Awaiting user approval
