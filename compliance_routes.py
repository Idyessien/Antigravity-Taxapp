from flask import Blueprint, render_template, request, flash, redirect, url_for, send_file, current_app
from flask_login import login_required, current_user
from models import db, Document, DocumentType, TaxDeadline, ProfileType, WHTCredit
from datetime import datetime, date
import uuid
import os

compliance_bp = Blueprint('compliance', __name__)

@compliance_bp.route('/vault', methods=['GET', 'POST'])
@login_required
def vault():
    if request.method == 'POST':
        # Prompt 7: Document Upload Logic
        if 'file' not in request.files:
            flash('No file part')
            return redirect(request.url)
            
        file = request.files['file']
        if file.filename == '':
            flash('No selected file')
            return redirect(request.url)
            
        doc_type_val = request.form.get('doc_type')
        certified = request.form.get('certified') == 'on'
        
        if not certified:
            flash('You must certify that this document is authentic.')
            return redirect(request.url)
            
        # Save file (simulated local save)
        uploads_dir = os.path.join(current_app.root_path, 'uploads')
        os.makedirs(uploads_dir, exist_ok=True)
        
        ext = os.path.splitext(file.filename)[1]
        unique_filename = f"{uuid.uuid4()}{ext}"
        save_path = os.path.join(uploads_dir, unique_filename)
        file.save(save_path)
        
        doc = Document(
            user_id=current_user.id,
            filename=file.filename,
            file_type=DocumentType(doc_type_val),
            file_path=unique_filename,
            is_self_reported_certified=True
        )
        db.session.add(doc)
        db.session.commit()
        flash('Document uploaded securely to Vault.')
        
    documents = Document.query.filter_by(user_id=current_user.id).order_by(Document.uploaded_at.desc()).all()
    
    return render_template('vault.html', documents=documents, doc_types=DocumentType)

@compliance_bp.route('/generate_letter')
@login_required
def generate_hr_letter():
    return render_template('hr_letter.html', user=current_user, date=datetime.now())

@compliance_bp.route('/calendar')
@login_required
def calendar():
    _ensure_deadlines(current_user)
    deadlines = TaxDeadline.query.filter_by(user_id=current_user.id).order_by(TaxDeadline.due_date).all()
    
    total = len(deadlines)
    completed = sum(1 for d in deadlines if d.is_completed)
    score = (completed / total * 100) if total > 0 else 100
    
    return render_template('calendar.html', deadlines=deadlines, score=score)

@compliance_bp.route('/calendar/complete/<int:id>')
@login_required
def complete_deadline(id):
    d = TaxDeadline.query.get_or_404(id)
    if d.user_id == current_user.id:
        d.is_completed = True
        db.session.commit()
        flash('Marked as complete!')
    return redirect(url_for('compliance.calendar'))

@compliance_bp.route('/wht', methods=['GET', 'POST'])
@login_required
def wht_tracker():
    # Prompt 12: WHT Credit Tracker
    if request.method == 'POST':
        amount = float(request.form.get('amount'))
        payer = request.form.get('payer')
        desc = request.form.get('description')
        date_str = request.form.get('date') # YYYY-MM-DD
        
        date_obj = datetime.strptime(date_str, '%Y-%m-%d').date() if date_str else date.today()
        
        credit = WHTCredit(
            user_id=current_user.id,
            amount=amount,
            payer_name=payer,
            description=desc,
            date_received=date_obj,
            is_utilized=False
        )
        db.session.add(credit)
        db.session.commit()
        flash('WHT Credit Logged.')
        
    credits = WHTCredit.query.filter_by(user_id=current_user.id).order_by(WHTCredit.date_received.desc()).all()
    total_unutilized = sum(c.amount for c in credits if not c.is_utilized)
    
    return render_template('wht.html', credits=credits, total_unutilized=total_unutilized)

    return render_template('wht.html', credits=credits, total_unutilized=total_unutilized)

def _ensure_deadlines(user):
    current_year = date.today().year
    from sqlalchemy import extract
    
    # Check if deadlines ALREADY EXIST for this year
    existing = TaxDeadline.query.filter(
        TaxDeadline.user_id == user.id,
        extract('year', TaxDeadline.due_date) == current_year
    ).first()
    
    if existing:
        return

    deadlines = []
    
    if user.profile_type == ProfileType.INDIVIDUAL:
        deadlines.append(TaxDeadline(
            user_id=user.id,
            title="Personal Income Tax Filing",
            due_date=date(current_year, 3, 31),
            description="File Form A for Direct Assessment"
        ))
    else:
        deadlines.append(TaxDeadline(
            user_id=user.id,
            title="CIT Filing",
            due_date=date(current_year, 6, 30),
            description="File CIT returns (6 months after FYE)"
        ))
        
        next_month = date.today().month + 1
        if next_month > 12: next_month = 12
        
        deadlines.append(TaxDeadline(
            user_id=user.id,
            title=f"PAYE Remittance (Month {next_month-1})",
            due_date=date(current_year, next_month, 10),
            description="Remit employee taxes"
        ))
        
        deadlines.append(TaxDeadline(
            user_id=user.id,
            title=f"VAT Filing (Month {next_month-1})",
            due_date=date(current_year, next_month, 21),
            description="File VAT returns"
        ))
        
    for d in deadlines:
        db.session.add(d)
    db.session.commit()
