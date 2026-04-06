from flask import Blueprint, render_template, request, flash, redirect, url_for
from flask_login import login_required, current_user
from models import db, WHTCredit, Document, DocumentType, ProfileType
from tax_logic import calculate_nigeria_tax
from datetime import datetime

wht_bp = Blueprint('wht', __name__)

@wht_bp.route('/tax-liability')
@login_required
def tax_liability():
    # 0. Get Year from Request (Default to Current)
    now_year = datetime.utcnow().year
    selected_year = request.args.get('year', now_year, type=int)
    
    # 1. Calculate Tax Position for Selected Year
    tax_info = calculate_nigeria_tax(current_user, year=selected_year)
    
    # 2. Fetch WHT Credits
    # Filter credits by the selected year too? 
    # Usually Credits are "wallet" based, but for liability matching, we should check date_received?
    # Or just show available credits vs this year's liability?
    # Let's show ALL valid, unexpired credits available to offset.
    credits = WHTCredit.query.filter_by(user_id=current_user.id).order_by(WHTCredit.date_received.desc()).all()
    
    # 3. Separate Final vs Offsettable
    offsettable_credits = [c for c in credits if not c.is_final_tax]
    final_tax_credits = [c for c in credits if c.is_final_tax]
    
    total_offsettable = sum(c.amount for c in offsettable_credits)
    total_final = sum(c.amount for c in final_tax_credits)
    
    # 4. Calculate Net Payable
    gross_tax = tax_info.get('total_tax', 0.0)
    net_payable = max(0, gross_tax - total_offsettable)
    
    return render_template('tax_liability.html',
                           tax_info=tax_info,
                           credits=credits,
                           offsettable_total=total_offsettable,
                           final_tax_total=total_final,
                           net_payable=net_payable,
                           user=current_user,
                           profile_type=current_user.profile_type,
                           selected_year=selected_year,
                           current_year=now_year,
                           datetime=datetime)

@wht_bp.route('/wht/add', methods=['POST'])
@login_required
def add_wht_credit():
    payer = request.form.get('payer_name')
    amount_str = request.form.get('amount', '0').replace(',', '')
    amount = float(amount_str) if amount_str else 0.0
    description = request.form.get('description')
    date_str = request.form.get('date')
    is_final = True if request.form.get('is_final_tax') else False
    
    credit_date = datetime.utcnow()
    if date_str:
        try:
            credit_date = datetime.strptime(date_str, '%Y-%m-%d')
        except ValueError:
            pass
            
    if amount > 0:
        credit = WHTCredit(
            user_id=current_user.id,
            amount=amount,
            payer_name=payer,
            description=description,
            date_received=credit_date,
            is_final_tax=is_final
        )
        db.session.add(credit)
        db.session.commit()
        flash('WHT Credit added successfully!')
        
    return redirect(url_for('wht.tax_liability'))

@wht_bp.route('/wht/delete/<int:id>')
@login_required
def delete_wht_credit(id):
    credit = WHTCredit.query.get_or_404(id)
    if credit.user_id == current_user.id:
        db.session.delete(credit)
        db.session.commit()
        flash('Credit deleted.')
    return redirect(url_for('wht.tax_liability'))
