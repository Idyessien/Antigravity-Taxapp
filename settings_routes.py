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
    from datetime import timedelta
    current_month_start = now - timedelta(days=30)
    
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
        
    from models import Subscription
    subscriptions = Subscription.query.filter_by(user_id=current_user.id).order_by(Subscription.next_due_date).all()
    
    # Compute Category Breakdown for Hero View
    expense_breakdown = {}
    total_expenses = 0.0
    for exp in recent_expenses:
        cat_name = exp.category.group if exp.category else "Uncategorized"
        expense_breakdown[cat_name] = expense_breakdown.get(cat_name, 0.0) + exp.amount
        total_expenses += exp.amount
        
    breakdown_list = [{"name": k, "amount": v} for k, v in expense_breakdown.items()]
    breakdown_list.sort(key=lambda x: x["amount"], reverse=True)
    
    hero_data = {
        "total": total_expenses,
        "breakdown": breakdown_list
    }

    return render_template('expenses.html', 
                           categories=categories, 
                           category_groups=category_groups,
                           budget_map=budget_map,
                           recent_expenses=recent_expenses,
                           budget_status=budget_status,
                           subscriptions=subscriptions,
                           hero_data=hero_data)

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

# --- SUBSCRIPTION TRACKER Endpoints ---

@settings_bp.route('/subscriptions/add', methods=['POST'])
@login_required
def add_subscription():
    from models import Subscription, db
    from datetime import datetime
    
    name = request.form.get('name')
    amount_str = request.form.get('amount')
    category_id = request.form.get('category_id')
    billing_cycle = request.form.get('billing_cycle', 'Monthly')
    next_due_str = request.form.get('next_due_date')
    
    if name and amount_str and category_id and next_due_str:
        try:
            amount = float(amount_str)
            next_due = datetime.strptime(next_due_str, '%Y-%m-%d').date()
            
            sub = Subscription(
                user_id=current_user.id,
                category_id=int(category_id),
                name=name,
                amount=amount,
                billing_cycle=billing_cycle,
                next_due_date=next_due
            )
            db.session.add(sub)
            db.session.commit()
            flash(f'Subscription "{name}" created successfully!')
        except Exception as e:
            flash(f"Error adding subscription: {str(e)}")
            
    return redirect(url_for('settings.expenses'))

@settings_bp.route('/subscriptions/log/<int:id>', methods=['POST'])
@login_required
def log_subscription(id):
    from models import Subscription, Expense, db
    from datetime import datetime
    
    sub = Subscription.query.get_or_404(id)
    if sub.user_id != current_user.id:
        flash("Unauthorized")
        return redirect(url_for('settings.expenses'))
        
    # 1. Create the Expense
    exp = Expense(
        user_id=current_user.id,
        category_id=sub.category_id,
        amount=sub.amount,
        description=f"Subscription: {sub.name}",
        date=datetime.utcnow()
    )
    db.session.add(exp)
    
    # 2. Push the due date forward logically
    try:
        from dateutil.relativedelta import relativedelta
        if sub.billing_cycle == 'Monthly':
            sub.next_due_date = sub.next_due_date + relativedelta(months=1)
        elif sub.billing_cycle == 'Yearly':
            sub.next_due_date = sub.next_due_date + relativedelta(years=1)
        elif sub.billing_cycle == 'Weekly':
            sub.next_due_date = sub.next_due_date + relativedelta(weeks=1)
    except ImportError:
        from datetime import timedelta
        if sub.billing_cycle == 'Monthly':
            sub.next_due_date = sub.next_due_date + timedelta(days=30)
        elif sub.billing_cycle == 'Yearly':
            sub.next_due_date = sub.next_due_date + timedelta(days=365)
        elif sub.billing_cycle == 'Weekly':
            sub.next_due_date = sub.next_due_date + timedelta(days=7)
            
    db.session.commit()
    flash(f'Logged {sub.name} subscription! Next due date pushed to {sub.next_due_date}.')
    return redirect(url_for('settings.expenses'))

@settings_bp.route('/subscriptions/delete/<int:id>')
@login_required
def delete_subscription(id):
    from models import Subscription, db
    sub = Subscription.query.get_or_404(id)
    if sub.user_id == current_user.id:
        db.session.delete(sub)
        db.session.commit()
        flash('Subscription removed.')
    return redirect(url_for('settings.expenses'))


@settings_bp.route('/statement/template')
@login_required
def download_statement_template():
    from flask import Response
    csv_content = (
        "Date,Description,Debit,Credit\n"
        "2026-10-01,Monthly Salary Payment,0,350000\n"
        "2026-10-03,EKEDC Prepaid Electricity Token,15000,0\n"
        "2026-10-05,TotalEnergies Fuel Station,25000,0\n"
        "2026-10-10,Shoprite Supermarket Groceries,42000,0\n"
    )
    return Response(
        csv_content,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment;filename=Nigeria_Bank_Statement_Template.csv"}
    )


@settings_bp.route('/statement/import', methods=['POST'])
@login_required
def import_bank_statement():
    import csv
    import io
    import re
    from datetime import datetime
    from models import Expense, Income, IncomeType, Currency, Category, CategoryTarget, CategorizationRule, ProfileType

    uploaded_file = request.files.get('statement_file')
    pdf_password = request.form.get('pdf_password', '').strip()
    redirect_to = request.form.get('redirect_to') or url_for('settings.expenses')

    if not uploaded_file or not uploaded_file.filename:
        flash('Please select a CSV or PDF bank statement file to upload.', 'warning')
        return redirect(redirect_to)

    filename = uploaded_file.filename.lower()

    # Build category lookup for this user
    is_ind = (current_user.profile_type == ProfileType.INDIVIDUAL)
    target_prof = CategoryTarget.INDIVIDUAL if is_ind else CategoryTarget.BUSINESS
    user_cats = Category.query.filter(
        (Category.user_id == current_user.id) | (Category.user_id == None),
        Category.target_profile.in_([target_prof, CategoryTarget.BOTH]),
        Category.name != "Investments & Savings"
    ).all()
    cat_by_name = {c.name.lower(): c for c in user_cats}
    default_cat = user_cats[0] if user_cats else Category.query.first()
    custom_rules = CategorizationRule.query.filter_by(is_active=True).all()

    def match_expense_category(desc_text):
        d = (desc_text or '').lower()
        # 1. Check Admin CategorizationRules first
        for rule in custom_rules:
            if rule.keyword and rule.keyword.lower() in d:
                rule.match_count = (rule.match_count or 0) + 1
                matched = Category.query.get(rule.category_id)
                if matched:
                    return matched.id

        # 2. Built-in Nigerian keyword heuristics
        keyword_map = [
            (['rent', 'landlord', 'tenancy'], 'rent (annual/monthly)' if is_ind else 'office rent'),
            (['ekedc', 'ikedc', 'aedc', 'phed', 'nepa', 'phcn', 'electricity', 'power', 'disco', 'meter token'], 'electricity' if is_ind else 'electricity (office)'),
            (['mtn', 'airtel', 'glo', '9mobile', 'spectranet', 'starlink', 'fiberone', 'data', 'airtime', 'internet'], 'internet/ data' if is_ind else 'internet/data (office)'),
            (['uber', 'bolt', 'indrive', 'lagride'], 'ride-hailing (uber, bolt, indrive etc)' if is_ind else 'logistics & delivery'),
            (['total', 'nnpc', 'oando', 'conoil', 'ardova', 'bovas', 'mrs', 'fuel', 'petrol', 'diesel', 'filling station'], 'petrol/diesel (vehicle)' if is_ind else 'diesel/fuel (generator/vehicle)'),
            (['shoprite', 'spar', 'ebano', 'prince ebeano', 'market', 'supermarket', 'food', 'restaurant', 'chowdeck', 'glovo', 'chicken republic', 'kilimanjaro'], 'food' if is_ind else 'office supplies & consumables'),
            (['hospital', 'pharmacy', 'medplus', 'healthplus', 'clinic', 'medical', 'drug'], 'medical expenses (prescriptions etc)' if is_ind else 'salaries & wages'),
            (['hmo', 'axa mansard', 'reliance hmo', 'hygeia', 'health insurance'], 'health insurance'),
            (['life insurance', 'life assurance', 'leadway'], 'life insurance / assurance'),
            (['rsa', 'pencom', 'stanbic ibtc pension', 'arm pension', 'crusader', 'voluntary pension'], 'voluntary pension / rsa' if is_ind else 'pension contribution (employer)'),
            (['nhf', 'federal mortgage', 'fmbn'], 'nhf contribution (voluntary)'),
            (['dstv', 'gotv', 'netflix', 'showmax', 'spotify', 'multichoice', 'youtube'], 'cable tv/ streaming' if is_ind else 'software & subscriptions'),
            (['aws', 'google cloud', 'microsoft', 'zoom', 'canva', 'github', 'openai'], 'subscription services (icloud, apps etc)' if is_ind else 'software & subscriptions'),
            (['salary', 'wages', 'payroll', 'stipend'], 'salaries & wages'),
            (['stamp duty', 'emtl', 'sms alert', 'card maintenance', 'cot', 'commission', 'vat on', 'bank charge', 'nip charge', 'transfer fee'], 'bank charges'),
            (['stock', 'inventory', 'raw material', 'wholesale', 'restock'], 'stock / inventory & raw materials (resale)')
        ]
        for kw_list, target_cat_name in keyword_map:
            if any(k in d for k in kw_list):
                if target_cat_name in cat_by_name:
                    return cat_by_name[target_cat_name].id
        return default_cat.id if default_cat else 1

    def parse_date_flexible(d_str):
        if not d_str:
            return datetime.utcnow()
        d_str = d_str.strip()
        for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y', '%d %b %Y', '%d-%b-%Y', '%d %B %Y', '%m/%d/%Y', '%Y/%m/%d', '%d-%b-%y', '%d/%m/%y'):
            try:
                return datetime.strptime(d_str, fmt)
            except ValueError:
                continue
        return datetime.utcnow()

    def parse_num_clean(val):
        if not val:
            return 0.0
        s = re.sub(r'[^0-9.-]', '', str(val))
        try:
            return abs(float(s)) if s else 0.0
        except ValueError:
            return 0.0

    rows_to_process = [] # list of (date_obj, description, debit_amt, credit_amt)

    if filename.endswith('.csv'):
        try:
            raw_bytes = uploaded_file.read()
            try:
                text = raw_bytes.decode('utf-8-sig')
            except UnicodeDecodeError:
                text = raw_bytes.decode('latin-1', errors='ignore')

            reader = csv.DictReader(io.StringIO(text))
            if reader.fieldnames:
                headers = [h.strip() for h in reader.fieldnames if h]
                for row in reader:
                    norm_row = { (k.strip().lower() if k else ''): (v.strip() if v else '') for k, v in row.items() }
                    date_val = norm_row.get('date') or norm_row.get('trans date') or norm_row.get('transaction date') or norm_row.get('value date') or ''
                    desc_val = norm_row.get('description') or norm_row.get('narration') or norm_row.get('remarks') or norm_row.get('details') or norm_row.get('reference') or 'Bank Transaction'
                    debit_val = norm_row.get('debit') or norm_row.get('withdrawal') or norm_row.get('money out') or norm_row.get('dr') or ''
                    credit_val = norm_row.get('credit') or norm_row.get('deposit') or norm_row.get('money in') or norm_row.get('cr') or ''
                    amt_val = norm_row.get('amount') or ''
                    type_val = (norm_row.get('type') or norm_row.get('transaction type') or norm_row.get('dr/cr') or '').lower()

                    d_amt = parse_num_clean(debit_val)
                    c_amt = parse_num_clean(credit_val)
                    if d_amt == 0 and c_amt == 0 and amt_val:
                        raw_signed = str(amt_val).replace(',', '').strip()
                        if raw_signed.startswith('-') or 'dr' in type_val or 'debit' in type_val or 'out' in type_val:
                            d_amt = parse_num_clean(amt_val)
                        else:
                            c_amt = parse_num_clean(amt_val)

                    if d_amt > 0 or c_amt > 0:
                        rows_to_process.append((parse_date_flexible(date_val), desc_val[:240], d_amt, c_amt))
        except Exception as e:
            flash(f'Could not parse CSV file: {str(e)}', 'danger')
            return redirect(redirect_to)

    elif filename.endswith('.pdf'):
        try:
            from pypdf import PdfReader
            reader = PdfReader(uploaded_file)
            if reader.is_encrypted:
                if pdf_password:
                    reader.decrypt(pdf_password)
                else:
                    flash('This PDF bank statement is password-protected. Please enter your PDF password and try again.', 'warning')
                    return redirect(redirect_to)

            full_text = ""
            for page in reader.pages:
                full_text += (page.extract_text() or "") + "\n"

            # Match transaction lines starting with a date e.g. 01/10/2026, 01-Oct-2026, 2026-10-01
            line_pattern = re.compile(
                r'^\s*(\d{1,4}[-/\s](?:\d{1,2}|[A-Za-z]{3})[-/\s]\d{2,4})\s+(.+?)\s+([-+]?[\d,]+\.\d{2})(?:\s+([-+]?[\d,]+\.\d{2}))?(?:\s+([-+]?[\d,]+\.\d{2}))?\s*$'
            )
            for line in full_text.splitlines():
                m = line_pattern.match(line.strip())
                if m:
                    dt_str, desc_part, n1, n2, n3 = m.groups()
                    d_amt = 0.0
                    c_amt = 0.0
                    desc_lower = desc_part.lower()
                    # If 3 numbers on the line: usually Debit, Credit, Balance
                    if n1 and n2 and n3:
                        d_amt = parse_num_clean(n1)
                        c_amt = parse_num_clean(n2)
                    else:
                        # 1 or 2 numbers (Amount + Balance): infer Debit vs Credit from keywords/sign
                        val = parse_num_clean(n1)
                        if str(n1).startswith('-') or any(w in desc_lower for w in ['trf to', 'pos', 'web', 'ussd', 'airtime', 'bill', 'charge', 'levy', 'debit', 'dr', 'withdrawal', 'purchase']):
                            d_amt = val
                        elif any(w in desc_lower for w in ['trf from', 'salary', 'credit', 'cr', 'deposit', 'inward', 'payment from']):
                            c_amt = val
                        else:
                            d_amt = val
                    if d_amt > 0 or c_amt > 0:
                        rows_to_process.append((parse_date_flexible(dt_str), desc_part[:240], d_amt, c_amt))
        except Exception as e:
            flash(f'Could not read PDF statement: {str(e)}', 'danger')
            return redirect(redirect_to)
    else:
        flash('Unsupported file format. Please upload a .CSV or .PDF bank statement.', 'warning')
        return redirect(redirect_to)

    inc_count = 0
    exp_count = 0
    default_inc_type = IncomeType.SALARY if is_ind else (IncomeType.PRODUCT_SALES if current_user.profile_type == ProfileType.SMALL_BUSINESS else IncomeType.CORE_REVENUE)
    alt_inc_type = IncomeType.SIDE_GIG if is_ind else IncomeType.SERVICE_FEES

    for dt_obj, desc, d_amt, c_amt in rows_to_process:
        if d_amt > 0:
            cat_id = match_expense_category(desc)
            exp = Expense(
                user_id=current_user.id,
                category_id=cat_id,
                amount=d_amt,
                description=desc,
                date=dt_obj
            )
            db.session.add(exp)
            exp_count += 1
        if c_amt > 0:
            chosen_inc_type = default_inc_type if ('salary' in desc.lower() or not is_ind) else alt_inc_type
            inc = Income(
                user_id=current_user.id,
                amount=c_amt,
                date=dt_obj,
                description=desc,
                income_type=chosen_inc_type,
                currency=Currency.NGN,
                gross_vs_net="Gross",
                is_taxable=True
            )
            db.session.add(inc)
            inc_count += 1

    db.session.commit()
    if inc_count == 0 and exp_count == 0:
        flash('No transactions were detected in the uploaded statement. Try using the CSV format or check the sample template.', 'warning')
    else:
        flash(f'Bank Statement Imported! Automatically logged {inc_count} income(s) and {exp_count} categorized expense(s).', 'success')
    return redirect(redirect_to)

