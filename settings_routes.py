from flask import Blueprint, render_template, request, flash, redirect, url_for
from flask_login import login_required, current_user
from models import db, UserSetting, Category, Budget, CategoryTarget
import json

settings_bp = Blueprint('settings', __name__)

@settings_bp.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    # Fetch or Create Settings
    user_setting = UserSetting.query.filter_by(user_id=current_user.id).first()
    if not user_setting:
        user_setting = UserSetting(user_id=current_user.id)
        db.session.add(user_setting)
        db.session.add(user_setting)
        db.session.commit()
    
    # Logic Restored: Fetch groups for hidden toggle view
    target = CategoryTarget.INDIVIDUAL if current_user.profile_type.value == 'Individual' else CategoryTarget.BUSINESS
    
    groups = (
        db.session.query(Category.group)
        .filter(
            (Category.target_profile == target) | 
            (Category.target_profile == CategoryTarget.BOTH)
        )
        .distinct()
        .all()
    )
    group_list = [g[0] for g in groups if g[0]]
    current_hidden = user_setting.hidden_category_groups.split(',')

    
    return render_template('settings.html', 
                           groups=group_list, 
                           current_hidden=current_hidden)

@settings_bp.route('/settings/preferences', methods=['POST'])
@login_required
def update_preferences():
    user_setting = UserSetting.query.filter_by(user_id=current_user.id).first()
    if not user_setting:
        user_setting = UserSetting(user_id=current_user.id)
        db.session.add(user_setting)
    
    # 1. Hidden Groups
    hidden_groups = request.form.getlist('hidden_groups')
    user_setting.hidden_category_groups = ",".join(hidden_groups)
    
    # 2. Theme
    theme = request.form.get('theme')
    if theme in ['light', 'dark']:
        user_setting.theme = theme
        
    db.session.commit()
    flash('Preferences updated!')
    return redirect(url_for('settings.settings'))

@settings_bp.route('/settings/profile', methods=['POST'])
@login_required
def update_profile():
    from werkzeug.security import generate_password_hash
    password = request.form.get('password')
    confirm = request.form.get('confirm_password')
    
    if password:
        if password != confirm:
            flash('Passwords do not match.')
        else:
            current_user.password_hash = generate_password_hash(password)
            db.session.commit()
            flash('Password updated successfully!')
            
    return redirect(url_for('settings.settings'))

@settings_bp.route('/settings/export', methods=['POST'])
@login_required
def export_data():
    import csv
    import io
    from flask import Response
    from models import Expense, Income
    
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Write Headers
    writer.writerow(['Type', 'Date', 'Amount', 'Category/Source', 'Description'])
    
    # Write Income
    incomes = Income.query.filter_by(user_id=current_user.id).all()
    for inc in incomes:
        writer.writerow(['Income', inc.date.strftime('%Y-%m-%d'), inc.amount, inc.source_name, inc.description])
        
    # Write Expenses
    expenses = Expense.query.filter_by(user_id=current_user.id).all()
    for exp in expenses:
        writer.writerow(['Expense', exp.date.strftime('%Y-%m-%d'), -exp.amount, exp.category.name if exp.category else 'Unknown', exp.description])
        
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-disposition": "attachment; filename=financial_data.csv"}
    )

@settings_bp.route('/settings/reset', methods=['POST'])
@login_required
def reset_data():
    confirmation = request.form.get('confirmation')
    if confirmation == 'DELETE':
        from models import Expense, Income, Investment, SavingsGoal, Invoice, Debtor
        
        # Delete All
        Expense.query.filter_by(user_id=current_user.id).delete()
        Income.query.filter_by(user_id=current_user.id).delete()
        Investment.query.filter_by(user_id=current_user.id).delete()
        SavingsGoal.query.filter_by(user_id=current_user.id).delete()
        
        # Business Stuff
        Invoice.query.filter_by(user_id=current_user.id).delete()
        Debtor.query.filter_by(user_id=current_user.id).delete()
        
        db.session.commit()
        flash('All financial data has been wiped.')
    else:
        flash('Confirmation failed. Please type "DELETE" exactly.')
        
    return redirect(url_for('settings.settings'))

@settings_bp.route('/expenses', methods=['GET', 'POST'])
@login_required
def expenses():
    # Fetch user categories
    current_target = CategoryTarget.INDIVIDUAL if current_user.profile_type.value == 'Individual' else CategoryTarget.BUSINESS
    
    categories = Category.query.filter(
        (Category.target_profile == CategoryTarget.BOTH) |
        (Category.target_profile == current_target)
    ).filter(Category.name != "Investments & Savings").order_by(Category.group, Category.name).all()
    
    # Get unique groups for template loop, handling None in sort
    category_groups = sorted(list(set(c.group for c in categories)), key=lambda x: x or "zzzz")
    
    if request.method == 'POST':
        for cat in categories:
            limit_val = request.form.get(f'limit_{cat.id}')
            if limit_val:
                try:
                    # Strip commas for currency masking support
                    limit = float(limit_val.replace(',', ''))
                    # Check if budget exists
                    bud = Budget.query.filter_by(user_id=current_user.id, category_id=cat.id).first()
                    if not bud:
                        bud = Budget(user_id=current_user.id, category_id=cat.id)
                        db.session.add(bud)
                    bud.monthly_limit = limit
                except ValueError:
                    pass
        db.session.commit()
        flash('Expense limits updated!')
    
    # Helper to get current limit
    budgets = Budget.query.filter_by(user_id=current_user.id).all()
    budget_map = {b.category_id: b.monthly_limit for b in budgets}
    
    # Filter Logic
    from models import Expense
    from datetime import datetime, timedelta
    
    query = Expense.query.filter_by(user_id=current_user.id)
    
    # 1. Search Query
    search_q = request.args.get('search')
    if search_q:
        query = query.filter((Expense.description.ilike(f'%{search_q}%')) | (Expense.amount.ilike(f'%{search_q}%')))
        
    # 2. Date Range
    date_range = request.args.get('date_range', '4w') # Default 4 weeks
    now = datetime.utcnow()
    
    if date_range == '4w':
        start_date = now - timedelta(weeks=4)
        query = query.filter(Expense.date >= start_date)
    elif date_range == '3m':
        start_date = now - timedelta(weeks=12)
        query = query.filter(Expense.date >= start_date)
    elif date_range == '6m':
        start_date = now - timedelta(weeks=26)
        query = query.filter(Expense.date >= start_date)
    elif date_range == '12m':
        start_date = now - timedelta(weeks=52)
        query = query.filter(Expense.date >= start_date)
    elif date_range == 'custom':
        s_str = request.args.get('start_date')
        e_str = request.args.get('end_date')
        if s_str:
            try:
                s_date = datetime.strptime(s_str, '%Y-%m-%d')
                query = query.filter(Expense.date >= s_date)
            except ValueError: pass
        if e_str:
            try:
                e_date = datetime.strptime(e_str, '%Y-%m-%d')
                query = query.filter(Expense.date <= e_date)
            except ValueError: pass
            
            except ValueError: pass
            
    # Filter out "Investments & Savings" from the VIEW list to avoid clutter
    # (But keep them in the database for Net Worth calc)
    query = query.join(Expense.category).filter(Category.name != "Investments & Savings")
    
    recent_expenses = query.order_by(Expense.date.desc()).all()
    
    # Budget Warning Logic
    # Map category_id -> {is_over: bool, limit: float, spent: float}
    # We need total spent per category for the current month to flag warnings correctly
    # regardless of the filter view. Budget is usually monthly.
    
    from sqlalchemy import func
    current_month_start = datetime(now.year, now.month, 1)
    
    monthly_spend = db.session.query(Expense.category_id, func.sum(Expense.amount))\
        .filter(Expense.user_id == current_user.id, Expense.date >= current_month_start)\
        .group_by(Expense.category_id).all()
        
    spend_map = {cat_id: amt for cat_id, amt in monthly_spend}
    
    budget_status = {}
    for cat in categories:
        limit = budget_map.get(cat.id, 0.0)
        spent = spend_map.get(cat.id, 0.0)
        budget_status[cat.id] = {
            'limit': limit,
            'spent': spent,
            'is_over': (spent > limit) if limit > 0 else False
        }
    
    return render_template('expenses.html', 
                           categories=categories, 
                           category_groups=category_groups,
                           budget_map=budget_map,
                           recent_expenses=recent_expenses,
                           budget_status=budget_status)

@settings_bp.route('/expenses/add', methods=['POST'])
@login_required
def add_expense():
    from models import Expense
    from datetime import datetime, timedelta
    
    category_id = request.form.get('category_id')
    amount_str = request.form.get('amount', '0').replace(',', '')
    amount = float(amount_str) if amount_str else 0.0
    description = request.form.get('description')
    date_str = request.form.get('date')
    
    expense_date = datetime.utcnow()
    if date_str:
        try:
            expense_date = datetime.strptime(date_str, '%Y-%m-%d')
        except ValueError:
            pass
            
    add_to_wealth = request.form.get('add_to_wealth')
    amortize = request.form.get('amortize') # Checkbox for 12-month split
    
    if category_id and amount:
        if amortize:
            # Amortization Logic (Split into 12 months)
            monthly_amount = amount / 12
            base_desc = description or "Amortized Expense"
            
            for i in range(12):
                # Calculate future date (Primitive month add to avoid dependencies)
                # Logic: Add i*30 days is rough. Better: Increment month/year manually.
                
                # Manual Month Increment
                new_month = expense_date.month + i
                new_year = expense_date.year + (new_month - 1) // 12
                new_month = (new_month - 1) % 12 + 1
                
                try:
                    # Handle day overflow (e.g. Feb 30 -> Feb 28/29)
                    # Simple hack: cap day at 28 if > 28? Or use replacing logic.
                    # Lets stick to day 1 if original day is problematic? No, user entered specific date.
                    # Let's just try to keep the day, fall back to last day of month if ValueError.
                    # Actually, simple trick: set day=1, add i months, then add original days? No.
                    # Let's just use day 1 for amortized entries? 
                    # "Reflect in monthly expenditure" -> Date matters.
                    # Let's use `timedelta(days=30 * i)` as a safe fallback? 360 days/year isn't bad for rough estimation.
                    # But proper accounting prefers month alignment.
                    
                    current_entry_date = datetime(new_year, new_month, min(expense_date.day, 28)) # Cap at 28 to be safe for all months
                except ValueError:
                    current_entry_date = datetime(new_year, new_month, 1)

                exp = Expense(
                    user_id=current_user.id,
                    category_id=category_id,
                    amount=monthly_amount,
                    description=f"{base_desc} (Month {i+1}/12)",
                    date=current_entry_date
                )
                db.session.add(exp)
                
                # Investment Sync (for each entry)
                if add_to_wealth:
                    try:
                        from models import Investment, AssetType, InvestmentSubType
                        new_inv = Investment(
                            user_id=current_user.id,
                            name=f"{base_desc} (Month {i+1}/12)",
                            asset_type=AssetType.STOCK, 
                            sub_type=InvestmentSubType.CORPORATE,
                            total_value=monthly_amount,
                            created_at=current_entry_date
                        )
                        db.session.add(new_inv)
                    except:
                        pass # Fail silently for individual syncs to keep flow moving
                        
            db.session.commit()
            flash(f'Expense amortized over 12 months ({monthly_amount:,.2f}/mo)!')
            
        else:
            # Standard Single Entry
            exp = Expense(
                user_id=current_user.id,
                category_id=category_id,
                amount=amount,
                description=description,
                date=expense_date
            )
            db.session.add(exp)
            
            # Investment Sync
            if add_to_wealth:
                try:
                    from models import Investment, AssetType, InvestmentSubType
                    description = description or "Expense Investment"
                    new_inv = Investment(
                        user_id=current_user.id,
                        name=description,
                        asset_type=AssetType.STOCK, 
                        sub_type=InvestmentSubType.CORPORATE,
                        total_value=amount,
                        created_at=expense_date
                    )
                    db.session.add(new_inv)
                    db.session.commit() # Commit both
                    flash('Expense logged + Added to Wealth Portfolio!')
                except Exception as e:
                    db.session.commit() # Commit expense at least
                    flash(f'Expense logged, but Wealth Sync failed: {str(e)}')
            else:
                 db.session.commit()
                 flash('Expense logged successfully!')
        
    return redirect(url_for('settings.expenses'))

@settings_bp.route('/expenses/delete/<int:id>')
@login_required
def delete_expense(id):
    from models import Expense
    exp = Expense.query.get_or_404(id)
    if exp.user_id == current_user.id:
        db.session.delete(exp)
        db.session.commit()
        flash('Expense deleted.')
    return redirect(url_for('settings.expenses'))

@settings_bp.route('/settings/custom_category', methods=['POST'])
@login_required
def add_custom_category():
    name = request.form.get('name')
    group = request.form.get('group')
    
    if name and group:
        target = CategoryTarget.INDIVIDUAL if current_user.profile_type.value == 'Individual' else CategoryTarget.BUSINESS
        
        # Check duplicate
        exists = Category.query.filter_by(name=name, target_profile=target).first()
        if not exists:
            cat = Category(name=name, group=group, target_profile=target, is_custom=True) 
            db.session.add(cat)
            db.session.commit()
            flash(f'Category "{name}" added!')
        else:
            flash('Category already exists.')
            
    return redirect(url_for('settings.expenses'))

