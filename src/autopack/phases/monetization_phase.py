"""Monetization Phase Implementation for Autonomous Build System.

This module implements the MONETIZATION phase type, which enables the autonomous
executor to generate revenue model strategies, payment integration guides, and
pricing recommendations.

Monetization phases are used when:
- A project needs revenue model strategy
- Payment integration setup is required (Stripe, PayPal, etc.)
- Pricing tiers need to be designed and recommended
- Billing and subscription setup requires guidance
- Compliance requirements (GDPR, PCI-DSS) need documentation

Design Principles:
- Monetization phases leverage deployment phase outputs for cost analysis
- Multiple revenue models can be generated in parallel
- Pricing recommendations are data-driven
- Compliance checklists ensure regulatory adherence
- Results are cached and reusable across phases
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class MonetizationStatus(Enum):
    """Status of a monetization phase."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class MonetizationConfig:
    """Configuration for a monetization phase."""

    revenue_models: List[str] = field(
        default_factory=lambda: ["freemium", "subscription", "pay_per_use"]
    )
    payment_providers: List[str] = field(default_factory=lambda: ["stripe"])
    pricing_strategy: str = "tiered"  # tiered, usage_based, flat_rate
    target_market: str = "b2b"  # b2b, b2c
    enable_trial_period: bool = True
    trial_duration_days: int = 14
    tax_regions: List[str] = field(default_factory=lambda: ["US", "EU"])
    gdpr_compliance: bool = True
    save_to_history: bool = True
    max_duration_minutes: Optional[int] = None


@dataclass
class MonetizationInput:
    """Input data for monetization phase."""

    product_name: str
    target_audience: str
    value_proposition: str
    deployment_info: Optional[Dict[str, Any]] = None  # From deploy phase


@dataclass
class MonetizationOutput:
    """Output from monetization phase."""

    monetization_guide_path: Optional[str] = None
    pricing_model_path: Optional[str] = None
    integration_guide_path: Optional[str] = None
    recommended_tiers: List[Dict[str, Any]] = field(default_factory=list)
    payment_providers_configured: List[str] = field(default_factory=list)
    integration_complexity: str = "medium"
    compliance_checklist: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


@dataclass
class MonetizationPhase:
    """Represents a monetization phase with its configuration and state."""

    phase_id: str
    description: str
    config: MonetizationConfig
    input_data: Optional[MonetizationInput] = None
    status: MonetizationStatus = MonetizationStatus.PENDING
    output: Optional[MonetizationOutput] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert phase to dictionary representation."""
        output_dict = None
        if self.output:
            output_dict = {
                "monetization_guide_path": self.output.monetization_guide_path,
                "pricing_model_path": self.output.pricing_model_path,
                "integration_guide_path": self.output.integration_guide_path,
                "recommended_tiers": self.output.recommended_tiers,
                "payment_providers_configured": self.output.payment_providers_configured,
                "integration_complexity": self.output.integration_complexity,
                "compliance_checklist": self.output.compliance_checklist,
                "warnings": self.output.warnings,
            }

        input_dict = None
        if self.input_data:
            input_dict = {
                "product_name": self.input_data.product_name,
                "target_audience": self.input_data.target_audience,
                "value_proposition": self.input_data.value_proposition,
                "deployment_info": self.input_data.deployment_info,
            }

        return {
            "phase_id": self.phase_id,
            "description": self.description,
            "status": self.status.value,
            "config": {
                "revenue_models": self.config.revenue_models,
                "payment_providers": self.config.payment_providers,
                "pricing_strategy": self.config.pricing_strategy,
                "target_market": self.config.target_market,
                "enable_trial_period": self.config.enable_trial_period,
                "trial_duration_days": self.config.trial_duration_days,
                "tax_regions": self.config.tax_regions,
                "gdpr_compliance": self.config.gdpr_compliance,
                "save_to_history": self.config.save_to_history,
                "max_duration_minutes": self.config.max_duration_minutes,
            },
            "input_data": input_dict,
            "output": output_dict,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "error": self.error,
        }


class MonetizationPhaseExecutor:
    """Executor for monetization phases."""

    def __init__(
        self,
        workspace_path: Optional[Path] = None,
        build_history_path: Optional[Path] = None,
    ):
        """Initialize the executor.

        Args:
            workspace_path: Optional path to workspace for artifact generation
            build_history_path: Optional path to BUILD_HISTORY.md
        """
        self.workspace_path = workspace_path or Path.cwd()
        self.build_history_path = build_history_path

    def execute(self, phase: MonetizationPhase) -> MonetizationPhase:
        """Execute a monetization phase.

        Args:
            phase: The phase to execute

        Returns:
            The updated phase with results
        """
        logger.info(f"Executing monetization phase: {phase.phase_id}")

        phase.status = MonetizationStatus.IN_PROGRESS
        phase.started_at = datetime.now()
        phase.output = MonetizationOutput()
        phase.error = None

        try:
            # Validate input
            if not phase.input_data:
                phase.status = MonetizationStatus.FAILED
                phase.error = "No input data provided for monetization phase"
                return phase

            # Generate monetization artifacts
            self._generate_monetization_artifacts(phase)

            # Mark as completed if not already failed
            if phase.status == MonetizationStatus.IN_PROGRESS:
                phase.status = MonetizationStatus.COMPLETED

            # Save to history if configured
            if phase.config.save_to_history and self.build_history_path:
                self._save_to_history(phase)

        except Exception as e:
            logger.error(f"Phase execution failed: {e}", exc_info=True)
            phase.status = MonetizationStatus.FAILED
            phase.error = str(e)

        finally:
            phase.completed_at = datetime.now()

        return phase

    def _generate_monetization_artifacts(self, phase: MonetizationPhase) -> None:
        """Generate monetization artifacts.

        Args:
            phase: The phase being executed
        """
        if not phase.output or not phase.input_data:
            return

        # Generate pricing model recommendations
        self._generate_pricing_model(phase)

        # Generate payment integration guide
        self._generate_integration_guide(phase)

        # Generate compliance checklist
        self._generate_compliance_checklist(phase)

    def _generate_pricing_model(self, phase: MonetizationPhase) -> None:
        """Generate pricing model recommendations.

        Args:
            phase: The phase being executed
        """
        if not phase.output or not phase.input_data:
            return

        pricing_content = f"""# Pricing Model for {phase.input_data.product_name}

## Target Market
- **Primary**: {phase.input_data.target_audience}
- **Strategy**: {phase.config.pricing_strategy}

## Executive Summary
{phase.input_data.value_proposition}

## Revenue Models Considered
"""

        if "freemium" in phase.config.revenue_models:
            pricing_content += self._generate_freemium_model(phase)

        if "subscription" in phase.config.revenue_models:
            pricing_content += self._generate_subscription_model(phase)

        if "pay_per_use" in phase.config.revenue_models:
            pricing_content += self._generate_payperuse_model(phase)

        pricing_content += """

## Recommended Implementation Path
1. Start with freemium tier for user acquisition
2. Introduce premium features after reaching 1000 users
3. Add enterprise tier for large organizations
4. Monitor churn and adjust pricing quarterly

## Key Metrics to Track
- Customer Acquisition Cost (CAC)
- Lifetime Value (LTV)
- Monthly Recurring Revenue (MRR)
- Churn Rate
- Net Promoter Score (NPS)
"""

        # Write pricing model
        monetize_dir = self.workspace_path / "monetization"
        monetize_dir.mkdir(parents=True, exist_ok=True)
        pricing_path = monetize_dir / "PRICING_MODEL.md"
        pricing_path.write_text(pricing_content, encoding="utf-8")

        phase.output.pricing_model_path = str(pricing_path)
        logger.info(f"Generated pricing model: {pricing_path}")

        # Generate recommended tiers
        if phase.config.pricing_strategy == "tiered":
            phase.output.recommended_tiers = [
                {
                    "name": "Free",
                    "price": "$0/month",
                    "features": ["Basic features", "Community support"],
                    "users": "Solo developers, students",
                },
                {
                    "name": "Pro",
                    "price": "$29/month",
                    "features": [
                        "All free features",
                        "Advanced features",
                        "Email support",
                    ],
                    "users": "Small teams",
                },
                {
                    "name": "Enterprise",
                    "price": "Custom",
                    "features": [
                        "All pro features",
                        "Premium support",
                        "SLA",
                        "Custom integration",
                    ],
                    "users": "Large organizations",
                },
            ]

    def _generate_freemium_model(self, phase: MonetizationPhase) -> str:
        """Generate freemium model details.

        Args:
            phase: The phase being executed

        Returns:
            Markdown content for freemium model
        """
        return """

### 1. Freemium Model

**How it works**: Users get free access to core features with limitations.
Premium users unlock advanced features and higher limits.

**Advantages**:
- Low barrier to entry attracts users
- Natural funnel from free to paid
- User base for word-of-mouth marketing

**Implementation**:
```
Free Tier:
- 10 API calls/day
- 1GB storage
- Community support

Premium Tier:
- Unlimited API calls
- 100GB storage
- Priority email support
```

**Expected Conversion**: 2-5% of free users convert to paid (industry average)
"""

    def _generate_subscription_model(self, phase: MonetizationPhase) -> str:
        """Generate subscription model details.

        Args:
            phase: The phase being executed

        Returns:
            Markdown content for subscription model
        """
        trial_text = (
            f"with {phase.config.trial_duration_days}-day free trial"
            if phase.config.enable_trial_period
            else ""
        )

        return f"""

### 2. Subscription Model

**How it works**: Users pay a recurring fee (monthly/annually) for access.

**Advantages**:
- Predictable recurring revenue (MRR/ARR)
- Customer lifetime value easier to forecast
- Strong incentive to build long-term relationships

**Implementation**:
```
Monthly Tiers {trial_text}:
- Starter: $19/month (small teams)
- Professional: $49/month (growing teams)
- Enterprise: Custom pricing (enterprises)
```

**Annual Discount**: 20% discount for annual prepayment
(increases LTV and improves cash flow)
"""

    def _generate_payperuse_model(self, phase: MonetizationPhase) -> str:
        """Generate pay-per-use model details.

        Args:
            phase: The phase being executed

        Returns:
            Markdown content for pay-per-use model
        """
        return """

### 3. Pay-Per-Use Model

**How it works**: Users pay for what they consume (API calls, storage, compute).

**Advantages**:
- Aligns costs with usage and value
- No friction for trying out service
- Users naturally pay more as they scale

**Implementation**:
```
Usage-Based Pricing:
- API Calls: $0.01 per 1000 calls
- Storage: $0.023 per GB/month
- Compute: $0.50 per CPU-hour
- Support: Volume discounts for >$1000/month
```

**Billing**: Monthly invoice based on usage
"""

    def _generate_integration_guide(self, phase: MonetizationPhase) -> None:
        """Generate payment integration guide.

        Args:
            phase: The phase being executed
        """
        if not phase.output or not phase.input_data:
            return

        guide_content = f"""# Payment Integration Guide for {phase.input_data.product_name}

## Supported Payment Providers

"""

        if "stripe" in phase.config.payment_providers:
            guide_content += self._generate_stripe_integration()

        if "paypal" in phase.config.payment_providers:
            guide_content += self._generate_paypal_integration()

        guide_content += """

## Webhook Configuration

### Stripe Webhooks
- `charge.succeeded`: Process successful payment
- `charge.failed`: Handle failed payment
- `customer.subscription.updated`: Handle subscription changes
- `customer.subscription.deleted`: Process cancellations

### PayPal Webhooks
- `PAYMENT.CAPTURE.COMPLETED`: Process completed payment
- `BILLING.SUBSCRIPTION.CREATED`: Handle subscription creation
- `BILLING.SUBSCRIPTION.CANCELLED`: Handle subscription cancellation

## Tax Handling

### EU - Value Added Tax (VAT)
- Digital services subject to VAT
- Rate: 17-27% depending on country
- Implementation: Use `tax_id` verification

### US - Sales Tax
- State-based (varies by state)
- Some states exempt digital services
- Implementation: Geo-IP based detection + manual configuration

### Compliance
- Keep records of all transactions for 7 years
- Implement PCI-DSS Level 1 compliance
- Use payment processor tokenization (never store full card numbers)
"""

        monetize_dir = self.workspace_path / "monetization"
        monetize_dir.mkdir(parents=True, exist_ok=True)
        guide_path = monetize_dir / "PAYMENT_INTEGRATION.md"
        guide_path.write_text(guide_content, encoding="utf-8")

        phase.output.integration_guide_path = str(guide_path)
        phase.output.payment_providers_configured = phase.config.payment_providers
        logger.info(f"Generated integration guide: {guide_path}")

    def _generate_stripe_integration(self) -> str:
        """Generate Stripe integration guide.

        Returns:
            Markdown content for Stripe setup
        """
        return """

### Stripe Integration

**Setup**:
1. Create Stripe account at https://stripe.com
2. Get API keys from dashboard
3. Install Stripe library: `pip install stripe`

**Basic Implementation**:

```python
import stripe

stripe.api_key = os.environ['STRIPE_SECRET_KEY']

# Create a payment intent
intent = stripe.PaymentIntent.create(
    amount=2000,  # $20.00 in cents
    currency='usd',
    payment_method_types=['card'],
    metadata={'product': 'pro_subscription'}
)

# Confirm payment from frontend
confirmed = stripe.PaymentIntent.confirm(
    intent.id,
    payment_method='pm_xxxxx'
)
```

**Subscription Management**:

```python
# Create subscription
subscription = stripe.Subscription.create(
    customer='cus_xxxxx',
    items=[
        {
            'price': 'price_xxxxx',
            'quantity': 1
        }
    ],
    payment_behavior='default_incomplete'
)

# Cancel subscription
stripe.Subscription.delete('sub_xxxxx')
```

**Webhooks**:

```python
from flask import request

@app.route('/webhook', methods=['POST'])
def webhook():
    event = json.loads(request.data)

    if event['type'] == 'charge.succeeded':
        handle_successful_payment(event['data']['object'])

    return {'status': 'ok'}
```

**Pricing**:
- 2.2% + 30¢ per transaction
- No monthly fees
- Industry standard security
"""

    def _generate_paypal_integration(self) -> str:
        """Generate PayPal integration guide.

        Returns:
            Markdown content for PayPal setup
        """
        return """

### PayPal Integration

**Setup**:
1. Create PayPal Business account
2. Get Client ID and Secret from app.paypal.com
3. Install PayPal SDK: `pip install paypalrestsdk`

**Basic Implementation**:

```python
import paypalrestsdk

api = paypalrestsdk.Api({
    'mode': 'sandbox',  # or 'live'
    'client_id': os.environ['PAYPAL_CLIENT_ID'],
    'client_secret': os.environ['PAYPAL_CLIENT_SECRET']
})

# Create payment
payment = paypalrestsdk.Payment({
    'intent': 'sale',
    'payer': {
        'payment_method': 'paypal'
    },
    'redirect_urls': {
        'return_url': 'https://example.com/return',
        'cancel_url': 'https://example.com/cancel'
    },
    'transactions': [{
        'amount': {
            'total': '20.00',
            'currency': 'USD'
        }
    }]
})

if payment.create():
    print("Payment created successfully")
else:
    print(payment.error)
```

**Subscription Billing**:

```python
# Create billing plan
plan = paypalrestsdk.BillingPlan({
    'name': 'Pro Plan',
    'description': '$29/month subscription',
    'type': 'REGULAR'
})

# Create billing agreement
agreement = paypalrestsdk.BillingAgreement({
    'name': 'Pro Plan Agreement',
    'description': 'Pro subscription plan',
    'start_date': '2024-01-01T00:00:00Z',
    'plan': {'id': plan.id}
})
```

**Pricing**:
- 2.9% + 30¢ per transaction
- 3.5% for international
- No setup fees
"""

    def _generate_compliance_checklist(self, phase: MonetizationPhase) -> None:
        """Generate compliance checklist.

        Args:
            phase: The phase being executed
        """
        if not phase.output:
            return

        compliance_items = [
            "☐ Terms of Service (ToS) document created",
            "☐ Privacy Policy compliant with GDPR (if EU users)",
            "☐ Privacy Policy compliant with CCPA (if California users)",
            "☐ Cookie policy and consent implemented",
            "☐ Payment processing PCI-DSS compliant (use payment processor tokenization)",
            "☐ Data encryption in transit (HTTPS/TLS)",
            "☐ Data encryption at rest",
            "☐ User data deletion policy documented",
            "☐ Data backup and disaster recovery plan",
            "☐ Incident response plan in place",
            "☐ Tax registration for all applicable regions",
            "☐ Invoice system with audit trail",
            "☐ Refund policy clearly documented",
            "☐ Chargeback dispute process defined",
            "☐ Support contact information published",
            "☐ SLA (Service Level Agreement) if applicable",
            "☐ Status page for monitoring uptime",
            "☐ GDPR Data Processing Agreement (DPA) if applicable",
        ]

        phase.output.compliance_checklist = compliance_items
        logger.info("Generated compliance checklist")

    def _save_to_history(self, phase: MonetizationPhase) -> None:
        """Save phase results to BUILD_HISTORY.

        Args:
            phase: The phase to save
        """
        if not self.build_history_path:
            return

        entry = self._format_history_entry(phase)

        try:
            with open(self.build_history_path, "a", encoding="utf-8") as f:
                f.write("\n" + entry + "\n")
        except Exception as e:
            logger.warning(f"Failed to save to build history: {e}")

    def _format_history_entry(self, phase: MonetizationPhase) -> str:
        """Format phase as BUILD_HISTORY entry.

        Args:
            phase: The phase to format

        Returns:
            Formatted markdown entry
        """
        lines = [
            f"## Monetization Phase: {phase.phase_id}",
            f"**Description**: {phase.description}",
            f"**Status**: {phase.status.value}",
            f"**Started**: {phase.started_at}",
            f"**Completed**: {phase.completed_at}",
            "",
        ]

        if phase.output:
            lines.append("### Monetization Strategy")
            if phase.output.recommended_tiers:
                lines.append("- **Recommended Tiers**:")
                for tier in phase.output.recommended_tiers:
                    lines.append(f"  - {tier.get('name')}: {tier.get('price')}")
            if phase.output.payment_providers_configured:
                lines.append(
                    f"- **Payment Providers**: {', '.join(phase.output.payment_providers_configured)}"
                )
            if phase.output.compliance_checklist:
                lines.append(f"- **Compliance Items**: {len(phase.output.compliance_checklist)}")
            lines.append("")

        if phase.error:
            lines.append(f"**Error**: {phase.error}")
            lines.append("")

        return "\n".join(lines)


def create_monetization_phase(
    phase_id: str,
    product_name: str,
    target_audience: str,
    value_proposition: str,
    **kwargs,
) -> MonetizationPhase:
    """Factory function to create a monetization phase.

    Args:
        phase_id: Unique phase identifier
        product_name: Name of the product
        target_audience: Target audience description
        value_proposition: Value proposition of the product
        **kwargs: Additional configuration options

    Returns:
        Configured MonetizationPhase instance
    """
    config = MonetizationConfig(**kwargs)
    input_data = MonetizationInput(
        product_name=product_name,
        target_audience=target_audience,
        value_proposition=value_proposition,
    )

    return MonetizationPhase(
        phase_id=phase_id,
        description=f"Monetization phase: {phase_id}",
        config=config,
        input_data=input_data,
    )
