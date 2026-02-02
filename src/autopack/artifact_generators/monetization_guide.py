"""MonetizationGuide artifact generator for revenue model strategy.

Generates comprehensive monetization guides with revenue model options,
payment provider integration, pricing strategies, and compliance checklists.
"""

from __future__ import annotations

import logging
from typing import List, Optional

logger = logging.getLogger(__name__)


class MonetizationGuide:
    """Generates structured monetization guides for different revenue models.

    Produces comprehensive monetization guidance including:
    - Revenue model analysis (freemium, subscription, pay-per-use)
    - Payment provider integration guides (Stripe, PayPal)
    - Pricing strategy recommendations
    - Compliance and regulatory requirements
    - Financial projections and metrics
    """

    # Supported revenue models
    REVENUE_MODELS = {
        "freemium": {
            "name": "Freemium",
            "description": "Free tier with limited features, premium tier for advanced features",
            "suitable_for": ["B2B SaaS", "Developer tools", "Productivity apps"],
            "conversion_rate": "2-5%",
            "pros": ["Low barrier to entry", "Large user base", "Word-of-mouth marketing"],
            "cons": ["High support costs", "Server costs for free users", "Conversion is key"],
        },
        "subscription": {
            "name": "Subscription (SaaS)",
            "description": "Monthly or annual recurring revenue",
            "suitable_for": ["B2B SaaS", "Content platforms", "Cloud services"],
            "conversion_rate": "N/A",
            "pros": ["Predictable MRR", "High LTV", "Strong customer relationships"],
            "cons": ["Churn risk", "Customer acquisition cost critical", "Retention focused"],
        },
        "pay_per_use": {
            "name": "Pay-Per-Use (Usage-Based)",
            "description": "Users pay for consumption (API calls, storage, compute)",
            "suitable_for": ["Cloud services", "APIs", "Platform services"],
            "conversion_rate": "N/A",
            "pros": ["Aligns cost with value", "No friction to start", "Scales with customer"],
            "cons": ["Revenue unpredictable", "High infrastructure costs", "Complex billing"],
        },
        "one_time": {
            "name": "One-Time Purchase",
            "description": "One-time payment for product/service",
            "suitable_for": ["Software licenses", "Physical products", "Services"],
            "conversion_rate": "N/A",
            "pros": ["Simple billing", "Immediate revenue", "Clear value proposition"],
            "cons": ["One-time revenue only", "Need continuous sales", "No recurring base"],
        },
    }

    # Supported payment providers
    PAYMENT_PROVIDERS = {
        "stripe": {
            "name": "Stripe",
            "description": "Leading global payment processor",
            "pricing": "2.2% + $0.30 per transaction",
            "features": ["Cards", "Bank transfers", "Subscriptions", "Invoicing"],
            "countries": "130+",
            "recommended_for": "B2B and B2C SaaS",
        },
        "paypal": {
            "name": "PayPal",
            "description": "Established payment platform with large user base",
            "pricing": "2.9% + $0.30 per transaction",
            "features": ["Cards", "PayPal wallet", "Subscriptions", "Invoicing"],
            "countries": "200+",
            "recommended_for": "Global B2C payments",
        },
        "square": {
            "name": "Square",
            "description": "Payment processor focused on in-person and online",
            "pricing": "2.6% + $0.30 per transaction",
            "features": ["Cards", "In-person", "Subscriptions", "Invoicing"],
            "countries": "US, UK, Canada, Australia",
            "recommended_for": "Small business and retail",
        },
        "adyen": {
            "name": "Adyen",
            "description": "Enterprise payment platform",
            "pricing": "Contact for enterprise pricing",
            "features": ["Cards", "Wallets", "Local methods", "Custom solutions"],
            "countries": "180+",
            "recommended_for": "Enterprise and high-volume",
        },
    }

    def __init__(self) -> None:
        """Initialize the MonetizationGuide generator."""
        logger.info("[MonetizationGuide] Initializing monetization guide generator")

    def generate(
        self,
        product_name: str,
        target_audience: str,
        revenue_models: Optional[List[str]] = None,
        payment_providers: Optional[List[str]] = None,
        pricing_strategy: str = "tiered",
    ) -> str:
        """Generate a comprehensive monetization guide.

        Args:
            product_name: Name of the product
            target_audience: Target audience description
            revenue_models: List of revenue models to include (defaults to all)
            payment_providers: List of payment providers to include (defaults to Stripe)
            pricing_strategy: Pricing strategy (tiered, usage_based, flat_rate)

        Returns:
            Markdown string with monetization guide
        """
        logger.info(f"[MonetizationGuide] Generating monetization guide for {product_name}")

        if revenue_models is None:
            revenue_models = list(self.REVENUE_MODELS.keys())
        else:
            # Validate model names
            revenue_models = [m for m in revenue_models if m in self.REVENUE_MODELS]
            if not revenue_models:
                revenue_models = list(self.REVENUE_MODELS.keys())
                logger.warning("[MonetizationGuide] No valid revenue models specified, using all")

        if payment_providers is None:
            payment_providers = ["stripe"]
        else:
            # Validate provider names
            payment_providers = [p for p in payment_providers if p in self.PAYMENT_PROVIDERS]
            if not payment_providers:
                payment_providers = ["stripe"]
                logger.warning(
                    "[MonetizationGuide] No valid payment providers specified, using Stripe"
                )

        content = "# Monetization Strategy\n\n"

        # Add introduction
        content += self._generate_introduction(product_name, target_audience)

        # Add executive summary
        content += self._generate_executive_summary(revenue_models, pricing_strategy)

        # Add revenue model sections
        content += self._generate_revenue_models_section(revenue_models)

        # Add payment provider section
        content += self._generate_payment_providers_section(payment_providers)

        # Add pricing strategy section
        content += self._generate_pricing_strategy_section(pricing_strategy)

        # Add implementation roadmap
        content += self._generate_implementation_roadmap(product_name)

        # Add financial metrics section
        content += self._generate_financial_metrics()

        # Add compliance section
        content += self._generate_compliance_section()

        return content

    def _generate_introduction(self, product_name: str, target_audience: str) -> str:
        """Generate introduction section.

        Args:
            product_name: Product name
            target_audience: Target audience description

        Returns:
            Markdown introduction
        """
        return f"""## Introduction

This monetization guide provides a comprehensive strategy for {product_name} to generate sustainable revenue.

**Target Audience**: {target_audience}

**Goal**: Build a scalable, sustainable revenue model that aligns with customer value and market demands.

"""

    def _generate_executive_summary(self, revenue_models: List[str], pricing_strategy: str) -> str:
        """Generate executive summary.

        Args:
            revenue_models: Selected revenue models
            pricing_strategy: Pricing strategy

        Returns:
            Markdown executive summary
        """
        models_text = ", ".join(self.REVENUE_MODELS[m]["name"] for m in revenue_models)

        return f"""## Executive Summary

**Recommended Approach**: {models_text}

**Pricing Strategy**: {pricing_strategy.title()}

**Key Metrics**: Customer Acquisition Cost (CAC), Lifetime Value (LTV), Monthly Recurring Revenue (MRR), Churn Rate

### Revenue Model Comparison

| Model | Pros | Cons | Best For |
|-------|------|------|----------|
"""

    def _generate_revenue_models_section(self, revenue_models: List[str]) -> str:
        """Generate revenue models section.

        Args:
            revenue_models: Selected revenue models

        Returns:
            Markdown revenue models section
        """
        content = "## Revenue Models\n\n"

        for i, model_key in enumerate(revenue_models, 1):
            model = self.REVENUE_MODELS[model_key]
            content += f"### {i}. {model['name']}\n\n"
            content += f"**Description**: {model['description']}\n\n"
            content += f"**Suitable for**: {', '.join(model['suitable_for'])}\n\n"

            if model_key == "freemium":
                content += self._generate_freemium_details()
            elif model_key == "subscription":
                content += self._generate_subscription_details()
            elif model_key == "pay_per_use":
                content += self._generate_payperuse_details()
            elif model_key == "one_time":
                content += self._generate_onetime_details()

            content += f"**Expected Conversion Rate**: {model['conversion_rate']}\n\n"
            content += "**Advantages**:\n"
            for pro in model["pros"]:
                content += f"- {pro}\n"
            content += "\n**Disadvantages**:\n"
            for con in model["cons"]:
                content += f"- {con}\n"
            content += "\n"

        return content

    def _generate_freemium_details(self) -> str:
        """Generate freemium model details."""
        return """**Implementation Example**:
```
Free Tier:
- Core features (read-only)
- 10 API calls/day
- Community support
- Ads enabled

Premium Tier ($29/month):
- Advanced features (full access)
- Unlimited API calls
- Priority email support
- No ads
```

**Conversion Strategy**:
- Free tier targets individual users and small teams
- Premium tier targets growing teams with more advanced needs
- Focus on free-to-paid conversion (typically 2-5%)
- Upsell based on usage patterns and feature needs

"""

    def _generate_subscription_details(self) -> str:
        """Generate subscription model details."""
        return """**Implementation Example**:
```
Starter ($19/month or $190/year):
- Up to 5 users
- Core features
- Email support

Professional ($49/month or $490/year):
- Up to 50 users
- Advanced features
- Priority support

Enterprise (Custom):
- Unlimited users
- All features + custom integrations
- Dedicated account manager
- SLA guarantees
```

**Retention Strategy**:
- Focus on user adoption and value demonstration
- Regular communication and feature updates
- Strong customer support to reduce churn
- 20% discount for annual prepayment (improves cash flow and LTV)

"""

    def _generate_payperuse_details(self) -> str:
        """Generate pay-per-use model details."""
        return """**Implementation Example**:
```
API Calls: $0.01 per 1,000 calls
Storage: $0.023 per GB/month
Compute: $0.50 per CPU-hour
Support: Included in usage

Volume Discounts:
- >$100/month: 10% discount
- >$1,000/month: 20% discount
```

**Billing Strategy**:
- Monthly invoicing based on actual usage
- Clear usage dashboards for transparency
- Alerts when approaching budget limits
- Overage fees with customer approval

"""

    def _generate_onetime_details(self) -> str:
        """Generate one-time purchase model details."""
        return """**Implementation Example**:
```
Individual License: $99
Team License (5 seats): $249
Enterprise License (unlimited): $999
```

**Distribution Channels**:
- Direct sales (online store, email sales)
- Marketplace listings (AppStore, etc.)
- Reseller partnerships
- Enterprise sales team

"""

    def _generate_payment_providers_section(self, payment_providers: List[str]) -> str:
        """Generate payment providers section.

        Args:
            payment_providers: Selected payment providers

        Returns:
            Markdown payment providers section
        """
        content = "## Payment Providers\n\n"

        for provider_key in payment_providers:
            provider = self.PAYMENT_PROVIDERS[provider_key]
            content += f"### {provider['name']}\n\n"
            content += f"**Description**: {provider['description']}\n\n"
            content += f"- **Pricing**: {provider['pricing']}\n"
            content += f"- **Features**: {', '.join(provider['features'])}\n"
            content += f"- **Countries**: {provider['countries']}\n"
            content += f"- **Recommended for**: {provider['recommended_for']}\n\n"

        return content

    def _generate_pricing_strategy_section(self, strategy: str) -> str:
        """Generate pricing strategy section.

        Args:
            strategy: Pricing strategy

        Returns:
            Markdown pricing strategy section
        """
        content = f"## Pricing Strategy: {strategy.title()}\n\n"

        if strategy == "tiered":
            content += """### Tiered Pricing

**How it works**: Multiple price points with increasing features

**Benefits**:
- Appeals to different customer segments
- Encourages upselling
- Increases average revenue per user (ARPU)

**Example Tiers**:
1. **Basic** - Core features for individuals ($0-$29)
2. **Professional** - Advanced features for small teams ($29-$99)
3. **Enterprise** - Custom features for large organizations ($100+)

"""
        elif strategy == "usage_based":
            content += """### Usage-Based Pricing

**How it works**: Price based on consumption/usage metrics

**Benefits**:
- Fair pricing model (users pay for what they use)
- No friction to start
- Revenue scales with customer success
- Natural ceiling on costs for customers

**Metrics to track**:
- API calls
- Storage consumed
- Compute hours
- Active users
- Transactions processed

"""
        elif strategy == "flat_rate":
            content += """### Flat-Rate Pricing

**How it works**: Single price for all customers with same access level

**Benefits**:
- Simplicity for customers
- Easy to understand and compare
- Lower operational complexity

**Drawbacks**:
- May leave money on table from high-value customers
- Discourages usage by value-conscious customers

"""

        return content

    def _generate_implementation_roadmap(self, product_name: str) -> str:
        """Generate implementation roadmap.

        Args:
            product_name: Product name

        Returns:
            Markdown roadmap
        """
        return """## Implementation Roadmap

### Phase 1: Foundation (Weeks 1-4)
- [ ] Set up payment processor account (Stripe recommended)
- [ ] Implement payment APIs in backend
- [ ] Create billing database schema
- [ ] Develop subscription management UI
- [ ] Set up webhook handlers for payment events

### Phase 2: Free Tier & Metering (Weeks 5-8)
- [ ] Implement usage tracking
- [ ] Create limits enforcement (quota management)
- [ ] Build free-to-paid upgrade flow
- [ ] A/B test freemium conversion funnel
- [ ] Set up analytics for conversion metrics

### Phase 3: Premium Features (Weeks 9-12)
- [ ] Gate advanced features behind premium tier
- [ ] Implement feature flags for tiering
- [ ] Create premium-only documentation
- [ ] Design customer onboarding for premium
- [ ] Set up premium support channels

### Phase 4: Compliance & Scaling (Weeks 13+)
- [ ] Implement PCI-DSS compliance
- [ ] Set up tax handling (VAT, sales tax)
- [ ] Create Terms of Service and Privacy Policy
- [ ] Implement usage reporting and invoicing
- [ ] Monitor payment success rates and optimize

## Key Metrics to Track

**Customer Acquisition**
- Cost per customer (CAC)
- Conversion rate from free to paid
- Marketing ROI by channel

**Revenue**
- Monthly Recurring Revenue (MRR)
- Annual Recurring Revenue (ARR)
- Average Revenue Per User (ARPU)

**Retention**
- Customer churn rate
- Revenue churn rate
- Lifetime Value (LTV)
- LTV:CAC ratio (target 3:1 or higher)

**Usage**
- Daily Active Users (DAU)
- Monthly Active Users (MAU)
- Feature adoption rates
- Usage growth rate

"""

    def _generate_financial_metrics(self) -> str:
        """Generate financial metrics section."""
        return """## Financial Modeling

### Sample Projections (Based on 10,000 Free Users)

**Year 1 Assumptions**:
- 2% free-to-paid conversion rate = 200 paying customers
- Average revenue per user: $30/month
- Monthly churn rate: 3%

| Month | Customers | MRR | ARR | CAC Payback |
|-------|-----------|-----|-----|-------------|
| 1 | 20 | $600 | $7,200 | N/A |
| 3 | 56 | $1,680 | $20,160 | 4 months |
| 6 | 110 | $3,300 | $39,600 | 3 months |
| 12 | 200 | $6,000 | $72,000 | 2 months |

### Break-Even Analysis

**Monthly Fixed Costs**:
- Infrastructure: $2,000
- Team (1 engineer, 0.5 support): $8,000
- Marketing: $2,000
- **Total**: $12,000/month

**Break-Even Point**:
- At $30 ARPU: 400 paying customers
- Expected timeline: 12-18 months with focused growth

### Pricing Sensitivity

| ARPU | Customers at Break-Even | Timeline |
|------|------------------------|----------|
| $20 | 600 | 18 months |
| $30 | 400 | 12 months |
| $50 | 240 | 8 months |

**Conclusion**: Aim for $30+ ARPU through tier mix and upselling.

"""

    def _generate_compliance_section(self) -> str:
        """Generate compliance section."""
        return """## Compliance and Legal

### Payment Processing Compliance
- **PCI-DSS**: Use payment processor tokenization (never store card numbers)
- **Payment Card Industry Standards**: Annual compliance audit
- **SOC 2**: Implement if targeting enterprise

### Tax Compliance

**EU - Value Added Tax (VAT)**
- Digital services subject to VAT
- Rate: 17-27% depending on customer location
- Must collect VAT and remit to authorities
- Use tax ID verification to identify B2B customers

**US - Sales Tax**
- Varies by state (some exempt digital services)
- Physical nexus triggers collection obligation
- Economic nexus may apply (varies by state)
- Use sales tax calculator (TaxJar, Avalara)

**International**
- Set up local entities if significant revenue in region
- Consult local tax advisor for each market

### Terms of Service (ToS)
- [ ] Acceptable use policy
- [ ] Liability limitations
- [ ] Service level guarantees
- [ ] Billing and refund policy
- [ ] Data retention and deletion policy

### Privacy Policy
- [ ] Data collection disclosures
- [ ] GDPR compliance (if EU users)
- [ ] CCPA compliance (if California users)
- [ ] Data subject rights (access, deletion, portability)
- [ ] Cookie policy and consent

### Refund Policy
- Clear refund terms (e.g., 30-day, no questions asked)
- Chargeback dispute procedures
- Partial refund criteria
- Document refund reasons for analytics

## Next Steps

1. **Validate assumptions**: Survey target customers on willingness to pay
2. **Create pricing page**: Showcase tiers and pricing
3. **Implement payment integration**: Set up Stripe or chosen provider
4. **Launch beta monetization**: Test with small customer segment
5. **Iterate based on feedback**: Adjust pricing and tiers as needed
6. **Scale marketing**: Expand customer base systematically

"""
