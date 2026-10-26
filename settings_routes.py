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


@settings_bp.route('/expenses/clear-all', methods=['POST'])
@login_required
def clear_all_expenses():
    from models import Expense
    deleted = Expense.query.filter_by(user_id=current_user.id).delete()
    db.session.commit()
    flash(f'Cleared {deleted} expense record(s).', 'info')
    return redirect(url_for('settings.expenses'))


@settings_bp.route('/expenses/update-category/<int:id>', methods=['POST'])
@login_required
def update_expense_category(id):
    from models import Expense, Category
    exp = Expense.query.get_or_404(id)
    if exp.user_id == current_user.id:
        new_cat_id = request.form.get('category_id', type=int)
        if new_cat_id and Category.query.get(new_cat_id):
            exp.category_id = new_cat_id
            db.session.commit()
            flash('Expense category updated.', 'success')
    return redirect(url_for('settings.expenses'))


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
        Category.target_profile.in_([target_prof, CategoryTarget.BOTH])
    ).all()
    cat_by_name = {c.name.lower(): c for c in user_cats}

    # IMPORTANT: Default fallback for Individual MUST be 'Gifts' (for personal transfers / general spending),
    # NEVER user_cats[0] (which is 'Rent (Annual/Monthly)' and would falsely inflate Rent Relief!).
    if is_ind:
        default_cat = (
            cat_by_name.get('gifts')
            or cat_by_name.get('food')
            or next((c for c in user_cats if 'rent' not in c.name.lower()), None)
        )
    else:
        default_cat = (
            cat_by_name.get('office supplies & consumables')
            or cat_by_name.get('logistics & delivery')
            or next((c for c in user_cats if 'rent' not in c.name.lower()), None)
        )

    custom_rules = CategorizationRule.query.filter_by(is_active=True).all()

    def match_expense_category(desc_text):
        d = (desc_text or '').lower()

        # 1. Check Admin CategorizationRules first (using word boundaries for short keywords)
        for rule in custom_rules:
            if rule.keyword:
                kw = rule.keyword.strip().lower()
                if len(kw) <= 4:
                    matched_kw = bool(re.search(r'\b' + re.escape(kw) + r'\b', d))
                else:
                    matched_kw = (kw in d)
                if matched_kw:
                    rule.match_count = (rule.match_count or 0) + 1
                    matched = Category.query.get(rule.category_id)
                    if matched:
                        return matched.id

        # 2. Word-boundary regex rules ordered so specific stated descriptions ALWAYS win
        # before falling back to 'Gifts' for personal transfers.
        # Notice '\brent\b' is used so words like 'current', 'parent', 'different', 'restaurant' NEVER match Rent!
        regex_rules = [
            # Food, Groceries & Restaurants
            (r'\b(food|foodstuff|grocer\w*|lunch|dinner|breakfast|meal|restaurant|eatery|canteen|bakery|supermarket|shoprite|spar|ebeano|justrite|hubmart|bokku|chowdeck|glovo|chicken republic|kilimanjaro|domino\w*|pizza|shawarma|suya|amala|bukka|pastry|snacks|refreshment)\b',
             'food' if is_ind else 'office supplies & consumables'),

            # Electricity & Power
            (r'\b(ekedc|ikedc|aedc|phed|ibedc|kedco|jedc|eedc|bedc|yedc|nepa|phcn|electricity|electric|disco|prepaid meter|meter token|light bill|buypower|irecharge)\b',
             'electricity' if is_ind else 'electricity (office)'),

            # Cooking Gas & Water
            (r'\b(cooking gas|lpg|gas cylinder|gas refill)\b',
             'cooking gas' if is_ind else 'office supplies & consumables'),
            (r'\b(water bill|water board|water supply|pure water|cway|dispensary water)\b',
             'water' if is_ind else 'office supplies & consumables'),

            # Cable TV & Streaming
            (r'\b(dstv|gotv|startimes|multichoice|netflix|showmax|spotify|prime video|youtube premium|cable tv)\b',
             'cable tv/ streaming' if is_ind else 'software & subscriptions'),

            # Internet, Data & Airtime
            (r'\b(mtn|airtel|glo|globacom|9mobile|etisalat|spectranet|starlink|fiberone|ipnx|smile|tizeti|internet|data|airtime|vtu|recharge|wifi|broadband)\b',
             'internet/ data' if is_ind else 'internet/data (office)'),

            # Petrol / Diesel / Fuel
            (r'\b(total|totalenergies|nnpc|oando|conoil|ardova|bovas|mrs|mobil|rainoil|matrix|nipco|fuel|petrol|pms|diesel|ago|filling station|service station)\b',
             'petrol/diesel (vehicle)' if is_ind else 'diesel/fuel (generator/vehicle)'),

            # Ride-Hailing & Public Transport
            (r'\b(uber|bolt|indrive|lagride|rida|cab|taxi)\b',
             'ride-hailing (uber, bolt, indrive etc)' if is_ind else 'logistics & delivery'),
            (r'\b(danfo|brt|keke|napep|okada|transport|tfare|t-fare|bus fare|cowry|air peace|ibom air|arik|valuejet|flight|train)\b',
             'public transport (danfo, brt, keke)' if is_ind else 'logistics & delivery'),

            # Vehicle Maintenance & Car Papers
            (r'\b(mechanic|vulcanizer|rewire|panel beater|car wash|servicing|engine oil|tyre|tire|car battery|spare part|brake|gearbox|radiator|vehicle maintenance|car repair)\b',
             'vehicle maintenance' if is_ind else 'diesel/fuel (generator/vehicle)'),
            (r'\b(car license|vehicle license|hackney|road worthiness|frsc|driver license|motor insurance|third party insurance|autoreg)\b',
             'car license and insurance' if is_ind else 'levies & lg charges'),

            # Education / School Fees
            (r'\b(school fee\w*|tuition|creche|nursery|primary school|secondary school|college|university|polytechnic|waec|jamb|neco|lesson teacher|textbook\w*|school uniform|pta)\b',
             'school fees/creche' if is_ind else 'staff training'),

            # Health, Medical & Life Assurance
            (r'\b(hmo|axa mansard|reliance hmo|hygeia|avon hmo|leadway health|clearline|health insurance)\b',
             'health insurance'),
            (r'\b(life insurance|life assurance|assurance policy)\b',
             'life insurance / assurance'),
            (r'\b(hospital|clinic|pharmacy|chemist|medplus|healthplus|mopheth|alpha pharmacy|nett pharmacy|drug\w*|medication|prescription\w*|doctor|dental|dentist|optician|lab test|medical|treatment|surgery)\b',
             'medical expenses (prescriptions etc)' if is_ind else 'salaries & wages'),

            # Statutory Reliefs (Pension & NHF)
            (r'\b(rsa|pencom|pfa|stanbic ibtc pension|arm pension|crusader|access pension|fcmb pension|veritas|oak pension|premium pension|trustfund|voluntary pension)\b',
             'voluntary pension / rsa' if is_ind else 'pension contribution (employer)'),
            (r'\b(nhf|national housing fund|fmbn|federal mortgage)\b',
             'nhf contribution (voluntary)'),

            # Tithe, Charity & Religious Offerings
            (r'\b(tithe\w*|tithing|offering|church|mosque|parish|ministry|rccg|redeemed|living faith|winners|mountain of fire|mfm|christ embassy|daystar|dunamis|catholic|anglican|nasfat|zakat|sadaqah|charity|donation|orphanage)\b',
             'tithe/charity' if is_ind else 'corporate social responsibility (csr)'),

            # Gym, Toiletries, Clothing & Self Care
            (r'\b(gym|fitness|i-fitness|ifitness|workout)\b',
             'gym membership' if is_ind else 'office supplies & consumables'),
            (r'\b(toiletries|soap|detergent|toothpaste|tissue|diaper\w*|pampers|sanitary)\b',
             'toiletries' if is_ind else 'office supplies & consumables'),
            (r'\b(clothing|clothes|shirt|dress|shoe\w*|sneakers|boutique|tailor|fashion|salon|barber|haircut|braids|wig|makeup|make-up|spa|pedicure|manicure|skincare|perfume|laundry|dry cleaning)\b',
             'clothing & personal self care' if is_ind else 'office supplies & consumables'),

            # App & Software Subscriptions
            (r'\b(icloud|apple\.com|google play|chatgpt|openai|canva|zoom|microsoft|office 365|dropbox|adobe|aws|github|subscription)\b',
             'subscription services (icloud, apps etc)' if is_ind else 'software & subscriptions'),

            # Housing Dues & Explicit Rent (strictly whole-word \brent\b or tenancy/landlord)
            (r'\b(estate dues|security dues|estate levy|resident association|service charge)\b',
             'estate/security dues' if is_ind else 'office rent'),
            (r'\b(land use charge|tenement rate)\b',
             'land use charge / tenement rate' if is_ind else 'levies & lg charges'),
            (r'\b(house rent|annual rent|monthly rent|apartment rent|shop rent|office rent|rent payment|tenancy|landlord|rent)\b',
             'rent (annual/monthly)' if is_ind else 'office rent'),

            # Business Stock / Salaries / Bank Charges
            (r'\b(stock|inventory|raw material\w*|wholesale|restock)\b',
             'stock / inventory & raw materials (resale)' if not is_ind else 'gifts'),
            (r'\b(salary|salaries|wages|payroll|stipend)\b',
             'salaries & wages' if not is_ind else 'gifts'),
            (r'\b(stamp duty|emtl|electronic money transfer levy|sms alert|card maintenance|account maintenance|cot|commission|vat on|bank charge\w*|nip charge|transfer fee)\b',
             'bank charges' if 'bank charges' in cat_by_name else ('gifts' if is_ind else 'office supplies & consumables')),

            # Personal Transfers / Gifts / Upkeep / Allowance
            (r'\b(gift\w*|birthday|wedding|anniversary|allowance|upkeep|pocket money|family|mum|mom|dad|sister|brother|wife|husband|friend|support|giveaway|trf|transfer|nip|fip|sent to)\b',
             'gifts' if is_ind else 'office supplies & consumables'),
        ]

        for pattern, target_cat_name in regex_rules:
            if re.search(pattern, d):
                if target_cat_name in cat_by_name:
                    return cat_by_name[target_cat_name].id

        return default_cat.id if default_cat else 1

    def match_income_type(desc_text):
        d = (desc_text or '').lower()
        if not is_ind:
            if current_user.profile_type == ProfileType.SMALL_BUSINESS:
                return IncomeType.SERVICE_FEES if re.search(r'\b(service|consult\w*|retainer|fee\w*)\b', d) else IncomeType.PRODUCT_SALES
            return IncomeType.CORE_REVENUE
        if re.search(r'\b(salary|salaries|payroll|wages|stipend|allowance)\b', d):
            return IncomeType.SALARY
        if re.search(r'\b(dividend\w*|interest|coupon|yield|mutual fund|treasury bill|bond)\b', d):
            return IncomeType.INVESTMENT
        if re.search(r'\b(gift\w*|birthday|upkeep|pocket money|family)\b', d):
            return IncomeType.GIFT
        return IncomeType.SIDE_GIG

    def parse_date_flexible(d_str):
        if not d_str:
            return datetime.utcnow()
        d_str = re.sub(r'\s+', ' ', str(d_str).strip())
        # Strip trailing timestamp if present e.g. '2026-10-20 14:32:10'
        d_part = d_str.split(' ')[0] if re.match(r'^\d{1,4}[-/]\d{1,2}[-/]\d{1,4}\s+\d{1,2}:', d_str) else d_str
        for fmt in (
            '%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y', '%d.%m.%Y',
            '%d %b %Y', '%d-%b-%Y', '%d/%b/%Y', '%d %B %Y', '%d-%B-%Y',
            '%d %b, %Y', '%b %d, %Y', '%B %d, %Y',
            '%m/%d/%Y', '%Y/%m/%d', '%d-%b-%y', '%d/%m/%y', '%d-%m-%y'
        ):
            try:
                dt = datetime.strptime(d_part, fmt)
                if dt.year < 100:
                    dt = dt.replace(year=dt.year + 2000)
                return dt
            except ValueError:
                continue
        return datetime.utcnow()

    def parse_num_clean(val):
        if val is None:
            return 0.0
        s = str(val).strip()
        if not s or s in ('-', '--', '—', 'N/A', 'nil', 'null'):
            return 0.0
        s_clean = re.sub(r'[^0-9.-]', '', s)
        if not s_clean or s_clean in ('-', '.', '-.'):
            return 0.0
        try:
            return abs(float(s_clean))
        except ValueError:
            return 0.0

    rows_to_process = []  # list of (date_obj, description, debit_amt, credit_amt)

    if filename.endswith('.csv'):
        try:
            raw_bytes = uploaded_file.read()
            try:
                text = raw_bytes.decode('utf-8-sig')
            except UnicodeDecodeError:
                text = raw_bytes.decode('latin-1', errors='ignore')

            all_csv_rows = list(csv.reader(io.StringIO(text)))
            if not all_csv_rows:
                flash('The uploaded CSV file is empty.', 'warning')
                return redirect(redirect_to)

            # 1. Locate the true header row (skipping bank account summary metadata rows at the top)
            header_idx = 0
            best_score = -1
            header_keywords = {'date', 'description', 'narration', 'remarks', 'details', 'particulars', 'debit', 'credit', 'withdrawal', 'deposit', 'amount', 'balance', 'dr', 'cr', 'inflow', 'outflow', 'money in', 'money out'}
            for idx, r in enumerate(all_csv_rows[:30]):
                cells = [re.sub(r'\s+', ' ', (c or '').strip().lower()) for c in r if c and c.strip()]
                if len(cells) < 2:
                    continue
                score = sum(1 for c in cells if any(hk in c for hk in header_keywords))
                if score > best_score and score >= 2:
                    best_score = score
                    header_idx = idx
                    if score >= 3:
                        break

            raw_headers = [re.sub(r'\s+', ' ', (h or '').strip().lower()) for h in all_csv_rows[header_idx]]

            # 2. Identify column indices by flexible header matching
            date_cols = []
            desc_cols = []
            debit_cols = []
            credit_cols = []
            amount_cols = []
            type_cols = []
            balance_cols = []

            for i, h in enumerate(raw_headers):
                if not h:
                    continue
                if any(w in h for w in ['trans date', 'transaction date', 'posting date', 'entry date']) or h == 'date':
                    date_cols.insert(0, i)
                elif 'date' in h:
                    date_cols.append(i)
                elif any(w in h for w in ['description', 'narration', 'remarks', 'particulars', 'details', 'memo', 'beneficiary', 'summary', 'notes', 'narrative']):
                    desc_cols.append(i)
                elif any(w in h for w in ['debit', 'withdrawal', 'money out', 'outflow', 'paid out']) or h in ('dr', 'dr amount', 'dr.'):
                    debit_cols.append(i)
                elif any(w in h for w in ['credit', 'deposit', 'money in', 'inflow', 'paid in', 'lodgement']) or h in ('cr', 'cr amount', 'cr.'):
                    credit_cols.append(i)
                elif any(w in h for w in ['balance', 'bal']):
                    balance_cols.append(i)
                elif any(w in h for w in ['type', 'dr/cr', 'cr/dr', 'direction', 'indicator', 'entry']):
                    type_cols.append(i)
                elif 'amount' in h or h in ('value', 'amt'):
                    amount_cols.append(i)
                elif 'reference' in h or 'ref' in h:
                    # Only use reference as fallback description if no main description exists
                    desc_cols.append(i)

            raw_parsed = []  # (dt_obj, desc_val, d_amt, c_amt, single_amt, single_raw, type_str, bal_val)
            for r in all_csv_rows[header_idx + 1:]:
                if not r or not any(c and c.strip() for c in r):
                    continue

                def get_cell(idx_list):
                    for idx in idx_list:
                        if idx < len(r) and r[idx] and r[idx].strip():
                            return r[idx].strip()
                    return ''

                date_val = get_cell(date_cols)
                # Combine ALL non-empty description/narration/remarks/beneficiary columns so nothing is missed
                desc_parts = []
                for idx in desc_cols:
                    if idx < len(r) and r[idx] and r[idx].strip():
                        val = r[idx].strip()
                        if val not in desc_parts and not re.match(r'^[\d,.-]+$', val):
                            desc_parts.append(val)
                desc_val = ' - '.join(desc_parts) if desc_parts else 'Bank Transaction'

                # Skip summary/total footer rows
                if re.search(r'\b(opening balance|closing balance|total debit|total credit|statement summary)\b', desc_val.lower()):
                    continue

                d_raw = get_cell(debit_cols)
                c_raw = get_cell(credit_cols)
                amt_raw = get_cell(amount_cols)
                type_val = get_cell(type_cols).lower()
                bal_raw = get_cell(balance_cols)

                d_amt = parse_num_clean(d_raw)
                c_amt = parse_num_clean(c_raw)
                s_amt = parse_num_clean(amt_raw)
                bal_val = parse_num_clean(bal_raw) if bal_raw else None

                # Handle cases where Credit/Debit column itself has CR/DR or Amount column is used
                if d_amt == 0 and c_amt == 0 and s_amt > 0:
                    amt_str_clean = amt_raw.strip().upper()
                    if (
                        amt_str_clean.endswith('CR')
                        or amt_str_clean.startswith('+')
                        or any(w in type_val for w in ['cr', 'credit', 'inflow', 'deposit', 'money in', 'inward'])
                    ):
                        c_amt = s_amt
                    elif (
                        amt_str_clean.endswith('DR')
                        or amt_str_clean.startswith('-')
                        or (amt_str_clean.startswith('(') and amt_str_clean.endswith(')'))
                        or any(w in type_val for w in ['dr', 'debit', 'outflow', 'withdrawal', 'money out', 'outward'])
                    ):
                        d_amt = s_amt
                    else:
                        # Defer to balance delta or keyword check below
                        pass

                raw_parsed.append((parse_date_flexible(date_val), desc_val[:240], d_amt, c_amt, s_amt, amt_raw, type_val, bal_val))

            # Resolve any single-amount rows where d_amt == 0 and c_amt == 0 using balance (chronological or reverse-chronological) or keywords
            chrono_hits = 0
            rev_hits = 0
            for i in range(len(raw_parsed)):
                s_amt = raw_parsed[i][4]
                b_curr = raw_parsed[i][7]
                if s_amt > 0 and b_curr is not None:
                    if i > 0 and raw_parsed[i - 1][7] is not None:
                        if abs(abs(b_curr - raw_parsed[i - 1][7]) - s_amt) < 2.0:
                            chrono_hits += 1
                    if i + 1 < len(raw_parsed) and raw_parsed[i + 1][7] is not None:
                        if abs(abs(b_curr - raw_parsed[i + 1][7]) - s_amt) < 2.0:
                            rev_hits += 1
            is_reverse_csv = (rev_hits > chrono_hits)

            for i, (dt_obj, desc_val, d_amt, c_amt, s_amt, amt_raw, type_val, bal_val) in enumerate(raw_parsed):
                if d_amt == 0 and c_amt == 0 and s_amt > 0:
                    resolved = False
                    ref_bal = None
                    if not is_reverse_csv and i > 0:
                        ref_bal = raw_parsed[i - 1][7]
                    elif is_reverse_csv and (i + 1) < len(raw_parsed):
                        ref_bal = raw_parsed[i + 1][7]

                    if bal_val is not None and ref_bal is not None:
                        if abs((bal_val - ref_bal) - s_amt) < 2.0:
                            c_amt = s_amt
                            resolved = True
                        elif abs((ref_bal - bal_val) - s_amt) < 2.0:
                            d_amt = s_amt
                            resolved = True
                    if not resolved:
                        dl = desc_val.lower()
                        if re.search(r'\b(cr|credit|trf from|transfer from|from|inward|deposit|salary|reversal|refund|received)\b', dl):
                            c_amt = s_amt
                        else:
                            d_amt = s_amt
                if d_amt > 0 or c_amt > 0:
                    rows_to_process.append((dt_obj, desc_val, d_amt, c_amt))

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

            # Group PDF lines into multi-line transaction blocks starting with a date
            date_start_re = re.compile(
                r'^\s*(\d{1,4}[-/\s.](?:\d{1,2}|[A-Za-z]{3,9})[-/\s.]\d{2,4})\b(.*)$'
            )
            ignore_line_re = re.compile(
                r'^\s*(page\s+\d+|trans\s*date|transaction\s*date|date\s+narration|opening\s+balance|balance\s+brought\s+forward|closing\s+balance|total\s+debit|total\s+credit|statement\s+of\s+account|account\s+number|customer\s+statement)\b',
                re.IGNORECASE
            )

            # Check if there is an Opening Balance in the header text
            opening_bal = None
            ob_match = re.search(
                r'(?:opening\s+bal\w*|balance\s+brought\s+forward|bal\s+b/f|starting\s+balance)[\s:₦NGN]*((?:\d{1,3}(?:,\d{3})+|\d+)\.\d{2})',
                full_text,
                re.IGNORECASE
            )
            if ob_match:
                opening_bal = parse_num_clean(ob_match.group(1))

            tx_blocks = []  # list of [dt_str, combined_body_str]
            for raw_line in full_text.splitlines():
                line = raw_line.strip()
                if not line or ignore_line_re.search(line):
                    continue
                m_date = date_start_re.match(line)
                if m_date:
                    dt_str, remainder = m_date.groups()
                    tx_blocks.append([dt_str.strip(), remainder.strip()])
                elif tx_blocks:
                    # Continuation line of the current transaction narration/amounts
                    tx_blocks[-1][1] = (tx_blocks[-1][1] + " " + line).strip()

            # Tokenize amounts (both comma-formatted and unformatted decimals) & dash placeholders
            amt_or_dash_re = re.compile(
                r'(?:([-+]?(?:₦|NGN|\$)?\s*(?:\d{1,3}(?:,\d{3})+|\d+)\.\d{2}(?:\s*(?:CR|DR))?)|(?<=\s)(--|—|-)(?=\s+[₦\d]))',
                re.IGNORECASE
            )

            parsed_pdf_txs = []
            for dt_str, body in tx_blocks:
                # Strip secondary Value Date or timestamp at the very beginning of body
                body_clean = re.sub(
                    r'^(\d{1,4}[-/\s.](?:\d{1,2}|[A-Za-z]{3,9})[-/\s.]\d{2,4}\s*|\d{1,2}:\d{2}(?::\d{2})?\s*)+',
                    '',
                    body
                ).strip()

                matches = list(amt_or_dash_re.finditer(body_clean))
                if not matches:
                    continue

                tokens = []
                for m in matches:
                    num_str, dash_str = m.groups()
                    if num_str:
                        tokens.append(('NUM', parse_num_clean(num_str), num_str.strip().upper()))
                    elif dash_str:
                        tokens.append(('DASH', 0.0, dash_str))

                num_tokens = [t for t in tokens if t[0] == 'NUM']
                if not num_tokens:
                    continue

                # Build clean description by removing matched amount/dash tokens from body_clean
                desc_cleaned = amt_or_dash_re.sub(' ', body_clean)
                desc_cleaned = re.sub(r'\s+', ' ', desc_cleaned).strip(' -|:/,')
                if not desc_cleaned:
                    desc_cleaned = "Bank Transaction"

                curr_bal = num_tokens[-1][1] if len(num_tokens) >= 2 else None
                parsed_pdf_txs.append({
                    'dt_obj': parse_date_flexible(dt_str),
                    'desc': desc_cleaned[:240],
                    'tokens': tokens,
                    'num_tokens': num_tokens,
                    'curr_bal': curr_bal
                })

            # Detect whether PDF transactions are chronological (oldest first) or reverse-chronological (newest first)
            chrono_pdf_hits = 0
            rev_pdf_hits = 0
            for idx, item in enumerate(parsed_pdf_txs):
                if len(item['num_tokens']) == 2 and item['curr_bal'] is not None:
                    amt_v = item['num_tokens'][0][1]
                    b_c = item['curr_bal']
                    prev_b = parsed_pdf_txs[idx - 1]['curr_bal'] if idx > 0 else opening_bal
                    if prev_b is not None and abs(abs(b_c - prev_b) - amt_v) < 2.0:
                        chrono_pdf_hits += 1
                    if (idx + 1) < len(parsed_pdf_txs) and parsed_pdf_txs[idx + 1]['curr_bal'] is not None:
                        next_b = parsed_pdf_txs[idx + 1]['curr_bal']
                        if abs(abs(b_c - next_b) - amt_v) < 2.0:
                            rev_pdf_hits += 1
            is_reverse_pdf = (rev_pdf_hits > chrono_pdf_hits)

            for idx, item in enumerate(parsed_pdf_txs):
                tokens = item['tokens']
                num_tokens = item['num_tokens']
                desc = item['desc']
                dl = desc.lower()
                d_amt = 0.0
                c_amt = 0.0
                curr_bal = item['curr_bal']

                # Case 1: 3 or more numeric amounts -> last 3 are (Debit, Credit, Balance)
                if len(num_tokens) >= 3:
                    n_deb = num_tokens[-3][1]
                    n_cred = num_tokens[-2][1]
                    if n_deb > 0 and n_cred == 0:
                        d_amt = n_deb
                    elif n_cred > 0 and n_deb == 0:
                        c_amt = n_cred
                    else:
                        d_amt = n_deb
                        c_amt = n_cred

                # Case 2: Dash placeholder + 2 numeric amounts e.g. ('DASH', 'NUM'(Credit), 'NUM'(Balance))
                elif len(num_tokens) == 2 and any(t[0] == 'DASH' for t in tokens[-3:]):
                    last_three = tokens[-3:]
                    amt_val = num_tokens[0][1]
                    if last_three[0][0] == 'DASH':
                        c_amt = amt_val
                    elif last_three[1][0] == 'DASH':
                        d_amt = amt_val

                # Case 3: 2 numeric amounts (Amount, Balance) or 1 numeric amount
                if d_amt == 0 and c_amt == 0:
                    amt_val, amt_raw = num_tokens[0][1], num_tokens[0][2]
                    ref_bal = None
                    if not is_reverse_pdf:
                        ref_bal = parsed_pdf_txs[idx - 1]['curr_bal'] if idx > 0 else opening_bal
                    else:
                        ref_bal = parsed_pdf_txs[idx + 1]['curr_bal'] if (idx + 1) < len(parsed_pdf_txs) else opening_bal

                    # 3a. Explicit CR/DR/+/- on the amount token itself
                    if amt_raw.endswith('CR') or amt_raw.startswith('+'):
                        c_amt = amt_val
                    elif amt_raw.endswith('DR') or amt_raw.startswith('-'):
                        d_amt = amt_val
                    # 3b. Running Balance delta check (mathematical certainty!)
                    elif curr_bal is not None and ref_bal is not None and abs(curr_bal - ref_bal) > 0.001:
                        if abs((curr_bal - ref_bal) - amt_val) < 2.0:
                            c_amt = amt_val
                        elif abs((ref_bal - curr_bal) - amt_val) < 2.0:
                            d_amt = amt_val

                    # 3c. Keyword check in narration if balance comparison wasn't possible (e.g. very first row without Opening Balance)
                    if d_amt == 0 and c_amt == 0:
                        if re.search(r'\b(cr|credit|inward|deposit|trf from|transfer from|received from|payment from|nip cr|fip cr|salary|reversal|refund|interest|dividend)\b', dl):
                            c_amt = amt_val
                        elif re.search(r'\b(dr|debit|outward|withdrawal|trf to|transfer to|sent to|paid to|nip dr|pos|atm|web|ussd|airtime|bill|charge|levy|emtl|stamp duty|commission)\b', dl):
                            d_amt = amt_val
                        elif re.search(r'\bfrom\b', dl) and not re.search(r'\bto\b', dl):
                            c_amt = amt_val
                        else:
                            d_amt = amt_val

                if d_amt > 0 or c_amt > 0:
                    rows_to_process.append((item['dt_obj'], desc, d_amt, c_amt))

        except Exception as e:
            flash(f'Could not read PDF statement: {str(e)}', 'danger')
            return redirect(redirect_to)
    else:
        flash('Unsupported file format. Please upload a .CSV or .PDF bank statement.', 'warning')
        return redirect(redirect_to)

    inc_count = 0
    exp_count = 0

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
            chosen_inc_type = match_income_type(desc)
            inc = Income(
                user_id=current_user.id,
                amount=c_amt,
                date=dt_obj,
                description=desc,
                income_type=chosen_inc_type,
                currency=Currency.NGN,
                gross_vs_net="Gross",
                is_taxable=(chosen_inc_type != IncomeType.GIFT)
            )
            db.session.add(inc)
            inc_count += 1

    db.session.commit()
    if inc_count == 0 and exp_count == 0:
        flash('No transactions were detected in the uploaded statement. Try using the CSV format or check the sample template.', 'warning')
    else:
        flash(f'Bank Statement Imported! Automatically logged {inc_count} income(s) (Credits) and {exp_count} categorized expense(s) (Debits).', 'success')
    return redirect(redirect_to)


