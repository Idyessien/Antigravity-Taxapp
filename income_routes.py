from flask import Blueprint, render_template, request, flash, redirect, url_for
from flask_login import login_required, current_user
from models import db, Income, IncomeType, Currency
from datetime import datetime, timedelta

from tax_logic import calculate_gross_from_net

income_bp = Blueprint('income', __name__)

@income_bp.route('/income', methods=['GET', 'POST'])
@login_required
def income_dashboard():
    if request.method == 'POST':
        # Add Income Logic
        amount_str = request.form.get('amount', '0').replace(',', '')
        amount = float(amount_str) if amount_str else 0.0
        date_str = request.form.get('date')
        income_type = request.form.get('income_type')
        currency = request.form.get('currency', 'NGN')
        gross_vs_net = request.form.get('gross_vs_net', 'Gross')
        description = request.form.get('description')
        
        income_date = datetime.utcnow()
        if date_str:
            try:
                income_date = datetime.strptime(date_str, '%Y-%m-%d')
            except ValueError:
                pass
                
        # Handle "Monthly" Frequency -> Just a tag now, or we can ignore frequency as requested
        # User wants "Month by Month input", so we treat it as single entry.
        
        new_income = Income(
            user_id=current_user.id,
            amount=amount,
            date=income_date,
            description=description,
            income_type=IncomeType(income_type),
            currency=Currency(currency),
            gross_vs_net="Gross" # User requested to remove Net option
            # frequency handled implicitly as One-Off
        )
        db.session.add(new_income)
        db.session.commit()
        flash('Income logged successfully!')
        return redirect(url_for('income.income_dashboard'))

    # Filter Logic
    query = Income.query.filter_by(user_id=current_user.id)
    
    # 1. Search Query
    search_q = request.args.get('search')
    if search_q:
        query = query.filter((Income.description.ilike(f'%{search_q}%')) | (Income.amount.cast(db.String).ilike(f'%{search_q}%')))
        
    # 2. Date Range
    date_range = request.args.get('date_range', '4w') # Default 4 weeks
    now = datetime.utcnow()
    
    if date_range == '4w':
        start_date = now - timedelta(weeks=4)
        query = query.filter(Income.date >= start_date)
    elif date_range == '3m':
        start_date = now - timedelta(days=90)
        query = query.filter(Income.date >= start_date)
    elif date_range == '6m':
        start_date = now - timedelta(days=180)
        query = query.filter(Income.date >= start_date)
    elif date_range == '12m':
        start_date = now - timedelta(days=365)
        query = query.filter(Income.date >= start_date)
    elif date_range == 'custom':
        start_str = request.args.get('start_date')
        end_str = request.args.get('end_date')
        if start_str:
            try:
                s_date = datetime.strptime(start_str, '%Y-%m-%d')
                query = query.filter(Income.date >= s_date)
            except ValueError: pass
        if end_str:
            try:
                e_date = datetime.strptime(end_str, '%Y-%m-%d')
                e_date = e_date + timedelta(days=1)
                query = query.filter(Income.date < e_date)
            except ValueError: pass
            
    recent_incomes = query.order_by(Income.date.desc()).all()
    
    # Brought Forward (Calculated dynamically or kept as variable)
    # User said "Remove brought forward green dashboard in the Income tab only".
    # So we don't need to pass 'brought_forward' to template anymore, or we can leave it but not show it.
    
    return render_template('income.html', 
                           incomes=recent_incomes, 
                           income_types=IncomeType)

@income_bp.route('/income/edit/<int:id>', methods=['POST'])
@login_required
def edit_income(id):
    inc = Income.query.get_or_404(id)
    if inc.user_id != current_user.id:
        flash('Unauthorized access.')
        return redirect(url_for('income.income_dashboard'))
        
    inc.source_name = request.form.get('source_name')
    inc.income_type = IncomeType(request.form.get('income_type'))
    
    amount_str = request.form.get('amount', '0').replace(',', '')
    inc.amount = float(amount_str) if amount_str else 0.0
    
    inc.currency = Currency(request.form.get('currency'))
    inc.gross_vs_net = request.form.get('gross_vs_net')
    inc.description = request.form.get('description')
    
    date_str = request.form.get('date')
    if date_str:
        try:
            inc.date = datetime.strptime(date_str, '%Y-%m-%d')
        except ValueError:
            pass

    frequency = request.form.get('frequency', 'One-Off')
    if frequency == 'Monthly' and inc.income_type == IncomeType.SALARY:
         # Edit logic: If switching to Monthly, re-annualize? 
         # Risk of double-annualizing if already annual. 
         # We assume Edit overrides Amount directly. 
         # If User explicitly changes Amount AND sets Frequency=Monthly, we calc.
         # But usually Edit is direct. Let's just apply Net-to-Gross if changed.
         pass 

    inc.gross_vs_net = "Gross"
    # Previously had Net-to-Gross conversion logic here, removed per user request.
            
    # Re-check taxable status just in case type changed
    inc.is_taxable = True
    if inc.income_type in [IncomeType.GIFT, IncomeType.BROUGHT_FORWARD]:
        inc.is_taxable = False
        
    db.session.commit()
    flash('Income entry updated!')
    return redirect(url_for('income.income_dashboard'))

    
    # Grid View Data

@income_bp.route('/income/delete/<int:id>', methods=['GET', 'POST'])
@login_required
def delete_income(id):
    inc = Income.query.get_or_404(id)
    if inc.user_id != current_user.id:
        flash('Unauthorized access.')
        return redirect(url_for('income.income_dashboard'))

    try:
        db.session.delete(inc)
        db.session.commit()
        flash('Income entry deleted successfully.')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting income: {str(e)}')
        
    return redirect(url_for('income.income_dashboard'))
