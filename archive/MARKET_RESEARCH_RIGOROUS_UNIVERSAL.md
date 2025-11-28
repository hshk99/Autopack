# Rigorous Market Research Template (Universal)

**Version**: 2.0
**Purpose**: Product-agnostic framework for rigorous business viability analysis
**Last Updated**: 2025-11-27

---

## Instructions for Use

This template is **product-agnostic** and can be reused for any product idea. Fill in all sections with quantitative data, cite sources, and be brutally honest about assumptions.

**Critical Principles**:
1. **Quantify everything**: TAM in $, WTP in $/mo, CAC in $, LTV in $, switching barrier in $ + hours
2. **Cite sources**: Every claim needs a source (official data, research, competitor website, expert interview)
3. **Segment-level detail**: Analyze ALL potential segments, not just your favorite niche
4. **Honest switching analysis**: "Why would users switch FROM competitors TO us?" with realistic likelihood %
5. **10x differentiation, not 10%**: If you can't articulate a 10x advantage, say so explicitly
6. **Risk-aware**: Identify dealbreakers early, don't sugarcoat weak moat or unclear differentiation

---

## PROJECT INFORMATION

**Product Name**: `{product_name}`
**Date**: `{date}`
**Analyst**: `{analyst_name}`
**One-Sentence Description**: `{product_description}`

---

## PART 1: MARKET SIZE & OPPORTUNITY ANALYSIS

### 1.1 Total Addressable Market (TAM)

**Definition**: The total revenue opportunity if you captured 100% of the entire market globally.

**TAM Calculation**:
- **Method**: `{bottom_up | top_down | value_theory}`
- **Formula**: `{calculation_formula}`
- **Result**: `{TAM_value}` (e.g., $13.7B in 2025)
- **CAGR**: `{growth_rate}%` (e.g., 17.9% CAGR 2025-2032)
- **TAM by 2030**: `{TAM_future}`

**Sources**:
- `{source_1}` (e.g., Gartner report, Statista, industry association)
- `{source_2}`

**Critical Question**: Is this market large enough? (Rule of thumb: TAM >$1B for VC-backable, >$100M for bootstrapped SaaS)

---

### 1.2 Serviceable Addressable Market (SAM)

**Definition**: The portion of TAM you can realistically reach with your product and distribution.

**SAM Calculation**:
- **Geographic Constraints**: `{regions_served}` (e.g., English-speaking countries, OECD nations)
- **Platform Constraints**: `{platforms}` (e.g., Desktop only, excludes mobile users)
- **Customer Type**: `{customer_types}` (e.g., B2C individuals, excludes enterprise)
- **Result**: `{SAM_value}` (e.g., $500M-$700M)
- **% of TAM**: `{SAM_percentage}%`

**Sources**:
- `{source_for_geographic_data}`
- `{source_for_platform_adoption}`

**Critical Question**: Can you realistically reach this SAM with your distribution model?

---

### 1.3 Serviceable Obtainable Market (SOM)

**Definition**: The portion of SAM you can capture in a realistic timeframe (Year 1, 3, 5).

**SOM Projections**:
- **Year 1**: `{SOM_Y1}` (e.g., $50K-$70K revenue = 0.01% of SAM)
- **Year 3**: `{SOM_Y3}` (e.g., $500K-$700K = 0.1% of SAM)
- **Year 5**: `{SOM_Y5}` (e.g., $2.5M-$3.5M = 0.5% of SAM)

**Assumptions**:
- User acquisition rate: `{user_acquisition_rate}`
- Conversion rate: `{conversion_rate}%`
- Churn rate: `{churn_rate}%`
- ARPU: `{arpu}`

**Reality Check**: Is 0.5-1% of SAM by Year 5 achievable given competitive intensity?

---

### 1.4 Market Size by Segment

Break TAM into customer segments:

| Segment | Global Users | % of TAM | TAM (Revenue) | Growth Rate |
|---------|--------------|----------|---------------|-------------|
| `{segment_1}` | `{user_count_1}` | `{percentage_1}%` | `{revenue_1}` | `{growth_1}%` |
| `{segment_2}` | `{user_count_2}` | `{percentage_2}%` | `{revenue_2}` | `{growth_2}%` |
| `{segment_3}` | `{user_count_3}` | `{percentage_3}%` | `{revenue_3}` | `{growth_3}%` |

**Sources**:
- `{source_for_segment_sizing}`

**Critical Question**: Which segment is largest? Which is growing fastest? (Don't automatically pick your favorite niche)

---

## PART 2: CUSTOMER SEGMENT ANALYSIS (ALL SEGMENTS)

Analyze **ALL** potential segments, not just your target. For each segment:

### Segment 1: `{segment_1_name}`

**Size**: `{segment_1_user_count}` users globally, `{segment_1_revenue}` market

**Profile**:
- **Demographics**: `{age, income, location, occupation}`
- **Psychographics**: `{tech-savviness, risk tolerance, decision-making}`
- **Pain Points** (ranked by severity):
  1. `{pain_point_1}`
  2. `{pain_point_2}`
  3. `{pain_point_3}`

**Economics**:
- **Willingness to Pay (WTP)**: `{WTP_min}`-`{WTP_max}`/month (or one-time `{WTP_onetime}`)
  - Source: `{source_for_WTP}` (competitor pricing, surveys, expert interviews)
- **Customer Acquisition Cost (CAC)**: `{CAC_min}`-`{CAC_max}`
  - Channel: `{primary_channel}` (e.g., content marketing $30-$50, paid ads $100-$200)
  - Source: `{source_for_CAC}` (industry benchmarks, similar products)
- **Lifetime Value (LTV)**: `{LTV_min}`-`{LTV_max}`
  - Calculation: `{ARPU}` × `{retention_months}` months × `{gross_margin}%`
  - Source: `{source_for_churn}` (industry average, competitor data)
- **LTV/CAC Ratio**: `{LTV_CAC_ratio}`
  - ✅ EXCELLENT (>6.0), ✅ GOOD (3.0-6.0), ⚠️ MARGINAL (1.5-3.0), ❌ POOR (<1.5)

**Competitive Intensity**:
- **Incumbents**: `{competitor_1, competitor_2, competitor_3}`
- **Switching Barrier**: `{LOW | MEDIUM | HIGH}` (see Part 4)
- **Market Saturation**: `{percentage}%` (how many already use competitor solutions)

**Priority Factors**:
- **Pros**: `{why_target_this_segment}` (e.g., large market, low CAC, clear pain)
- **Cons**: `{why_NOT_target}` (e.g., low WTP, high switching barrier, commoditized)

---

### Segment 2: `{segment_2_name}`

[Repeat structure above]

---

### Segment 3: `{segment_3_name}`

[Repeat structure above]

---

### 2.X Segment Priority Matrix

Rank segments by **profitability potential**, NOT just market size:

| Segment | Market Size | WTP | CAC | LTV | LTV/CAC | Priority | Rationale |
|---------|-------------|-----|-----|-----|---------|----------|-----------|
| `{segment_1}` | `{size_1}` | `{WTP_1}` | `{CAC_1}` | `{LTV_1}` | `{ratio_1}` | **1st** | `{why_first}` |
| `{segment_2}` | `{size_2}` | `{WTP_2}` | `{CAC_2}` | `{LTV_2}` | `{ratio_2}` | **2nd** | `{why_second}` |
| `{segment_3}` | `{size_3}` | `{WTP_3}` | `{CAC_3}` | `{LTV_3}` | `{ratio_3}` | **3rd** | `{why_third}` |

**Strategic Recommendation**: Target `{priority_segment}` first because `{rationale}`.

**Critical Question**: Which segments should we target FIRST for profitability? (Largest ≠ Best)

---

## PART 3: COMPETITIVE LANDSCAPE

### 3.1 Existing Solutions Analysis

Identify **ALL** major competitors (aim for 20-30+):

#### Competitor 1: `{competitor_1_name}`

- **Type**: `{enterprise | SMB | consumer | open-source}`
- **Platform**: `{web | desktop | mobile | all}`
- **Pricing**: `{pricing_model}` (e.g., $50-$300/user/month, freemium, one-time $49)
- **Users/Revenue** (if known): `{user_count}` users, `{revenue}` ARR
- **Key Features**:
  - `{feature_1}`
  - `{feature_2}`
  - `{feature_3}`
- **Strengths** (✅):
  - `{strength_1}` (e.g., "Established brand, 100K+ users")
  - `{strength_2}` (e.g., "Deep feature set for enterprise")
- **Weaknesses** (❌):
  - `{weakness_1}` (e.g., "Expensive, $100-$500/mo excludes individuals")
  - `{weakness_2}` (e.g., "Cloud-only, privacy concerns for sensitive data")
- **User Complaints** (from reviews, forums, support tickets):
  - `{complaint_1}`
  - `{complaint_2}`
- **Source**: `{competitor_website, G2, Capterra, ProductHunt, Reddit}`

---

[Repeat for Competitor 2, 3, ... N]

---

### 3.2 Competitive Comparison Matrix

| Solution | Type | Platform | Pricing | Users | Strengths | Weaknesses | Market Position |
|----------|------|----------|---------|-------|-----------|------------|-----------------|
| `{competitor_1}` | `{type}` | `{platform}` | `{price}` | `{users}` | `{strengths}` | `{weaknesses}` | `{leader | challenger | niche}` |
| `{competitor_2}` | ... | ... | ... | ... | ... | ... | ... |

**Market Leaders**: `{leader_1, leader_2}` (>50% market share, dominant brand)
**Challengers**: `{challenger_1, challenger_2}` (10-30% share, growing)
**Niche Players**: `{niche_1, niche_2}` (<10% share, specialized)

---

### 3.3 Competitor Revenue & User Base

(Where publicly available or estimable)

| Competitor | Users | Revenue (ARR) | Pricing | Market Share | Growth Rate |
|------------|-------|---------------|---------|--------------|-------------|
| `{competitor_1}` | `{users_1}` | `{revenue_1}` | `{pricing_1}` | `{share_1}%` | `{growth_1}%` |
| `{competitor_2}` | ... | ... | ... | ... | ... |

**Sources**:
- `{source_for_revenue}` (e.g., Crunchbase, SimilarWeb, investor reports, press releases)

**Critical Question**: How are competitors making money? Can we compete on pricing AND margin?

---

## PART 4: SWITCHING COST ANALYSIS

**MOST CRITICAL SECTION**: Why would existing users switch FROM competitors TO us?

For each major competitor, analyze:

### 4.1 From `{Competitor_A}` (e.g., Sparkle - Mac General Users)

**Their Strengths**:
- `{strength_1}` (e.g., "Automatic, Mac-native, personalized")
- `{strength_2}` (e.g., "One-click cleanup, no manual work")

**Their Weaknesses**:
- `{weakness_1}` (e.g., "Mac-only, excludes 75% of desktop users")
- `{weakness_2}` (e.g., "Imprecise categorization, filename-based only")
- `{weakness_3}` (e.g., "One-time cleanup, no ongoing maintenance")

**User Pain Points** (from reviews, forums):
- `{pain_1}` (e.g., "Doesn't work on Windows, need cross-platform")
- `{pain_2}` (e.g., "Miscategorizes files, need content understanding")
- `{pain_3}` (e.g., "Cleanup is temporary, files get messy again")

**Switching Barrier** (quantify):
- **Sunk Cost**: `{dollar_amount}` (e.g., $20 one-time purchase = LOW)
- **Time Cost**: `{hours}` (e.g., <1 hour to set up new tool = LOW)
- **Learning Curve**: `{LOW | MEDIUM | HIGH}` (e.g., LOW if similar UX)
- **Lock-in Effects**: `{none | mild | strong}` (e.g., NONE, files stay in OS)
- **Overall Barrier**: **`{LOW | MEDIUM | HIGH}`**

**What We MUST Offer to Win**:
1. `{requirement_1}` (e.g., "Cross-platform (Windows + Mac + Linux)")
2. `{requirement_2}` (e.g., "Content understanding (OCR + LLM) vs filename-based")
3. `{requirement_3}` (e.g., "Ongoing maintenance (continuous monitoring)")
4. `{requirement_4}` (e.g., "Granular control (rules, profiles, preview)")

**Is It Enough?** (Be brutally honest):
- **Realistic Switching Likelihood**: `{percentage}%` (e.g., 40-50%)
- **Rationale**: `{why_this_percentage}` (e.g., "Cross-platform + content understanding is 2-3x better, not 10x. Many Mac users happy with Sparkle 'good enough' solution.")

**Source**: `{user_reviews_link, competitor_forum, G2_reviews}`

---

### 4.2 From `{Competitor_B}` (e.g., ChronoVault - Legal Professionals)

[Repeat structure above]

**Switching Barrier**: **`{HIGH}`** (e.g., $3K-$10K sunk cost in training/setup, 10-40 hours migration, mission-critical for trials)

**Realistic Switching Likelihood**: `{percentage}%` (e.g., 30-40%)

---

[Repeat for 3-5 major competitors]

---

### 4.3 Switching Cost Tiers (Summary)

| Barrier Level | Cost | Time | Competitors | Switching Likelihood | Strategy |
|---------------|------|------|-------------|----------------------|----------|
| **LOW** | <$100 | <1 hour | `{competitors}` | 40-60% | Target first (easiest wins) |
| **MEDIUM** | $100-$1,000 | 1-10 hours | `{competitors}` | 20-40% | Target if strong differentiation |
| **HIGH** | >$1,000 | >10 hours | `{competitors}` | 10-30% | Target only if 10x better + desperate pain |

**Critical Question**: Are switching costs too high to acquire customers profitably?

---

## PART 5: TRUE DIFFERENTIATION ANALYSIS

### 5.1 What We Do 10x Better (Not 10% Better)

**❌ WEAK Differentiation** (avoid these claims):
- `{weak_claim_1}` (e.g., "We're cross-platform" – competitors can add this easily)
- `{weak_claim_2}` (e.g., "We're privacy-first" – niche concern, many prefer cloud)
- `{weak_claim_3}` (e.g., "We're cheaper" – race to bottom, unsustainable)

**✅ STRONG Differentiation** (10x outcome, not 10% better):
- `{strong_diff_1}` (e.g., "First AI file organizer that understands document CONTENT (OCR+LLM), not just filenames. 90%+ categorization accuracy vs competitors' 60-70%.")
- `{strong_diff_2}` (e.g., "Only product with scenario-based packs (tax/BAS, immigration, legal timelines) that save users 50-80% accountant/lawyer fees.")
- `{strong_diff_3}` (e.g., "Combines general-purpose file organization WITH professional legal/tax features at 1/5th the price of enterprise tools.")

**Quantify the 10x**:
- **Baseline** (competitor): `{baseline_metric}` (e.g., "Sparkle: 60-70% accuracy, $20 one-time")
- **Our Product**: `{our_metric}` (e.g., "Us: 90%+ accuracy, $10/mo with ongoing maintenance")
- **10x Calculation**: `{calculation}` (e.g., "1.5x accuracy + ongoing value = 3-5x better, NOT 10x. Honest assessment: This is 3x better, not 10x.")

**Critical Question**: Is this TRULY 10x better, or just 2-3x? Be honest. If not 10x, can we make it 10x?

---

### 5.2 Unfair Advantages

What competitive advantages are **defensible** (hard for competitors to replicate)?

1. **`{advantage_1}`** (e.g., "Proprietary training data from 100K users × 1,000 corrections = 100M examples")
   - **Defensibility**: `{LOW | MEDIUM | HIGH}` (e.g., MEDIUM - competitors can build over 12-24 months)

2. **`{advantage_2}`** (e.g., "Brand/trust in legal community via partnerships with legal aid orgs")
   - **Defensibility**: `{defensibility_level}`

3. **`{advantage_3}`** (e.g., "Network effects: User-generated rules shared via community")
   - **Defensibility**: `{defensibility_level}`

**Sources**:
- `{source_for_advantage_validation}`

---

### 5.3 Competitive Moat (Defensibility Framework)

| Moat Type | Description | Strength | Time to Replicate | Rationale |
|-----------|-------------|----------|-------------------|-----------|
| **Technology Barrier** | `{tech_description}` | `{LOW | MEDIUM | HIGH}` | `{months}` | `{rationale}` |
| **Data Advantage** | `{data_description}` | `{strength}` | `{months}` | `{rationale}` |
| **Network Effects** | `{network_description}` | `{strength}` | `{months}` | `{rationale}` |
| **Brand/Trust** | `{brand_description}` | `{strength}` | `{months}` | `{rationale}` |
| **Regulatory/Compliance** | `{regulatory_description}` | `{strength}` | `{months}` | `{rationale}` |

**Overall Moat Strength**: `{WEAK | MODERATE | STRONG}`

**Time to Competitive Parity**: `{months}` (How long until competitors catch up if we launch successfully?)

**Critical Question**: Do we have a DEFENSIBLE advantage or just a temporary edge?

---

### 5.4 Wedge Thesis

What's our **wedge** into the market? (How do we gain initial traction before competitors react?)

**Wedge Strategy**:
1. **Initial Beachhead**: `{segment}` (e.g., "Windows users frustrated by lack of Sparkle alternative")
2. **Why This Wedge**: `{rationale}` (e.g., "Sparkle doesn't serve Windows, 75% of desktop market, LOW competitive intensity")
3. **Expand From Wedge**: `{expansion_path}` (e.g., "Once established on Windows, expand to Mac with '10x better than Sparkle' positioning")

**Critical Question**: Can we establish dominance in the wedge BEFORE competitors react?

---

## PART 6: PRICING STRATEGY & REVENUE MODEL

### 6.1 Competitor Pricing Analysis

| Competitor | Pricing Model | Free Tier | Paid Tier(s) | Enterprise | Conversion Rate |
|------------|---------------|-----------|--------------|------------|-----------------|
| `{competitor_1}` | `{model}` | `{free_features}` | `{paid_price}` | `{enterprise_price}` | `{conversion}%` |
| `{competitor_2}` | ... | ... | ... | ... | ... |

**Insights**:
- **Average ARPU**: `{average_ARPU}` (e.g., $15/mo for SaaS, $50 one-time for desktop apps)
- **Freemium Conversion**: `{freemium_conversion}%` (industry benchmark: 2-5% for SaaS, <1% for consumer apps)
- **Price Sensitivity**: `{HIGH | MEDIUM | LOW}` (based on user reviews, churn data)

**Sources**:
- `{competitor_pricing_pages}`
- `{industry_reports}` (e.g., "SaaS freemium conversion benchmarks")

---

### 6.2 Proposed Multi-Tier Strategy

Design pricing tiers to **maximize market capture** (mass market + premium users):

#### **Tier 1: Free** (Mass Market Capture)

**Purpose**: `{purpose}` (e.g., "Acquire 100K+ users, demonstrate value, convert 5-10% to paid")

**Features**:
- `{feature_1}` (e.g., "1,000 files/month limit")
- `{feature_2}` (e.g., "Basic AI categorization, local only")
- `{feature_3}` (e.g., "Manual export, no automated packs")

**Limitations**:
- `{limitation_1}` (e.g., "No cloud OCR/LLM")
- `{limitation_2}` (e.g., "No scenario packs")

**Target Users**: `{target}` (e.g., "Students, casual users, 'try before buy'")

---

#### **Tier 2: Pro** (`{pro_price}`/month) (Power Users)

**Purpose**: `{purpose}` (e.g., "Convert freemium users who hit limits or want advanced features")

**Features** (everything in Free, PLUS):
- `{pro_feature_1}` (e.g., "Unlimited files/month")
- `{pro_feature_2}` (e.g., "Cloud OCR/LLM fallback for tricky docs")
- `{pro_feature_3}` (e.g., "Rules & Profiles engine, natural-language rule builder")
- `{pro_feature_4}` (e.g., "Semantic search and Q&A")

**Target Users**: `{target}` (e.g., "Freelancers, sole traders, power users")

**Conversion Assumption**: `{conversion}%` of free users (industry benchmark: 5-8% for productivity SaaS)

---

#### **Tier 3: Business** (`{business_price}`/month) (High-ARPU Specialists)

**Purpose**: `{purpose}` (e.g., "High-ARPU segment with specialized needs – legal, tax, immigration professionals")

**Features** (everything in Pro, PLUS):
- `{business_feature_1}` (e.g., "Legal evidence timeline cockpit with court-ready exports")
- `{business_feature_2}` (e.g., "Tax/BAS pack builder with country-specific templates")
- `{business_feature_3}` (e.g., "Immigration pack builder with visa-specific checklists")
- `{business_feature_4}` (e.g., "Priority support, advanced OCR with handwriting")

**Target Users**: `{target}` (e.g., "Solo legal practitioners, accountants, immigration consultants, self-represented litigants, sole traders with tax obligations")

**Conversion Assumption**: `{conversion}%` of users who start a pack workflow (e.g., 30-40%)

---

#### **Tier 4: Enterprise** (Custom) (Phase 2+)

**Purpose**: `{purpose}` (e.g., "Teams, firms, consultancies")

**Features** (everything in Business, PLUS):
- `{enterprise_feature_1}` (e.g., "Team features, shared rules, collaborative packs")
- `{enterprise_feature_2}` (e.g., "API access for integrations")
- `{enterprise_feature_3}` (e.g., "SSO, user management, on-premise deployment option")

**Target Users**: `{target}` (e.g., "Law firms (5-50 lawyers), accounting firms, immigration consultancies")

**Launch**: Defer to Month 18+ (focus on individual users first)

---

### 6.3 Revenue Projections

**Assumptions**:
- Tier mix: `{free_percentage}%` Free, `{pro_percentage}%` Pro, `{business_percentage}%` Business
- Conversion rates: Year 1 (`{Y1_conversion}%`), Year 3 (`{Y3_conversion}%`), Year 5 (`{Y5_conversion}%`)
- Churn: `{churn_rate}%` annual (retention `{retention_months}` months)
- ARPU: Weighted average `{weighted_ARPU}` (Pro `{pro_ARPU}` × `{pro_mix}%` + Business `{business_ARPU}` × `{business_mix}%`)

| Year | Total Users | Paid Users | Conversion | ARPU | **Revenue** | **Profit** (Margin) |
|------|-------------|------------|------------|------|-------------|---------------------|
| 1    | `{Y1_users}` | `{Y1_paid}` | `{Y1_conv}%` | `{Y1_ARPU}` | **`{Y1_revenue}`** | `{Y1_profit}` (`{Y1_margin}%`) |
| 3    | `{Y3_users}` | `{Y3_paid}` | `{Y3_conv}%` | `{Y3_ARPU}` | **`{Y3_revenue}`** | `{Y3_profit}` (`{Y3_margin}%`) |
| 5    | `{Y5_users}` | `{Y5_paid}` | `{Y5_conv}%` | `{Y5_ARPU}` | **`{Y5_revenue}`** | `{Y5_profit}` (`{Y5_margin}%`) |

**Sensitivity Analysis**:
- If conversion `{sensitivity_conversion_low}%` (pessimistic): Revenue `{revenue_low}`
- If ARPU `{sensitivity_ARPU_low}` (pessimistic): Revenue `{revenue_ARPU_low}`
- If churn `{sensitivity_churn_high}%` (pessimistic): LTV `{LTV_pessimistic}`, Revenue `{revenue_churn_high}`

**Critical Question**: Are these projections realistic given competitive intensity and switching barriers?

---

## PART 7: PROFITABILITY ANALYSIS

### 7.1 Unit Economics (Weighted Average)

**Customer Acquisition Cost (CAC)** (weighted across segments):
- **Segment 1 CAC**: `{CAC_1}` (channel: `{channel_1}`, e.g., content marketing $30-$50)
- **Segment 2 CAC**: `{CAC_2}` (channel: `{channel_2}`, e.g., paid ads $100-$200)
- **Segment 3 CAC**: `{CAC_3}` (channel: `{channel_3}`, e.g., partnerships $50-$100)
- **Weighted Average CAC**: **`{weighted_CAC}`**
- **Source**: `{source_for_CAC}` (industry benchmarks, similar products, agency quotes)

**Lifetime Value (LTV)** (weighted across tiers):
- **Free Tier LTV**: $0 (monetizes via conversion to paid)
- **Pro Tier LTV**: `{pro_LTV}` (formula: `{pro_ARPU}` × `{retention_months}` months × `{gross_margin}%`)
- **Business Tier LTV**: `{business_LTV}`
- **Weighted Average LTV**: **`{weighted_LTV}`**
- **Source**: `{source_for_churn}` (industry averages, competitor data, cohort analysis)

**LTV/CAC Ratio**: **`{LTV_CAC_ratio}`**
- ✅ **EXCELLENT** (>6.0): Highly profitable, strong unit economics
- ✅ **GOOD** (3.0-6.0): Healthy, sustainable business
- ⚠️ **MARGINAL** (1.5-3.0): Acceptable for freemium mass market, risky otherwise
- ❌ **POOR** (<1.5): Unprofitable, don't build unless capital-intensive network effects play

**Payback Period**: **`{payback_months}` months**
- Formula: `{CAC}` / (`{ARPU}` × `{gross_margin}%`)
- ✅ **GOOD** (<12 months): Can reinvest quickly
- ⚠️ **ACCEPTABLE** (12-18 months): Requires capital for growth
- ❌ **RISKY** (>18 months): High capital requirement, slow growth

**Sources**:
- `{source_for_unit_economics}` (e.g., SaaS Capital benchmarks, competitor investor decks)

---

### 7.2 Cost Structure

Break down all costs (fixed + variable):

#### **Development Costs** (One-time + Ongoing)

- **Initial Build**: `{dev_cost_initial}` (e.g., $200K-$300K for 6-9 month MVP)
  - Salaries: `{salaries}` (e.g., 2 engineers × $100K × 6 months = $100K)
  - Tools/Services: `{tools}` (e.g., cloud credits, APIs, software licenses = $10K)
  - Contingency: `{contingency}` (20% buffer = $22K)
- **Ongoing Maintenance**: `{dev_cost_ongoing}` /month (e.g., $20K-$30K/mo for 1-2 engineers)

#### **Infrastructure Costs** (Variable with Users)

- **Hosting**: `{hosting_cost}` per 1,000 users/month (e.g., AWS/GCP ~$500-$1,000)
- **Cloud APIs** (OCR/LLM): `{API_cost}` per paid user/month (e.g., $0.50-$2.00/user)
- **Storage**: `{storage_cost}` per TB/month (e.g., $20-$50)
- **Bandwidth**: `{bandwidth_cost}` per TB/month (e.g., $80-$120)

#### **Marketing Costs** (Variable with Acquisition)

- **Content Marketing**: `{content_cost}` (e.g., SEO, blog, YouTube = $5K-$10K/mo)
- **Paid Ads** (if used): `{ads_cost}` (e.g., Google Ads, LinkedIn Ads = $10K-$30K/mo)
- **Partnerships**: `{partnership_cost}` (e.g., affiliate commissions = 20% of revenue from referred users)

#### **Support Costs**

- **Free/Pro Tier**: Email support only, `{support_cost_low}` per user/month (e.g., $0.10)
- **Business Tier**: Priority support (email + chat), `{support_cost_high}` per user/month (e.g., $5-$10)

#### **Total Cost Structure** (Example for 1,000 Paid Users)

| Cost Category | Fixed/Month | Variable/User/Month | Total (1,000 users) |
|---------------|-------------|---------------------|---------------------|
| Development (Ongoing) | `{dev_fixed}` | - | `{dev_total}` |
| Infrastructure | `{infra_fixed}` | `{infra_variable}` | `{infra_total}` |
| Marketing | `{marketing_fixed}` | `{CAC_amortized}` | `{marketing_total}` |
| Support | - | `{support_variable}` | `{support_total}` |
| **TOTAL COSTS** | `{total_fixed}` | `{total_variable}` | **`{total_cost}`** |

**Gross Margin**: `{gross_margin}%` (e.g., 70% for SaaS is typical, 50-60% for infrastructure-heavy)

---

### 7.3 Break-Even Analysis

**Break-even Point** (when revenue = costs):
- **Formula**: Fixed Costs / (ARPU × Gross Margin%)
- **Break-even Paying Users**: **`{breakeven_users}`** (e.g., 5,000-8,000 paying users)
- **Break-even Total Users** (assuming `{conversion}%` conversion): **`{breakeven_total_users}`** (e.g., 100,000-160,000 total users if 5% conversion)
- **Time to Break-even**: **`{breakeven_months}` months** (e.g., 18-24 months)
  - Assumptions: User growth rate `{growth_rate}%`/month

**Path to Profitability**:
1. **Month 6**: `{M6_users}` users, `{M6_paid}` paying, `{M6_revenue}` revenue, `{M6_burn}` burn rate → **-`{M6_loss}`** loss
2. **Month 12**: `{M12_users}` users, `{M12_paid}` paying, `{M12_revenue}` revenue, `{M12_burn}` burn rate → **-`{M12_loss}`** loss
3. **Month 18**: `{M18_users}` users, `{M18_paid}` paying, `{M18_revenue}` revenue, `{M18_burn}` burn rate → **Break-even or +`{M18_profit}`** profit
4. **Year 3**: `{Y3_users}` users, `{Y3_paid}` paying, `{Y3_revenue}` revenue → **+`{Y3_profit}`** profit (`{Y3_margin}%` margin)

**Capital Requirement** (to reach break-even):
- **Total Capital Needed**: **`{capital_required}`** (e.g., $400K-$600K)
  - Development: `{dev_capital}`
  - Marketing: `{marketing_capital}`
  - Infrastructure: `{infra_capital}`
  - Runway: `{runway_months}` months to break-even

**Funding Strategy**: `{bootstrap | seed_round | series_A}`
- If **bootstrap**: Scope down MVP to `{bootstrap_cost}`, slower growth
- If **seed round**: Raise `{seed_amount}`, target `{seed_milestones}` for Series A
- If **Series A**: Raise `{series_A_amount}` after proving unit economics at `{series_A_threshold}` users

**Critical Question**: Is this financially viable given capital requirements and time to profitability?

---

## PART 8: TECHNICAL FEASIBILITY & RISK

### 8.1 Technology Limitations (Current State of the Art)

What are the **current technical constraints** that affect product viability?

| Technology Area | Current Limitation | Impact on Product | Workaround/Mitigation | Risk Level |
|-----------------|-------------------|-------------------|----------------------|------------|
| `{tech_area_1}` | `{limitation_1}` | `{impact_1}` | `{workaround_1}` | `{risk_level_1}` |
| `{tech_area_2}` | `{limitation_2}` | `{impact_2}` | `{workaround_2}` | `{risk_level_2}` |

**Examples**:
- **OCR Accuracy**: Tesseract ~30% on complex docs, GPT-4 Vision ~80% (expensive). Impact: May need hybrid approach, affects cost. Risk: MEDIUM.
- **Local LLM Performance**: 7B models score 3.85/5 on legal tasks (vs GPT-4o 4.5/5). Impact: May need cloud fallback. Risk: MEDIUM.
- **Cross-platform UI Consistency**: Tauri WebView differences (CSS rendering). Impact: UI bugs on Linux/Windows. Risk: LOW (extensive testing mitigates).

**Sources**:
- `{source_for_tech_benchmarks}` (research papers, vendor docs, benchmarking sites)

---

### 8.2 Development Risks

| Risk | Likelihood | Impact | Mitigation | Contingency |
|------|-----------|--------|------------|-------------|
| **`{risk_1}`** | `{L/M/H}` | `{L/M/H}` | `{mitigation_1}` | `{contingency_1}` |
| **`{risk_2}`** | `{L/M/H}` | `{L/M/H}` | `{mitigation_2}` | `{contingency_2}` |

**Examples**:
- **Local LLM insufficient for legal inference** (Likelihood: MEDIUM, Impact: HIGH)
  - Mitigation: Hybrid approach (local primary, cloud fallback), extensive testing with real case files
  - Contingency: Offer cloud-only mode for Business tier at lower price
- **50-phase build takes 2x longer (12-18 months vs 6-9)** (Likelihood: HIGH, Impact: CRITICAL)
  - Mitigation: Scope down to 30-40 phases, defer features to Phase 2
  - Contingency: Pivot to Legal-only (simpler MVP), or raise bridge funding

---

### 8.3 Cost vs Revenue Feasibility

**Development Cost vs Year 1 Revenue**:
- **Estimated Dev Cost**: `{dev_cost_total}` (e.g., $200K-$300K for MVP)
- **Year 1 Revenue**: `{Y1_revenue}` (e.g., $108K)
- **ROI Year 1**: `{Y1_ROI}` (e.g., -64% = loss of $192K-$92K)

**Development Cost vs Year 3 Revenue**:
- **Total Dev Cost** (incl ongoing): `{dev_cost_Y3}` (e.g., $200K initial + $20K/mo × 36 months = $920K cumulative)
- **Year 3 Revenue**: `{Y3_revenue}` (e.g., $1.92M)
- **Year 3 Profit**: `{Y3_profit}` (e.g., $1.22M after costs)
- **Cumulative ROI**: `{cumulative_ROI}` (e.g., +33% = profit of $300K after recovering $920K costs)

**Critical Question**: Do we have the resources to sustain 18-24 month burn to break-even? Is the risk acceptable?

---

## PART 9: FEATURE & WORKFLOW OPPORTUNITIES

### 9.1 Core Product Features (What to Build)

Based on competitive gaps and user pain points:

| Feature Category | Must-Have (MVP) | Should-Have (Phase 2) | Nice-to-Have (Phase 3+) | Differentiation Impact |
|------------------|-----------------|----------------------|-------------------------|------------------------|
| `{category_1}` | `{must_have_1}` | `{should_have_1}` | `{nice_to_have_1}` | `{impact_1}` |
| `{category_2}` | `{must_have_2}` | `{should_have_2}` | `{nice_to_have_2}` | `{impact_2}` |

**Examples**:
- **AI Content Understanding**: Must-Have (OCR + LLM for categorization), Should-Have (Semantic search), Nice-to-Have (Voice Q&A). Impact: HIGH (10x differentiation driver).
- **Scenario Packs**: Must-Have (Generic templates), Should-Have (Country-specific tax/immigration), Nice-to-Have (User-generated pack sharing). Impact: HIGH (unique to us).

**Prioritization Criteria**:
1. **Differentiation Impact**: Does this create 10x advantage? (High priority)
2. **Segment Value**: Which segments care most? (Align with segment priority)
3. **Technical Feasibility**: Can we build with current tech? (Risk assessment)
4. **Cost/Benefit**: Does revenue from feature justify dev cost? (ROI)

---

### 9.2 Domain-Specific Workflows (Packs/Templates)

If product involves **scenario-based** or **domain-specific** workflows (e.g., tax prep, legal evidence, onboarding flows):

**Pack/Workflow Opportunities**:

| Pack/Workflow Type | Target Segment | Revenue Impact | Complexity | Priority |
|--------------------|----------------|----------------|------------|----------|
| `{pack_1}` | `{segment_1}` | `{revenue_impact_1}` | `{complexity_1}` | `{priority_1}` |
| `{pack_2}` | `{segment_2}` | `{revenue_impact_2}` | `{complexity_2}` | `{priority_2}` |

**Examples**:
- **Tax/BAS Pack (Rideshare Driver)**: Segment = Sole traders, Revenue = $50/mo × 10K users = $500K/year, Complexity = MEDIUM, Priority = HIGH (clear pain, high WTP).
- **Immigration Pack (Partner Visa)**: Segment = Visa applicants, Revenue = $50 one-time × 50K users = $2.5M, Complexity = LOW, Priority = HIGH (desperate pain, willing to pay).

**Pack Design Principles**:
1. **Configuration-Driven**: New packs via YAML/JSON templates, not code changes
2. **Country/Locale Variants**: Same pack structure, different field mappings per jurisdiction
3. **Explainability**: Every output links back to source data (traceability)
4. **No Legal/Tax Advice**: Disclaimers, focus on organization not eligibility

---

### 9.3 Data & Telemetry Strategy

**Purpose**: Understand product usage, improve features, train models (while respecting privacy)

**Data Collection Levels**:

#### **Level 0: Minimal Analytics** (Default, Always-On)
- **What**: Pseudonymous user ID, OS, app version, RAM, feature usage counts, performance metrics
- **What NOT**: No file paths, no filenames, no extracted text, no embeddings
- **Purpose**: Product analytics (which features used, error rates, performance bottlenecks)
- **Privacy**: GDPR/CCPA compliant, no PII

#### **Level 1: "Help Improve" Opt-In**
- **What**: Aggregated, content-adjacent stats (e.g., "many users use `[Date]_[Vendor]_[Amount]` naming pattern")
- **What NOT**: No raw content, no individual user data
- **Purpose**: Improve categorization rules, suggest better presets
- **Privacy**: Aggregated only, no re-identification possible

#### **Level 2: Content-Based Telemetry** (Avoid for Sensitive Domains)
- **What**: Embeddings, anonymized document snippets (for model training)
- **When**: ONLY if user explicitly opts in with high-friction consent (not legal/tax/immigration domains)
- **Purpose**: Train better models (e.g., improve OCR, categorization)
- **Privacy**: Strict retention policies (delete after 90 days), no raw content

**User Controls**:
- Global toggle: "Send anonymous usage data" (Level 0)
- Separate toggle: "Help improve FileOrganizer" (Level 1)
- High-friction opt-in for Level 2 (if ever implemented)
- Easy data deletion request

**Critical Principle**: Privacy-first products (legal, tax, immigration) must default to Level 0 only. Consumer products can offer Level 1 opt-in.

---

## PART 10: RISK MATRIX & PIVOT OPTIONS

### 10.1 Top 10 Risks (Likelihood × Impact)

| # | Risk | Likelihood (1-10) | Impact (1-10) | Priority Score | Mitigation | Contingency |
|---|------|-------------------|---------------|----------------|------------|-------------|
| 1 | `{risk_1}` | `{L1}` | `{I1}` | **`{L1 × I1}`** | `{mitigation_1}` | `{contingency_1}` |
| 2 | `{risk_2}` | `{L2}` | `{I2}` | **`{L2 × I2}`** | `{mitigation_2}` | `{contingency_2}` |
| ... | ... | ... | ... | ... | ... | ... |
| 10 | `{risk_10}` | `{L10}` | `{I10}` | **`{L10 × I10}`** | `{mitigation_10}` | `{contingency_10}` |

**Examples**:
1. **Sparkle adds cross-platform** (Likelihood: 7, Impact: 8, Score: 56)
   - Mitigation: Execute fast (12-18 month window), build data moat, focus on scenario packs Sparkle won't have
   - Contingency: Position as "Sparkle for cleanup, FileOrganizer for life admin and legal work"

2. **Differentiation insufficient (not 10x)** (Likelihood: 6, Impact: 10, Score: 60)
   - Mitigation: Measure 90%+ categorization accuracy, A/B test vs Sparkle, validate with beta users
   - Contingency: If <10x, pivot to Legal-only (clearer 10x for that segment)

**Critical Risks** (Priority Score >50): `{list_critical_risks}`

---

### 10.2 Pivot Triggers (When to Change Strategy)

Define **specific metrics** that trigger strategic pivots:

#### **Pivot 1: From General to Legal-Only**
- **Trigger Conditions**:
  - Month 6: If General user conversion <`{threshold_conversion}%` (vs `{legal_conversion}%` for legal pack users)
  - Month 12: If General user churn >`{threshold_churn}%` (vs <`{legal_churn}%` for Business tier)
- **Action**: Focus all marketing on legal professionals, raise Business tier to $`{new_price}`/mo, discontinue free tier

#### **Pivot 2: From Local-First to Cloud-First**
- **Trigger Conditions**:
  - Month 12: If >`{threshold_cloud_preference}%` of users prefer cloud OCR/LLM despite privacy concerns
  - Month 18: If local LLM accuracy consistently <`{threshold_accuracy}%` (vs cloud LLM `{cloud_accuracy}%`)
- **Action**: Offer cloud-only tier at lower price ($`{cloud_price}`/mo), keep local-first for privacy-conscious users

#### **Pivot 3: From Freemium to Paid-Only**
- **Trigger Conditions**:
  - Month 12: If freemium conversion <`{threshold_freemium}%` (vs industry benchmark `{industry_benchmark}%`)
  - Month 18: If free tier costs (support + infrastructure) exceed `{threshold_cost}%` of paid tier revenue
- **Action**: Discontinue free tier, offer 14-day free trial instead

#### **Pivot 4: Shut Down**
- **Trigger Conditions**:
  - Month 18: If <`{threshold_users}` paying users (vs target `{target_users}` for break-even)
  - Month 24: If still not profitable and unable to raise funding
- **Action**: Offer refunds, open-source codebase (good for brand/reputation), graceful shutdown

**Critical Question**: What's the sunk cost we're willing to accept before pivoting or shutting down? (e.g., $200K, 12 months)

---

### 10.3 Kill Criteria (When NOT to Build)

**Dealbreakers** (If ANY of these are true, this is a NO-GO):

1. **TAM too small**: TAM <`{min_TAM}` (e.g., <$100M for bootstrapped, <$1B for VC-backed)
2. **Switching barrier too high**: >80% of target users have HIGH switching barrier AND switching likelihood <20%
3. **No 10x differentiation**: After honest analysis, product is only 2-3x better, not 10x
4. **Weak unit economics**: LTV/CAC <`{min_LTV_CAC}` (e.g., <1.5) with no path to improvement
5. **Unfundable**: Capital requirement >$`{max_capital}` (e.g., >$1M) and unable to raise
6. **Technical infeasibility**: Critical features require breakthroughs that don't exist (e.g., AGI, cold fusion)
7. **Regulatory impossibility**: Product is illegal or requires impossible compliance (e.g., crypto in banned jurisdictions)

**Current Status**: `{GO | CONDITIONAL GO | NO-GO}`

If **CONDITIONAL GO**, what conditions MUST be met?: `{list_conditions}`

---

## PART 11: GO/NO-GO RECOMMENDATION

### 11.1 Scoring (Out of 10)

| Dimension | Score | Rationale |
|-----------|-------|-----------|
| **Market Opportunity** | `{market_score}`/10 | `{market_rationale}` (TAM size, growth rate, accessibility) |
| **Competitive Position** | `{competitive_score}`/10 | `{competitive_rationale}` (Differentiation, defensibility, switching likelihood) |
| **Financial Viability** | `{financial_score}`/10 | `{financial_rationale}` (Unit economics, time to profitability, revenue potential) |
| **Technical Feasibility** | `{technical_score}`/10 | `{technical_rationale}` (Current tech readiness, development risk, cost feasibility) |

**Overall Score**: **`{overall_score}`/10**

**Calculation**: Average of 4 dimensions (or weighted if some more critical)

---

### 11.2 Decision Framework

| Score Range | Decision | Confidence | Action |
|-------------|----------|------------|--------|
| **8-10** | **Strong GO** | High confidence | Build with full commitment, raise funding if needed |
| **6-7** | **Conditional GO** | Moderate confidence | Build with **specific conditions** and **pivot triggers** |
| **4-5** | **PIVOT** | Low confidence | Rethink core assumptions, consider different segment/market/approach |
| **1-3** | **NO-GO** | Very low confidence | Don't build, too many dealbreakers |

**This Product's Decision**: **`{decision}`** (`{overall_score}`/10)

---

### 11.3 Recommendation

#### **If GO**:

**Top 3 Strategic Imperatives** (MUST get right):
1. **`{imperative_1}`** (e.g., "Nail 10x differentiation: 90%+ categorization accuracy vs competitors' 60-70%")
2. **`{imperative_2}`** (e.g., "Execute fast: Ship MVP in 6-9 months, acquire 5K users in 18 months before competitors react")
3. **`{imperative_3}`** (e.g., "Build data moat: 100K users × 1,000 corrections = 100M training examples competitors can't replicate")

**Biggest Risk to Success**: `{biggest_risk}` (e.g., "Weak competitive moat – 12-24 month lead easily replicable")

**Segment Prioritization**: Target `{priority_segment}` first because `{segment_rationale}`

**10x Differentiation Statement**: `{differentiation_statement}` (e.g., "First AI file organizer that understands document CONTENT, not just filenames, with 90%+ accuracy + scenario packs for tax/legal/immigration at 1/5th enterprise tool prices")

**MVP Scope**: `{MVP_phases}` phases over `{MVP_months}` months, defer `{deferred_features}` to Phase 2

---

#### **If CONDITIONAL GO**:

**Conditions for Success**:
1. `{condition_1}` (e.g., "Validate 10x differentiation in Month 3 alpha: 90%+ accuracy confirmed")
2. `{condition_2}` (e.g., "Monitor General user conversion at Month 6: If <5%, pivot to Legal-only")
3. `{condition_3}` (e.g., "Secure $`{capital}`K capital for 18-24 month runway to break-even")

**Red Flags to Watch**:
- `{red_flag_1}` (e.g., "If Sparkle announces cross-platform in Month 6")
- `{red_flag_2}` (e.g., "If local LLM accuracy <70% in Month 3 testing")

**Pivot Triggers**: See section 10.2 for specific metrics

---

#### **If NO-GO**:

**Dealbreakers**:
1. `{dealbreaker_1}` (e.g., "Switching barrier too high: 80% of legal users have HIGH barrier, only 20% likely to switch")
2. `{dealbreaker_2}` (e.g., "No 10x differentiation: Honest analysis shows only 2x better than incumbents")
3. `{dealbreaker_3}` (e.g., "Weak unit economics: LTV/CAC = 0.8, unprofitable at scale")

**What Would Make It Viable**:
- `{viability_change_1}` (e.g., "If we could achieve 10x better accuracy (95%+) via proprietary AI")
- `{viability_change_2}` (e.g., "If incumbents raised prices 3-5x, creating price umbrella")
- `{viability_change_3}` (e.g., "If new regulation created compliance burden incumbents can't meet")

**Likelihood of Changes**: `{likelihood}` (e.g., LOW – don't wait, explore other opportunities)

---

## PART 12: NEXT 90 DAYS (If GO)

### 12.1 Immediate Actions (Week 1-4)

1. **`{action_1}`** (e.g., "Validate 10x differentiation with 20 alpha testers: Measure categorization accuracy vs Sparkle")
2. **`{action_2}`** (e.g., "Define pack configuration schema (YAML/JSON) for tax/immigration/legal templates")
3. **`{action_3}`** (e.g., "Secure $`{capital}`K seed funding or bootstrap with $`{bootstrap_capital}`K personal capital")
4. **`{action_4}`** (e.g., "Recruit 50 beta users from target segment (e.g., Windows users, solo legal practitioners)")

---

### 12.2 Build Plan (Month 1-3)

**Phase 1: Foundation** (Months 1-2)
- `{build_milestone_1}` (e.g., "Core infrastructure: Desktop app shell, database, file scanner, onboarding")

**Phase 2: AI Capabilities** (Months 2-3)
- `{build_milestone_2}` (e.g., "OCR + LLM integration: Local (Tesseract, Qwen2-7B) + cloud fallback (GPT-4 Vision, GPT-4o)")

**Deliverable Month 3**: `{month_3_deliverable}` (e.g., "Alpha with 50 testers, 80% usability score, <5 critical bugs")

---

### 12.3 Market Validation (Month 1-3)

**Validation Experiments**:
1. **`{validation_1}`** (e.g., "Landing page + email signup: Target 1,000 signups in 30 days via ProductHunt, Reddit, HN")
2. **`{validation_2}`** (e.g., "Competitor user interviews: Talk to 20 Sparkle/ChronoVault users, validate pain points and switching likelihood")
3. **`{validation_3}`** (e.g., "Pricing survey: Test $5/$10/$20 Pro tier pricing with 100 survey respondents, measure WTP")

**Success Metrics Month 3**:
- `{metric_1}` (e.g., "1,000+ email signups (indicates demand)")
- `{metric_2}` (e.g., "50 alpha testers recruited (indicates user interest)")
- `{metric_3}` (e.g., "80%+ usability score (indicates product quality)")

---

## APPENDIX: SOURCES & METHODOLOGY

### Sources Used

List all sources with links:

1. **Market Size**: `{source_1}` (e.g., [Gartner: Enterprise File Management Market 2025](https://example.com))
2. **Competitor Pricing**: `{source_2}` (e.g., Sparkle website, ChronoVault pricing page)
3. **User Complaints**: `{source_3}` (e.g., G2 reviews, ProductHunt comments, Reddit r/productivity)
4. **Technology Benchmarks**: `{source_4}` (e.g., OCR accuracy research papers, LLM eval leaderboards)
5. **Unit Economics**: `{source_5}` (e.g., SaaS Capital benchmarks, investor decks)

... (list all 20-50 sources)

---

### Methodology Notes

**How TAM/SAM/SOM Calculated**:
- `{methodology_description}` (e.g., "Bottom-up: 200M desktop users globally × 10% addressable (productivity-focused) × $10 ARPU = $2B SAM")

**How Switching Likelihood Estimated**:
- `{methodology_description}` (e.g., "Based on user review sentiment analysis (500 reviews) + expert interviews (10 users)")

**How LTV/CAC Calculated**:
- `{methodology_description}` (e.g., "LTV = ARPU $10/mo × 20 months retention × 70% margin = $140. CAC = Blended $80 (content $30-$50 70%, paid ads $100-$200 30%). Ratio = 140/80 = 1.75")

---

## METADATA

**Document Version**: `{version}` (e.g., 2.0)
**Template Version**: 2.0
**Created**: `{date}`
**Last Updated**: `{date}`
**Analyst**: `{name}`
**Review Status**: `{draft | peer_reviewed | approved}`
**Next Review Date**: `{date}` (recommend quarterly updates for fast-moving markets)

---

**END OF TEMPLATE**

---

## HOW TO USE THIS TEMPLATE

1. **Copy this template** to a new file: `MARKET_RESEARCH_RIGOROUS_{PRODUCT_NAME}.md`
2. **Fill in ALL sections** with quantitative data, cite sources, be brutally honest
3. **Replace ALL `{placeholders}`** with actual values
4. **Validate assumptions** with real data (not guesses)
5. **Get peer review** from someone who will challenge your assumptions
6. **Feed to GPT** (using `GPT_STRATEGIC_ANALYSIS_UNIVERSAL.md` template) for strategic validation
7. **Update quarterly** as market/competitive landscape changes

**Critical Success Factors**:
- ✅ Quantify everything (TAM in $, CAC in $, switching likelihood in %)
- ✅ Segment-level detail (not just "the market" but 3-5 specific segments)
- ✅ Honest switching analysis (realistic likelihood, not wishful thinking)
- ✅ 10x differentiation test (if not 10x, say so explicitly)
- ✅ Risk-aware (identify dealbreakers early, don't hide weak moat)

**Common Mistakes to Avoid**:
- ❌ Using TAM without SAM/SOM (overstates opportunity)
- ❌ Analyzing only your favorite segment (misses larger markets)
- ❌ Assuming "build it and they will come" (ignores switching barriers)
- ❌ Claiming 10x when it's 2-3x (dishonest differentiation)
- ❌ Ignoring capital requirements (underestimates risk)

**This template is your truth-serum. Use it to prevent building unprofitable products.**
