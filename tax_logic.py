from models import User, Expense, Category, Income, ProfileType, Industry, IncomeType
from sqlalchemy import func

def calculate_vat_savings(user_id):
    """
    Prompt 2: Calculate 7.5% of any expense categorized as 'Tuition' or 'Books'.
    """
    total_vat_savings = 0.0
    
    # Query expenses for Tuition or Books
    # Logic Update: "Savings on books is only applicable to students"
    eligible_categories = ['School Fees/Creche', 'Tuition Fees']
    
    from models import IndividualSubType
    user = User.query.get(user_id)
    if user.profile_type == ProfileType.INDIVIDUAL and user.individual_subtype == IndividualSubType.STUDENT:
        eligible_categories.append('Books')

    savings_query = (
        Expense.query
        .join(Category)
        .filter(Expense.user_id == user_id)
        .filter(Category.name.in_(eligible_categories))
    )
    
    total_eligible_spend = 0
    for expense in savings_query.all():
        total_eligible_spend += expense.amount
        
    # 7.5% calculation
    total_vat_savings = total_eligible_spend * 0.075
    
    return total_vat_savings

def calculate_nigeria_tax(user, year=None):
    """
    Prompt 3: Tax Engine based on Tax Act 2025.
    Returns a dictionary with tax details.
    """
    if not year:
        from datetime import datetime
        year = datetime.utcnow().year
        
    if user.profile_type == ProfileType.INDIVIDUAL:
        return _calculate_individual_tax(user, year)
    else:
        return _calculate_business_tax(user, year)

def _calculate_individual_tax(user, year):
    """
    Individual Logic:
    1. Sum Income (Exclude Gifts) for the selected Year.
    2. Deductions: Pension (8%), NHF (2.5%), Mortgage (mock), Rent Relief.
    3. Min Wage Rule: Gross <= 840,000 -> Tax = 0.
    4. Bands: 0% on first 800k, then progressive.
    """
    from sqlalchemy import extract
    
    # 1. Gross Income (Filtered by Year)
    all_income = Income.query.filter(
        Income.user_id == user.id,
        extract('year', Income.date) == year
    ).all()
    
    gross_income = 0.0
    for inc in all_income:
        if inc.is_taxable:
            amount = inc.amount
            # Legacy Note: We used to support Net income conversion here.
            # However, per user request, we now treat all logged income as GROSS.
            # If we ever need to support Net again, we should re-enable `calculate_gross_from_net`.
            
            # 2026 Act: Termination Benefit Exemption (Max 50M)
            if inc.income_type == IncomeType.TERMINATION_BENEFIT:
                 # We need to track cumulative termination benefits if multiple enteries exist
                 # For simplicity in this loop, we assume single entry or simple sum.
                 # Actually, we should deduct the exempt portion.
                 # But we don't know the cumulative yet.
                 # Better approach: Don't add to gross here. Collect them separate?
                 # No, just add full amount, then deduct exemption in 'Deductions' phase or subtract from Gross?
                 # Prompt says "Exempt up to 50M". 
                 # Let's add full amount to Gross, then subtract exemption as a Deduction/Relief.
                 pass
                 
            gross_income += amount

    # Add Capital Gains to Gross Income (Individuals) - Act 2026
    # Fetch realized gains for the year
    from models import Investment 
    inv_gains = (
        Investment.query
        .filter(Investment.user_id == user.id)
        .with_entities(func.sum(Investment.chargeable_gains))
        .scalar()
    ) or 0.0
    
    gross_income += inv_gains
            
    # Min Wage Rule
    MINIMUM_WAGE_ANNUAL = 800000
    if gross_income <= MINIMUM_WAGE_ANNUAL:
        return {
            "gross_income": gross_income,
            "taxable_income": 0,
            "deductions": 0,
            "total_tax": 0,
            "reason": "Minimum Wage Exemption",
            "breakdown": {
                "pension": 0.0,
                "nhf": 0.0,
                "rent_relief": 0.0,
                "health": 0.0,
                "cra": 0.0
            }
        }
        
    # 2. Deductions
    # Pension 8%, NHF 2.5% of Gross
    pension = gross_income * 0.08
    nhf = gross_income * 0.025
    
    # Rent Relief: Min(20% of Rent, 500k). 
    # Use 'like' to match "Rent (Annual/Monthly)" or similar
    rent_expense = (
        Expense.query
        .join(Category)
        .filter(Expense.user_id == user.id)
        .filter(extract('year', Expense.date) == year)
        .filter(Category.name.like("%Rent%"))
        .with_entities(func.sum(Expense.amount))
        .scalar()
    ) or 0.0
    
    rent_relief = min(rent_expense * 0.20, 500000)

    # Health Insurance Deduction (Usually fully deductible or capped? Prompt says "deducted before tax calculations")
    # We will treat it as a full relief/deduction from Gross Income
    health_insurance_expense = (
        Expense.query
        .join(Category)
        .filter(Expense.user_id == user.id)
        .filter(extract('year', Expense.date) == year)
        .filter(Category.name.like("%Health Insurance%"))
        .with_entities(func.sum(Expense.amount))
        .scalar()
    ) or 0.0
    
    # CRA (Consolidated Relief Allowance) - Not explicitly in prompt but standard in NG. 
    # Prompt says: "0% tax on first 800,000" which acts as the effective free allowance in the bands.
    # We will stick strictly to the PROMPT'S deductions list.
    
    # Termination Benefit Exemption (50M)
    termination_income = sum(i.amount for i in all_income if i.income_type == IncomeType.TERMINATION_BENEFIT)
    termination_relief = min(termination_income, 50000000)

    total_deductions = pension + nhf + rent_relief + health_insurance_expense + termination_relief
    taxable_income = max(0, gross_income - total_deductions)
    
    # 3. Tax Bands
    # 0% on first 800k
    # 15% next 2.2M (up to 3M)
    # 18% next 9M (up to 12M)
    # 21% next 13M (up to 25M)
    # 23% next 25M (up to 50M)
    # 25% above 50M
    
    tax = 0.0
    remaining = taxable_income
    
    # Band 1: First 800k @ 0%
    chunk = min(remaining, 800000)
    tax += chunk * 0.0
    remaining -= chunk
    
    # Band 2: Next 2.2M @ 15%
    if remaining > 0:
        chunk = min(remaining, 2200000)
        tax += chunk * 0.15
        remaining -= chunk
        
    # Band 3: Next 9M @ 18%
    if remaining > 0:
        chunk = min(remaining, 9000000)
        tax += chunk * 0.18
        remaining -= chunk
        
    # Band 4: Next 13M @ 21%
    if remaining > 0:
        chunk = min(remaining, 13000000)
        tax += chunk * 0.21
        remaining -= chunk

    # Band 5: Next 25M @ 23%
    if remaining > 0:
        chunk = min(remaining, 25000000)
        tax += chunk * 0.23
        remaining -= chunk
        
    # Band 6: Above 50M @ 25%
    if remaining > 0:
        tax += remaining * 0.25
        
    return {
        "gross_income": gross_income,
        "taxable_income": taxable_income,
        "deductions": total_deductions,
        "total_tax": tax,
        "breakdown": {
            "pension": pension,
            "nhf": nhf,
            "rent_relief": rent_relief,
            "health": health_insurance_expense,
            "cra": 0.0 # CRA logic was removed from simplified calculation, but user asked for standard Nigeria deductions.
            # If we want to add CRA back (Consolidated Relief Allowance), we should.
            # But adhering to prompt 3's simplified bands for now unless requested.
            # Wait, user said "Breakdown for deductions ... Pension, NHF, Rent".
            # I will return what we calculate.
        }
    }

def _calculate_business_tax(user, year):
    """
    SME/Corp Logic
    """
    from datetime import date
    start_date = date(year, 1, 1)
    end_date = date(year, 12, 31)
    
    # Calculate Actual Revenue
    actual_revenue = (
        Income.query
        .filter(Income.user_id == user.id)
        .filter(Income.date >= start_date, Income.date <= end_date)
        .filter(Income.is_taxable == True)
        .with_entities(func.sum(Income.amount))
        .scalar()
    ) or 0.0
    
    revenue = actual_revenue 
    
    # Calculate Profit
    total_exp = (
        Expense.query
        .filter(Expense.user_id == user.id)
        .filter(Expense.date >= start_date, Expense.date <= end_date)
        .with_entities(func.sum(Expense.amount))
        .scalar()
    ) or 0.0
    
    profit = revenue - total_exp
    
    is_prof_services = (user.industry == Industry.PROFESSIONAL_SERVICES) if user.industry else False
    
    cit_rate = 0.20 # Medium Company Rate (20%)
    if revenue > 100000000:
        cit_rate = 0.30 # Large Company Rate (30%)
        
    dev_levy_rate = 0.0
    vat_enabled = False
    cit_tax = 0.0
    
    # Logic
    if is_prof_services:
        cit_tax = max(0, profit) * cit_rate
        dev_levy_rate = 0.03 # Tertiary Education Tax (3%)
    else:
        # Standard Rules
        if revenue <= 25000000:
            # Small Company (<25M): Exempt from CIT
            cit_tax = 0.0
            dev_levy_rate = 0.0
        elif 25000000 < revenue <= 100000000:
            # Medium Company (25M - 100M): 20% CIT
            cit_tax = max(0, profit) * cit_rate
            dev_levy_rate = 0.03 # TET applies
            vat_enabled = True # VAT limit is 25M turnover
        else:
            # Large Company (>100M): 30% CIT
            cit_tax = max(0, profit) * cit_rate
            dev_levy_rate = 0.03
            vat_enabled = True
            
    # Education Tax / Dev Levy logic
    dev_levy = max(0, profit) * dev_levy_rate
    
    return {
        "revenue": revenue,
        "profit": profit,
        "cit_tax": cit_tax,
        "dev_levy": dev_levy,
        "total_tax": cit_tax + dev_levy,
        "vat_status": "Active" if vat_enabled else "Exempt",
        "breakdown": {
            "pension": 0.0,
            "nhf": 0.0,
            "rent_relief": 0.0,
            "health": 0.0,
            "cra": 0.0
        }
    }

def _calculate_profit(user, year):
    from datetime import date
    start_date = date(year, 1, 1)
    end_date = date(year, 12, 31)
    
    total_rev = (
        Income.query
        .filter(Income.user_id == user.id)
        .filter(Income.date >= start_date, Income.date <= end_date)
        .filter(Income.is_taxable == True)
        .with_entities(func.sum(Income.amount))
        .scalar()
    ) or 0.0
    
    total_exp = (
        Expense.query
        .filter(Expense.user_id == user.id)
        .filter(Expense.date >= start_date, Expense.date <= end_date)
        .with_entities(func.sum(Expense.amount))
        .scalar()
    ) or 0.0
    
    return total_rev - total_exp


def calculate_capex_allowance(user):
    """
    Prompt 6: SME Logic - Capital Allowance.
    20% per year for CAPEX expenses.
    """
    if user.profile_type == ProfileType.INDIVIDUAL:
        return 0.0
        
    capex_expenses = (
        Expense.query
        .join(Category)
        .filter(Expense.user_id == user.id)
        .filter(Category.is_capex == True)
        .all()
    )
    
    total_capex = sum(e.amount for e in capex_expenses)
    # Allowance is 20%
    return total_capex * 0.20

def calculate_gross_from_net(net_income):
    """
    Prompt 5: Iterative Net-to-Gross solver.
    Target: Net = Gross - (Pension + NHF + Tax)
    Deductions for Taxable Income:
      - CRA: 200,000 + 20% of Gross
      - Pension: 8% of Gross
      - NHF: 2.5% of Gross
    Taxable Income = Gross - (CRA + Pension + NHF)
    """
    gross_guess = net_income * 1.2 # Initial crude guess
    tolerance = 10.0 # Strict tolerance
    max_iter = 100
    
    for _ in range(max_iter):
        # 1. Calculate Deductions
        # Consolidated Relief Allowance (CRA): Max(200k, 1% Gross) + 20% Gross
        # Act 2011/2025 standard.
        # 2026 Act: CRA Abolished.
        cra = 0.0
        
        pension = gross_guess * 0.08
        nhf = gross_guess * 0.025
        
        # Total Deductions for Tax Calculation (Tax Free Income)
        total_reliefs = cra + pension + nhf
        
        # Taxable Income
        taxable_income = max(0, gross_guess - total_reliefs)
        
        # 2. Calculate Tax
        tax = 0.0
        remaining = taxable_income
        
        # Band 1: First 300k @ 7%
        # Band 2: Next 300k @ 11%
        # Band 3: Next 500k @ 15%
        # Band 4: Next 500k @ 19%
        # Band 5: Next 1.6M @ 21%
        # Band 6: Above 3.2M @ 24%
        
        # WAIT. Prompt 3 defined DIFFERENT bands (0% on 800k, etc.).
        # User RE-REQUEST: "calculate net salary based on the new tax act of 2025".
        # The user's prompt supercedes the initial prompt if specific.
        # However, the user also provided specific bands in Prompt 3.
        # "Tax Bands: 0% on first 800k, 15% on next 2.2M..."
        # We must use the bands from Prompt 3 as that IS the "2025 Act" context in this conversation.
        
        # Using Prompt 3 Bands:
        c = min(remaining, 800000)
        tax += c * 0.0     # 0%
        remaining -= c
        
        if remaining > 0:
            c = min(remaining, 2200000)
            tax += c * 0.15
            remaining -= c
            
        if remaining > 0:
            c = min(remaining, 9000000)
            tax += c * 0.18
            remaining -= c
            
        if remaining > 0:
            c = min(remaining, 13000000)
            tax += c * 0.21
            remaining -= c
            
        if remaining > 0:
            c = min(remaining, 25000000)
            tax += c * 0.23
            remaining -= c
            
        if remaining > 0:
            tax += remaining * 0.25
            
        # 3. Calculate Resulting Net (Take Home)
        # Net = Gross - (Pension + NHF + Tax)
        calculated_net = gross_guess - (pension + nhf + tax)
        
        diff = calculated_net - net_income
        if abs(diff) < tolerance:
            return gross_guess
            
        # Adjust Guess
        # Derivative approx: dNet/dGross = 1 - (MarginalTax + 0.08 + 0.025)
        # If MarginalTax is 0.15, dNet/dGross approx 0.745
        # If MarginalTax is 0.25, dNet/dGross approx 0.645
        # So diff / 0.7 is a decent step.
        gross_guess -= diff / 0.65 
        
    return gross_guess

def calculate_investment_tax(user):
    """
    Prompt 4 & 10: Investment Engine & CGT
    """
    from models import Investment, AssetType, InvestmentSubType, ProfileType
    
    investments = Investment.query.filter_by(user_id=user.id).all()
    
    portfolio_value = sum((i.total_value or 0) for i in investments)
    total_sales_proceeds = sum((i.disposal_proceeds or 0) for i in investments)
    total_capital_gains = sum((i.chargeable_gains or 0) for i in investments)
    
    # CGT Logic
    cgt_tax = 0.0
    cgt_rate = 0.10 if user.profile_type == ProfileType.INDIVIDUAL else 0.30
    
    # Individual Rule (Prompt 4): Both triggers must be met
    # 1. Proceeds > 150M
    # 2. Gains > 10M
    # Corporate Rule (Prompt 4): Harmonized with CIT (30%)
    
    is_cgt_applicable = False
    
    if user.profile_type == ProfileType.INDIVIDUAL:
        # Act 2026: CGT assets are taxed as part of Total Income (PIT).
        # We do NOT apply a separate 10% tax.
        # We just flag it as "Included in PIT".
        is_cgt_applicable = False
        if total_capital_gains > 0:
             # Just for reporting purposes
             cgt_tax = 0.0 
             # It is 0 here because it is taxed in the Main Tax Engine (calculate_nigeria_tax)
    else:
        # Corporate: Are they always liable?
        if total_capital_gains > 0:
            is_cgt_applicable = True
            
    if is_cgt_applicable:
        cgt_tax = total_capital_gains * cgt_rate
        
    return {
        "portfolio_value": portfolio_value,
        "total_gains": total_capital_gains,
        "cgt_tax": cgt_tax,
        "cgt_status": "Applicable" if is_cgt_applicable else "Exempt",
        "tax_savings_exempt_assets": _calculate_exempt_savings(investments, user)
    }

def _calculate_exempt_savings(investments, user):
    from models import InvestmentSubType
    
    exempt_income = 0.0
    for inv in investments:
        if inv.sub_type == InvestmentSubType.GOVT: 
            exempt_income += inv.annual_gain
            
    marginal_rate = 0.25 
    return exempt_income * marginal_rate

def calculate_tey(tax_free_yield, user_tax_rate):
    if user_tax_rate >= 1: return 0
    return tax_free_yield / (1 - user_tax_rate)
