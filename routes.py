from flask import Blueprint, render_template, request, redirect, url_for
from flask_login import login_required, current_user
from models import db

main = Blueprint('main', __name__)

@main.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
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
    from datetime import datetime
    
    # 30-Day Free Trial Logic
    trial_days_total = 30
    user_created = current_user.created_at or datetime.utcnow()
    days_used = (datetime.utcnow() - user_created).days
    trial_days_left = max(0, trial_days_total - days_used)
    is_trial_expired = not current_user.is_pro and days_used >= trial_days_total
    
    if is_trial_expired:
        vat_savings = 0.0
        tax_info = {'total_tax': 0, 'tax_details': [], 'breakdown': {}}
    else:
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
    alerts = check_growth_alerts(current_user, tax_info) if not is_trial_expired else []
    ai_suggestions = get_ai_suggestions(current_user, tax_info, vat_savings) if not is_trial_expired else []
    
    # Chart Data Preparation (Budget vs Actual & Cash Flow)
    from models import Category, Expense, Income, Investment, Budget
    from sqlalchemy import func, extract
    from datetime import datetime
    import json
    
    now = datetime.utcnow()
    from datetime import timedelta
    current_month_start = now - timedelta(days=30) # Use 30-day rolling window to avoid 1st-of-month panic
    
    def get_financials(time_filter=None):
        # Base queries
        exp_q = db.session.query(Category.group, func.sum(Expense.amount)).join(Expense).filter(Expense.user_id == current_user.id)
        inc_q = db.session.query(func.sum(Income.amount)).filter(Income.user_id == current_user.id)
        inv_q = db.session.query(func.sum(Investment.total_value)).filter(Investment.user_id == current_user.id)
        
        multiplier = 1
        if time_filter == 'monthly':
            exp_q = exp_q.filter(Expense.date >= current_month_start)
            inc_q = inc_q.filter(Income.date >= current_month_start)
            inv_q = inv_q.filter(Investment.created_at >= current_month_start)
        elif time_filter == 'yearly':
            exp_q = exp_q.filter(extract('year', Expense.date) == now.year)
            inc_q = inc_q.filter(extract('year', Income.date) == now.year)
            inv_q = inv_q.filter(extract('year', Investment.created_at) == now.year)
            multiplier = 12
        else: # all_time
            # For all-time budget multiplier, approximate months since created
            user_created = current_user.created_at or datetime.utcnow()
            months_active = (now.year - user_created.year) * 12 + now.month - user_created.month + 1
            multiplier = max(1, months_active)
            
        exp_data = exp_q.group_by(Category.group).all()
        
        # Build Actuals map
        actuals_map = {e[0]: e[1] for e in exp_data}
        
        # Get Budgets
        budgets_data = db.session.query(Category.group, func.sum(Budget.monthly_limit)).join(Budget).filter(Budget.user_id == current_user.id).group_by(Category.group).all()
        budgets_map = {b[0]: (b[1] * multiplier) for b in budgets_data}
        
        # Merge categories (we want to show all categories that have either budget or actual)
        all_categories = set(actuals_map.keys()).union(set(budgets_map.keys()))
        
        budget_vs_actual = []
        for cat in all_categories:
            actual = actuals_map.get(cat, 0.0)
            budget = budgets_map.get(cat, 0.0)
            
            if budget > 0:
                pct = (actual / budget) * 100
            else:
                pct = 100 if actual > 0 else 0
                
            status = "On Track"
            if budget > 0:
                if pct > 100: status = "OVER BUDGET"
                elif pct < 85: status = "Under Budget"
                elif pct >= 85: status = "Warning"
                
            budget_vs_actual.append({
                "category": cat,
                "budget": budget,
                "actual": actual,
                "pct": min(100, pct), 
                "raw_pct": pct,       
                "status": status
            })
            
        budget_vs_actual.sort(key=lambda x: x['actual'], reverse=True)
        
        inc_total = inc_q.scalar() or 0.0
        exp_total = sum(actuals_map.values())
        inv_total = inv_q.scalar() or 0.0
        
        savings_total = max(0.0, inc_total - exp_total - inv_total)
        
        return {
            "budget_vs_actual": budget_vs_actual,
            "cash_flow": {
                "income": inc_total,
                "expenses": exp_total,
                "investment": inv_total,
                "savings": savings_total
            }
        }
        
    dashboard_data = {
        "monthly": get_financials("monthly"),
        "yearly": get_financials("yearly"),
        "all_time": get_financials("all_time")
    }

    
    # Investments
    investments = Investment.query.filter_by(user_id=current_user.id).all()
    total_investment = sum((i.total_value or 0) for i in investments)
    
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
                           dashboard_data=dashboard_data,
                           monthly_income=dashboard_data['monthly']['cash_flow']['income'],
                           monthly_expenses=dashboard_data['monthly']['cash_flow']['expenses'],
                           monthly_unspent=dashboard_data['monthly']['cash_flow']['income'] - dashboard_data['monthly']['cash_flow']['expenses'],
                           is_trial_expired=is_trial_expired,
                           trial_days_left=trial_days_left)
