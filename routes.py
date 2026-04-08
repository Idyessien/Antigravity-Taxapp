from flask import Blueprint, render_template, request, redirect, url_for
from flask_login import login_required, current_user
from models import db

main = Blueprint('main', __name__)

@main.route('/')
def index():
    return render_template('landing.html')

@main.route('/onboarding')
@login_required
def onboarding():
    return render_template('onboarding.html', user=current_user)

@main.route('/onboarding/complete', methods=['POST'])
@login_required
def onboarding_complete():
    from models import db, SavingsGoal, TaxDeadline
    from datetime import date, datetime
    
    # 1. Update Profile Logic
    if current_user.profile_type.name != 'INDIVIDUAL':
        # Business
        industry = request.form.get('industry')
        employees = request.form.get('employees')
        
        if industry:
            current_user.industry = industry # Assuming model has this field or we'll skip if not
            # Note: If User model doesn't have industry column, this might fail unless added. 
            # I recall 'industry' being used in tax_logic.py line 242: user.industry == Industry.PROFESSIONAL...
            # So the column exists.
            
        if employees == 'yes':
            # Create PAYE Deadline
            next_month = date.today().month + 1
            year = date.today().year
            if next_month > 12: next_month = 12
            
            # Check exist
            exists = TaxDeadline.query.filter_by(user_id=current_user.id, title='PAYE Remittance (Setup)').first()
            if not exists:
                deadline = TaxDeadline(
                    user_id=current_user.id,
                    title='PAYE Remittance (Setup)',
                    due_date=date(year, next_month, 10),
                    description="Remit employee taxes (Auto-created)"
                )
                db.session.add(deadline)
                
    else:
        # Individual
        goal_name = request.form.get('goal')
        if goal_name:
            # Create Goal
            goal = SavingsGoal(
                user_id=current_user.id,
                name=goal_name,
                target_amount=100000, # Default target
                current_amount=0,
                deadline=date(date.today().year, 12, 31)
            )
            db.session.add(goal)
            
    db.session.commit()
    return redirect(url_for('main.dashboard'))

@main.route('/dashboard')
@login_required
def dashboard():
    from tax_logic import calculate_vat_savings, calculate_nigeria_tax
    from models import WHTCredit
    
    vat_savings = calculate_vat_savings(current_user.id)
    tax_info = calculate_nigeria_tax(current_user)
    
    # WHT Logic
    credits = WHTCredit.query.filter_by(user_id=current_user.id, is_utilized=False).all()
    total_wht_credit = sum(c.amount for c in credits)
    
    # Net Payable
    gross_tax = tax_info.get('total_tax', 0)
    net_tax_payable = max(0, gross_tax - total_wht_credit)
    
    from alerts_logic import check_growth_alerts, get_ai_suggestions
    
    # Alerts & AI
    alerts = check_growth_alerts(current_user, tax_info)
    ai_suggestions = get_ai_suggestions(current_user, tax_info, vat_savings)
    
    # Chart Data Preparation (Prompt: "Pull graphs on demand")
    # 1. Expenses by Category
    from models import Category, Expense, Income, Investment
    from sqlalchemy import func
    
    expense_data = db.session.query(Category.group, func.sum(Expense.amount))\
        .join(Expense)\
        .filter(Expense.user_id == current_user.id)\
        .group_by(Category.group).all()
    expense_labels = [e[0] for e in expense_data]
    expense_values = [e[1] for e in expense_data]
    
    # 2. Income vs Investment (Composition)
    total_income = tax_info.get('gross_income', 0)
    # Get total investment value
    investments = Investment.query.filter_by(user_id=current_user.id).all()
    total_investment = sum((i.total_value or 0) for i in investments)
    
    # 3. Monthly Trends (Income vs Expense) - Advanced
    # Group by Month
    # Simplified for MVP: Monthly Cash Flow
    
    from datetime import datetime
    now = datetime.utcnow()
    current_month_start = datetime(now.year, now.month, 1)
    
    # Monthly Income
    monthly_income = db.session.query(func.sum(Income.amount))\
        .filter(Income.user_id == current_user.id, Income.date >= current_month_start).scalar() or 0.0
        
    # Monthly Expenses
    monthly_expenses = db.session.query(func.sum(Expense.amount))\
        .filter(Expense.user_id == current_user.id, Expense.date >= current_month_start).scalar() or 0.0
        
    # Unspent (Brought Forward logic context, but here it's monthly surplus)
    monthly_unspent = monthly_income - monthly_expenses
    
    # Tax Optimization Nudge
    # Estimated Annual Tax: tax_info.get('total_tax', 0)
    # Potential Reduction: Assume 50% reduction possible via max relief (Pension + Bonds)
    est_tax = tax_info.get('total_tax', 0)
    potential_savings_pct = 0.0
    if est_tax > 0:
        # Dummy logic for "Calculate percent"
        # If they haven't maxed out Pension (8%) and Life Insurance/NHF, they can save.
        # Let's say potential is 20% of tax if they optimize.
        potential_savings_pct = 20.0
    
    comparison_labels = ['Monthly Income', 'Monthly Expenses', 'Unspent']
    comparison_values = [monthly_income, monthly_expenses, max(0, monthly_unspent)]

    # --- Profile Specific Logic ---
    net_worth = 0.0
    business_metrics = {}
    
    from models import ProfileType
    
    if current_user.profile_type == ProfileType.INDIVIDUAL:
        # Net Worth = Total Investments + (Total Income - Total Expenses)
        # 1. Cumulative Cash Flow (Surplus)
        total_income_all = db.session.query(func.sum(Income.amount)).filter(Income.user_id == current_user.id).scalar() or 0.0
        total_expense_all = db.session.query(func.sum(Expense.amount)).filter(Expense.user_id == current_user.id).scalar() or 0.0
        cash_balance = total_income_all - total_expense_all
        
        # 2. Investments
        net_worth = total_investment + cash_balance
    else:
        # Business Logic
        # Revenue = Total Income
        # Profit = Income - Expenses
        # Debtors (Placeholder for now) = 0
        total_rev = db.session.query(func.sum(Income.amount)).filter(Income.user_id == current_user.id).scalar() or 0.0
        total_exp = db.session.query(func.sum(Expense.amount)).filter(Expense.user_id == current_user.id).scalar() or 0.0
        profit = total_rev - total_exp
        
        business_metrics = {
            "revenue": total_rev,
            "profit": profit,
            "margin": (profit / total_rev * 100) if total_rev > 0 else 0.0
        }

    return render_template('dashboard.html', 
                           user=current_user,
                           vat_savings=vat_savings,
                           tax_info=tax_info,
                           wht_credit=total_wht_credit,
                           net_payable=net_tax_payable,
                           alerts=alerts,
                           ai_suggestions=ai_suggestions,
                           # Profile Metrics
                           net_worth=net_worth,
                           business_metrics=business_metrics,
                           ProfileType=ProfileType, # Pass Enum to template
                           # Chart Data
                           expense_labels=expense_labels,
                           expense_values=expense_values,
                           comp_labels=comparison_labels,
                           comp_values=comparison_values,
                           monthly_income=monthly_income,
                           monthly_expenses=monthly_expenses,
                           monthly_unspent=monthly_unspent,
                           potential_savings_pct=potential_savings_pct)
