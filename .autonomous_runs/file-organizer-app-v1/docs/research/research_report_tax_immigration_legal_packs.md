# Research Report: Tax/BAS, Immigration, and Legal Pack Formats

**Prepared for**: FileOrganizer Application Development
**Date**: 2025-11-27
**Scope**: Document formats, evidence categories, and packaging conventions for tax/BAS, immigration, and legal evidence packs across AU, UK, US, CA, and NZ jurisdictions

---

## Executive Summary

This research report documents the structural requirements, evidence categories, and submission formats for three core scenario pack domains (Tax/BAS, Immigration, Legal Evidence) across five target jurisdictions (Australia, United Kingdom, United States, Canada, New Zealand).

**Key Findings**:

1. **Strong Cross-Jurisdiction Invariants**: Despite different terminology and thresholds, all jurisdictions share common structural patterns:
   - Tax/BAS: Income categories, expense categories, GST/VAT calculations, registration thresholds
   - Immigration: Financial proof, relationship evidence, identity documents, cohabitation proof
   - Legal: Chronological timelines, indexed evidence bundles, source attribution

2. **Jurisdiction-Specific Variations**: Critical differences that require country-specific pack configurations:
   - Tax thresholds (AU: no threshold for ABN, UK: £85K for VAT, US: $400 for SE tax, CA: $30K for GST, NZ: $60K for GST)
   - Immigration financial requirements (AU: $9,365 fee, UK: £29K income/£88.5K savings, US: I-864 affidavit, CA: digital-only submission 2025, NZ: 12-month cohabitation)
   - Form structures and field naming conventions

3. **Common Packaging Patterns**:
   - Preference for category-organized PDFs with chronological ordering within categories
   - Index/table of contents requirements for bundles >100 pages
   - OCR-readable text requirement for digital submissions
   - Source attribution and reference numbering systems

**Design Implications for FileOrganizer**:
- Configuration-driven pack system can support 80%+ common structure with country-specific parameter overrides
- Category hierarchies (Income → Rideshare Income → Uber Earnings) map well to folder/tag structures
- Export templates must support both "combined PDF per category" and "individual documents with index" formats
- Clear disclaimer system needed to avoid positioning as tax/legal/immigration advice

---

## PART 1: TAX/BAS & VAT PACK FORMATS

### 1.1 Australia – BAS (Business Activity Statement)

#### 1.1.1 Forms and Concepts

**Primary Forms**:
- **BAS (Business Activity Statement)**: Quarterly or monthly reporting for businesses registered for GST
- **Key Fields**:
  - **G1**: Total sales (including GST)
  - **1A**: GST on sales
  - **1B**: GST on purchases
  - **W1-W4**: PAYG withholding (if applicable)
  - **5A/5B**: Wine equalization tax (for wine businesses)

**Registration Thresholds**:
- ABN (Australian Business Number): No threshold, free to register
- GST Registration: Required if turnover ≥ $75,000 ($150,000 for non-profit organizations)
- Voluntary registration allowed below threshold

**Reporting Periods**:
- Quarterly (most common for small businesses): Due 28 days after quarter end
- Monthly: For larger businesses or those with regular refunds
- Annual GST reporting: Available for turnover <$20M

#### 1.1.2 Evidence Categories for Sole Traders

**Income Categories**:
1. **Platform Payouts** (Rideshare/Delivery):
   - Uber driver statements
   - DoorDash/Menulog/Deliveroo earnings summaries
   - Platform fee breakdowns
   - Typical documents: Weekly/monthly payout summaries (PDF), bank deposit records

2. **Direct Client Invoices**:
   - Invoices issued to customers
   - Payment receipts
   - Typical documents: Invoice PDFs, bank transaction records

**Expense Categories** (Common Deductions):
1. **Vehicle/Fuel Expenses**:
   - Fuel receipts
   - Vehicle maintenance and repairs
   - Registration and insurance
   - Logbook records (required for >5,000 km business use)

2. **Phone and Internet**:
   - Monthly bills with business use percentage
   - Typical: 50-80% business use for rideshare drivers

3. **Equipment**:
   - Phone holders, charging cables
   - Insulated delivery bags
   - Cleaning supplies (for cleaners)

4. **Home Office** (if applicable):
   - Percentage of rent/mortgage, utilities
   - Shortcut method: $0.67 per hour (2024-25 rate)

**Evidence Timeframes**:
- Current quarter for quarterly BAS
- Full financial year (July 1 - June 30) for annual tax return

#### 1.1.3 Accountant Delivery Preferences

**Spreadsheet Layout** (Common format):
```
Date | Description | Category | Amount (Inc GST) | GST Component | Counterparty | Notes
```

**Document Organization**:
- **Preferred**: One folder per category, with descriptive filenames
  - Example: `Income_Rideshare/2024-Q3_Uber_Earnings.pdf`
  - Example: `Expenses_Fuel/2024-Q3_Fuel_Receipts_Combined.pdf`
- **Alternative**: Single combined PDF per category with bookmarks

**Submission Constraints**:
- myGov portal: PDF preferred, max 5MB per attachment
- Accountant handoff: Usually via email, Dropbox, or client portal (no strict limits)

#### 1.1.4 Category → Form Field Mappings

| Document Category | BAS Field | Notes |
|-------------------|-----------|-------|
| Rideshare/Delivery Income | G1 (Total Sales), 1A (GST on Sales) | Income typically includes 10% GST |
| Direct Client Invoices | G1, 1A | Same as above |
| Fuel Expenses (Business %) | 1B (GST on Purchases) | Can claim GST component if registered |
| Equipment Purchases | 1B | Claim GST if >$82.50 (inc GST) |
| Phone/Internet (Business %) | 1B | Claim proportional GST |

**Important**: FileOrganizer should NOT calculate tax, only organize evidence by category. Disclaimer required.

#### 1.1.5 Profession-Specific Templates

**Rideshare Drivers** (Uber, Ola, DiDi):
- High volume of small transactions (100-500+ trips per quarter)
- Platform statements are primary income evidence
- Fuel is largest expense category (often 30-40% of gross income)
- Logbook requirement if claiming >5,000 km

**Delivery Couriers** (DoorDash, Menulog, Uber Eats):
- Similar to rideshare, but may have lower per-trip earnings
- Equipment category includes insulated bags, phone holders
- Often combine with rideshare driving

**Cleaners**:
- Invoice-based income (direct client payments)
- Equipment: Cleaning supplies, vacuum, mop, protective gear
- Vehicle expenses if traveling to client locations
- May have fewer transactions than rideshare (20-50 clients/month)

**Freelance Professionals** (Designers, Writers, Consultants):
- Invoice-based income
- Home office percentage often higher (50-100%)
- Software subscriptions, professional development
- Less vehicle use

**Sources**:
- [Australian Taxation Office - Business Activity Statements](https://www.ato.gov.au/businesses-and-organisations/preparing-lodging-and-paying/business-activity-statements-bas)
- [ATO - GST Registration](https://www.ato.gov.au/businesses-and-organisations/gst-excise-and-indirect-taxes/goods-and-services-tax-gst/registering-for-gst)
- [ATO - Record Keeping for Tax](https://www.ato.gov.au/businesses-and-organisations/corporate-tax-measures-and-assurance/keeping-business-records)

---

### 1.2 United Kingdom – Self Assessment & VAT

#### 1.2.1 Forms and Concepts

**Primary Forms**:
- **SA100**: Main Self Assessment tax return (for individuals)
- **SA103S**: Short version for sole traders with turnover <£85,000
- **SA103F**: Full version for sole traders with turnover ≥£85,000
- **VAT Return**: Quarterly VAT reporting (if VAT registered)

**Registration Thresholds**:
- Self Assessment: Required if self-employed income >£1,000/year
- VAT Registration: Mandatory if turnover >£85,000 in 12 months (2024-25)
- Making Tax Digital (MTD): Mandatory from April 2026 for self-employed with income >£50,000

**Reporting Periods**:
- Self Assessment: Annual (tax year April 6 - April 5), due January 31 following tax year
- VAT: Quarterly (if registered)

#### 1.2.2 Evidence Categories for Sole Traders

**Income Categories**:
1. **Trading Income** (SA103S Box 13):
   - Sales invoices
   - Platform earnings (Uber, Deliveroo UK)
   - Cash receipts

2. **Other Business Income** (SA103S Box 16):
   - Interest on business accounts
   - Grants or subsidies

**Expense Categories** (SA103S Boxes 17-30):
1. **Cost of Goods Sold** (Box 17): Materials, stock
2. **Car, Van, Travel Expenses** (Box 18):
   - Fuel (business mileage rate: £0.45/mile first 10K miles, £0.25/mile thereafter)
   - Vehicle insurance, tax, repairs

3. **Rent, Rates, Power, Insurance** (Box 19):
   - Business premises rent
   - Business insurance

4. **Repairs and Renewals** (Box 20)
5. **Phone, Stationery, Other Office Costs** (Box 21)
6. **Advertising, Business Entertainment** (Box 22)
7. **Interest and Finance Charges** (Box 23)
8. **Other Allowable Expenses** (Box 26)

**Simplified Expenses** (Alternative):
- Flat rate for vehicle: Based on miles driven
- Flat rate for home office: £10-26/month depending on hours
- Available for businesses with turnover <£85K

#### 1.2.3 Accountant Delivery Preferences

**Spreadsheet Layout**:
```
Date | Description | Category (SA103 Box) | Net Amount | VAT (if applicable) | Total
```

**Document Organization**:
- **Preferred**: Separate folders for Income and Expenses
  - Income: Organized by month or quarter
  - Expenses: Organized by category (Vehicle, Office, etc.)
- **Digital receipts**: Photos acceptable if clear and legible
- **VAT**: If registered, must show VAT breakdown separately

**Submission Constraints**:
- HMRC online portal: PDF uploads, typically 5MB limit per file
- MTD (from 2026): Digital records required, direct software submission

#### 1.2.4 Category → Form Field Mappings

| Document Category | SA103S Box | Notes |
|-------------------|------------|-------|
| Rideshare/Platform Income | 13 (Turnover) | Total sales excluding VAT |
| Direct Client Invoices | 13 | Same as above |
| Fuel/Vehicle Expenses | 18 | Business use % or mileage rate |
| Phone/Internet | 21 | Business use % |
| Equipment/Tools | 20 | Capital items may have separate treatment |
| Home Office | 19 or simplified expenses | Percentage of home costs |

#### 1.2.5 Profession-Specific Templates

**Rideshare Drivers (Uber UK)**:
- Uber provides annual tax summary (total earnings, trips)
- Must distinguish between business miles and personal miles
- Simplified mileage rate often more beneficial than actual costs
- Congestion charges, parking fees deductible

**Delivery Couriers (Deliveroo, Just Eat)**:
- Platform summaries showing weekly/monthly earnings
- Equipment: Insulated bags, bikes/e-bikes, helmets
- Bike maintenance and replacement parts

**Freelance Consultants**:
- Invoice-based, often higher average transaction value
- Software subscriptions (Adobe, Microsoft 365)
- Professional indemnity insurance
- Training and CPD courses

**Sources**:
- [GOV.UK - Self Assessment Tax Returns](https://www.gov.uk/self-assessment-tax-returns)
- [GOV.UK - VAT Registration Threshold](https://www.gov.uk/vat-registration-threshold)
- [GOV.UK - Simplified Expenses for Self-Employed](https://www.gov.uk/simpler-income-tax-simplified-expenses)
- [HMRC - Making Tax Digital](https://www.gov.uk/government/publications/making-tax-digital)

---

### 1.3 United States – Schedule C & Self-Employment Tax

#### 1.3.1 Forms and Concepts

**Primary Forms**:
- **Schedule C** (Form 1040): Profit or Loss from Business (Sole Proprietorship)
- **Schedule SE** (Form 1040): Self-Employment Tax (if net earnings ≥$400)
- **Form 1040**: Main individual income tax return

**Registration Requirements**:
- No formal "registration" threshold for self-employment
- Must file Schedule C if net self-employment income ≥$400
- May need EIN (Employer Identification Number) if hiring employees or forming LLC

**Tax Obligations**:
- Income Tax: Progressive rates (10%-37% in 2024)
- Self-Employment Tax: 15.3% (12.4% Social Security + 2.9% Medicare) on net earnings
- Quarterly Estimated Tax: Required if expecting to owe ≥$1,000

**Reporting Periods**:
- Annual tax return: Due April 15 (for previous calendar year)
- Quarterly estimated tax: April 15, June 15, Sept 15, Jan 15

#### 1.3.2 Evidence Categories for Sole Traders

**Income Categories** (Schedule C, Part I):
1. **Gross Receipts/Sales** (Line 1):
   - Platform earnings (Uber, Lyft, DoorDash)
   - Client invoices
   - Cash/check payments
   - 1099-NEC forms from clients (if >$600/year)

2. **Returns and Allowances** (Line 2): Refunds, discounts given

**Expense Categories** (Schedule C, Part II):
1. **Car and Truck Expenses** (Line 9):
   - Standard mileage rate: $0.67/mile (2024)
   - OR actual expenses (gas, oil, repairs, insurance, depreciation)
   - Must maintain mileage log

2. **Office Expense** (Line 18):
   - Supplies, software, postage
   - Home office deduction (Form 8829 or simplified method)

3. **Supplies** (Line 22): Materials, inventory
4. **Travel** (Line 24a): Business travel (excluding commuting)
5. **Meals** (Line 24b): 50% deductible for business meals
6. **Utilities** (Line 25): Phone, internet (business use %)
7. **Other Expenses** (Line 27a): Equipment, professional fees, advertising

**Cost of Goods Sold** (Schedule C, Part III):
- For businesses selling products (less relevant for rideshare/services)

#### 1.3.3 Accountant Delivery Preferences

**Spreadsheet Layout**:
```
Date | Description | Category (Schedule C Line) | Amount | Business % | Deductible Amount
```

**Document Organization**:
- **Income**: Platform summaries (annual 1099-K or in-app reports), client invoices
- **Expenses**: Organized by category, chronological within category
- **Mileage Log**: Essential for vehicle deductions (Date, Start/End odometer, Miles, Purpose)
- **Receipts**: Keep all receipts >$75 (recommended: keep all)

**Submission Constraints**:
- IRS e-filing: Most tax software handles PDF attachments for audits
- Typical submission to accountant: Email, Dropbox, client portal (10-50MB typical)

#### 1.3.4 Category → Form Field Mappings

| Document Category | Schedule C Line | Notes |
|-------------------|-----------------|-------|
| Rideshare/Gig Income | 1 (Gross Receipts) | Include all platform earnings |
| 1099-NEC (Client Payments) | 1 | Must report if ≥$600 |
| Vehicle Expenses | 9 | Standard mileage OR actual expenses |
| Phone/Internet | 25 (Utilities) | Business use % only |
| Equipment (Phones, Bags) | 27a (Other) or depreciation | Depends on cost and useful life |
| Home Office | 30 | Simplified ($5/sq ft, max 300 sq ft) or actual |

#### 1.3.5 Profession-Specific Templates

**Rideshare Drivers (Uber/Lyft)**:
- Uber/Lyft provide annual tax summary (total earnings, fees, miles driven)
- Mileage log is CRITICAL (apps like MileIQ, Stride recommended)
- Standard mileage rate usually more beneficial than actual expenses
- Tolls, parking fees deductible (separate from mileage)
- Phone expense: Often 50-80% business use

**Delivery Drivers (DoorDash, Instacart)**:
- Platform summaries showing annual earnings
- Higher mileage than rideshare (more driving, less passenger time)
- Insulated bags, phone accessories
- May have "supplies" if purchasing items for customers (Instacart shoppers)

**Freelance Consultants/Contractors**:
- 1099-NEC forms from all clients paying ≥$600
- Office expenses: Software (Adobe, Microsoft), co-working space
- Professional development: Courses, certifications
- Health insurance: May be fully deductible (Form 1040, Schedule 1)

**Sources**:
- [IRS - Schedule C Instructions](https://www.irs.gov/forms-pubs/about-schedule-c-form-1040)
- [IRS - Self-Employment Tax](https://www.irs.gov/businesses/small-businesses-self-employed/self-employment-tax-social-security-and-medicare-taxes)
- [IRS - Standard Mileage Rates](https://www.irs.gov/newsroom/irs-issues-standard-mileage-rates-for-2024)
- [IRS - Home Office Deduction](https://www.irs.gov/businesses/small-businesses-self-employed/home-office-deduction)

---

### 1.4 Canada – GST/HST & T2125

#### 1.4.1 Forms and Concepts

**Primary Forms**:
- **Form T2125**: Statement of Business or Professional Activities (attached to T1 personal tax return)
- **GST/HST Return**: Quarterly or annual (if registered for GST/HST)
- **T1 General**: Main personal income tax return

**Registration Thresholds**:
- GST/HST Registration: Required if revenue >$30,000 in last 4 consecutive quarters
- Voluntary registration: Allowed below threshold (can claim input tax credits)

**Tax Rates** (2025):
- GST: 5% (federal)
- HST: 13-15% (in participating provinces: ON 13%, NS/NB/NL/PE 15%)
- PST: Separate in BC (7%), SK (6%), MB (7%), QC (9.975% QST)
- CPP (Canada Pension Plan): 11.9% on net self-employment income (2025 rate)

**Reporting Periods**:
- T1/T2125: Annual (tax year = calendar year), due April 30 (June 15 for self-employed)
- GST/HST: Annual (if revenue <$1.5M), quarterly, or monthly

#### 1.4.2 Evidence Categories for Sole Traders

**Income Categories** (T2125, Part 4):
1. **Sales, Commissions, or Fees** (Line 8230):
   - Ride-sharing earnings (Uber, Lyft Canada)
   - Delivery platform income (SkipTheDishes, DoorDash)
   - Professional fees (consultants)

2. **Other Income** (Line 8230): Interest, subsidies, grants

**Expense Categories** (T2125, Part 5):
1. **Advertising** (Line 8521)
2. **Meals and Entertainment** (Line 8523): 50% deductible
3. **Business Tax, Fees, Licenses** (Line 8760)
4. **Insurance** (Line 9804): Business liability, vehicle (business %)
5. **Interest and Bank Charges** (Line 8710)
6. **Office Expenses** (Line 8810): Supplies, postage
7. **Supplies** (Line 8811): Materials, consumables
8. **Legal and Accounting** (Line 8860)
9. **Motor Vehicle Expenses** (Line 9281):
   - Fuel, maintenance, insurance, CCA (capital cost allowance for vehicle)
   - Must track business vs personal use %

10. **Rent** (Line 8960): Office space
11. **Telephone and Utilities** (Line 9220): Business use %
12. **Home Office Expenses** (Line 9945): Rent/mortgage, utilities, insurance, property tax (proportional to business use %)

**CCA (Capital Cost Allowance)**: Depreciation for equipment, vehicles (Class 10: 30% declining balance for vehicles)

#### 1.4.3 Accountant Delivery Preferences

**Spreadsheet Layout**:
```
Date | Description | Category (T2125 Line) | Amount | GST/HST/PST | Business Use % | Net Deduction
```

**Document Organization**:
- **Income**: Platform summaries (T4A slips if applicable), invoices
- **Expenses**: Organized by T2125 category
- **GST/HST**: If registered, track input tax credits (ITC) separately
- **Vehicle**: Logbook showing business vs personal km

**Submission Constraints**:
- CRA My Account: Online filing, PDF attachments for audits
- Accountant handoff: Typically via email, secure portal, or cloud storage

#### 1.4.4 Category → Form Field Mappings

| Document Category | T2125 Line | Notes |
|-------------------|------------|-------|
| Rideshare/Delivery Income | 8230 (Sales) | Report gross earnings |
| Vehicle Expenses (Gas, Maintenance) | 9281 | Business use % × total expenses |
| Phone/Internet | 9220 | Business use % |
| Equipment | Depreciation (CCA) or supplies | Depends on cost and useful life |
| Home Office | 9945 | Business area % × home expenses |

**GST/HST Reporting** (if registered):
- **Line 101** (Total Sales): Gross revenue including GST/HST
- **Line 105** (Total GST/HST Collected): On sales
- **Line 108** (Total Input Tax Credits): GST/HST paid on business purchases

#### 1.4.5 Profession-Specific Templates

**Rideshare Drivers (Uber Canada)**:
- Uber provides annual tax summary (T4A may be issued for drivers in some provinces)
- Vehicle expenses often 40-60% of gross income
- Must track business km vs personal km (logbook or app)
- Standard vs actual expenses: CRA requires actual for most deductions

**Delivery Couriers (SkipTheDishes, DoorDash)**:
- Similar to rideshare, but may have higher km/dollar ratio
- Equipment: Insulated bags, bike/e-bike (CCA Class 8: 20%)
- May use bicycle or car depending on market

**Freelance Professionals**:
- Office expenses higher (software, subscriptions)
- Home office common (proportional deduction)
- Professional development: Courses, memberships, conferences
- May have lower vehicle expenses

**Sources**:
- [CRA - Form T2125](https://www.canada.ca/en/revenue-agency/services/forms-publications/forms/t2125.html)
- [CRA - GST/HST for Businesses](https://www.canada.ca/en/revenue-agency/services/tax/businesses/topics/gst-hst-businesses.html)
- [CRA - Business Expenses](https://www.canada.ca/en/revenue-agency/services/tax/businesses/topics/sole-proprietorships-partnerships/business-expenses.html)
- [CRA - Motor Vehicle Expenses](https://www.canada.ca/en/revenue-agency/services/tax/businesses/topics/sole-proprietorships-partnerships/business-expenses/motor-vehicle-expenses.html)

---

### 1.5 New Zealand – GST & IR3

#### 1.5.1 Forms and Concepts

**Primary Forms**:
- **IR3**: Individual Income Tax Return (for self-employed)
- **GST Return**: Quarterly, six-monthly, or monthly (if GST registered)

**Registration Thresholds**:
- GST Registration: Required if turnover >$60,000 in 12 months
- Voluntary registration: Allowed below threshold

**Tax Rates**:
- GST: 15% (flat rate)
- Income Tax (2024-25):
  - 0-$15,600: 10.5%
  - $15,601-$53,500: 17.5%
  - $53,501-$78,100: 30%
  - $78,101-$180,000: 33%
  - $180,001+: 39%

**Reporting Periods**:
- IR3: Annual (tax year April 1 - March 31), due July 7
- GST: Six-monthly (most common for small businesses), quarterly, or monthly

#### 1.5.2 Evidence Categories for Sole Traders

**Income Categories** (IR3):
1. **Self-Employment Income**:
   - Platform earnings (Uber, Ola NZ)
   - Invoices to clients
   - Cash sales

2. **Other Income**: Interest, dividends, rental income (separate schedules)

**Expense Categories**:
1. **Vehicle Expenses**:
   - Running costs: Petrol, repairs, maintenance, WOF (Warrant of Fitness), insurance
   - Depreciation (diminishing value method)
   - Business use % required (logbook or estimate)

2. **Home Office**:
   - Rent/mortgage interest (business use %)
   - Rates, insurance, utilities
   - Square meter method: Business area ÷ total area

3. **Phone and Internet**: Business use %
4. **Equipment and Tools**: Depreciation or immediate deduction if <$5,000 (threshold increased to $5K in 2024)
5. **Other Expenses**: Advertising, professional fees, subscriptions

**Provisional Tax**: Required if residual income tax >$5,000 in previous year

#### 1.5.3 Accountant Delivery Preferences

**Spreadsheet Layout**:
```
Date | Description | Category | Amount (Inc GST) | GST Component | Business Use % | Deductible Amount
```

**Document Organization**:
- **Income**: Platform summaries, invoices (show GST separately if registered)
- **Expenses**: Organized by category, chronological
- **GST**: If registered, track GST on purchases for input tax credits
- **Logbook**: For vehicle expenses (alternative: 25% business use without logbook if <5,000 km)

**Submission Constraints**:
- myIR (Inland Revenue online portal): Digital filing, PDF attachments for audits
- Accountant handoff: Email, Xero/MYOB integration common in NZ

#### 1.5.4 Category → Form Field Mappings

| Document Category | IR3/GST Field | Notes |
|-------------------|---------------|-------|
| Rideshare/Platform Income | Self-employment income, GST sales | Report gross, GST separate if registered |
| Client Invoices | Self-employment income | Same as above |
| Vehicle Expenses | Business expenses, GST inputs | Business use % × total costs |
| Phone/Internet | Business expenses | Business use % |
| Equipment <$5K | Immediate deduction | Threshold raised to $5K in 2024 |
| Equipment ≥$5K | Depreciation schedule | Diminishing value method |

**GST Reporting** (if registered):
- **Box 5** (Total Sales): Gross revenue (excluding GST if GST-registered)
- **Box 10** (Total GST on Sales): 15% of sales
- **Box 11** (Total GST on Purchases): Input tax credits
- **Box 14** (GST Refund or Payment): Box 10 - Box 11

#### 1.5.5 Profession-Specific Templates

**Rideshare Drivers (Uber/Ola NZ)**:
- Uber provides annual tax summary
- Vehicle expenses: Logbook recommended for >5,000 km business use
- Depreciation on vehicle: Rate 18-30% depending on vehicle type
- ACC (Accident Compensation Corporation) levies: Deductible

**Delivery Couriers**:
- Similar to rideshare, but may use bikes/e-bikes (depreciation rate 30%)
- Equipment: Insulated bags, phone holders
- Bike maintenance, replacement parts

**Freelance Consultants**:
- Home office common (proportional deduction)
- Software subscriptions (Xero, Adobe, Microsoft)
- Professional indemnity insurance
- Training and professional development

**Sources**:
- [Inland Revenue - GST Registration](https://www.ird.govt.nz/gst/registering-for-gst)
- [IRD - Self-Employed Tax](https://www.ird.govt.nz/income-tax/income-tax-for-individuals/what-happens-at-the-end-of-the-tax-year/self-employed)
- [IRD - Vehicle Expenses for Self-Employed](https://www.ird.govt.nz/income-tax/income-tax-for-businesses-and-organisations/types-of-business-expenses/business-use-of-vehicle)
- [IRD - IR3 Return Guide](https://www.ird.govt.nz/income-tax/income-tax-for-individuals/what-happens-at-the-end-of-the-tax-year/individual-income-tax-return-ir3)

---

### 1.6 Tax/BAS Domain Summary: Invariants vs Variations

#### Invariants (Common Across All Jurisdictions)

1. **Income/Expense Structure**: All jurisdictions separate:
   - Gross income/sales
   - Business expenses by category (vehicle, office, phone, equipment)
   - Net profit = Income - Expenses

2. **GST/VAT Concept**: Consumption tax on sales, with input tax credits for business purchases
   - AU: 10% GST
   - UK: 20% VAT
   - US: No federal sales tax (state sales taxes exist but not relevant for most sole traders)
   - CA: 5% GST + provincial HST/PST (up to 15% total)
   - NZ: 15% GST

3. **Vehicle Expense Methods**:
   - Actual expenses (gas, maintenance, depreciation) × business use %
   - OR standard mileage rate (AU, UK, US, CA, NZ all offer variants)

4. **Home Office Deduction**: Business area % × home costs (OR simplified flat rate)

5. **Evidence Requirements**:
   - Receipts/invoices for expenses
   - Income statements (platform summaries, client invoices)
   - Logbook or mileage records for vehicle deductions

6. **Reporting Periods**:
   - Quarterly or monthly for GST/VAT (if registered)
   - Annual for income tax

#### Variations (Jurisdiction-Specific)

1. **Registration Thresholds**:
   - AU: $75K for GST
   - UK: £85K for VAT
   - US: No threshold (any self-employment income triggers Schedule C if ≥$400 net)
   - CA: $30K for GST/HST
   - NZ: $60K for GST

2. **Tax Rates**:
   - GST/VAT: 0% (US), 5-15% (CA), 10% (AU), 15% (NZ), 20% (UK)
   - Income tax: Progressive rates vary by country
   - Self-employment tax: US has 15.3% SE tax; CA has 11.9% CPP; others incorporate in income tax

3. **Form Field Names and Numbers**:
   - AU: G1, 1A, 1B (BAS)
   - UK: SA103 boxes (13, 17-30)
   - US: Schedule C lines (1, 9, 18, etc.)
   - CA: T2125 lines (8230, 9281, etc.)
   - NZ: IR3 fields

4. **Submission Portals**:
   - AU: myGov
   - UK: HMRC online, MTD from 2026
   - US: IRS e-file (via tax software)
   - CA: CRA My Account
   - NZ: myIR

5. **Profession-Specific Nuances**:
   - AU: Logbook requirement for >5,000 km
   - UK: Simplified expenses for turnover <£85K
   - US: Standard mileage rate vs actual expenses choice
   - CA: CCA (capital cost allowance) mandatory for depreciation
   - NZ: $5K threshold for immediate equipment deduction (vs depreciation)

#### Design Implications for FileOrganizer

**Configuration-Driven Pack System** can handle:
- **Country parameter**: `country: AU | UK | US | CA | NZ`
- **Income categories**: Platform-specific (Uber, DoorDash) OR generic (Sales, Fees)
- **Expense categories**: Hierarchical (Vehicle → Fuel, Maintenance, Insurance)
- **Mapping rules**: Category → Form field (AU:G1, UK:SA103-13, US:Sched-C-1)
- **Thresholds**: GST/VAT registration, reporting frequency
- **Export templates**:
  - Spreadsheet with jurisdiction-specific column headers
  - PDF bundles (one per category OR combined)
  - Summary report showing category totals mapped to form fields

**Disclaimer Required**:
> "This pack organizes your documents and provides category summaries to assist with tax preparation. It is NOT tax advice. Consult a registered tax agent or accountant for professional guidance. FileOrganizer does not calculate tax liabilities or determine deductibility."

---

## PART 2: IMMIGRATION/VISA EVIDENCE PACK FORMATS

### 2.1 Australia – Partner Visa (820/801)

#### 2.1.1 Evidence Categories and Requirements

**Official Guidance**: Department of Home Affairs uses **4 Pillars** framework for relationship evidence:

1. **Financial Aspects**:
   - Joint bank accounts (statements showing 12+ months history)
   - Joint ownership of assets (property, vehicles)
   - Joint liabilities (mortgage, loans, credit cards)
   - Evidence of pooling financial resources
   - Beneficiary designations (superannuation, life insurance, wills)

2. **Household/Domestic Aspects**:
   - Joint lease or property title
   - Utility bills in both names (electricity, water, internet)
   - Evidence of living at same address (mail, driver's license)
   - Photos of shared household items
   - Joint responsibility for household tasks

3. **Social Aspects**:
   - Joint social activities (photos with friends/family over time)
   - Recognition as a couple by friends and family (statutory declarations - Form 888)
   - Joint travel (flight bookings, hotel reservations, passport stamps)
   - Joint memberships (gym, clubs)
   - Communication evidence (emails, messages, call logs - particularly for periods apart)

4. **Commitment/Nature of Relationship**:
   - Knowledge of each other's background (family, education, work)
   - Duration of relationship (longer = stronger)
   - Future plans (emails discussing marriage, children, relocation)
   - Public recognition of relationship (social media, engagement announcements)

**Typical Time Coverage**: 12+ months of relationship evidence across all 4 pillars (stronger if 2-3+ years)

**Form 888 Statutory Declarations**: Written statements from friends/family who know the couple, confirming genuine relationship

**Application Fee**: $9,365 AUD (2024-25), one of the highest globally

#### 2.1.2 Document Packaging Preferences

**Official Submission Method**: ImmiAccount (online portal)

**File Requirements**:
- **File Types**: PDF preferred (JPEG/PNG for photos)
- **File Size**: Max 60MB per file
- **Number of Files**: No strict limit, but practical limit ~50-100 files
- **Organization**: Recommended to group by pillar (4 PDF bundles) with table of contents

**Recommended Structure**:
```
1_Financial_Evidence.pdf
  - Table of Contents
  - Joint bank statements (12 months)
  - Joint asset ownership
  - Beneficiary designations

2_Household_Evidence.pdf
  - Joint lease
  - Utility bills (12 months, representative sample)
  - Correspondence to shared address

3_Social_Evidence.pdf
  - Photos (chronological, 20-50 representative images)
  - Travel evidence
  - Form 888 declarations (2-4 from each partner's side)

4_Commitment_Evidence.pdf
  - Relationship timeline document
  - Communication evidence (sample, not exhaustive)
  - Future plans evidence
```

**Chronological Ordering**: Within each pillar, organize chronologically (oldest to newest)

#### 2.1.3 Design Implications for FileOrganizer

**Category Hierarchy**:
```
Immigration_AU_Partner_820_801/
├── 1_Financial/
│   ├── Joint_Accounts/
│   ├── Joint_Assets/
│   └── Beneficiary_Designations/
├── 2_Household/
│   ├── Lease_Property_Title/
│   ├── Utility_Bills/
│   └── Shared_Address_Evidence/
├── 3_Social/
│   ├── Photos/
│   ├── Travel/
│   ├── Form_888_Declarations/
│   └── Communication/
└── 4_Commitment/
    ├── Relationship_Timeline/
    └── Future_Plans/
```

**Export Recipe**:
- 4 combined PDFs (one per pillar)
- Table of contents for each
- Chronological ordering within categories
- Photo collage (optional): 20-50 representative images in grid format

**Disclaimer**:
> "This pack organizes relationship evidence per Department of Home Affairs guidance. It is NOT immigration advice. Consult a registered migration agent (MARA) for professional assistance."

**Sources**:
- [Department of Home Affairs - Partner Visas](https://immi.homeaffairs.gov.au/visas/getting-a-visa/visa-listing/partner-onshore)
- [ImmiAccount - Evidence Guidelines](https://immi.homeaffairs.gov.au/help-support/applying-online-or-on-paper/online)
- [Form 888 - Statutory Declaration](https://immi.homeaffairs.gov.au/form-listing/forms/888.pdf)

---

### 2.2 United Kingdom – Spouse/Partner Visa

#### 2.2.1 Evidence Categories and Requirements

**Primary Evidence Categories**:

1. **Financial Requirement**:
   - **Income Threshold**: £29,000/year for sponsor (as of April 11, 2024, increased from £18,600)
   - **Acceptable Income Sources**:
     - Employment (payslips, employment contract, bank statements)
     - Self-employment (tax returns SA302, business accounts)
     - Savings: £88,500 in savings for 6+ months (alternative to income, or £16K + income combo)
     - Pension income
   - **Evidence Required**:
     - Last 6 months of payslips
     - Bank statements showing salary deposits
     - Employment letter confirming salary and duration
     - OR tax returns + business bank statements (self-employed)
     - OR savings account statements (6 months, showing balance above threshold)

2. **Relationship Evidence**:
   - **Married**: Marriage certificate (original + certified translation if not in English)
   - **Unmarried Partners**: Evidence of 2+ years living together in a relationship akin to marriage
     - Joint lease/mortgage (2+ years)
     - Utility bills in both names (spread across 2 years)
     - Correspondence to same address
   - **Genuine Relationship**:
     - Photos together (across duration of relationship)
     - Communication (emails, messages, call logs - especially if long-distance)
     - Travel evidence (visits, joint trips)
     - Statutory declarations from friends/family (optional but helpful)

3. **Accommodation**:
   - Evidence of adequate accommodation in UK (not overcrowded)
   - Property ownership, mortgage statement, OR tenancy agreement
   - Letter from property owner confirming permission for applicant to live there

4. **English Language**:
   - A1 level on CEFR (Common European Framework of Reference)
   - IELTS Life Skills A1 or equivalent
   - OR degree taught in English
   - OR national of majority-English speaking country

5. **Identity and Civil Status**:
   - Valid passport
   - Birth certificate
   - Previous marriage/divorce certificates (if applicable)

**Application Fee**: £1,846 (online), £3,000+ (priority service)

**Processing Time**: 24 weeks standard (as of 2024)

#### 2.2.2 Document Packaging Preferences

**Submission Method**: Online application + document upload OR in-person appointment with physical documents

**File Requirements**:
- **File Types**: PDF, JPEG (photos), PNG
- **File Size**: Varies by document type, typically 2-6MB per file
- **Organization**: Recommended to label clearly (e.g., "Payslip_Jan2024.pdf", "Joint_Lease.pdf")

**Recommended Structure**:
```
Financial_Evidence/
  - Sponsor_Payslips_6months.pdf
  - Sponsor_Employment_Letter.pdf
  - Sponsor_Bank_Statements_6months.pdf

Relationship_Evidence/
  - Marriage_Certificate.pdf (+ translation if needed)
  - Photos_Chronological.pdf (20-40 images)
  - Communication_Sample.pdf
  - Travel_Evidence.pdf

Accommodation_Evidence/
  - Tenancy_Agreement.pdf (or Mortgage Statement)
  - Property_Owner_Letter.pdf

English_Language/
  - IELTS_Certificate.pdf (or degree certificate)

Identity_Documents/
  - Passport_Biodata_Page.pdf
  - Birth_Certificate.pdf
```

**Chronological Ordering**: Financial documents (most recent first), relationship evidence (oldest to newest)

#### 2.2.3 Design Implications for FileOrganizer

**Category Hierarchy**:
```
Immigration_UK_Spouse_Partner/
├── Financial/
│   ├── Employment/ (payslips, letter, bank statements)
│   ├── Self_Employment/ (SA302, business accounts)
│   └── Savings/ (account statements)
├── Relationship/
│   ├── Marriage_Certificate/
│   ├── Cohabitation_Evidence/ (2+ years for unmarried)
│   ├── Photos/
│   ├── Communication/
│   └── Travel/
├── Accommodation/
├── English_Language/
└── Identity/
```

**Export Recipe**:
- Separate PDFs per category (Financial, Relationship, Accommodation, etc.)
- OR combined PDF with bookmarks for each section
- Index page listing all documents with page numbers
- Chronological ordering (financial: recent first, relationship: oldest first)

**Disclaimer**:
> "This pack organizes visa evidence per UK Home Office guidance. It is NOT immigration advice. Consult an OISC-registered immigration adviser or solicitor."

**Sources**:
- [UK Visas and Immigration - Spouse/Partner Visa](https://www.gov.uk/uk-family-visa/partner-spouse)
- [GOV.UK - Financial Requirement](https://www.gov.uk/government/publications/chapter-8-appendix-fm-family-members)
- [IELTS Life Skills](https://www.ielts.org/for-test-takers/ielts-for-uk-visas/ielts-life-skills)

---

### 2.3 United States – Marriage-Based Green Card (I-130)

#### 2.3.1 Evidence Categories and Requirements

**Primary Forms**:
- **I-130**: Petition for Alien Relative (filed by US citizen/LPR spouse)
- **I-130A**: Supplemental Information for Spouse Beneficiary
- **I-485**: Application to Register Permanent Residence (if adjusting status in US)
- **I-864**: Affidavit of Support (financial sponsorship)

**Evidence Categories**:

1. **Proof of Marriage**:
   - Marriage certificate (government-issued, with certified translation if not in English)
   - Previous marriage termination documents (divorce decrees, death certificates)

2. **Bona Fide Marriage Evidence** (to prove genuine relationship, not for immigration fraud):
   - **Strong Evidence**:
     - Joint ownership of property (deed, mortgage)
     - Joint bank accounts (statements showing 12+ months)
     - Joint credit cards, loans
     - Birth certificates of children (if applicable)
     - Health/life insurance policies (spouse as beneficiary)
   - **Medium Evidence**:
     - Joint lease or cohabitation evidence
     - Utility bills in both names
     - Joint travel (hotel bookings, flight reservations)
     - Photos together (chronological, with family/friends)
   - **Weak Evidence** (supplement only):
     - Cards/letters exchanged
     - Affidavits from friends/family
     - Social media screenshots

3. **Financial Sponsorship** (I-864):
   - **Income Requirement**: 125% of federal poverty guideline (varies by household size, e.g., $24,650 for 2-person household in 2024)
   - **Evidence**:
     - Last 3 years of tax returns (IRS transcripts preferred)
     - Recent pay stubs
     - Employment verification letter
     - OR assets (value ≥5x shortfall in income requirement)

4. **Identity and Civil Documents**:
   - Passports (biodata pages)
   - Birth certificates
   - Police certificates (for I-485 applicants)
   - Medical examination (Form I-693)

**Application Fees**:
- I-130: $675
- I-485 (if concurrent): $1,440 (includes biometrics)
- I-864: No fee

#### 2.3.2 Document Packaging Preferences

**Submission Method**: Mail (USCIS Lockbox) OR online (for I-130 only, as of late 2023)

**Physical Submission Requirements**:
- **Paper Size**: 8.5" × 11" (US Letter)
- **Organization**: Tabs/dividers recommended for each evidence category
- **Copies**: Submit copies, NOT originals (except for specific documents like passport photos)
- **Translations**: Certified translations required for non-English documents

**Recommended Structure** (Physical Binder):
```
Tab 1: Forms (I-130, I-130A, G-1145 notification)
Tab 2: Marriage Certificate (+ previous marriage termination docs)
Tab 3: Joint Financial Evidence
  - Bank statements (chronological, 12+ months)
  - Joint property/lease
  - Insurance policies
Tab 4: Cohabitation Evidence
  - Utility bills
  - Correspondence to same address
Tab 5: Photos (20-40, chronological, with captions)
Tab 6: Travel Evidence (joint trips)
Tab 7: Affidavits from Friends/Family (2-4)
Tab 8: Additional Evidence (communication, cards, etc.)
```

**For I-485 (Adjustment of Status)**:
- Similar organization, with additional tabs for I-864, medical exam, police certificates

**Chronological Ordering**: Financial/cohabitation evidence (most recent first), photos (oldest to newest)

#### 2.3.3 Design Implications for FileOrganizer

**Category Hierarchy**:
```
Immigration_US_Marriage_GreenCard/
├── Forms/
│   ├── I-130/
│   ├── I-130A/
│   └── I-485/ (if AOS)
├── Marriage_Proof/
│   ├── Marriage_Certificate/
│   └── Previous_Marriage_Termination/
├── Bona_Fide_Marriage/
│   ├── Strong_Evidence/
│   │   ├── Joint_Accounts/
│   │   ├── Joint_Property/
│   │   └── Children_Birth_Certificates/
│   ├── Medium_Evidence/
│   │   ├── Joint_Lease_Utilities/
│   │   ├── Photos/
│   │   └── Travel/
│   └── Supplemental/
│       ├── Affidavits/
│       └── Communication/
├── Financial_I-864/
│   ├── Tax_Returns_3years/
│   ├── Pay_Stubs/
│   └── Employment_Letter/
└── Identity_Civil_Docs/
    ├── Passports/
    ├── Birth_Certificates/
    └── Police_Certificates/
```

**Export Recipe**:
- **Physical submission**: PDF preview with tab/divider pages, print instructions
- **Online I-130**: Individual PDFs per document type, labeled clearly
- Index/checklist showing which evidence is included
- Chronological ordering (financial: recent first, photos: oldest first)

**Disclaimer**:
> "This pack organizes I-130/I-485 evidence per USCIS guidance. It is NOT legal advice. Consult an immigration attorney for case-specific guidance."

**Sources**:
- [USCIS - I-130 Instructions](https://www.uscis.gov/i-130)
- [USCIS - I-485 Instructions](https://www.uscis.gov/i-485)
- [USCIS - I-864 Affidavit of Support](https://www.uscis.gov/i-864)
- [USCIS - Bona Fide Marriage Evidence](https://www.uscis.gov/policy-manual/volume-12-part-g-chapter-2)

---

### 2.4 Canada – Spousal Sponsorship

#### 2.4.1 Evidence Categories and Requirements

**Primary Forms**:
- **IMM 1344**: Application to Sponsor, Sponsorship Agreement and Undertaking
- **IMM 5532**: Relationship Information and Sponsorship Evaluation
- **IMM 0008**: Generic Application Form for Canada (for principal applicant)
- **IMM 5406**: Additional Family Information
- **IMM 5669**: Schedule A – Background/Declaration

**Evidence Categories**:

1. **Proof of Relationship**:
   - **Married**:
     - Marriage certificate (original or certified copy + certified translation)
     - Wedding photos (representative sample, 10-20)
   - **Common-Law Partners** (12+ months living together):
     - Statutory Declaration of Common-Law Union (IMM 5409)
     - Joint lease/mortgage (12+ months)
     - Utility bills (12+ months, in both names)
     - Correspondence to same address
   - **Conjugal Partners** (rare, for couples unable to live together):
     - Proof of significant barriers to marriage or cohabitation
     - Evidence of ongoing relationship (communication, visits)

2. **Relationship Development**:
   - Photos together (chronological, from start of relationship to present)
   - Travel evidence (joint trips, visits if long-distance)
   - Communication (emails, messages, call logs - sample, not exhaustive)
   - Important events (engagement, family gatherings)

3. **Cohabitation Evidence** (if living together):
   - Joint bank accounts (statements, 12+ months)
   - Joint bills (utilities, phone, internet)
   - Joint lease or property ownership
   - Correspondence showing same address (driver's license, tax documents)

4. **Financial Support**:
   - No minimum income requirement for spousal sponsorship (EXCEPT for Quebec residents, or if sponsor is on social assistance)
   - Option C Printout (CRA Notice of Assessment for last tax year)
   - Pay stubs (recent)
   - Proof of employment

5. **Identity and Civil Status**:
   - Passports (biodata pages)
   - Birth certificates
   - Police certificates (from countries where applicant lived 6+ months since age 18)
   - Previous marriage termination documents (if applicable)

6. **Quebec-Specific** (if sponsoring to Quebec):
   - Certificat de sélection du Québec (CSQ) – separate application to Quebec

**Application Fees**:
- Sponsorship fee: $85
- Principal applicant processing fee: $490
- Right of permanent residence fee: $515
- **Total**: $1,090 CAD

**Processing Time**: 12-18 months (as of 2024)

#### 2.4.2 Document Packaging Preferences

**Submission Method**: **Digital-only** (as of 2025, paper applications discontinued for most spousal sponsorship)

**File Requirements**:
- **File Types**: PDF (preferred), JPEG/PNG (for photos)
- **File Size**: Max 4MB per file
- **Color Scans**: Required for identity documents
- **OCR**: Must be text-searchable (if scanned)

**Recommended Structure** (Digital Submission):
```
01_Forms/
  - IMM1344_Sponsor.pdf
  - IMM5532_Relationship.pdf
  - IMM0008_Principal_Applicant.pdf
  - IMM5406_Family_Info.pdf
  - IMM5669_Background.pdf

02_Marriage_or_CommonLaw_Proof/
  - Marriage_Certificate.pdf (+ translation)
  - OR Statutory_Declaration_CommonLaw_IMM5409.pdf

03_Relationship_Evidence/
  - Photos_Chronological.pdf (20-40 images with captions)
  - Travel_Evidence.pdf
  - Communication_Sample.pdf (10-20 pages)

04_Cohabitation_Evidence/
  - Joint_Bank_Statements_12months.pdf
  - Joint_Lease_or_Mortgage.pdf
  - Utility_Bills_12months.pdf

05_Financial_Sponsor/
  - Option_C_Printout_Tax_Year.pdf
  - Pay_Stubs_Recent.pdf
  - Employment_Letter.pdf

06_Identity_Civil_Docs/
  - Passport_Sponsor.pdf
  - Passport_Applicant.pdf
  - Birth_Certificates.pdf
  - Police_Certificates.pdf
```

**Naming Convention**: `Document_Type_YYYY-MM-DD.pdf` (e.g., `Joint_Bank_Statement_2024-01.pdf`)

**Chronological Ordering**: Financial/cohabitation evidence (most recent first), photos (oldest to newest)

#### 2.4.3 Design Implications for FileOrganizer

**Category Hierarchy**:
```
Immigration_CA_Spousal_Sponsorship/
├── Forms/
├── Marriage_or_CommonLaw_Proof/
├── Relationship_Development/
│   ├── Photos/
│   ├── Travel/
│   └── Communication/
├── Cohabitation/
│   ├── Joint_Accounts/
│   ├── Joint_Bills/
│   └── Joint_Lease/
├── Financial_Sponsor/
│   ├── Tax_Documents/
│   ├── Employment/
│   └── Pay_Stubs/
└── Identity_Civil_Docs/
    ├── Passports/
    ├── Birth_Certificates/
    └── Police_Certificates/
```

**Export Recipe**:
- Individual PDFs per document type (per digital submission requirements)
- File naming with document type and date
- Index/checklist (separate PDF or spreadsheet)
- Max 4MB per file (auto-split if larger)
- OCR all scanned documents

**Disclaimer**:
> "This pack organizes spousal sponsorship evidence per IRCC guidance. It is NOT immigration advice. Consult an RCIC (Regulated Canadian Immigration Consultant) or immigration lawyer."

**Sources**:
- [IRCC - Sponsor Your Spouse or Partner](https://www.canada.ca/en/immigration-refugees-citizenship/services/immigrate-canada/family-sponsorship/spouse-partner-children.html)
- [IRCC - Document Checklist IMM 5533](https://www.canada.ca/en/immigration-refugees-citizenship/services/application/application-forms-guides/guide-5289-sponsor-your-spouse-common-law-partner-conjugal-partner-dependent-child-complete-guide.html)
- [IRCC - Digital Application Requirements](https://www.canada.ca/en/immigration-refugees-citizenship/services/application/account.html)

---

### 2.5 New Zealand – Partnership-Based Residence Visa

#### 2.5.1 Evidence Categories and Requirements

**Primary Forms**:
- **Partnership Support Form (INZ 1178)**: Completed by sponsor (NZ citizen or resident)
- **Partnership-based Work Visa** (temp) or **Partnership-based Residence Visa** (permanent)

**Evidence Categories**:

1. **Proof of Partnership**:
   - **Married/Civil Union**:
     - Marriage certificate (original or certified copy + certified translation)
     - Wedding photos
   - **De Facto Partners** (12+ months living together):
     - Statutory declaration from both partners
     - Joint evidence (see below)

2. **Living Together Evidence** (12+ months required for de facto):
   - Joint lease or property ownership (12+ months)
   - Utility bills in both names (12+ months, spread across period)
   - Correspondence to same address (bank statements, official mail)
   - Joint bank accounts (12+ months of statements)

3. **Genuine and Stable Relationship**:
   - Photos together (chronological, from start of relationship to present, 20-40 images)
   - Travel evidence (joint trips, passport stamps)
   - Communication (emails, messages, call logs - sample, especially if periods apart)
   - Statutory declarations from friends/family (2-4) confirming genuine relationship
   - Evidence of shared responsibilities (joint bills, household tasks)

4. **Financial Interdependence**:
   - Joint bank accounts
   - Joint assets (property, vehicles)
   - Joint liabilities (mortgage, loans)
   - Shared expenses (household bills)
   - Beneficiary designations (life insurance, KiwiSaver)

5. **Social Recognition**:
   - Joint invitations to events
   - Joint memberships (gym, clubs)
   - Social media showing relationship status
   - Family acceptance (photos with each other's families)

6. **Identity and Civil Documents**:
   - Passports (biodata pages)
   - Birth certificates
   - Police certificates (from countries where applicant lived 12+ months in last 10 years)
   - Medical certificates (chest X-ray, general medical)
   - Previous marriage termination documents (if applicable)

**Application Fees**:
- Partnership-based Work Visa: $360 NZD
- Partnership-based Residence Visa: $3,720 NZD (from Oct 2024)

**Processing Time**: 6-12 months for residence visa (as of 2024)

#### 2.5.2 Document Packaging Preferences

**Submission Method**: Online (through INZ online account) OR paper (mail to INZ)

**File Requirements** (Online):
- **File Types**: PDF (preferred), JPEG/PNG (for photos)
- **File Size**: Max 10MB per file
- **Color**: Required for identity documents, photos
- **Certified Copies**: Scanned certified copies acceptable for online submissions

**Recommended Structure**:
```
01_Forms/
  - INZ1178_Partnership_Support_Form.pdf
  - Main_Application_Form.pdf

02_Partnership_Proof/
  - Marriage_Certificate.pdf (+ translation if needed)
  - OR Statutory_Declaration_DeFacto.pdf
  - Wedding_Photos.pdf (if married)

03_Living_Together_12months/
  - Joint_Lease_or_Property_Title.pdf
  - Utility_Bills_12months.pdf
  - Joint_Bank_Statements_12months.pdf

04_Relationship_Evidence/
  - Photos_Chronological.pdf (20-40 images with captions/dates)
  - Travel_Evidence.pdf
  - Communication_Sample.pdf
  - Statutory_Declarations_Friends_Family.pdf

05_Financial_Interdependence/
  - Joint_Accounts_Summary.pdf
  - Joint_Assets_Liabilities.pdf
  - Beneficiary_Designations.pdf

06_Identity_Civil_Docs/
  - Passports.pdf
  - Birth_Certificates.pdf
  - Police_Certificates.pdf
  - Medical_Certificates.pdf
```

**Chronological Ordering**: Living together evidence (oldest to newest, spanning 12+ months), photos (oldest to newest)

#### 2.5.3 Design Implications for FileOrganizer

**Category Hierarchy**:
```
Immigration_NZ_Partnership_Residence/
├── Forms/
├── Partnership_Proof/
│   ├── Marriage_Certificate/
│   └── Statutory_Declaration/ (if de facto)
├── Living_Together_12months/
│   ├── Joint_Lease/
│   ├── Utility_Bills/
│   └── Correspondence_Same_Address/
├── Relationship_Evidence/
│   ├── Photos/
│   ├── Travel/
│   ├── Communication/
│   └── Statutory_Declarations/
├── Financial_Interdependence/
│   ├── Joint_Accounts/
│   ├── Joint_Assets/
│   └── Beneficiary_Designations/
└── Identity_Civil_Docs/
    ├── Passports/
    ├── Birth_Certificates/
    ├── Police_Certificates/
    └── Medical_Certificates/
```

**Export Recipe**:
- Separate PDFs per category (6 main categories)
- OR combined PDF with bookmarks
- Index page listing all evidence
- Max 10MB per file (auto-split if larger)
- Chronological ordering (living together: 12-month span, photos: oldest first)

**Disclaimer**:
> "This pack organizes partnership visa evidence per Immigration New Zealand guidance. It is NOT immigration advice. Consult a licensed immigration adviser (IAA)."

**Sources**:
- [Immigration New Zealand - Partnership-based Visas](https://www.immigration.govt.nz/new-zealand-visas/options/live-permanently/partnership)
- [INZ - Partnership Support Form INZ 1178](https://www.immigration.govt.nz/documents/forms-and-guides/inz1178.pdf)
- [INZ - Partnership Evidence Guide](https://www.immigration.govt.nz/documents/partnerships-evidence-guide.pdf)

---

### 2.6 Immigration Domain Summary: Invariants vs Variations

#### Invariants (Common Across All Jurisdictions)

1. **Core Evidence Types**:
   - **Identity**: Passports, birth certificates
   - **Relationship Proof**: Marriage certificate OR cohabitation evidence (12+ months for de facto/common-law)
   - **Financial Evidence**: Joint accounts, joint assets, income proof (for sponsor)
   - **Cohabitation**: Joint lease, utility bills, correspondence to same address
   - **Social Evidence**: Photos, travel, statutory declarations/affidavits from friends/family

2. **Chronological Organization**: All jurisdictions prefer chronological ordering of evidence (oldest to newest for relationship development, most recent first for financial documents)

3. **Genuine Relationship Test**: All jurisdictions assess whether the relationship is genuine (not for immigration fraud), using similar evidence categories

4. **Translation Requirements**: Certified translations required for documents not in English (or French for Canada)

5. **Supporting Statements**: Statutory declarations/affidavits from third parties (friends, family) are valued across all jurisdictions

#### Variations (Jurisdiction-Specific)

1. **Financial Requirements**:
   - **AU**: No minimum income, but high application fee ($9,365)
   - **UK**: Strict income threshold (£29K) or savings (£88.5K)
   - **US**: 125% of poverty guideline (e.g., $24,650 for 2-person household)
   - **CA**: No minimum income for spousal sponsorship (except Quebec/social assistance cases)
   - **NZ**: No minimum income, but sponsor must demonstrate ability to support

2. **Cohabitation Requirements**:
   - **AU**: Not required for married couples, but strengthens application for de facto
   - **UK**: 2+ years required for unmarried partners (OR marriage)
   - **US**: Not required (can sponsor before living together), but strengthens bona fide marriage case
   - **CA**: 12+ months required for common-law (OR marriage)
   - **NZ**: 12+ months required for de facto (OR marriage/civil union)

3. **Submission Method**:
   - **AU**: Online (ImmiAccount)
   - **UK**: Online + document upload OR in-person appointment
   - **US**: Mail (paper) OR online (I-130 only, as of 2023)
   - **CA**: Digital-only (as of 2025)
   - **NZ**: Online OR paper (mail)

4. **File Size/Type Limits**:
   - **AU**: Max 60MB per file
   - **UK**: 2-6MB typical per file
   - **US**: Physical submission (no file size limit), or online (varies)
   - **CA**: Max 4MB per file
   - **NZ**: Max 10MB per file

5. **Processing Times**:
   - **AU**: 18-24 months (820/801)
   - **UK**: 24 weeks (6 months)
   - **US**: 12-24 months (I-130 + I-485 concurrent)
   - **CA**: 12-18 months
   - **NZ**: 6-12 months (residence visa)

#### Design Implications for FileOrganizer

**Configuration-Driven Pack System** can handle:
- **Country parameter**: `country: AU | UK | US | CA | NZ`
- **Visa type parameter**: `type: spouse | partner | de_facto | common_law`
- **Evidence categories**: Hierarchical (Financial → Joint Accounts → Bank Statements)
- **Submission constraints**: Max file size, file type, digital vs physical
- **Export templates**:
  - Category-based PDFs (Financial, Relationship, Accommodation, etc.)
  - Index/checklist with jurisdictional requirements
  - Chronological ordering within categories
  - Photo collage option (grid format)

**Checklist System** (Non-Legal-Advice):
- "Suggested evidence types" per category (e.g., "Joint bank statements: 12+ months")
- "Typical minimum time coverage" (e.g., "Cohabitation: 12 months for de facto")
- Clear disclaimer: "This is a packaging tool, not immigration advice."

**Disclaimer Required**:
> "This pack organizes visa evidence based on official immigration guidance. It is NOT immigration advice and does not assess eligibility or likelihood of approval. Consult a registered immigration adviser or attorney for case-specific guidance."

---

### 2.7 Template Volatility and Maintenance Strategy

**Per GPT Strategic Review**: Immigration template maintenance is critical for Phase 2.5 (Immigration Premium Service).

#### 2.7.1 Volatility Assessment

**High-Volatility Countries** (Quarterly Reviews Required):
1. **Australia (AU)**:
   - **Drivers**: Annual application fee changes (predictable), Form 888 updates (occasional), policy guidance changes (frequent)
   - **Recent Changes**: 2024-25 fee increase ($9,095 → $9,365), digital-first ImmiAccount improvements
   - **Risk**: High (7/10) - Partner visa is politically sensitive, frequent policy adjustments
   - **Recommended Review**: Quarterly (October, January, April, July to align with fee cycles)

2. **United Kingdom (UK)**:
   - **Drivers**: Income threshold adjustments, post-Brexit policy changes, Home Office guidance updates
   - **Recent Changes**: 2024 income threshold increase (£18.6K → £29K), English language test changes
   - **Risk**: High (8/10) - Conservative government policy shifts, immigration bill changes
   - **Recommended Review**: Quarterly (January, April, July, October)

3. **Canada (CA)**:
   - **Drivers**: Digital portal redesigns (2025 digital-only shift), Express Entry score changes
   - **Recent Changes**: 2025 digital-only spousal sponsorship, portal interface updates
   - **Risk**: Medium-High (6/10) - Generally stable but portal changes require template updates
   - **Recommended Review**: Quarterly (for 2025-2026 during digital transition), then semi-annual

**Medium-Volatility Countries** (Semi-Annual Reviews):
4. **United States (US)**:
   - **Drivers**: Administration policy changes, USCIS fee adjustments, online filing expansion
   - **Recent Changes**: 2023 online I-130 filing, 2024 fee increases
   - **Risk**: Medium (5/10) - Marriage-based green card relatively stable process
   - **Recommended Review**: Semi-annual (January, July)

5. **New Zealand (NZ)**:
   - **Drivers**: Skilled Migrant Category changes (affects partner category indirectly), cost of living adjustments
   - **Recent Changes**: 2024 SMC reforms, processing time improvements
   - **Risk**: Low-Medium (4/10) - Partnership visa requirements relatively stable
   - **Recommended Review**: Semi-annual (January, July)

#### 2.7.2 Expert Verification Network

**Required for Premium Service** (Phase 2.5):

| Country | Expert Type | Credentials | Compensation | Backup Coverage |
|---------|-------------|-------------|--------------|-----------------|
| AU | MARA Agent | Migration Agents Registration Authority (Reg #XXXX) | $300-$500/quarterly review | 2-3 agents |
| UK | OISC Advisor | Office of the Immigration Services Commissioner (Level 2+) | £200-£400/quarterly review | 2-3 advisors |
| US | Immigration Attorney | American Immigration Lawyers Association (AILA) member | $400-$600/semi-annual review | 2-3 attorneys |
| CA | RCIC | Regulated Canadian Immigration Consultant (RCIC #XXXX) | CAD $300-$500/quarterly review | 2-3 consultants |
| NZ | IAA Advisor | Immigration Advisers Authority (IAA #XXXX) | NZD $250-$400/semi-annual review | 2-3 advisors |

**Expert Review Workflow**:
1. **Week 1**: Expert reviews official guidance changes since last review (government websites, legislation, case law)
2. **Week 2**: Expert flags required template updates (category changes, new requirements, obsolete guidance)
3. **Week 3**: FileOrganizer team updates YAML templates, documents changelog
4. **Week 4**: Expert validates updated templates, signs off on changes

**Emergency Review Trigger**: Major policy changes (e.g., portal redesign, fee increase, new visa subclass) → 7-day turnaround

#### 2.7.3 Template Update Distribution

**Free Tier** (Static Templates):
- Templates frozen at download version (e.g., v1.0.0)
- Age warning displayed after 6 months: "⚠️ Template 6+ months old. Requirements may have changed."
- Manual re-download option: "Download Latest Version" (free but no automatic updates)

**Premium Tier** (Automatic Updates):
- In-app notification: "AU Partner Visa template updated to v1.2.0 (Form 888 changes)"
- User options:
  1. **Update existing pack** (re-classify documents if categories changed)
  2. **Start new pack with v1.2.0** (keep old pack at v1.0.0)
  3. **Review changelog first** (diff view showing what changed)
- Version locking: Mid-pack stability (user completing pack at v1.0.0 can finish with v1.0.0)

#### 2.7.4 Deprecation Strategy

**When to deprecate a template**:
- Visa subclass abolished or merged (e.g., AU 457 → TSS 482)
- Template accuracy <80% due to major reforms
- Expert network unavailable for 2+ quarters (no verification possible)

**Deprecation Workflow**:
1. Mark template as "Deprecated" in metadata
2. Display warning to users: "⚠️ This visa subclass was abolished on [date]. Use [new template] instead."
3. Redirect users to replacement template (if available)
4. Archive old template (read-only, no updates)

#### 2.7.5 User Communication Strategy

**Update Notification Channels**:
1. **In-App**: Banner notification when user opens pack: "Update available: v1.0.0 → v1.2.0 ([changelog](#))"
2. **Email**: Monthly digest for Premium users: "Your subscribed templates (AU Partner, UK Spouse) were updated this month"
3. **App Push Notification** (optional, opt-in): "URGENT: AU Partner Visa template updated (fee increase)"

**Changelog Format** (User-Friendly):
```markdown
### AU Partner Visa 820/801 - v1.2.0 (2025-04-01)

**What Changed**:
- ✅ Application fee updated: $9,365 → $9,520 (2025-26 financial year)
- ✅ Form 888 updated: New Question 12 added (social media evidence)
- ⚠️ Financial evidence: Now requires 12 months (was 6 months)

**Action Required**:
- If you're still gathering evidence: Add 6 more months of financial docs
- If you've already submitted: No action needed (you're grandfathered)

**Official Source**: [Department of Home Affairs - Partner Visa Guidance](https://example.com)

**Verified By**: Jane Doe, MARA Reg #1234567 (2025-03-28)
```

#### 2.7.6 Phase 2.5 Business Model Integration

**Premium Service Pricing** (per GPT Strategic Review):
- **Single Country**: $9.99/month (quarterly updates)
- **All Countries**: $19.99/month (quarterly updates for all 5)
- **One-Time**: $39 (12-month updates, single country, no auto-renew)

**Success Metrics**:
- Premium adoption: 10-15% of immigration pack users
- Churn: <20% annually
- Expert network retention: >80% (keep experts engaged)
- Template accuracy: >90% (measured by user feedback, expert validation)

**Risk Mitigation**:
- If expert unavailable for 2 quarters → Pause Premium for affected country, offer refunds
- If accuracy <80% → Emergency review, freeze Premium sales until fixed
- If Premium adoption <5% → Pivot to "pay-per-update" model ($9.99 one-time per template update)

---

## PART 3: LEGAL EVIDENCE & TIMELINE PACK FORMATS

### 3.1 Legal Chronology/Timeline Format

#### 3.1.1 Standard Column Structure

Legal chronologies (also called legal timelines) are used across jurisdictions to organize events in litigation or case preparation. While specific formats vary, **common column structures** include:

**Core Columns**:
1. **Date**: Specific date (YYYY-MM-DD or DD/MM/YYYY)
2. **Time** (optional): Timestamp for precision (HH:MM, especially for incidents)
3. **Event Description**: Concise summary of what happened
4. **Parties Involved**: Who was involved (plaintiff, defendant, witnesses, third parties)
5. **Source Document**: Reference to evidence (e.g., "Doc 1", "Email from J. Smith, p. 2", "Bates 001234")
6. **Category/Type**: Event category (Incident, Correspondence, Filing, Medical, Employment, etc.)

**Additional Columns** (Context-Specific):
- **Location**: Where event occurred
- **Witness/Author**: Who observed or created the document
- **Relevance/Notes**: Significance to case, commentary
- **Page/Paragraph Reference**: Specific location in source document
- **Issue Tag**: Link to legal issue or claim (e.g., "Breach of Contract", "Negligence")

**Example Table Structure**:

| Date       | Time  | Event Description | Parties | Source | Category | Notes |
|------------|-------|-------------------|---------|--------|----------|-------|
| 2023-01-15 | 09:30 | Incident: Slip and fall at Store X | Plaintiff, Store Manager | Incident Report (Doc 1) | Incident | Wet floor, no signage |
| 2023-01-15 | 10:15 | Ambulance called | Plaintiff, Paramedics | Ambulance Log (Doc 2) | Medical | Transported to Hospital Y |
| 2023-01-16 | - | Letter to Store X re: injury | Plaintiff → Store X | Letter (Doc 3, Bates 00001-00002) | Correspondence | Demand for compensation |

#### 3.1.2 Best Practices for Chronologies

1. **Objectivity**: Stick to observable facts, avoid subjective interpretation or argument
2. **Source Attribution**: Every event must reference a source document (for credibility and verifiability)
3. **Chronological Order**: Oldest to newest (ascending date order)
4. **Conciseness**: Event descriptions should be brief but informative (1-3 sentences)
5. **Consistency**: Use consistent date/time formats, category labels, and citation styles
6. **Searchability**: Digital chronologies should be text-searchable (OCR for scanned docs)

**Common Event Categories**:
- **Incident**: Key events central to the case (accident, breach, termination)
- **Correspondence**: Emails, letters, text messages
- **Filing**: Court documents, legal notices, complaints
- **Medical**: Doctor visits, diagnoses, treatments, medical reports
- **Employment**: Hiring, performance reviews, disciplinary actions, termination
- **Financial**: Payments, invoices, contracts
- **Witness**: Witness statements, depositions, interviews

#### 3.1.3 Software and Tools

**Common Tools for Legal Chronologies**:
- **Excel/Google Sheets**: Spreadsheet with columns (Date, Event, Source, etc.)
- **Word/Google Docs**: Table format with columns
- **Specialized Software**:
  - **CaseFleet**: Case chronology and fact management
  - **Clio**: Practice management with timeline features
  - **DISCO**: eDiscovery with timeline visualization
  - **MasterFile**: Timeline and case management
  - **Lexology**: Court bundle software with timeline integration

**Export Formats**:
- **Spreadsheet** (Excel, CSV): For data manipulation and filtering
- **PDF Table**: For court submission or sharing with opposing counsel
- **Visual Timeline**: Graphical representation (Gantt-style, horizontal timeline)

#### 3.1.4 Design Implications for FileOrganizer

**Category Hierarchy**:
```
Legal_Timeline/
├── Source_Documents/
│   ├── Incident_Reports/
│   ├── Correspondence/
│   ├── Court_Filings/
│   ├── Medical_Records/
│   ├── Employment_Records/
│   └── Financial_Records/
└── Chronology_Output/
    ├── Chronology_Spreadsheet.xlsx
    ├── Chronology_PDF.pdf
    └── Timeline_Visual.pdf (optional)
```

**Auto-Generated Chronology Features**:
- **OCR + LLM Extraction**: Extract date, parties, event description from documents
- **Automatic Categorization**: Classify events (Incident, Correspondence, etc.)
- **Source Linking**: Reference source document with Bates numbering or document ID
- **Export Options**:
  - Excel table (Date, Time, Event, Parties, Source, Category, Notes)
  - PDF table (formatted for printing)
  - Visual timeline (optional, graphical representation)

**Columns for FileOrganizer-Generated Chronology**:
```
Date | Time | Event Description | Parties | Source Document (ID) | Category | Page/Ref | Notes
```

**Disclaimer**:
> "This chronology is an organizational tool generated from your documents. It is NOT legal advice and may contain errors or omissions. Review and verify all entries with your attorney before using in legal proceedings."

**Sources**:
- [Legal Chronologies - A Beginner's Guide](https://recordgrabber.com/blog/what-is-a-legal-chronology/)
- [How to Create Case Chronologies with Legal Timelines | CaseFleet](https://www.casefleet.com/timelines-case-timeline-software)
- [How to Create a Legal Timeline For Proper Case Chronology](https://www.rev.com/blog/legal-timeline-case-chronology)
- [How to Build Fact-Based Legal Timelines | DISCO](https://csdisco.com/blog/fact-based-legal-timelines)

---

### 3.2 Legal Evidence Bundle Format

#### 3.2.1 Evidence Bundle Structure

Legal evidence bundles (also called court bundles or trial bundles) organize documents for court submission, arbitration, or disclosure. **Common structural elements**:

1. **Index/Table of Contents**:
   - Lists all documents in the bundle with page numbers or tab numbers
   - Organized by section or chronologically
   - Hyperlinked (for electronic bundles)

2. **Dividers/Tabs** (Physical Bundles):
   - Numbered tabs for each document or section (e.g., Tab 1: Incident Reports, Tab 2: Correspondence)
   - Required for bundles >100 pages

3. **Document Numbering**:
   - Sequential document numbers (Document 1, 2, 3, ...) OR
   - Tab numbers (Tab 1, Tab 2, ...) OR
   - Bates numbering (stamped page numbers, e.g., SMITH001234)

4. **Pagination**:
   - **Physical**: Page numbers on bottom or top of each page
   - **Electronic**: PDF page numbering (must match physical bundle if both are submitted)
   - **Rule**: Numbering starts at page 1 for first page of first document and continues sequentially to last page

5. **Bookmarks** (Electronic Bundles):
   - All significant documents and sections must be bookmarked for navigation
   - Bookmark label includes page number (e.g., "Tab 1 – Incident Report (p. 12)")

6. **OCR** (Electronic Bundles):
   - All typed text must be OCR'd (optical character recognition) for searchability
   - Non-OCR bundles are often rejected or penalized (see Bailey v Stonewall case: £20K costs for "randomly thrown together" bundle)

#### 3.2.2 Indexing and Organization Approaches

**Approach 1: Chronological**
- All documents in date order (oldest to newest)
- Simple, easy to navigate for timeline-focused cases
- Example: Personal injury case (incident → medical → correspondence → settlement)

**Approach 2: Category-Based**
- Documents grouped by type (Correspondence, Pleadings, Expert Reports, etc.)
- Chronological within each category
- Example: Employment dispute (Employment Records → Disciplinary Actions → Correspondence → Termination Docs)

**Approach 3: Issue-Based**
- Documents grouped by legal issue or claim
- Example: Contract dispute (Issue 1: Formation → Issue 2: Performance → Issue 3: Breach → Issue 4: Damages)

**Approach 4: Hybrid**
- Combine chronological and category-based (e.g., Section 1: Pleadings (chronological), Section 2: Evidence (by type))

#### 3.2.3 Exhibit Labeling Conventions

**Traditional Labeling**:
- **Plaintiff's Exhibits**: Numbered (Exhibit 1, 2, 3, ...)
- **Defendant's Exhibits**: Lettered (Exhibit A, B, C, ...)
- **Multi-Part Exhibits**: Numbered and lettered (Exhibit 1A, 1B, 1C)

**Court-Specific Rules**:
- Some courts require specific exhibit formats (e.g., pre-marked exhibits, colored labels)
- Check local court rules or practice directions

#### 3.2.4 Common Errors to Avoid

**Bailey v Stonewall Case** (UK Employment Tribunal, 2024):
- **Issue**: 6,500-page bundle described as "exceptionally difficult to work with" and "randomly thrown together"
- **Problems**:
  - Non-OCR readable sections (scanned images without text layer)
  - Mismatched page numbers (PDF page numbers ≠ physical page numbers)
  - Duplicated documents
  - Incomplete indexing (missing hyperlinks)
  - Poor organization
- **Consequence**: £20,000 costs award against the party for unreasonable conduct

**Key Lessons**:
- OCR is mandatory for digital bundles
- Page numbering must be consistent across PDF and physical copies
- Index must be complete and hyperlinked
- Avoid duplicates (check for multiple copies of same document)
- Organization matters: Random ordering confuses court and counsel

#### 3.2.5 Formatting Standards

**File Formatting** (Electronic Bundles):
- **Font**: Uniform, legible font (Times New Roman or Arial, 12-point)
- **Margins**: 1 inch on all sides (standard)
- **Line Spacing**: Consistent (double-spacing for pleadings, single-spacing for exhibits)
- **Color**: Color allowed for demonstrative exhibits (diagrams, charts), but black-and-white acceptable for text documents

**Physical Bundle Standards**:
- **Paper Size**: A4 (UK/AU/NZ/CA) or Letter (US)
- **Binding**: Ring binder or lever arch file (for thick bundles), stapled or spiral-bound (for thin bundles)
- **Dividers**: Clearly labeled with tab numbers or section names

#### 3.2.6 Design Implications for FileOrganizer

**Category Hierarchy**:
```
Legal_Evidence_Bundle/
├── Index/
│   └── Index_with_Hyperlinks.pdf
├── Section_1_Pleadings/
│   ├── 01_Complaint.pdf
│   ├── 02_Answer.pdf
│   └── 03_Counterclaim.pdf
├── Section_2_Correspondence/
│   ├── 04_Letter_2023-01-15.pdf
│   ├── 05_Email_2023-02-10.pdf
│   └── ...
├── Section_3_Expert_Reports/
│   └── 20_Expert_Report_Dr_Smith.pdf
└── Combined_Bundle.pdf (all sections merged, with bookmarks)
```

**Auto-Generated Bundle Features**:
- **Index Generation**: Auto-create index with document names and page numbers
- **Pagination**: Sequential page numbering across all documents
- **Bookmarking**: Auto-bookmark each document in combined PDF
- **OCR**: Ensure all scanned documents are OCR'd
- **Deduplication**: Flag potential duplicate documents
- **Exhibit Labeling**: Auto-assign Exhibit numbers/letters per convention
- **Export Options**:
  - Combined PDF (all documents merged, bookmarked, OCR'd)
  - Individual PDFs per document (for selective submission)
  - Index as separate PDF or Word document
  - Print-ready version with divider pages

**Disclaimer**:
> "This evidence bundle is an organizational tool. It is NOT legal advice. Consult your attorney to ensure compliance with court rules and practice directions."

**Sources**:
- [The basic art of the perfect bundle - Pump Court Chambers](https://www.pumpcourtchambers.com/2024/04/30/the-basic-art-of-the-perfect-bundle/)
- [General guidance on electronic court bundles - Courts and Tribunals Judiciary](https://www.judiciary.uk/guidance-and-resources/general-guidance-on-electronic-court-bundles/)
- [How to Create an Index for Legal Documents — Bundledocs](https://www.bundledocs.com/blog/2012/4/24/how-to-create-an-index-for-legal-documents.html)
- [How to Prepare A Bundle For Court - I AM L.I.P](https://iamlip.com/statements-documents-and-bundles-you-will-need-to-produce-for-the-court/how-to-prepare-a-bundle-for-court/)

---

### 3.3 Legal Domain Summary: Invariants vs Variations

#### Invariants (Common Across Jurisdictions)

1. **Chronological Timelines**: Legal chronologies universally use date-ordered tables with columns for Date, Event, Source, Parties, Category
2. **Source Attribution**: Every entry in a chronology or exhibit in a bundle must reference a source document
3. **Indexed Bundles**: Evidence bundles require an index/table of contents listing all documents with page/tab numbers
4. **Sequential Numbering**: Documents or exhibits are numbered sequentially (1, 2, 3 OR A, B, C)
5. **OCR Requirement**: Digital submissions must be text-searchable (OCR'd)
6. **Pagination**: Consistent page numbering across physical and electronic versions
7. **Objective Presentation**: Legal timelines focus on facts, not argument

#### Variations (Jurisdiction-Specific)

1. **Court-Specific Rules**:
   - UK: CPR 32 PD 27.8 for bundle pagination and indexing
   - US: Federal and state courts have varying rules for exhibit marking and bundle format
   - AU/CA/NZ: Similar common-law traditions, but specific practice directions vary by court

2. **Exhibit Labeling**:
   - Plaintiff/Defendant: Numbers vs Letters (traditional, but not universal)
   - Some courts: Pre-marked exhibits with specific color-coding

3. **Physical vs Electronic**:
   - UK: Increasing preference for electronic bundles (especially post-COVID)
   - US: Mix of physical and electronic, varies by court
   - AU/CA/NZ: Growing electronic adoption, but physical still common

4. **File Size Limits**:
   - Vary by court and jurisdiction (no universal standard)
   - Typical: 5-10MB per file for court portals

#### Design Implications for FileOrganizer

**Generic Legal Timeline Pack**:
- Configuration-driven column structure (Date, Time, Event, Parties, Source, Category, Notes)
- Auto-extract events from documents (OCR + LLM)
- Export to Excel, PDF, or visual timeline
- Category tagging (Incident, Correspondence, Filing, Medical, Employment, Financial)

**Generic Legal Evidence Bundle Pack**:
- Auto-index generation with hyperlinks
- Sequential pagination and document numbering
- Bookmarking for electronic bundles
- OCR verification (flag non-searchable PDFs)
- Deduplication detection
- Export options: Combined PDF (bookmarked, OCR'd) OR individual PDFs + index

**Disclaimer Required**:
> "This legal timeline/bundle is an organizational tool. It is NOT legal advice and does not replace attorney review. Verify all entries, citations, and formatting comply with applicable court rules before submission."

---

## PART 4: CROSS-DOMAIN DESIGN IMPLICATIONS

### 4.1 Common Patterns Across All Domains

**Pattern 1: Category Hierarchy**
- All three domains (Tax, Immigration, Legal) use **hierarchical categories** to organize evidence:
  - Tax: Income → Platform Income → Uber Earnings
  - Immigration: Financial → Joint Accounts → Bank Statements
  - Legal: Correspondence → Emails → Email from Plaintiff 2023-01-15
- FileOrganizer's folder/tag structure maps well to this pattern

**Pattern 2: Chronological Ordering**
- All domains require chronological organization (within categories):
  - Tax: Receipts by date (most recent first for financials, oldest first for multi-year summaries)
  - Immigration: Relationship evidence by date (oldest to newest)
  - Legal: Timeline events by date (oldest to newest)
- FileOrganizer must support flexible chronological sorting

**Pattern 3: Source Attribution**
- All domains require linking outputs to source documents:
  - Tax: Expense category totals → individual receipts
  - Immigration: Relationship claim → supporting photos/bills
  - Legal: Chronology event → source document (Bates number or exhibit ID)
- FileOrganizer must maintain source references in exports

**Pattern 4: Index/Summary Generation**
- All domains benefit from auto-generated summaries:
  - Tax: Category totals (total fuel expenses: $5,432.10)
  - Immigration: Checklist of evidence types included
  - Legal: Index of documents with page numbers
- FileOrganizer should auto-generate these summaries

**Pattern 5: Export Flexibility**
- Users need multiple export formats:
  - Combined PDF per category (Tax: all fuel receipts in one PDF)
  - Individual PDFs with index (Immigration: separate files per document, max 4MB each)
  - Spreadsheet summaries (Tax: expense breakdown by category)
  - Visual outputs (Legal: timeline graph, Immigration: photo collage)

### 4.2 Configuration Schema Proposal

**Pack Template Structure** (YAML example):

```yaml
pack:
  id: "tax_au_bas_rideshare_v1"
  name: "Australia BAS - Rideshare Driver"
  domain: "tax"
  country: "AU"
  version: "1.0"
  description: "Organize quarterly BAS evidence for Australian rideshare drivers (Uber, Ola, etc.)"

  disclaimers:
    - "This pack organizes your documents for tax preparation. It is NOT tax advice."
    - "Consult a registered tax agent for professional guidance."

  categories:
    - id: "income_rideshare"
      name: "Rideshare Income"
      parent: "income"
      description: "Uber, Ola, DiDi earnings statements"
      typical_documents:
        - "Platform weekly/monthly summaries"
        - "Bank deposit records"
      form_mapping:
        - field: "G1"
          description: "Total Sales (including GST)"
        - field: "1A"
          description: "GST on Sales (10% of G1)"

    - id: "expenses_fuel"
      name: "Fuel Expenses"
      parent: "expenses"
      description: "Fuel receipts for business use"
      typical_documents:
        - "Fuel receipts (paper or digital)"
      deduction_notes: "Can claim business use % × total fuel costs"
      form_mapping:
        - field: "1B"
          description: "GST on Purchases"

  export_recipes:
    - type: "spreadsheet"
      format: "xlsx"
      columns:
        - "Date"
        - "Description"
        - "Category"
        - "Amount (Inc GST)"
        - "GST Component"
        - "Counterparty"
        - "Notes"

    - type: "pdf_bundle"
      mode: "per_category"  # OR "combined_all"
      include_index: true
      chronological_order: "desc"  # Most recent first for financials

  thresholds:
    - name: "GST Registration"
      value: 75000
      currency: "AUD"
      period: "annual"
      description: "Required if turnover ≥$75,000"
```

**Key Configuration Elements**:
- **Metadata**: Pack ID, name, domain, country, version
- **Categories**: Hierarchical structure with parent/child relationships
- **Form Mappings**: Category → tax form field (for summary reports)
- **Export Recipes**: Define output formats (spreadsheet, PDF, PPT)
- **Thresholds**: Country-specific values (GST registration, income limits)
- **Disclaimers**: Domain-appropriate legal disclaimers

### 4.3 Integration with FileOrganizer Core Engine

**Ingestion Pipeline**:
1. User selects pack (e.g., "Australia BAS - Rideshare")
2. Pack config loads category hierarchy and rules
3. User uploads documents (receipts, statements, etc.)
4. Core engine: OCR + LLM classification → assign to categories
5. Triage UI: Present unknowns or low-confidence classifications for user correction
6. User confirms or corrects category assignments
7. Pack state updated with categorized documents

**Rules & Profiles Engine**:
- Pack extends global rules with pack-specific overrides
- Example: Global rule "Bank statements → Financial Records" + Pack rule "Bank statements with Uber deposits → Rideshare Income"
- User corrections in pack context update pack rules (ephemeral) OR global rules (persistent, if user chooses to generalize)

**Export Pipeline**:
1. User triggers export (e.g., "Generate BAS summary")
2. Pack config defines export recipe (spreadsheet + PDF bundles)
3. Export engine:
   - Generates spreadsheet with category totals
   - Creates per-category PDFs (chronological ordering)
   - Auto-generates index/summary
   - Applies disclaimers to exports
4. Outputs saved to user-selected folder

**Triage UI Integration**:
- Show pack-specific checklist (e.g., "Suggested evidence: Fuel receipts (12 months)")
- Highlight missing or incomplete categories
- Allow user to reassign documents between categories (drag-and-drop)
- Update pack state in real-time

### 4.4 Handling Unknowns and User Corrections

**Scenario**: User uploads fuel receipt, but LLM classifies it as "Office Expense" (low confidence)

**Triage Flow**:
1. Triage UI shows document with suggested category "Office Expense" (confidence: 60%)
2. User sees pack-specific categories: "Fuel Expenses" is listed
3. User corrects: Reassigns to "Fuel Expenses"
4. System prompts: "Apply this correction as a rule for future documents?"
   - Option A: "Only for this pack" (ephemeral, pack-specific rule)
   - Option B: "For all packs" (persistent, global rule update)
5. User selects Option A → Pack rule updated: "Receipts from [Gas Station Name] → Fuel Expenses"

**Correction Persistence**:
- **Ephemeral** (pack instance): Correction applies only to current pack run
- **Persistent** (pack template): Correction updates pack template for future uses
- **Global** (core rules): Correction updates core classification rules for all packs

### 4.5 Safety and Disclaimers

**Where Disclaimers Appear**:
1. **Pack Selection Screen**: Before user starts pack, show disclaimer and require acknowledgment
2. **Export Outputs**: Include disclaimer text in generated spreadsheets, PDFs, PPTs (footer or header)
3. **Pack Summary Reports**: Disclaimer at top of summary (e.g., "Total Fuel Expenses: $5,432.10. This is NOT a tax deduction claim.")

**Disclaimer Language Examples**:

**Tax Packs**:
> "This pack organizes your documents and provides category summaries to assist with tax preparation. It is NOT tax advice and does NOT determine deductibility or calculate tax liabilities. Consult a registered tax agent or accountant for professional guidance."

**Immigration Packs**:
> "This pack organizes visa evidence based on official immigration guidance. It is NOT immigration advice and does NOT assess eligibility or likelihood of approval. Consult a registered migration agent (MARA), immigration attorney, RCIC, or licensed immigration adviser for case-specific guidance."

**Legal Packs**:
> "This legal timeline/evidence bundle is an organizational tool. It is NOT legal advice and does NOT replace attorney review. Verify all entries, citations, and formatting comply with applicable court rules before submission."

### 4.6 Country and Pack Extensibility

**Adding a New Country**:
1. Create new pack template YAML (e.g., `tax_de_vat_sole_trader_v1.yaml` for Germany)
2. Define country-specific categories, form mappings, thresholds
3. Add country code to FileOrganizer's country list
4. No code changes required (configuration-driven)

**Updating an Existing Pack**:
1. Increment pack version (e.g., `tax_au_bas_rideshare_v1.1.yaml`)
2. Update categories, mappings, or thresholds
3. Existing user packs continue using old version (no silent changes)
4. User can optionally upgrade pack to new version

**Pack Versioning**:
- **Version format**: Semantic versioning (major.minor.patch)
- **Version policy**: Breaking changes → major version bump (user must manually upgrade)
- **Backward compatibility**: Old pack instances remain valid, use their original config version

**Community Packs** (Future):
- Users can create and share custom pack templates
- Moderation/review process for safety and accuracy
- Rating/feedback system for pack quality

---

## PART 5: APPENDICES

### Appendix A: Tax Form Field Reference (High-Level)

**Australia BAS**:
- G1: Total Sales (including GST)
- 1A: GST on Sales (Output Tax)
- 1B: GST on Purchases (Input Tax Credit)
- W1-W4: PAYG Withholding

**UK Self Assessment SA103S**:
- Box 13: Turnover (Total Sales)
- Box 17: Cost of Goods Sold
- Box 18: Car, Van, Travel Expenses
- Box 19: Rent, Rates, Power, Insurance
- Box 21: Phone, Stationery, Office Costs
- Box 26: Other Allowable Expenses

**US Schedule C**:
- Line 1: Gross Receipts or Sales
- Line 9: Car and Truck Expenses
- Line 18: Office Expense
- Line 22: Supplies
- Line 25: Utilities
- Line 27a: Other Expenses

**Canada T2125**:
- Line 8230: Sales, Commissions, or Fees
- Line 9281: Motor Vehicle Expenses
- Line 9220: Telephone and Utilities
- Line 9945: Home Office Expenses

**New Zealand IR3**:
- Self-Employment Income field (no specific line number, section-based)
- Expense categories (similar to AU/UK/CA)

### Appendix B: Immigration Evidence Checklist (Generic)

**Financial Evidence**:
- [ ] Joint bank statements (12+ months)
- [ ] Joint property ownership or lease
- [ ] Joint credit cards or loans
- [ ] Beneficiary designations (life insurance, retirement accounts)

**Cohabitation Evidence**:
- [ ] Utility bills in both names (12+ months, spread across period)
- [ ] Correspondence to same address (official mail, driver's license)
- [ ] Photos of shared living space

**Relationship Evidence**:
- [ ] Marriage certificate (if married) OR statutory declaration (if de facto/common-law)
- [ ] Photos together (chronological, 20-40 images)
- [ ] Travel evidence (joint trips, passport stamps)
- [ ] Communication (emails, messages, call logs - sample, not exhaustive)
- [ ] Statutory declarations from friends/family (2-4)

**Identity/Civil Documents**:
- [ ] Passports (biodata pages)
- [ ] Birth certificates
- [ ] Police certificates
- [ ] Medical certificates (if required)
- [ ] Previous marriage termination documents (if applicable)

### Appendix C: Legal Timeline Categories (Generic)

**Event Categories**:
- **Incident**: Key events central to the case
- **Correspondence**: Emails, letters, text messages
- **Filing**: Court documents, legal notices
- **Medical**: Doctor visits, diagnoses, treatments
- **Employment**: Hiring, reviews, disciplinary actions, termination
- **Financial**: Payments, invoices, contracts
- **Witness**: Statements, depositions, interviews
- **Other**: Catch-all for uncategorized events

**Chronology Column Structure**:
| Date | Time | Event Description | Parties | Source Document | Category | Notes |
|------|------|-------------------|---------|-----------------|----------|-------|

### Appendix D: Evidence Bundle Index Template (Generic)

**Index Format**:

```
EVIDENCE BUNDLE INDEX
Case Name: [Plaintiff v Defendant]
Date: [YYYY-MM-DD]

SECTION 1: PLEADINGS
Document 1: Complaint (p. 1-15)
Document 2: Answer (p. 16-28)
Document 3: Counterclaim (p. 29-35)

SECTION 2: CORRESPONDENCE
Document 4: Letter from Plaintiff, 2023-01-15 (p. 36-37)
Document 5: Email from Defendant, 2023-02-10 (p. 38-39)
...

SECTION 3: EXPERT REPORTS
Document 20: Expert Report - Dr. Smith (p. 150-180)

Total Pages: 180
```

**Electronic Bundle**: Index must be hyperlinked (each document entry links to PDF bookmark)

---

## PART 6: CONCLUSION AND NEXT STEPS

### 6.1 Research Summary

This research report documents structural requirements, evidence categories, and packaging conventions for three core scenario pack domains across five jurisdictions:

**Tax/BAS Domain** (AU, UK, US, CA, NZ):
- Strong cross-jurisdiction invariants: Income/expense categories, GST/VAT concept, vehicle/home office deductions
- Jurisdiction-specific variations: Thresholds ($0-£85K), tax rates (0-20%), form field names
- Design implication: Configuration-driven pack system with country parameter + category mappings

**Immigration Domain** (AU, UK, US, CA, NZ):
- Strong cross-jurisdiction invariants: Financial, relationship, cohabitation, identity evidence types
- Jurisdiction-specific variations: Financial requirements (AU: $9,365 fee, UK: £29K income, US: 125% poverty guideline), cohabitation requirements (12-24 months for de facto), submission methods (digital vs physical)
- Design implication: Pack templates with country-specific checklists + file size/type constraints

**Legal Evidence Domain** (Cross-Jurisdictional):
- Universal patterns: Chronological timelines with Date/Event/Source/Category columns, indexed evidence bundles with sequential numbering
- Jurisdiction-specific variations: Court-specific rules (CPR 32 PD 27.8 in UK), exhibit labeling conventions
- Design implication: Generic timeline and bundle packs with flexible column/category structures

**Common Patterns Across All Domains**:
1. Hierarchical category structures (Income → Rideshare → Uber)
2. Chronological ordering (within categories)
3. Source attribution (link outputs to source documents)
4. Index/summary generation (auto-generated totals, checklists, tables of contents)
5. Export flexibility (spreadsheet, PDF, visual formats)

### 6.2 Key Design Decisions for FileOrganizer

1. **Configuration-Driven Pack System**: Use YAML/JSON templates to define pack metadata, categories, form mappings, export recipes, and disclaimers → Enables adding new packs/countries without code changes

2. **Category Hierarchy with Flexible Depth**: Support parent/child category relationships (e.g., Expenses → Vehicle → Fuel) → Maps well to folder/tag structure

3. **Jurisdiction Parameters**: Country and domain parameters drive pack behavior (thresholds, form fields, submission constraints) → Reuse 80% of pack logic, override 20% for country-specific needs

4. **Export Recipe System**: Define multiple export formats per pack (spreadsheet, PDF bundles, visual timelines) → Users get domain-appropriate outputs

5. **Disclaimer Framework**: Mandatory disclaimers at pack selection, in exports, and in summaries → Mitigate legal/tax/immigration advice risk

6. **Correction Persistence Options**: Allow users to apply corrections at pack instance, pack template, or global rule level → Balance flexibility with learning

7. **Versioning for Packs**: Semantic versioning for pack templates, no silent updates to existing user packs → Stability and predictability

### 6.3 Next Steps (For Implementation Plan)

This research report provides the **factual foundation** for pack design. The companion **Implementation Plan** (`implementation_plan_tax_immigration_legal_packs.md`) will:

1. Propose concrete configuration schema (YAML format with all required fields)
2. Define initial pack templates to implement (prioritized list)
3. Describe integration with FileOrganizer core engine (ingestion, triage, export)
4. Specify handling of unknowns and user corrections
5. Detail safety and disclaimer approach
6. Define country/pack extensibility mechanisms
7. Outline prioritized milestones for implementation

**This report is complete. Proceed to Implementation Plan for technical specifications.**

---

**Report prepared by**: Claude (Autopack Research Agent)
**Date**: 2025-11-27
**Word Count**: ~19,500 words
**Document Status**: Final, ready for review and implementation planning
