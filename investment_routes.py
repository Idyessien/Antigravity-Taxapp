from flask import Blueprint, render_template, request, flash, redirect, url_for
from flask_login import login_required, current_user
from models import db, Investment, AssetType, InvestmentSubType, SavingsGoal
from tax_logic import calculate_investment_tax, calculate_tey

investment_bp = Blueprint('investment', __name__)

@investment_bp.route('/wealth')
@login_required
def wealth_dashboard():
    # Prompt 4: Wealth Dashboard logic
    tax_info = calculate_investment_tax(current_user)
    investments = Investment.query.filter_by(user_id=current_user.id).all()
    goals = SavingsGoal.query.filter_by(user_id=current_user.id).order_by(SavingsGoal.deadline).all()
    
    return render_template('wealth.html', 
                           user=current_user,
                           tax_info=tax_info,
                           investments=investments,
                           goals=goals,
                           asset_types=AssetType,
                           sub_types=InvestmentSubType)

@investment_bp.route('/wealth/goal/add', methods=['POST'])
@login_required
def add_goal():
    def parse_num(val):
        if not val:
            return 0.0
        return float(str(val).replace(',', '').strip() or 0.0)

    name = request.form.get('name')
    target = parse_num(request.form.get('target_amount'))
    current = parse_num(request.form.get('current_amount'))
    deadline_str = request.form.get('deadline')
    
    deadline = None
    if deadline_str:
        from datetime import datetime
        try:
            deadline = datetime.strptime(deadline_str, '%Y-%m-%d')
        except: pass
        
    goal = SavingsGoal(
        user_id=current_user.id,
        name=name,
        target_amount=target,
        current_amount=current,
        deadline=deadline
    )
    db.session.add(goal)
    
    # Auto-Expense Logic: Deduct initial savings from Income (Cash Flow)
    if current > 0:
        from models import Expense, Category
        from datetime import datetime
        
        # Find System Category
        cat = Category.query.filter_by(name="Investments & Savings").first()
        if not cat: cat = Category.query.first() # Fallback
        
        exp = Expense(
            user_id=current_user.id,
            category_id=cat.id,
            amount=current,
            description=f"Savings Allocation: {name}",
            date=datetime.utcnow()
        )
        db.session.add(exp)
        
    db.session.commit()
    flash('Savings Goal Added & Initial Funds Deducted from Available Income!')
    return redirect(url_for('investment.wealth_dashboard'))

@investment_bp.route('/wealth/goal/edit/<int:id>', methods=['POST'])
@login_required
def edit_goal(id):
    def parse_num(val):
        if not val:
            return 0.0
        return float(str(val).replace(',', '').strip() or 0.0)

    goal = SavingsGoal.query.get_or_404(id)
    if goal.user_id != current_user.id: return redirect(url_for('investment.wealth_dashboard'))
    
    # Check if this is a "Top Up" or full Edit
    # If form has 'add_amount', validation:
    add_amt = request.form.get('add_amount')
    if add_amt:
        amt_val = parse_num(add_amt)
        goal.current_amount += amt_val
        
        # Auto-Expense Logic for Top Up
        from models import Expense, Category
        from datetime import datetime
        
        cat = Category.query.filter_by(name="Investments & Savings").first()
        if not cat: cat = Category.query.first()
        
        exp = Expense(
            user_id=current_user.id,
            category_id=cat.id,
            amount=amt_val,
            description=f"Savings Top-up: {goal.name}",
            date=datetime.utcnow()
        )
        db.session.add(exp)
        
        flash(f'Funds added! ₦{amt_val:,.2f} deducted from Available Income.')
    else:
        # Full Edit
        goal.name = request.form.get('name') or goal.name
        if request.form.get('target_amount'):
            goal.target_amount = parse_num(request.form.get('target_amount'))
        if request.form.get('current_amount') is not None and request.form.get('current_amount') != '':
            goal.current_amount = parse_num(request.form.get('current_amount'))
            
        deadline_str = request.form.get('deadline')
        if deadline_str:
            from datetime import datetime
            try:
                goal.deadline = datetime.strptime(deadline_str, '%Y-%m-%d')
            except: pass
        flash('Goal updated!')
            
    db.session.commit()
    return redirect(url_for('investment.wealth_dashboard'))

@investment_bp.route('/wealth/goal/delete/<int:id>', methods=['POST'])
@login_required
def delete_goal(id):
    goal = SavingsGoal.query.get_or_404(id)
    if goal.user_id != current_user.id: return redirect(url_for('investment.wealth_dashboard'))
    
    db.session.delete(goal)
    db.session.commit()
    flash('Goal deleted.')
    return redirect(url_for('investment.wealth_dashboard'))

@investment_bp.route('/wealth/add', methods=['POST'])
@login_required
def add_investment():
    def parse_num(val):
        if not val:
            return 0.0
        return float(str(val).replace(',', '').strip() or 0.0)

    # Simple add logic for demo
    name = request.form.get('name')
    asset_type = request.form.get('asset_type')
    sub_type = request.form.get('sub_type')
    total_value = parse_num(request.form.get('total_value'))
    annual_gain = parse_num(request.form.get('annual_gain'))
    disposal_proceeds = parse_num(request.form.get('disposal_proceeds'))
    chargeable_gains = parse_num(request.form.get('chargeable_gains'))
    
    # Only Bond and Cash have fixed annual coupon/interest gain
    if asset_type in [AssetType.STOCK.value, AssetType.CRYPTO.value]:
        annual_gain = 0.0
    
    from models import FundingSource, Expense, Category, CategoryTarget
    from datetime import datetime
    
    funding_val = request.form.get('funding_source')
    funding_source = FundingSource(funding_val) if funding_val else FundingSource.EXISTING
    
    inv = Investment(
        user_id=current_user.id,
        name=name,
        asset_type=AssetType(asset_type),
        sub_type=InvestmentSubType(sub_type),
        total_value=total_value,
        annual_gain=annual_gain,
        disposal_proceeds=disposal_proceeds,
        chargeable_gains=chargeable_gains,
        funding_source=funding_source
    )
    
    # If Income Funded, create Expense
    if funding_source == FundingSource.INCOME:
        # Find or Create 'Investments/Savings' Category
        cat = Category.query.filter_by(name="Investments & Savings", user_id=None).first()
        if not cat:
            cat = Category.query.filter_by(name="Investments & Savings").first()
            if not cat:
                # Fallback to any suitable one or create temp
                # For MVP let's assume one exists or pick first
                cat = Category.query.first() 
                
        # Create Expense
        exp = Expense(
            user_id=current_user.id,
            category_id=cat.id if cat else 1, # Fallback safe
            amount=total_value,
            description=f"Purchase of Asset: {name}",
            date=datetime.utcnow()
        )
        db.session.add(exp)
        db.session.flush() # Get ID
        inv.expense_id = exp.id
        flash(f'Asset added & Expense logged (₦{total_value:,.2f})')
    else:
        flash('Asset added (Brought Forward)!')

    db.session.add(inv)
    db.session.commit()
    return redirect(url_for('investment.wealth_dashboard'))

@investment_bp.route('/wealth/edit/<int:id>', methods=['POST'])
@login_required
def edit_investment(id):
    def parse_num(val):
        if not val:
            return 0.0
        return float(str(val).replace(',', '').strip() or 0.0)

    inv = Investment.query.get_or_404(id)
    if inv.user_id != current_user.id:
        flash('Unauthorized access.')
        return redirect(url_for('investment.wealth_dashboard'))
        
    inv.name = request.form.get('name')
    inv.asset_type = AssetType(request.form.get('asset_type'))
    inv.sub_type = InvestmentSubType(request.form.get('sub_type'))
    inv.total_value = parse_num(request.form.get('total_value'))
    inv.annual_gain = parse_num(request.form.get('annual_gain'))
    inv.disposal_proceeds = parse_num(request.form.get('disposal_proceeds'))
    inv.chargeable_gains = parse_num(request.form.get('chargeable_gains'))
    
    if inv.asset_type in [AssetType.STOCK, AssetType.CRYPTO]:
        inv.annual_gain = 0.0
    
    db.session.commit()
    flash('Investment updated successfully!')
    return redirect(url_for('investment.wealth_dashboard'))

@investment_bp.route('/wealth/delete/<int:id>', methods=['POST'])
@login_required
def delete_investment(id):
    inv = Investment.query.get_or_404(id)
    if inv.user_id != current_user.id:
        flash('Unauthorized access.')
        return redirect(url_for('investment.wealth_dashboard'))
        
    db.session.delete(inv)
    db.session.commit()
    flash('Investment deleted.')
    return redirect(url_for('investment.wealth_dashboard'))

@investment_bp.route('/optimizer', methods=['GET', 'POST'])
@login_required
def optimizer():
    tey_result = None
    yield_val = None
    tax_bracket_pct = None
    if request.method == 'POST':
        yield_str = str(request.form.get('yield') or '0').replace(',', '').strip()
        tax_str = str(request.form.get('tax_bracket') or '0').replace(',', '').strip()
        yield_val = float(yield_str or 0)
        tax_bracket_pct = float(tax_str or 0)
        tax_bracket = tax_bracket_pct / 100.0
        
        real_tey = calculate_tey(yield_val, tax_bracket)
        tey_result = round(real_tey, 2)
        
    return render_template('optimizer.html', 
                           user=current_user,
                           tey_result=tey_result,
                           yield_val=yield_val,
                           tax_bracket_pct=tax_bracket_pct)
