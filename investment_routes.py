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
    name = request.form.get('name')
    target = float(request.form.get('target_amount') or 0)
    current = float(request.form.get('current_amount') or 0)
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
    goal = SavingsGoal.query.get_or_404(id)
    if goal.user_id != current_user.id: return redirect(url_for('investment.wealth_dashboard'))
    
    # Check if this is a "Top Up" or full Edit
    # If form has 'add_amount', validation:
    add_amt = request.form.get('add_amount')
    if add_amt:
        amt_val = float(add_amt)
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
        goal.target_amount = float(request.form.get('target_amount') or goal.target_amount)
        if request.form.get('current_amount'):
            goal.current_amount = float(request.form.get('current_amount'))
            
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
    # Simple add logic for demo
    name = request.form.get('name')
    asset_type = request.form.get('asset_type')
    sub_type = request.form.get('sub_type')
    total_value = float(request.form.get('total_value') or 0)
    annual_gain = float(request.form.get('annual_gain') or 0)
    disposal_proceeds = float(request.form.get('disposal_proceeds') or 0)
    chargeable_gains = float(request.form.get('chargeable_gains') or 0)
    
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
    inv = Investment.query.get_or_404(id)
    if inv.user_id != current_user.id:
        flash('Unauthorized access.')
        return redirect(url_for('investment.wealth_dashboard'))
        
    inv.name = request.form.get('name')
    inv.asset_type = AssetType(request.form.get('asset_type'))
    inv.sub_type = InvestmentSubType(request.form.get('sub_type'))
    inv.total_value = float(request.form.get('total_value') or 0)
    inv.annual_gain = float(request.form.get('annual_gain') or 0)
    inv.disposal_proceeds = float(request.form.get('disposal_proceeds') or 0)
    inv.chargeable_gains = float(request.form.get('chargeable_gains') or 0)
    
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
    # Prompt 10: TEY Calculator
    # Access Control: "Pro Feature" - check is_pro?
    # For now, let's just show it but maybe add a badge.
    
    tey_result = None
    if request.method == 'POST':
        yield_val = float(request.form.get('yield') or 0)
        tax_bracket = float(request.form.get('tax_bracket') or 0) / 100
        
        real_tey = calculate_tey(yield_val, tax_bracket)
        tey_result = round(real_tey, 2)
        
    return render_template('optimizer.html', tey_result=tey_result)
