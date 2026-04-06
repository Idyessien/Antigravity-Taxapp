from flask import Blueprint, render_template, request, flash, redirect, url_for
from flask_login import login_required, current_user
from models import db, Debtor, Invoice, InvoiceItem, InvoiceStatus
from datetime import datetime

business_bp = Blueprint('business', __name__, url_prefix='/business')

@business_bp.route('/debtors', methods=['GET', 'POST'])
@login_required
def debtors():
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        phone = request.form.get('phone')
        
        new_debtor = Debtor(
            user_id=current_user.id,
            name=name,
            email=email,
            phone=phone
        )
        db.session.add(new_debtor)
        db.session.commit()
        flash('Debtor added successfully!')
        return redirect(url_for('business.debtors'))
        
    all_debtors = Debtor.query.filter_by(user_id=current_user.id).all()
    return render_template('business/debtors.html', debtors=all_debtors)

@business_bp.route('/invoices', methods=['GET', 'POST'])
@login_required
def invoices():
    if request.method == 'POST':
        debtor_id = request.form.get('debtor_id')
        due_date_str = request.form.get('due_date')
        
        # Determine Invoice Number (Simple Auto-increment logic)
        count = Invoice.query.filter_by(user_id=current_user.id).count()
        inv_number = f"INV-{datetime.utcnow().year}-{count + 1:03d}"
        
        due_date = datetime.utcnow()
        if due_date_str:
            due_date = datetime.strptime(due_date_str, '%Y-%m-%d')
            
        new_inv = Invoice(
            user_id=current_user.id,
            debtor_id=debtor_id,
            invoice_number=inv_number,
            due_date=due_date,
            status=InvoiceStatus.DRAFT
        )
        db.session.add(new_inv)
        db.session.flush() # Get ID
        
        # Add Items (Simple single item for MVP or complex JS form?)
        # Let's assume single item for MVP or redirect to "Edit Invoice"
        # We will redirect to Edit Invoice to add items.
        
        db.session.commit()
        return redirect(url_for('business.view_invoice', id=new_inv.id))
        
    all_invoices = Invoice.query.filter_by(user_id=current_user.id).order_by(Invoice.created_at.desc()).all()
    debtors = Debtor.query.filter_by(user_id=current_user.id).all()
    return render_template('business/invoices.html', invoices=all_invoices, debtors=debtors)

@business_bp.route('/invoice/<int:id>', methods=['GET', 'POST'])
@login_required
def view_invoice(id):
    inv = Invoice.query.get_or_404(id)
    if inv.user_id != current_user.id:
        flash('Unauthorized')
        return redirect(url_for('business.invoices'))
        
    if request.method == 'POST':
        # Add Item
        desc = request.form.get('description')
        qty = int(request.form.get('quantity', 1))
        price = float(request.form.get('price', 0))
        
        item = InvoiceItem(
            invoice_id=inv.id,
            description=desc,
            quantity=qty,
            unit_price=price,
            amount=qty * price
        )
        db.session.add(item)
        
        # Update Total
        inv.total_amount += item.amount
        db.session.commit()
        flash('Item added!')
        
    return render_template('business/invoice_view.html', invoice=inv)

@business_bp.route('/invoice/<int:id>/status/<status>')
@login_required
def update_invoice_status(id, status):
    inv = Invoice.query.get_or_404(id)
    if inv.user_id != current_user.id: return redirect(url_for('business.invoices'))
    
    if status == 'sent': inv.status = InvoiceStatus.SENT
    elif status == 'paid': 
        inv.status = InvoiceStatus.PAID
        # TODO: Auto-log as Income? Feature for later.
        
    db.session.commit()
    return redirect(url_for('business.view_invoice', id=id))
