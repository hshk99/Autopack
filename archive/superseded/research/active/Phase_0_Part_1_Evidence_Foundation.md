# Phase 0 Part 1: Evidence Foundation

**Status**: 🚧 Ready for Implementation
**Estimated Effort**: 20-30 hours
**Timeline**: Week 1, Days 1-3
**Build ID**: BUILD-034
**Depends On**: None (first part)
**Enables**: Part 2 (GitHub Discovery & Analysis)

---

## Executive Summary

Build the **Evidence-First Architecture** foundation that prevents citation laundering (CI-1 - the #1 trust failure identified by all 3 GPT reviewers). This is the critical showstopper fix that must work before proceeding to Parts 2-3.

**Core Principle**: Every finding MUST have a verifiable quote from its source. No quote → no finding.

**Success Criteria**:
- ✅ `Finding.validate()` catches missing or invalid `extraction_span`
- ✅ `FindingVerifier.verify_finding()` detects fabricated quotes
- ✅ Hash verification prevents span tampering
- ✅ All unit tests pass (10-15 tests)
- ✅ Manual smoke test: LLM cannot bypass quote requirement

**STOP/GO Gate**: If validation fails → abort Phase 0 or simplify to curated registry approach

---

## Background & Rationale

### The Citation Laundering Problem (CI-1)

In the v2.1 implementation plan, the `Finding` dataclass had an **Optional extraction_span**:

```python
# v2.1 (VULNERABLE):
@dataclass
class Finding:
    source_url: str
    extraction_span: Optional[str] = None  # ❌ Can be None!
```

This allowed LLMs to:
1. Generate a claim: "Market size is $500M annually"
2. Attach a plausible URL: `https://example.com/market-report`
3. Set `extraction_span = None` (perfectly legal!)
4. System validates: ✅ Has URL ✅ Has timestamp → PASSES
5. **Reality**: The URL doesn't contain that claim, but system can't detect it

**All 3 GPT reviewers** independently identified this as the **#1 trust failure mode** that would make research outputs unverifiable.

### Why This Matters

Without evidence binding:
- Strategic GO/NO-GO decisions made on hallucinated "facts"
- No way to verify claims (which defeats the purpose of autonomous research)
- Audit trail is theater (citations don't prove anything)
- Competitors can game the system via prompt injection

### The Fix: REQUIRED Extraction Span

```python
# Phase 0 (ENFORCED):
@dataclass
class Finding:
    source_url: str
    extracted_at: datetime
    extraction_span: str  # ✅ REQUIRED (min 20 chars)
    extraction_span_hash: str  # SHA-256 for verification
```

**Key Insight**: The quote IS the evidence. If the LLM can't extract a quote, the finding isn't valid.

---

## Implementation Specification

### 1. Directory Structure

```
src/autopack/research/
├── __init__.py
├── models/
│   ├── __init__.py
│   ├── evidence.py          # Finding dataclass + VerificationResult
│   └── validators.py        # FindingVerifier
└── tests/
    ├── __init__.py
    ├── test_finding_validation.py
    └── test_finding_verification.py
```

### 2. Core Components

#### 2.1 Finding Dataclass (`src/autopack/research/models/evidence.py`)

**Purpose**: Represents a single piece of evidence extracted from a source

**Required Fields**:
```python
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Tuple
import hashlib
import re


@dataclass
class Finding:
    """
    A single piece of evidence extracted from a source.

    CRITICAL CONSTRAINT: extraction_span is REQUIRED (not Optional).
    This prevents LLMs from fabricating claims without quotes.

    Example:
        Finding(
            category="market_intelligence",
            title="GitHub Star Growth Rate",
            content="File organization tools on GitHub show 15-20% annual growth in stars",
            source_url="https://github.com/search?q=file+organization",
            extracted_at=datetime.now(timezone.utc),
            extraction_span="file organization repositories grew from 1,234 to 1,456 stars (15% growth)",
            extraction_span_hash="a3f2...",
            relevance_score=8,
            recency_score=9,
            trust_score=3
        )
    """

    # Content
    category: str  # e.g., "market_intelligence", "competitive_analysis", "technical_analysis"
    title: str  # Brief title (5-10 words)
    content: str  # Extracted finding (1-3 sentences)

    # Evidence (ALL REQUIRED)
    source_url: str  # Full URL of source
    extracted_at: datetime  # UTC timestamp
    extraction_span: str  # ✅ REQUIRED: Quoted text from source (min 20 chars)
    extraction_span_hash: str  # SHA-256 of normalized extraction_span

    # Optional: character offsets for precise location
    char_offsets: Optional[Tuple[int, int]] = None

    # Scoring (0-10)
    relevance_score: int  # How relevant to research goal
    recency_score: int  # How recent (10 = this week, 0 = >1 year old)
    trust_score: int  # Source trust tier (0-3: Unverified, Community, Credible, Authoritative)

    def validate(self) -> None:
        """
        Validate finding meets all requirements.

        Raises:
            ValueError: If any field is invalid
        """
        # Check 1: source_url exists and is not empty
        if not self.source_url:
            raise ValueError("Finding must have source_url")

        # Check 2: extracted_at exists
        if not self.extracted_at:
            raise ValueError("Finding must have extracted_at")

        # Check 3: extraction_span exists and meets minimum length
        if not self.extraction_span:
            raise ValueError("Finding must have extraction_span (cannot be None or empty)")

        if len(self.extraction_span) < 20:
            raise ValueError(f"extraction_span too short: {len(self.extraction_span)} chars (min 20)")

        # Check 4: hash matches
        expected_hash = self._compute_hash(self.extraction_span)
        if self.extraction_span_hash != expected_hash:
            raise ValueError("extraction_span_hash mismatch (possible tampering)")

        # Check 5: scores are in valid range
        if not (0 <= self.relevance_score <= 10):
            raise ValueError(f"relevance_score out of range: {self.relevance_score} (must be 0-10)")

        if not (0 <= self.recency_score <= 10):
            raise ValueError(f"recency_score out of range: {self.recency_score} (must be 0-10)")

        if not (0 <= self.trust_score <= 3):
            raise ValueError(f"trust_score out of range: {self.trust_score} (must be 0-3)")

    @staticmethod
    def _compute_hash(span: str) -> str:
        """
        Compute SHA-256 hash of normalized span.

        Normalization:
        - Strip leading/trailing whitespace
        - Collapse multiple spaces to single space
        - UTF-8 encoding

        Args:
            span: Text to hash

        Returns:
            Hexadecimal hash string
        """
        normalized = re.sub(r'\s+', ' ', span.strip())
        return hashlib.sha256(normalized.encode('utf-8')).hexdigest()

    @classmethod
    def create_with_hash(cls, extraction_span: str, **kwargs):
        """
        Factory method that auto-computes hash.

        Example:
            finding = Finding.create_with_hash(
                category="market_intelligence",
                title="GitHub Growth",
                content="...",
                source_url="...",
                extracted_at=datetime.now(timezone.utc),
                extraction_span="Quoted text from source...",
                relevance_score=8,
                recency_score=9,
                trust_score=3
            )
        """
        hash_value = cls._compute_hash(extraction_span)
        return cls(extraction_span=extraction_span, extraction_span_hash=hash_value, **kwargs)


@dataclass
class VerificationResult:
    """Result of verifying a Finding against its source content."""

    valid: bool  # True if verification passed
    reason: str  # Explanation (e.g., "All checks passed" or "extraction_span not found in source")
    confidence: float = 1.0  # Confidence in result (0.0-1.0)
```

#### 2.2 FindingVerifier (`src/autopack/research/models/validators.py`)

**Purpose**: Verify that findings are actually supported by source content

```python
import hashlib
import re
from typing import Optional

from .evidence import Finding, VerificationResult


class FindingVerifier:
    """
    Verifies that findings are actually supported by sources.

    This is the CRITICAL defense against citation laundering.
    """

    def __init__(self):
        pass

    async def verify_finding(self, finding: Finding, source_content: str) -> VerificationResult:
        """
        Verify that finding is supported by source content.

        Checks:
        1. extraction_span appears in source_content
        2. extraction_span_hash matches computed hash
        3. If numeric claim, extracted number matches span

        Args:
            finding: Finding to verify
            source_content: Raw HTML/text from source URL

        Returns:
            VerificationResult with validation status
        """

        # Check 1: Quote appears in source
        normalized_content = self._normalize_text(source_content)
        normalized_span = self._normalize_text(finding.extraction_span)

        if normalized_span not in normalized_content:
            return VerificationResult(
                valid=False,
                reason="extraction_span not found in source content",
                confidence=1.0
            )

        # Check 2: Hash matches
        expected_hash = hashlib.sha256(normalized_span.encode('utf-8')).hexdigest()
        if finding.extraction_span_hash != expected_hash:
            return VerificationResult(
                valid=False,
                reason="extraction_span_hash mismatch (possible tampering)",
                confidence=1.0
            )

        # Check 3: If numeric claim, validate extraction
        if finding.category in ["market_intelligence", "competitive_analysis"]:
            numeric_valid = self._verify_numeric_extraction(finding, normalized_span)
            if not numeric_valid:
                return VerificationResult(
                    valid=False,
                    reason="numeric claim does not match extraction_span",
                    confidence=0.9  # Slightly lower confidence (could be edge case)
                )

        return VerificationResult(valid=True, reason="All checks passed", confidence=1.0)

    def _normalize_text(self, text: str) -> str:
        """
        Normalize text for comparison.

        - Strip leading/trailing whitespace
        - Collapse multiple spaces to single space
        - Lowercase (for case-insensitive matching)
        """
        normalized = re.sub(r'\s+', ' ', text.strip())
        return normalized.lower()

    def _verify_numeric_extraction(self, finding: Finding, normalized_span: str) -> bool:
        """
        Verify that numeric claims match extraction_span.

        Example:
            content: "Market size is $500M"
            extraction_span: "the market is valued at approximately $500 million"
            → VALID (500M matches $500 million)

        Args:
            finding: Finding with numeric content
            normalized_span: Normalized extraction_span

        Returns:
            True if numeric claims are consistent
        """
        # Extract numbers from content
        content_numbers = re.findall(r'\d+(?:\.\d+)?', finding.content)

        # Extract numbers from span
        span_numbers = re.findall(r'\d+(?:\.\d+)?', normalized_span)

        if not content_numbers:
            # No numbers in content → no verification needed
            return True

        # Check that at least one number from content appears in span
        for num in content_numbers:
            if num in span_numbers:
                return True

        # No matching numbers found
        return False
```

### 3. Test Suite

#### 3.1 Test Finding Validation (`tests/test_finding_validation.py`)

```python
import pytest
from datetime import datetime, timezone
from autopack.research.models.evidence import Finding


class TestFindingValidation:
    """Test Finding dataclass validation."""

    def test_valid_finding(self):
        """Test that a valid finding passes validation."""
        finding = Finding.create_with_hash(
            category="market_intelligence",
            title="Test Finding",
            content="This is a test finding",
            source_url="https://example.com/test",
            extracted_at=datetime.now(timezone.utc),
            extraction_span="This is a quoted span from the source document that is long enough",
            relevance_score=8,
            recency_score=9,
            trust_score=3
        )

        # Should not raise
        finding.validate()

    def test_missing_extraction_span_fails(self):
        """Test that missing extraction_span raises ValueError."""
        with pytest.raises(ValueError, match="must have extraction_span"):
            finding = Finding(
                category="market_intelligence",
                title="Test",
                content="Test",
                source_url="https://example.com",
                extracted_at=datetime.now(timezone.utc),
                extraction_span="",  # ❌ Empty
                extraction_span_hash="fake",
                relevance_score=5,
                recency_score=5,
                trust_score=1
            )
            finding.validate()

    def test_short_extraction_span_fails(self):
        """Test that extraction_span < 20 chars raises ValueError."""
        with pytest.raises(ValueError, match="extraction_span too short"):
            finding = Finding.create_with_hash(
                category="market_intelligence",
                title="Test",
                content="Test",
                source_url="https://example.com",
                extracted_at=datetime.now(timezone.utc),
                extraction_span="Too short",  # ❌ Only 9 chars
                relevance_score=5,
                recency_score=5,
                trust_score=1
            )
            finding.validate()

    def test_hash_mismatch_fails(self):
        """Test that tampered hash raises ValueError."""
        finding = Finding(
            category="market_intelligence",
            title="Test",
            content="Test",
            source_url="https://example.com",
            extracted_at=datetime.now(timezone.utc),
            extraction_span="This is a valid span that is long enough to pass length check",
            extraction_span_hash="WRONG_HASH",  # ❌ Tampered
            relevance_score=5,
            recency_score=5,
            trust_score=1
        )

        with pytest.raises(ValueError, match="hash mismatch"):
            finding.validate()

    def test_invalid_scores_fail(self):
        """Test that invalid scores raise ValueError."""
        # Test relevance_score > 10
        with pytest.raises(ValueError, match="relevance_score out of range"):
            finding = Finding.create_with_hash(
                category="market_intelligence",
                title="Test",
                content="Test",
                source_url="https://example.com",
                extracted_at=datetime.now(timezone.utc),
                extraction_span="This is a valid extraction span",
                relevance_score=15,  # ❌ > 10
                recency_score=5,
                trust_score=1
            )
            finding.validate()

        # Test trust_score > 3
        with pytest.raises(ValueError, match="trust_score out of range"):
            finding = Finding.create_with_hash(
                category="market_intelligence",
                title="Test",
                content="Test",
                source_url="https://example.com",
                extracted_at=datetime.now(timezone.utc),
                extraction_span="This is a valid extraction span",
                relevance_score=5,
                recency_score=5,
                trust_score=5  # ❌ > 3
            )
            finding.validate()

    def test_create_with_hash_computes_correct_hash(self):
        """Test that create_with_hash factory method computes correct hash."""
        span = "This is a test extraction span from the source"
        finding = Finding.create_with_hash(
            category="market_intelligence",
            title="Test",
            content="Test",
            source_url="https://example.com",
            extracted_at=datetime.now(timezone.utc),
            extraction_span=span,
            relevance_score=5,
            recency_score=5,
            trust_score=1
        )

        # Manually compute expected hash
        import hashlib
        import re
        normalized = re.sub(r'\s+', ' ', span.strip())
        expected_hash = hashlib.sha256(normalized.encode('utf-8')).hexdigest()

        assert finding.extraction_span_hash == expected_hash
```

#### 3.2 Test Finding Verification (`tests/test_finding_verification.py`)

```python
import pytest
from datetime import datetime, timezone
from autopack.research.models.evidence import Finding
from autopack.research.models.validators import FindingVerifier


class TestFindingVerification:
    """Test FindingVerifier citation validation."""

    @pytest.fixture
    def verifier(self):
        return FindingVerifier()

    @pytest.mark.asyncio
    async def test_valid_finding_passes(self, verifier):
        """Test that a finding with valid quote passes verification."""
        source_content = """
        This is a test document about file organization.
        File organization tools on GitHub show 15-20% annual growth in stars.
        The market for productivity tools continues to expand.
        """

        finding = Finding.create_with_hash(
            category="market_intelligence",
            title="GitHub Growth",
            content="File organization tools show strong growth",
            source_url="https://example.com/test",
            extracted_at=datetime.now(timezone.utc),
            extraction_span="File organization tools on GitHub show 15-20% annual growth in stars",
            relevance_score=8,
            recency_score=9,
            trust_score=2
        )

        result = await verifier.verify_finding(finding, source_content)

        assert result.valid is True
        assert result.reason == "All checks passed"
        assert result.confidence == 1.0

    @pytest.mark.asyncio
    async def test_fabricated_quote_fails(self, verifier):
        """Test that a fabricated quote fails verification."""
        source_content = """
        This is a test document about file organization.
        File organization is important for productivity.
        """

        finding = Finding.create_with_hash(
            category="market_intelligence",
            title="Fake Finding",
            content="Market size is $500M",
            source_url="https://example.com/test",
            extracted_at=datetime.now(timezone.utc),
            extraction_span="The market size is estimated at $500 million annually",  # ❌ NOT in source!
            relevance_score=8,
            recency_score=9,
            trust_score=2
        )

        result = await verifier.verify_finding(finding, source_content)

        assert result.valid is False
        assert "not found in source" in result.reason
        assert result.confidence == 1.0

    @pytest.mark.asyncio
    async def test_case_insensitive_matching(self, verifier):
        """Test that quote matching is case-insensitive."""
        source_content = "FILE ORGANIZATION TOOLS ON GITHUB SHOW 15-20% ANNUAL GROWTH."

        finding = Finding.create_with_hash(
            category="market_intelligence",
            title="Growth",
            content="Growth rate is 15-20%",
            source_url="https://example.com/test",
            extracted_at=datetime.now(timezone.utc),
            extraction_span="file organization tools on github show 15-20% annual growth",  # Lowercase
            relevance_score=8,
            recency_score=9,
            trust_score=2
        )

        result = await verifier.verify_finding(finding, source_content)

        assert result.valid is True

    @pytest.mark.asyncio
    async def test_numeric_claim_mismatch_fails(self, verifier):
        """Test that mismatched numeric claims fail verification."""
        source_content = "The market grew by 5% last year."

        finding = Finding.create_with_hash(
            category="market_intelligence",
            title="Growth",
            content="Market grew by 15%",  # ❌ Says 15%, but span says 5%
            source_url="https://example.com/test",
            extracted_at=datetime.now(timezone.utc),
            extraction_span="the market grew by 5% last year",
            relevance_score=8,
            recency_score=9,
            trust_score=2
        )

        result = await verifier.verify_finding(finding, source_content)

        assert result.valid is False
        assert "numeric claim does not match" in result.reason
```

### 4. Manual Smoke Test

After all unit tests pass, perform this manual smoke test:

```python
# scripts/smoke_test_evidence.py

from datetime import datetime, timezone
from autopack.research.models.evidence import Finding
from autopack.research.models.validators import FindingVerifier


def smoke_test_citation_laundering():
    """
    Smoke test: Can LLM bypass quote requirement?

    This simulates the citation laundering attack:
    - LLM generates a claim
    - LLM attaches a plausible URL
    - LLM tries to skip extraction_span

    Expected: System rejects the finding
    """

    print("=== Smoke Test: Citation Laundering Attack ===\n")

    # Attack 1: Missing extraction_span
    print("[Attack 1] Missing extraction_span")
    try:
        finding = Finding(
            category="market_intelligence",
            title="Fake Market Size",
            content="Market size is $500M annually",
            source_url="https://example.com/market-report",
            extracted_at=datetime.now(timezone.utc),
            extraction_span="",  # ❌ Empty
            extraction_span_hash="fake",
            relevance_score=8,
            recency_score=9,
            trust_score=2
        )
        finding.validate()
        print("  ❌ FAILED: Attack succeeded (finding accepted)")
    except ValueError as e:
        print(f"  ✅ BLOCKED: {e}")

    # Attack 2: Short extraction_span
    print("\n[Attack 2] Too-short extraction_span")
    try:
        finding = Finding.create_with_hash(
            category="market_intelligence",
            title="Fake Market Size",
            content="Market size is $500M annually",
            source_url="https://example.com/market-report",
            extracted_at=datetime.now(timezone.utc),
            extraction_span="$500M",  # ❌ Only 5 chars
            relevance_score=8,
            recency_score=9,
            trust_score=2
        )
        finding.validate()
        print("  ❌ FAILED: Attack succeeded (finding accepted)")
    except ValueError as e:
        print(f"  ✅ BLOCKED: {e}")

    # Attack 3: Fabricated quote
    print("\n[Attack 3] Fabricated quote (not in source)")

    async def test_fabricated():
        source_content = "This page has nothing about market size."

        finding = Finding.create_with_hash(
            category="market_intelligence",
            title="Fake Market Size",
            content="Market size is $500M annually",
            source_url="https://example.com/market-report",
            extracted_at=datetime.now(timezone.utc),
            extraction_span="The market is estimated at $500 million annually",  # ❌ NOT in source
            relevance_score=8,
            recency_score=9,
            trust_score=2
        )

        verifier = FindingVerifier()
        result = await verifier.verify_finding(finding, source_content)

        if result.valid:
            print("  ❌ FAILED: Attack succeeded (finding accepted)")
        else:
            print(f"  ✅ BLOCKED: {result.reason}")

    import asyncio
    asyncio.run(test_fabricated())

    print("\n=== Smoke Test Complete ===")


if __name__ == "__main__":
    smoke_test_citation_laundering()
```

**Expected Output**:
```
=== Smoke Test: Citation Laundering Attack ===

[Attack 1] Missing extraction_span
  ✅ BLOCKED: Finding must have extraction_span (cannot be None or empty)

[Attack 2] Too-short extraction_span
  ✅ BLOCKED: extraction_span too short: 5 chars (min 20)

[Attack 3] Fabricated quote (not in source)
  ✅ BLOCKED: extraction_span not found in source content

=== Smoke Test Complete ===
```

---

## STOP/GO Validation Gate

After completing implementation and tests, evaluate:

### ✅ GO Criteria (Proceed to Part 2)

- [ ] All 10-15 unit tests pass
- [ ] Smoke test blocks all 3 attack vectors
- [ ] `Finding.validate()` enforces extraction_span requirement
- [ ] `FindingVerifier` correctly detects fabricated quotes
- [ ] Hash verification prevents tampering
- [ ] Code review complete (no obvious bypasses)

### ❌ STOP Criteria (Abort or Simplify)

If ANY of these occur:
- [ ] Cannot reliably detect fabricated quotes (false positive rate >5%)
- [ ] LLM can bypass quote requirement (attack succeeds in smoke test)
- [ ] Hash verification has exploitable weakness
- [ ] Implementation takes >40 hours (1.5× estimate → scope creep)

**If STOP**: Abort Phase 0, pivot to curated registry approach (120-150 hours, simpler)

---

## Implementation Checklist

- [ ] Create directory structure (`src/autopack/research/models/`)
- [ ] Implement `Finding` dataclass with REQUIRED extraction_span
- [ ] Implement `VerificationResult` dataclass
- [ ] Implement `FindingVerifier` class
- [ ] Write 10-15 unit tests
- [ ] All tests pass
- [ ] Create and run smoke test
- [ ] Code review (check for bypasses)
- [ ] Document findings in BUILD_HISTORY.md
- [ ] **STOP/GO Decision**: Proceed to Part 2?

---

## Related Documentation

- **Decision**: [DEC-011](../../docs/ARCHITECTURE_DECISIONS.md#DEC-011) - Evidence-First Architecture
- **Build**: [BUILD-034](../../docs/BUILD_HISTORY.md#BUILD-034) - Phase 0 Research System
- **Debug**: [DBG-003](../../docs/DEBUG_LOG.md#DBG-003) - Planning Cycle Diminishing Returns
- **Analysis**: `C:\Users\hshk9\.claude\plans\sunny-booping-seahorse.md`
- **GPT Feedback**: `C:\Users\hshk9\OneDrive\Backup\Desktop\ref4.md` (CI-1 identified by all 3 GPTs)

---

## Next Steps

**If GO**: Proceed to [Phase_0_Part_2_GitHub_Discovery_And_Analysis.md](./Phase_0_Part_2_GitHub_Discovery_And_Analysis.md)

**If STOP**: Create fallback implementation spec for curated registry approach
