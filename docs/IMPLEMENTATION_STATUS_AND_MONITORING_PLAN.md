# Implementation Status and Monitoring Plan

**Date**: November 26, 2025
**Context**: Post-category splitting implementation - tracking what's complete vs what requires monitoring

---

## Executive Summary

### Implementation Status: **Configuration Complete, Runtime Implementation Pending**

- ✅ **Phase 1a Complete**: Category splitting configuration in `models.yaml`
- ✅ **Phase 1b Complete**: API security (authentication, rate limiting)
- ✅ **Phase 1c Complete**: CI/CD security scanning pipeline
- ⏳ **Phase 2 Pending**: ModelRouter code to execute routing strategies
- ⏳ **Monitoring Setup**: Progress reports and telemetry (this document)

---

## Part 1: Implementation Status Checklist

### ✅ COMPLETED - Configuration Layer

#### 1. Category Splitting in `models.yaml`
**Status**: ✅ **COMPLETE**
**Date Completed**: November 26, 2025
**Location**: `config/models.yaml` lines 15-98

**What Was Done**:
```yaml
# Added 8 fine-grained categories with routing strategies:
- security_auth_change (best_first)
- external_feature_reuse_remote (best_first)
- schema_contract_change_destructive (best_first)
- external_feature_reuse_internal (progressive)
- schema_contract_change_additive (progressive)
- core_backend_high (progressive)
- docs (cheap_first)
- tests (cheap_first)
```

**Evidence**: Committed in "feat: implement category splitting & routing strategies (100% consensus)"

**No Monitoring Required**: This is pure configuration, not runtime behavior.

---

#### 2. Quota Enforcement Settings
**Status**: ✅ **COMPLETE**
**Date Completed**: November 26, 2025
**Location**: `config/models.yaml` lines 125-138

**What Was Done**:
```yaml
quota_enforcement:
  best_first_block_on_exhaustion: true
  progressive_block_on_exhaustion: true
  cheap_first_allow_downgrade: false
  on_quota_exhaustion: "raise_incident"
  never_fallback_categories:
    - security_auth_change
    - external_feature_reuse_remote
    - schema_contract_change_destructive
```

**Evidence**: Configuration added but NOT yet enforced by code.

**⚠️ MONITORING REQUIRED**: See "Part 2: Runtime Monitoring Required" below.

---

#### 3. API Authentication (AUTOPACK_API_KEY)
**Status**: ✅ **COMPLETE**
**Date Completed**: November 26, 2025
**Location**: `src/autopack/main.py` lines 15-35 (approx)

**What Was Done**:
- Added `verify_api_key()` function with X-API-Key header check
- Protected `/runs/start` endpoint with `dependencies=[Depends(verify_api_key)]`
- Created `.env.example` with generation instructions

**Evidence**: Committed in earlier security implementation phase.

**⚠️ MONITORING REQUIRED**: Auth rejection rate, false positives (see Part 2).

---

#### 4. Rate Limiting
**Status**: ✅ **COMPLETE**
**Date Completed**: November 26, 2025
**Location**: `src/autopack/main.py`

**What Was Done**:
- Added `slowapi` dependency
- Configured `@limiter.limit("10/minute")` on `/runs/start`
- Added rate limit exceeded handler

**Evidence**: Added to requirements.txt, integrated into main.py.

**⚠️ MONITORING REQUIRED**: Rate limit trigger frequency (see Part 2).

---

#### 5. CI/CD Security Pipeline
**Status**: ✅ **COMPLETE**
**Date Completed**: November 26, 2025
**Location**: `.github/workflows/security.yml`, `.github/dependabot.yml`

**What Was Done**:
- Safety + Trivy dependency scanning (daily)
- Trivy container scanning
- Gitleaks secret scanning
- CodeQL static analysis
- Dependabot auto-updates (weekly)

**Evidence**: Workflow files committed and in place.

**⚠️ MONITORING REQUIRED**: Scan results, false positive rate (see Part 2).

---

### ⏳ PENDING - Runtime Implementation

#### 6. ModelRouter Routing Strategy Execution
**Status**: ⏳ **NOT IMPLEMENTED**
**Target**: Phase 2 (Next 1-2 weeks)
**Location**: `src/autopack/model_router.py` (to be modified)

**What Needs to Be Done**:
```python
class RoutingStrategy(Enum):
    BEST_FIRST = "best_first"
    PROGRESSIVE = "progressive"
    CHEAP_FIRST = "cheap_first"

class ModelRouter:
    def select_model(
        self,
        category: str,
        complexity: str,
        attempt_num: int,
        role: str,
    ) -> str:
        """Select model based on routing strategy."""

        # 1. Check for routing policy
        policy = self.config.get("llm_routing_policies", {}).get(category)

        if policy:
            return self._apply_routing_strategy(policy, attempt_num, role)

        # 2. Fallback to legacy complexity-based
        return self._select_by_complexity(complexity, role)

    def _apply_routing_strategy(
        self,
        policy: Dict,
        attempt_num: int,
        role: str,
    ) -> str:
        """Apply routing strategy logic."""
        strategy = policy.get("strategy")

        if strategy == "best_first":
            # Always use primary, no escalation
            return policy.get(f"{role}_primary")

        elif strategy in ["progressive", "cheap_first"]:
            # Check escalation threshold
            escalate_config = policy.get("escalate_to", {})
            after_attempts = escalate_config.get("after_attempts", 999)

            if attempt_num >= after_attempts:
                return escalate_config.get(role)
            else:
                return policy.get(f"{role}_primary")
```

**Why Not Implemented Yet**: Configuration first, then runtime behavior. This is explicit Phase 2 work.

**⚠️ CRITICAL MONITORING REQUIRED**: This is THE key monitoring item - see Part 2.

---

#### 7. Category Detection Heuristics
**Status**: ⏳ **NOT IMPLEMENTED**
**Target**: Month 2
**Location**: `src/autopack/category_detector.py` (new file)

**What Needs to Be Done**:
```python
def detect_category(phase_spec: Dict) -> str:
    """Detect category from phase description and context."""
    description = phase_spec["description"].lower()
    files_changed = phase_spec.get("files_changed", [])

    # Security keywords
    if any(kw in description for kw in ["auth", "security", "permission", "oauth"]):
        return "security_auth_change"

    # Schema operations
    if "schema" in description or "migration" in description:
        if any(kw in description for kw in ["drop", "delete", "remove"]):
            return "schema_contract_change_destructive"
        else:
            return "schema_contract_change_additive"

    # External code
    if "external" in description or "library" in description:
        if any(kw in description for kw in ["github", "npm", "pypi"]):
            return "external_feature_reuse_remote"
        else:
            return "external_feature_reuse_internal"

    # Fallback
    return "core_backend_high"
```

**Why Not Implemented Yet**: Need actual phase data to validate heuristics.

**⚠️ CRITICAL MONITORING REQUIRED**: Accuracy of category detection (see Part 2).

---

#### 8. QuotaBlockError Exception Handling
**Status**: ⏳ **NOT IMPLEMENTED**
**Target**: Phase 2 (with ModelRouter enhancement)
**Location**: `src/autopack/model_router.py` (to be added)

**What Needs to Be Done**:
```python
class QuotaBlockError(Exception):
    """Raised when quota exhausted for never_fallback_categories."""
    pass

def select_model(self, category: str, ...) -> str:
    policy = self.config.get("llm_routing_policies", {}).get(category)

    if not policy:
        return self._select_by_complexity(complexity, role)

    # Check quota before selecting
    provider = self._get_provider_for_model(policy[f"{role}_primary"])

    if self._is_quota_exhausted(provider):
        enforcement = self.config.get("quota_enforcement", {})
        never_fallback = enforcement.get("never_fallback_categories", [])

        if category in never_fallback:
            raise QuotaBlockError(
                f"Quota exhausted for {provider}, cannot run {category} phase"
            )
```

**Why Not Implemented Yet**: Depends on ModelRouter enhancement.

**⚠️ MONITORING REQUIRED**: Frequency of quota exhaustion incidents (see Part 2).

---

#### 9. Dashboard Integration
**Status**: ⏳ **NOT IMPLEMENTED**
**Target**: Month 2
**Location**: Chatbot project dashboard (separate repo)

**What Needs to Be Done**:
- Category distribution chart
- Routing strategy breakdown
- Escalation frequency tracking
- Quota exhaustion incidents
- Cost by category

**Why Not Implemented Yet**: Need telemetry data first.

**⚠️ MONITORING REQUIRED**: Dashboard usage patterns (see Part 2).

---

## Part 2: Runtime Monitoring Required

### Critical Monitoring Item #1: Category Distribution

**What to Monitor**:
```
How many phases fall into each category?

Expected distribution:
- security_auth_change: <5%
- external_feature_reuse_remote: <2%
- schema_contract_change_destructive: <3%
- external_feature_reuse_internal: ~5%
- schema_contract_change_additive: ~10%
- core_backend_high: ~30%
- docs: ~20%
- tests: ~25%
```

**Why This Matters**:
- If security_auth_change is >10%, category is too broad
- If external_feature_reuse_remote is >5%, supply chain risk is high
- If most phases are "core_backend_high", detection heuristics are failing

**Decision Criteria**:
- ✅ Distribution matches expectations → keep current categories
- ⚠️ High-risk categories >10% → need to split further
- ❌ Most phases uncategorized → improve detection heuristics

**Review Timeline**: After 50 phases run (or 2 weeks, whichever comes first)

**Data Collection Method**:
```python
# Add to LlmService or ModelRouter
def log_category_usage(phase_id: str, category: str):
    # Write to telemetry DB or log file
    telemetry.record({
        "timestamp": datetime.utcnow(),
        "phase_id": phase_id,
        "category": category,
        "detected_or_explicit": "explicit" if "task_category" in phase_spec else "detected"
    })
```

---

### Critical Monitoring Item #2: Model Escalation Frequency

**What to Monitor**:
```
How often do progressive/cheap_first strategies escalate?

Expected escalation rates:
- external_feature_reuse_internal: ~20% (after_attempts: 2)
- schema_contract_change_additive: ~30% (after_attempts: 1)
- core_backend_high: ~15% (after_attempts: 2)
- docs: ~5% (after_attempts: 3)
- tests: ~10% (after_attempts: 2)
```

**Why This Matters**:
- If escalation >50% for a category, primary model is too weak
- If escalation <5% for a category, we're overpaying for primary model
- If escalation happens on attempt 1, we should switch to best_first

**Decision Criteria**:
- ✅ Escalation 10-30% → primary model is well-tuned
- ⚠️ Escalation >50% → upgrade primary model
- ⚠️ Escalation <5% → downgrade primary model (if non-security)
- ❌ Escalation >80% → switch to best_first

**Review Timeline**: After 100 phases run (or 1 month, whichever comes first)

**Data Collection Method**:
```python
def log_escalation(phase_id: str, category: str, from_model: str, to_model: str, attempt_num: int):
    telemetry.record({
        "timestamp": datetime.utcnow(),
        "phase_id": phase_id,
        "category": category,
        "from_model": from_model,
        "to_model": to_model,
        "attempt_num": attempt_num,
        "reason": "escalation_threshold_reached"
    })
```

---

### Critical Monitoring Item #3: Category Detection Accuracy

**What to Monitor**:
```
Manual review of detected categories for accuracy.

Sample size: 50 random phases
Review questions:
1. Was the category detected correctly?
2. If not, what category should it have been?
3. What keywords/patterns were missed?
```

**Why This Matters**:
- False negatives (security work classified as general) = security risk
- False positives (general work classified as security) = cost waste
- Accuracy <90% means detection heuristics need improvement

**Decision Criteria**:
- ✅ Accuracy >90% → keep current heuristics
- ⚠️ Accuracy 70-90% → refine keyword lists
- ❌ Accuracy <70% → redesign detection logic

**Review Timeline**: After 50 phases run, then monthly

**Data Collection Method**:
```python
# Generate review spreadsheet
def generate_category_review_report(phase_count: int = 50):
    """Export random sample for manual review."""
    phases = db.query(Phase).order_by(func.random()).limit(phase_count).all()

    csv_data = []
    for phase in phases:
        csv_data.append({
            "phase_id": phase.id,
            "description": phase.description,
            "detected_category": phase.category,
            "files_changed": phase.files_changed,
            "correct?": "",  # Manual review field
            "should_be": "",  # Manual review field
            "notes": ""  # Manual review field
        })

    return csv_data
```

---

### Critical Monitoring Item #4: Quota Exhaustion Incidents

**What to Monitor**:
```
Frequency and context of quota blocks.

Expected incidents:
- Total: 0 incidents/week (with current quotas)
- If incidents occur: which provider? which category?
```

**Why This Matters**:
- Quota blocks on security categories = critical incident
- Frequent quota blocks = need higher quotas or better rate limiting
- Blocks during low-usage periods = bug in quota tracking

**Decision Criteria**:
- ✅ Zero incidents → quotas are sufficient
- ⚠️ 1-2 incidents/month → acceptable, monitor trend
- ❌ Weekly incidents → increase quotas or reduce usage

**Review Timeline**: Weekly review, immediate alert on incident

**Data Collection Method**:
```python
def log_quota_incident(category: str, provider: str, phase_id: str):
    """Log quota exhaustion incident."""
    incident = {
        "timestamp": datetime.utcnow(),
        "severity": "CRITICAL" if category in NEVER_FALLBACK else "WARNING",
        "category": category,
        "provider": provider,
        "phase_id": phase_id,
        "weekly_usage": get_weekly_token_usage(provider),
        "quota_limit": get_quota_limit(provider)
    }

    # Write to incidents DB and alert
    db.add(QuotaIncident(**incident))

    if incident["severity"] == "CRITICAL":
        send_alert(incident)  # Email/Slack notification
```

---

### Critical Monitoring Item #5: Cost by Category

**What to Monitor**:
```
Token spend breakdown by category.

Expected cost distribution (weekly):
- security_auth_change: ~10% (best_first, rare)
- external_feature_reuse_remote: ~5% (best_first, very rare)
- schema_contract_change_destructive: ~8% (best_first, rare)
- external_feature_reuse_internal: ~8% (progressive)
- schema_contract_change_additive: ~12% (progressive)
- core_backend_high: ~40% (progressive, common)
- docs: ~5% (cheap_first)
- tests: ~12% (cheap_first)
```

**Why This Matters**:
- If security categories >30% of spend, they're too common
- If any single category >50% of spend, investigate why
- If escalation cost is high, primary models are too weak

**Decision Criteria**:
- ✅ Best_first categories <25% of spend → acceptable
- ⚠️ Best_first categories 25-40% → investigate frequency
- ❌ Best_first categories >40% → categories too broad or overused

**Review Timeline**: Weekly cost review, monthly deep dive

**Data Collection Method**:
```python
def calculate_cost_by_category(start_date: datetime, end_date: datetime):
    """Calculate token spend by category."""
    phases = db.query(Phase).filter(
        Phase.created_at.between(start_date, end_date)
    ).all()

    cost_breakdown = defaultdict(lambda: {"tokens": 0, "cost_usd": 0})

    for phase in phases:
        category = phase.category

        # Sum builder + auditor tokens
        total_tokens = (
            phase.builder_input_tokens + phase.builder_output_tokens +
            phase.auditor_input_tokens + phase.auditor_output_tokens
        )

        # Calculate cost (model-specific pricing)
        cost = calculate_token_cost(phase.builder_model, phase.auditor_model, total_tokens)

        cost_breakdown[category]["tokens"] += total_tokens
        cost_breakdown[category]["cost_usd"] += cost

    return cost_breakdown
```

---

### Critical Monitoring Item #6: API Authentication Behavior

**What to Monitor**:
```
API key auth rejection rate and patterns.

Expected metrics:
- Rejection rate: 0% (all requests have valid keys)
- If rejections occur: legitimate traffic or attacks?
```

**Why This Matters**:
- High rejection rate with legitimate users = UX issue
- Attack patterns = need additional security (IP whitelist, etc.)
- Zero rejections = auth is working correctly

**Decision Criteria**:
- ✅ Zero rejections or <1% false positives → working correctly
- ⚠️ 1-5% rejections → investigate if legitimate or attacks
- ❌ >5% rejections → auth config issue or active attack

**Review Timeline**: Weekly review, immediate alert on >10 rejections/hour

**Data Collection Method**:
```python
def log_auth_event(request: Request, success: bool, reason: str = None):
    """Log authentication attempts."""
    telemetry.record({
        "timestamp": datetime.utcnow(),
        "ip": request.client.host,
        "endpoint": request.url.path,
        "success": success,
        "reason": reason,  # "invalid_key", "missing_key", "success"
        "user_agent": request.headers.get("user-agent")
    })
```

---

### Critical Monitoring Item #7: Rate Limiting Triggers

**What to Monitor**:
```
Frequency of rate limit hits (10 runs/minute).

Expected metrics:
- Rate limit hits: 0-1/day (normal usage)
- If frequent hits: legitimate bursts or abuse?
```

**Why This Matters**:
- Frequent rate limits with legitimate usage = limit too low
- Rate limit abuse = need stricter limits or IP blocking
- Zero hits = limit is appropriate

**Decision Criteria**:
- ✅ 0-2 hits/week with legitimate users → working correctly
- ⚠️ Daily hits with legitimate users → increase to 20/minute
- ❌ Constant hits from single IP → potential abuse, block IP

**Review Timeline**: Weekly review, immediate alert on >5 hits/hour from single IP

**Data Collection Method**:
```python
def log_rate_limit_event(request: Request):
    """Log rate limit exceeded events."""
    telemetry.record({
        "timestamp": datetime.utcnow(),
        "ip": request.client.host,
        "endpoint": request.url.path,
        "current_rate": get_current_rate(request.client.host),
        "limit": "10/minute"
    })
```

---

### Critical Monitoring Item #8: Security Scan Results

**What to Monitor**:
```
Results from CI/CD security scanning pipeline.

Expected results:
- Critical vulnerabilities: 0
- High vulnerabilities: 0-2 (acceptable if patches unavailable)
- False positives: <10% of total alerts
```

**Why This Matters**:
- Critical vulnerabilities in production = immediate risk
- High false positive rate = alert fatigue
- Unpatched vulnerabilities = dependency update failures

**Decision Criteria**:
- ✅ Zero critical, <3 high → acceptable
- ⚠️ 1 critical or >5 high → investigate and patch
- ❌ Multiple criticals or unpatched for >1 week → escalate

**Review Timeline**: Daily automated scan, weekly manual review

**Data Collection Method**:
```python
# Parse GitHub Actions security.yml outputs
def parse_security_scan_results(workflow_run_id: str):
    """Parse Trivy/Safety/CodeQL results."""
    results = {
        "trivy_filesystem": parse_trivy_output("fs"),
        "trivy_container": parse_trivy_output("container"),
        "safety": parse_safety_output(),
        "codeql": parse_codeql_output(),
        "gitleaks": parse_gitleaks_output()
    }

    # Aggregate by severity
    summary = {
        "critical": sum(r["critical"] for r in results.values()),
        "high": sum(r["high"] for r in results.values()),
        "medium": sum(r["medium"] for r in results.values()),
        "low": sum(r["low"] for r in results.values())
    }

    return summary
```

---

## Part 3: Auto-Updated Progress Reports

### Telemetry Database Schema

**Location**: `src/autopack/telemetry.py` (new file)

**Schema**:
```python
# models/telemetry.py
from sqlalchemy import Column, Integer, String, Float, DateTime, JSON
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

class PhaseMetrics(Base):
    __tablename__ = "phase_metrics"

    id = Column(Integer, primary_key=True)
    phase_id = Column(String, index=True)
    category = Column(String, index=True)
    category_source = Column(String)  # "explicit" or "detected"

    builder_model = Column(String)
    auditor_model = Column(String)
    builder_attempts = Column(Integer)
    auditor_attempts = Column(Integer)
    escalated = Column(Boolean, default=False)

    builder_input_tokens = Column(Integer)
    builder_output_tokens = Column(Integer)
    auditor_input_tokens = Column(Integer)
    auditor_output_tokens = Column(Integer)

    cost_usd = Column(Float)
    duration_seconds = Column(Float)

    created_at = Column(DateTime, default=datetime.utcnow)

class QuotaIncident(Base):
    __tablename__ = "quota_incidents"

    id = Column(Integer, primary_key=True)
    severity = Column(String)  # "CRITICAL" or "WARNING"
    category = Column(String, index=True)
    provider = Column(String)
    phase_id = Column(String)

    weekly_usage_tokens = Column(Integer)
    quota_limit_tokens = Column(Integer)

    created_at = Column(DateTime, default=datetime.utcnow)

class AuthEvent(Base):
    __tablename__ = "auth_events"

    id = Column(Integer, primary_key=True)
    ip = Column(String, index=True)
    endpoint = Column(String)
    success = Column(Boolean)
    reason = Column(String)  # "invalid_key", "missing_key", "success"

    created_at = Column(DateTime, default=datetime.utcnow)

class RateLimitEvent(Base):
    __tablename__ = "rate_limit_events"

    id = Column(Integer, primary_key=True)
    ip = Column(String, index=True)
    endpoint = Column(String)
    current_rate = Column(Integer)
    limit_per_minute = Column(Integer, default=10)

    created_at = Column(DateTime, default=datetime.utcnow)

class SecurityScanResult(Base):
    __tablename__ = "security_scan_results"

    id = Column(Integer, primary_key=True)
    scan_type = Column(String)  # "trivy_fs", "trivy_container", "safety", "codeql", "gitleaks"

    critical_count = Column(Integer)
    high_count = Column(Integer)
    medium_count = Column(Integer)
    low_count = Column(Integer)

    details = Column(JSON)  # Full scan output

    created_at = Column(DateTime, default=datetime.utcnow)
```

---

### Weekly Progress Report Generator

**Location**: `scripts/generate_weekly_report.py` (new file)

**Auto-Run**: GitHub Actions weekly cron job

**Report Sections**:
```python
#!/usr/bin/env python3
"""Generate weekly monitoring report."""

import sys
from datetime import datetime, timedelta
from sqlalchemy import create_engine, func
from models.telemetry import PhaseMetrics, QuotaIncident, AuthEvent, RateLimitEvent, SecurityScanResult

def generate_weekly_report():
    """Generate comprehensive weekly monitoring report."""
    engine = create_engine(os.getenv("DATABASE_URL"))
    Session = sessionmaker(bind=engine)
    db = Session()

    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=7)

    report = {
        "period": f"{start_date.date()} to {end_date.date()}",
        "category_distribution": get_category_distribution(db, start_date, end_date),
        "escalation_rates": get_escalation_rates(db, start_date, end_date),
        "cost_breakdown": get_cost_breakdown(db, start_date, end_date),
        "quota_incidents": get_quota_incidents(db, start_date, end_date),
        "auth_metrics": get_auth_metrics(db, start_date, end_date),
        "rate_limit_metrics": get_rate_limit_metrics(db, start_date, end_date),
        "security_scan_summary": get_security_scan_summary(db, start_date, end_date)
    }

    # Write to markdown file
    write_report_markdown(report, "docs/WEEKLY_REPORT_LATEST.md")

    # Archive with date
    write_report_markdown(report, f"docs/reports/WEEKLY_REPORT_{end_date.strftime('%Y%m%d')}.md")

    db.close()
    return report

def get_category_distribution(db, start_date, end_date):
    """Get phase count by category."""
    results = db.query(
        PhaseMetrics.category,
        func.count(PhaseMetrics.id).label("count")
    ).filter(
        PhaseMetrics.created_at.between(start_date, end_date)
    ).group_by(
        PhaseMetrics.category
    ).all()

    total = sum(r.count for r in results)

    return [
        {
            "category": r.category,
            "count": r.count,
            "percentage": round(r.count / total * 100, 1) if total > 0 else 0
        }
        for r in results
    ]

def get_escalation_rates(db, start_date, end_date):
    """Get escalation frequency by category."""
    results = db.query(
        PhaseMetrics.category,
        func.count(PhaseMetrics.id).label("total"),
        func.sum(func.cast(PhaseMetrics.escalated, Integer)).label("escalated")
    ).filter(
        PhaseMetrics.created_at.between(start_date, end_date)
    ).group_by(
        PhaseMetrics.category
    ).all()

    return [
        {
            "category": r.category,
            "total": r.total,
            "escalated": r.escalated or 0,
            "escalation_rate": round((r.escalated or 0) / r.total * 100, 1) if r.total > 0 else 0
        }
        for r in results
    ]

def get_cost_breakdown(db, start_date, end_date):
    """Get cost by category."""
    results = db.query(
        PhaseMetrics.category,
        func.sum(PhaseMetrics.cost_usd).label("total_cost"),
        func.sum(
            PhaseMetrics.builder_input_tokens +
            PhaseMetrics.builder_output_tokens +
            PhaseMetrics.auditor_input_tokens +
            PhaseMetrics.auditor_output_tokens
        ).label("total_tokens")
    ).filter(
        PhaseMetrics.created_at.between(start_date, end_date)
    ).group_by(
        PhaseMetrics.category
    ).all()

    total_cost = sum(r.total_cost or 0 for r in results)

    return [
        {
            "category": r.category,
            "total_cost_usd": round(r.total_cost or 0, 2),
            "total_tokens": r.total_tokens or 0,
            "percentage_of_spend": round((r.total_cost or 0) / total_cost * 100, 1) if total_cost > 0 else 0
        }
        for r in results
    ]

def get_quota_incidents(db, start_date, end_date):
    """Get quota exhaustion incidents."""
    incidents = db.query(QuotaIncident).filter(
        QuotaIncident.created_at.between(start_date, end_date)
    ).order_by(QuotaIncident.created_at.desc()).all()

    return [
        {
            "timestamp": i.created_at.isoformat(),
            "severity": i.severity,
            "category": i.category,
            "provider": i.provider,
            "usage_vs_quota": f"{i.weekly_usage_tokens}/{i.quota_limit_tokens}"
        }
        for i in incidents
    ]

def get_auth_metrics(db, start_date, end_date):
    """Get authentication metrics."""
    total = db.query(func.count(AuthEvent.id)).filter(
        AuthEvent.created_at.between(start_date, end_date)
    ).scalar()

    failures = db.query(func.count(AuthEvent.id)).filter(
        AuthEvent.created_at.between(start_date, end_date),
        AuthEvent.success == False
    ).scalar()

    return {
        "total_requests": total,
        "failed_auth": failures,
        "failure_rate": round(failures / total * 100, 1) if total > 0 else 0
    }

def get_rate_limit_metrics(db, start_date, end_date):
    """Get rate limiting metrics."""
    total_hits = db.query(func.count(RateLimitEvent.id)).filter(
        RateLimitEvent.created_at.between(start_date, end_date)
    ).scalar()

    unique_ips = db.query(func.count(func.distinct(RateLimitEvent.ip))).filter(
        RateLimitEvent.created_at.between(start_date, end_date)
    ).scalar()

    return {
        "total_rate_limit_hits": total_hits,
        "unique_ips_affected": unique_ips
    }

def get_security_scan_summary(db, start_date, end_date):
    """Get latest security scan results."""
    latest_scans = {}

    for scan_type in ["trivy_fs", "trivy_container", "safety", "codeql", "gitleaks"]:
        latest = db.query(SecurityScanResult).filter(
            SecurityScanResult.scan_type == scan_type,
            SecurityScanResult.created_at.between(start_date, end_date)
        ).order_by(SecurityScanResult.created_at.desc()).first()

        if latest:
            latest_scans[scan_type] = {
                "critical": latest.critical_count,
                "high": latest.high_count,
                "medium": latest.medium_count,
                "low": latest.low_count,
                "scan_date": latest.created_at.isoformat()
            }

    return latest_scans

def write_report_markdown(report, filename):
    """Write report to markdown file."""
    with open(filename, "w") as f:
        f.write(f"# Autopack Weekly Monitoring Report\n\n")
        f.write(f"**Period**: {report['period']}\n\n")
        f.write(f"**Generated**: {datetime.utcnow().isoformat()}\n\n")

        f.write("---\n\n")

        # Category Distribution
        f.write("## 1. Category Distribution\n\n")
        f.write("| Category | Count | Percentage |\n")
        f.write("|----------|-------|------------|\n")
        for item in report["category_distribution"]:
            f.write(f"| {item['category']} | {item['count']} | {item['percentage']}% |\n")
        f.write("\n")

        # Escalation Rates
        f.write("## 2. Escalation Rates\n\n")
        f.write("| Category | Total | Escalated | Rate |\n")
        f.write("|----------|-------|-----------|------|\n")
        for item in report["escalation_rates"]:
            f.write(f"| {item['category']} | {item['total']} | {item['escalated']} | {item['escalation_rate']}% |\n")
        f.write("\n")

        # Cost Breakdown
        f.write("## 3. Cost Breakdown\n\n")
        f.write("| Category | Cost (USD) | Tokens | % of Spend |\n")
        f.write("|----------|------------|--------|------------|\n")
        for item in report["cost_breakdown"]:
            f.write(f"| {item['category']} | ${item['total_cost_usd']} | {item['total_tokens']:,} | {item['percentage_of_spend']}% |\n")
        f.write("\n")

        # Quota Incidents
        f.write("## 4. Quota Incidents\n\n")
        if report["quota_incidents"]:
            f.write("| Timestamp | Severity | Category | Provider | Usage/Quota |\n")
            f.write("|-----------|----------|----------|----------|-------------|\n")
            for item in report["quota_incidents"]:
                f.write(f"| {item['timestamp']} | {item['severity']} | {item['category']} | {item['provider']} | {item['usage_vs_quota']} |\n")
        else:
            f.write("✅ No quota incidents this week.\n")
        f.write("\n")

        # Auth Metrics
        f.write("## 5. Authentication Metrics\n\n")
        f.write(f"- Total requests: {report['auth_metrics']['total_requests']}\n")
        f.write(f"- Failed auth: {report['auth_metrics']['failed_auth']}\n")
        f.write(f"- Failure rate: {report['auth_metrics']['failure_rate']}%\n\n")

        # Rate Limit Metrics
        f.write("## 6. Rate Limiting Metrics\n\n")
        f.write(f"- Total rate limit hits: {report['rate_limit_metrics']['total_rate_limit_hits']}\n")
        f.write(f"- Unique IPs affected: {report['rate_limit_metrics']['unique_ips_affected']}\n\n")

        # Security Scan Summary
        f.write("## 7. Security Scan Summary\n\n")
        for scan_type, results in report["security_scan_summary"].items():
            f.write(f"### {scan_type}\n")
            f.write(f"- Critical: {results['critical']}\n")
            f.write(f"- High: {results['high']}\n")
            f.write(f"- Medium: {results['medium']}\n")
            f.write(f"- Low: {results['low']}\n")
            f.write(f"- Last scan: {results['scan_date']}\n\n")

if __name__ == "__main__":
    generate_weekly_report()
```

---

### GitHub Actions Workflow for Auto-Reports

**Location**: `.github/workflows/weekly-report.yml` (new file)

```yaml
name: Generate Weekly Monitoring Report

on:
  schedule:
    - cron: '0 9 * * MON'  # Every Monday at 9 AM UTC
  workflow_dispatch:  # Allow manual trigger

jobs:
  generate-report:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          pip install -r requirements.txt

      - name: Generate report
        env:
          DATABASE_URL: ${{ secrets.DATABASE_URL }}
        run: |
          python scripts/generate_weekly_report.py

      - name: Commit report
        run: |
          git config --global user.name "github-actions[bot]"
          git config --global user.email "github-actions[bot]@users.noreply.github.com"
          git add docs/WEEKLY_REPORT_LATEST.md
          git add docs/reports/WEEKLY_REPORT_*.md
          git commit -m "chore: auto-generated weekly monitoring report [skip ci]" || echo "No changes"
          git push
```

---

## Part 4: Review Timeline

### Weekly Reviews (Automated)
- **Every Monday**: Auto-generated report committed to repo
- **Manual review required**: Check for red flags in WEEKLY_REPORT_LATEST.md

### Bi-Weekly Reviews (Manual, ~30 min)
- **Category distribution**: On track with expectations?
- **Escalation rates**: Any categories need tuning?
- **Quota incidents**: Any warnings or critical incidents?
- **Cost trends**: Spending within budget?

### Monthly Deep Dives (Manual, ~2 hours)
- **Category detection accuracy**: Review sample of 50 phases
- **Security scan trends**: Any new vulnerabilities or patterns?
- **Performance analysis**: Latency, throughput, bottlenecks
- **Cost optimization**: Can we adjust primary models without sacrificing quality?

### Quarterly Reviews (Manual, ~4 hours)
- **Strategy effectiveness**: Are routing strategies achieving goals?
- **Category refinement**: Do we need to split or merge categories?
- **Model upgrades**: Are new models available that are better/cheaper?
- **System evolution**: What's working well? What needs redesign?

---

## Part 5: Decision Triggers

### Immediate Action Required (Alert Within 1 Hour)
- ✅ Critical quota incident (never_fallback category blocked)
- ✅ Critical security vulnerability discovered
- ✅ >10 auth failures from single IP in 1 hour
- ✅ >50% escalation rate for best_first category

### Action Required This Week
- ⚠️ High-risk category >10% of total phases
- ⚠️ Best_first categories >40% of total cost
- ⚠️ Escalation rate >80% for any progressive category
- ⚠️ >5 high-severity security vulnerabilities unpatched

### Review Next Monthly Deep Dive
- 📊 Escalation rate 50-80% for progressive category
- 📊 Cost trend increasing >20% week-over-week
- 📊 Category detection accuracy 70-90%
- 📊 >10 rate limit hits from legitimate users

### Monitor, No Action Yet
- ✓ All metrics within expected ranges
- ✓ Cost stable or decreasing
- ✓ Zero quota incidents
- ✓ Zero or minimal auth failures
- ✓ Category distribution matches expectations

---

## Summary

### What's Complete ✅
1. Category splitting configuration in `models.yaml`
2. Quota enforcement settings configured
3. API authentication implemented
4. Rate limiting implemented
5. CI/CD security pipeline implemented
6. Documentation and consensus achieved

### What's Pending (Phase 2) ⏳
1. ModelRouter code to execute routing strategies
2. Category detection heuristics
3. QuotaBlockError exception handling
4. Dashboard integration
5. Telemetry database and collection
6. Weekly report generation automation

### What Requires Monitoring 📊
1. Category distribution (review after 50 phases)
2. Model escalation frequency (review after 100 phases)
3. Category detection accuracy (review monthly with 50-phase sample)
4. Quota exhaustion incidents (alert immediately, review weekly)
5. Cost by category (review weekly)
6. API authentication behavior (review weekly)
7. Rate limiting triggers (review weekly)
8. Security scan results (review daily, deep dive weekly)

### Next Actions
1. ✅ **This document created** - implementation status confirmed
2. ⏳ **Next: Create FUTURE_CONSIDERATIONS_TRACKING.md** (items requiring runtime data for future decisions)
3. ⏳ **Then: Implement telemetry collection** (Phase 2, Week 1)
4. ⏳ **Then: Implement ModelRouter enhancements** (Phase 2, Week 1-2)
5. ⏳ **Then: Set up weekly report automation** (Phase 2, Week 2)
6. ⏳ **Then: First manual review after 50 phases run**

---

**End of Implementation Status and Monitoring Plan**
