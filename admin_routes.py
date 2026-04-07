import csv
from io import StringIO
from flask import Blueprint, render_template, abort, Response, request, redirect, url_for, flash, session
from flask_login import login_required, current_user, login_user
from models import db, User, Expense, Income, Announcement
from functools import wraps

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not getattr(current_user, 'is_admin', False):
            abort(403)
        return f(*args, **kwargs)
    return decorated_function

@admin_bp.route('/dashboard')
@login_required
@admin_required
def dashboard():
    users = User.query.order_by(User.created_at.desc()).all()
    
    # Analytics
    total_users = len(users)
    pro_users = sum(1 for u in users if u.is_pro)
    individual_count = sum(1 for u in users if u.profile_type.name == 'INDIVIDUAL')
    business_count = total_users - individual_count
    
    # Global Expenses
    total_expenses = db.session.query(db.func.sum(Expense.amount)).scalar() or 0
    total_income = db.session.query(db.func.sum(Income.amount)).scalar() or 0
    
    return render_template('admin/dashboard.html', 
                           users=users,
                           total_users=total_users,
                           pro_users=pro_users,
                           individual_count=individual_count,
                           business_count=business_count,
                           total_expenses=total_expenses,
                           total_income=total_income)

@admin_bp.route('/export_users')
@login_required
@admin_required
def export_users():
    users = User.query.all()
    
    # Create CSV in memory
    si = StringIO()
    cw = csv.writer(si)
    
    # Write Headers
    cw.writerow(['ID', 'Email', 'Profile Type', 'Is Pro', 'Is Admin', 'Is Verified', 'Joined Date', 'Total Expenses Logged', 'Total Income Logged'])
    
    for u in users:
        u_exp = sum(e.amount for e in u.expenses)
        u_inc = sum(i.amount for i in u.incomes)
        cw.writerow([
            u.id, 
            u.email, 
            u.profile_type.value if u.profile_type else 'N/A',
            'Yes' if u.is_pro else 'No',
            'Yes' if getattr(u, 'is_admin', False) else 'No',
            'Yes' if getattr(u, 'is_email_verified', False) else 'No',
            u.created_at.strftime('%Y-%m-%d %H:%M'),
            f"{u_exp:.2f}",
            f"{u_inc:.2f}"
        ])
        
    output = si.getvalue()
    return Response(
        output,
        mimetype="text/csv",
        headers={"Content-disposition": "attachment; filename=taxonthego_users.csv"}
    )

@admin_bp.route('/toggle_pro/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def toggle_pro(user_id):
    user = User.query.get_or_404(user_id)
    user.is_pro = not user.is_pro
    db.session.commit()
    flash(f"Pro status for {user.email} is now {'Active' if user.is_pro else 'Inactive'}.", "success")
    return redirect(url_for('admin.dashboard'))

@admin_bp.route('/toggle_admin/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def toggle_admin(user_id):
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        flash("You cannot demote yourself. Another admin must do it.", "warning")
    else:
        user.is_admin = not getattr(user, 'is_admin', False)
        db.session.commit()
        flash(f"Admin status toggled for {user.email}.", "success")
    return redirect(url_for('admin.dashboard'))

@admin_bp.route('/delete_user/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def delete_user(user_id):
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        flash("You cannot delete your own account from the admin panel.", "warning")
    elif getattr(user, 'is_admin', False):
         flash("You cannot delete other Admins.", "danger")
    else:
        db.session.delete(user)
        db.session.commit()
        flash(f"User {user.email} has been permanently deleted.", "success")
    return redirect(url_for('admin.dashboard'))

@admin_bp.route('/impersonate/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def impersonate(user_id):
    user_to_impersonate = User.query.get_or_404(user_id)
    
    # Store our real admin ID into the session so we can return later
    session['impersonating_admin_id'] = current_user.id
    
    # Force login as the target user
    login_user(user_to_impersonate)
    flash(f"You are now impersonating {user_to_impersonate.email}.", "warning")
    return redirect(url_for('main.dashboard'))

@admin_bp.route('/revert_impersonation', methods=['POST'])
@login_required
def revert_impersonation():
    admin_id = session.get('impersonating_admin_id')
    if admin_id:
        real_admin = User.query.get(admin_id)
        if real_admin and getattr(real_admin, 'is_admin', False):
            # Clean up the session manually
            session.pop('impersonating_admin_id', None)
            login_user(real_admin)
            flash("Impersonation ended. You are back in Admin Mode.", "success")
            return redirect(url_for('admin.dashboard'))
            
    # Fallback if something went weird
    flash("Could not revert impersonation securely.", "danger")
    return redirect(url_for('main.dashboard'))

@admin_bp.route('/announcement', methods=['POST'])
@login_required
@admin_required
def post_announcement():
    message = request.form.get('message')
    if message:
        # Deactivate all old ones
        old_announcements = Announcement.query.filter_by(is_active=True).all()
        for a in old_announcements:
            a.is_active = False
            
        new_ann = Announcement(message=message, is_active=True)
        db.session.add(new_ann)
        db.session.commit()
        flash("Global announcement posted!", "success")
    return redirect(url_for('admin.dashboard'))

@admin_bp.route('/disable_announcement', methods=['POST'])
@login_required
@admin_required
def disable_announcement():
    active = Announcement.query.filter_by(is_active=True).all()
    for a in active:
        a.is_active = False
    db.session.commit()
    flash("Announcement removed.", "info")
    return redirect(url_for('admin.dashboard'))
