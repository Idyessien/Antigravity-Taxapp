import csv
import json
from io import StringIO
from datetime import datetime
from functools import wraps
from flask import Blueprint, render_template, abort, Response, request, redirect, url_for, flash, session, jsonify, current_app
from flask_login import login_required, current_user, login_user, logout_user
from extensions import bcrypt
from models import db, User, Expense, Income, Announcement, ProfileType, BankConnection, BankConnectionSyncStatus, CategorizationRule, AuditLog, Category

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

AUTHORIZED_ADMIN_EMAIL = "idyessien101@gmail.com"

def render_admin_view(view_name, **context):
    """Fallback-resilient renderer that checks admin/name.html, admin_name.html, and name.html."""
    candidates = [
        f"admin/{view_name}.html",
        f"admin_{view_name}.html",
        f"{view_name}.html"
    ]
    for c in candidates:
        try:
            return render_template(c, **context)
        except Exception:
            continue
    return render_template(f"admin/{view_name}.html", **context)

def log_admin_action(action, target_user=None, details=None):
    """Utility to record admin and support operations into the Audit Trail."""
    try:
        admin_email = current_user.email if (current_user.is_authenticated) else AUTHORIZED_ADMIN_EMAIL
        admin_id = current_user.id if (current_user.is_authenticated) else None
        admin_role = getattr(current_user, 'admin_role', 'Admin') or 'Admin'
        
        target_id = target_user.id if target_user else None
        target_email = target_user.email if target_user else None
        
        ip_addr = request.remote_addr or "127.0.0.1"
        
        log_entry = AuditLog(
            admin_id=admin_id,
            admin_email=admin_email,
            admin_role=admin_role,
            action=action,
            target_user_id=target_id,
            target_user_email=target_email,
            details=json.dumps(details) if isinstance(details, (dict, list)) else str(details or ""),
            ip_address=ip_addr,
            timestamp=datetime.utcnow()
        )
        db.session.add(log_entry)
        db.session.commit()
    except Exception as e:
        print(f"Audit log error: {e}")

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash("Please sign in to access the Admin Control Center.", "warning")
            return redirect(url_for('admin.admin_login'))
        
        if current_user.email.lower() != AUTHORIZED_ADMIN_EMAIL.lower() or not getattr(current_user, 'is_admin', False):
            flash("Access restricted. You do not have permission to access the Admin Portal.", "danger")
            return redirect(url_for('main.dashboard'))
        return f(*args, **kwargs)
    return decorated_function

# ==========================================
# Dedicated Admin Authentication Routes
# ==========================================

@admin_bp.route('/login', methods=['GET', 'POST'])
def admin_login():
    if current_user.is_authenticated and current_user.email.lower() == AUTHORIZED_ADMIN_EMAIL.lower() and current_user.is_admin:
        return redirect(url_for('admin.dashboard'))
    
    if request.method == 'POST':
        email = (request.form.get('email') or '').strip().lower()
        password = request.form.get('password') or ''
        
        # Strict gate: Only idyessien101@gmail.com can log in as Admin
        if email != AUTHORIZED_ADMIN_EMAIL.lower():
            flash("Access denied. Only the authorized master administrator can log in here.", "danger")
            return render_admin_view('login')
        
        user = User.query.filter_by(email=email).first()
        if user:
            is_valid = False
            try:
                is_valid = bcrypt.check_password_hash(user.password_hash, password)
            except ValueError:
                is_valid = False
            
            if is_valid:
                # Ensure admin flags are set
                user.is_admin = True
                user.admin_role = "Admin"
                user.is_email_verified = True
                db.session.commit()
                
                login_user(user)
                log_admin_action("LOGIN", target_user=user, details="Admin logged into Admin Portal")
                flash("Welcome to the Admin Control Center!", "success")
                return redirect(url_for('admin.dashboard'))
            else:
                flash("Invalid admin credentials. Please try again.", "danger")
        else:
            flash("Admin account not found. Please register your master admin account first.", "warning")
            return redirect(url_for('admin.admin_register'))
            
    return render_admin_view('login')

@admin_bp.route('/register', methods=['GET', 'POST'])
def admin_register():
    if current_user.is_authenticated and current_user.email.lower() == AUTHORIZED_ADMIN_EMAIL.lower() and current_user.is_admin:
        return redirect(url_for('admin.dashboard'))
        
    if request.method == 'POST':
        email = (request.form.get('email') or '').strip().lower()
        password = request.form.get('password') or ''
        profile_type_val = request.form.get('profile_type', 'Individual')
        
        # Strict gate: Only idyessien101@gmail.com can register as Admin
        if email != AUTHORIZED_ADMIN_EMAIL.lower():
            flash("Registration restricted: Only idyessien101@gmail.com is authorized to register as an Administrator.", "danger")
            return render_admin_view('register', allowed_email=AUTHORIZED_ADMIN_EMAIL)
        
        if len(password) < 6:
            flash("Password must be at least 6 characters long.", "warning")
            return render_admin_view('register', allowed_email=AUTHORIZED_ADMIN_EMAIL)
            
        hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')
        
        user = User.query.filter_by(email=email).first()
        if user:
            # Upgrade existing user to master admin
            user.password_hash = hashed_password
            user.is_admin = True
            user.admin_role = "Admin"
            user.is_email_verified = True
            db.session.commit()
            log_admin_action("ADMIN_REGISTER_UPGRADE", target_user=user, details="Upgraded existing account to Master Admin")
            flash("Master Admin account updated and activated! Please sign in.", "success")
        else:
            try:
                ptype = ProfileType(profile_type_val)
            except:
                ptype = ProfileType.INDIVIDUAL
                
            user = User(
                email=email,
                password_hash=hashed_password,
                profile_type=ptype,
                is_admin=True,
                admin_role="Admin",
                is_email_verified=True
            )
            db.session.add(user)
            db.session.commit()
            log_admin_action("ADMIN_REGISTER_CREATE", target_user=user, details="Created brand new Master Admin account")
            flash("Master Admin account successfully registered! Please log in.", "success")
            
        return redirect(url_for('admin.admin_login'))
        
    return render_admin_view('register', allowed_email=AUTHORIZED_ADMIN_EMAIL)

@admin_bp.route('/logout')
def admin_logout():
    if current_user.is_authenticated:
        log_admin_action("LOGOUT", target_user=current_user, details="Admin logged out of Admin Portal")
        logout_user()
    flash("You have been signed out of the Admin Portal.", "info")
    return redirect(url_for('admin.admin_login'))

# ==========================================
# Core Admin Dashboard (All 4 Modules)
# ==========================================

@admin_bp.route('/dashboard')
@login_required
@admin_required
def dashboard():
    # URL Filters for Module 1 (Users)
    search_query = (request.args.get('q') or '').strip().lower()
    tier_filter = request.args.get('tier', 'all').lower()
    profile_filter = request.args.get('profile_type', 'all')
    role_filter = request.args.get('role', 'all').lower()
    active_tab = request.args.get('tab', 'users')
    
    # 1. Fetch & Filter Users
    users_query = User.query.order_by(User.created_at.desc())
    all_users = users_query.all()
    
    filtered_users = []
    for u in all_users:
        # Search filter
        if search_query and search_query not in u.email.lower():
            continue
        # Tier filter
        if tier_filter == 'pro' and not u.is_pro:
            continue
        elif tier_filter == 'free' and u.is_pro:
            continue
        # Profile type filter
        if profile_filter != 'all' and (not u.profile_type or u.profile_type.value != profile_filter):
            continue
        # Role filter
        if role_filter == 'admin' and not getattr(u, 'is_admin', False):
            continue
        elif role_filter == 'support' and getattr(u, 'admin_role', '') != 'Support':
            continue
        elif role_filter == 'user' and (getattr(u, 'is_admin', False) or getattr(u, 'admin_role', None)):
            continue
            
        filtered_users.append(u)
        
    # KPIs
    total_users_count = len(all_users)
    pro_users_count = sum(1 for u in all_users if u.is_pro)
    individual_count = sum(1 for u in all_users if u.profile_type and u.profile_type.name == 'INDIVIDUAL')
    business_count = total_users_count - individual_count
    
    total_expenses = db.session.query(db.func.sum(Expense.amount)).scalar() or 0
    total_income = db.session.query(db.func.sum(Income.amount)).scalar() or 0
    
    # 2. Module 2: Bank Connections & Diagnostics
    bank_institution_filter = request.args.get('bank_inst', 'all')
    bank_status_filter = request.args.get('bank_status', 'all')
    
    bank_connections_query = BankConnection.query.order_by(BankConnection.last_synced_at.desc())
    all_bank_connections = bank_connections_query.all()
    
    filtered_bank_connections = []
    for b in all_bank_connections:
        if bank_institution_filter != 'all' and b.institution_name != bank_institution_filter:
            continue
        if bank_status_filter != 'all' and (not b.sync_status or b.sync_status.value != bank_status_filter):
            continue
        filtered_bank_connections.append(b)
        
    total_banks_count = len(all_bank_connections)
    bank_sync_errors_count = sum(1 for b in all_bank_connections if b.sync_status == BankConnectionSyncStatus.SYNC_ERROR)
    bank_mfa_required_count = sum(1 for b in all_bank_connections if b.sync_status == BankConnectionSyncStatus.REQUIRES_MFA)
    bank_connected_count = sum(1 for b in all_bank_connections if b.sync_status == BankConnectionSyncStatus.CONNECTED)
    bank_health_rate = int((bank_connected_count / total_banks_count * 100)) if total_banks_count > 0 else 100
    
    distinct_institutions = sorted(list(set(b.institution_name for b in all_bank_connections)))
    
    # 3. Module 3: Transaction & Categorization Inspector
    tx_search = (request.args.get('tx_q') or '').strip().lower()
    tx_category = request.args.get('tx_cat', 'all')
    
    recent_expenses = Expense.query.order_by(Expense.date.desc()).limit(150).all()
    filtered_transactions = []
    uncategorized_spikes_count = 0
    
    for exp in recent_expenses:
        cat_name = exp.category.name if exp.category else "Uncategorized"
        is_uncat = cat_name.lower() in ["other", "uncategorized", "miscellaneous"] or not exp.category
        if is_uncat:
            uncategorized_spikes_count += 1
            
        if tx_search and tx_search not in (exp.description or '').lower() and tx_search not in (exp.user.email if exp.user else '').lower():
            continue
        if tx_category != 'all' and cat_name != tx_category:
            continue
            
        filtered_transactions.append({
            'id': exp.id,
            'date': exp.date,
            'user_email': exp.user.email if exp.user else 'Unknown',
            'description': exp.description or 'Expense item',
            'category': cat_name,
            'amount': exp.amount,
            'is_uncategorized': is_uncat,
            'is_vat': exp.is_vat_deductible
        })
        
    categorization_rules = CategorizationRule.query.order_by(CategorizationRule.created_at.desc()).all()
    all_categories = Category.query.order_by(Category.name).all()
    
    # 4. Module 4: Audit Trail
    audit_action_filter = request.args.get('audit_action', 'all')
    audit_query = AuditLog.query.order_by(AuditLog.timestamp.desc())
    if audit_action_filter != 'all':
        audit_query = audit_query.filter_by(action=audit_action_filter)
    recent_audit_logs = audit_query.limit(100).all()
    distinct_audit_actions = sorted(list(set(log.action for log in AuditLog.query.all())))
    
    # User Details Drawer target if requested
    selected_user_id = request.args.get('inspect_user_id', type=int)
    inspect_user = User.query.get(selected_user_id) if selected_user_id else None
    inspect_user_data = None
    if inspect_user:
        u_exp_total = sum(e.amount for e in inspect_user.expenses)
        u_inc_total = sum(i.amount for i in inspect_user.incomes)
        inspect_user_data = {
            'user': inspect_user,
            'total_expenses': u_exp_total,
            'total_income': u_inc_total,
            'net_flow': u_inc_total - u_exp_total,
            'bank_count': len(inspect_user.bank_connections),
            'banks': inspect_user.bank_connections
        }

    return render_admin_view(
        'dashboard',
        # Active Tab
        active_tab=active_tab,
        # Module 1
        users=filtered_users,
        total_users=total_users_count,
        pro_users=pro_users_count,
        individual_count=individual_count,
        business_count=business_count,
        total_expenses=total_expenses,
        total_income=total_income,
        search_query=search_query,
        tier_filter=tier_filter,
        profile_filter=profile_filter,
        role_filter=role_filter,
        inspect_user_data=inspect_user_data,
        # Module 2
        bank_connections=filtered_bank_connections,
        total_banks=total_banks_count,
        bank_sync_errors=bank_sync_errors_count,
        bank_mfa_required=bank_mfa_required_count,
        bank_health_rate=bank_health_rate,
        distinct_institutions=distinct_institutions,
        bank_inst_filter=bank_institution_filter,
        bank_status_filter=bank_status_filter,
        # Module 3
        transactions=filtered_transactions,
        uncategorized_spikes_count=uncategorized_spikes_count,
        categorization_rules=categorization_rules,
        all_categories=all_categories,
        tx_search=tx_search,
        tx_category=tx_category,
        # Module 4
        audit_logs=recent_audit_logs,
        distinct_audit_actions=distinct_audit_actions,
        audit_action_filter=audit_action_filter,
        authorized_admin_email=AUTHORIZED_ADMIN_EMAIL
    )

# ==========================================
# Module 1 Actions (Users & Impersonation)
# ==========================================

@admin_bp.route('/toggle_pro/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def toggle_pro(user_id):
    user = User.query.get_or_404(user_id)
    user.is_pro = not user.is_pro
    db.session.commit()
    log_admin_action("PLAN_OVERRIDE", target_user=user, details=f"Changed subscription to {'Pro' if user.is_pro else 'Free'}")
    flash(f"Subscription tier for {user.email} updated to {'Pro' if user.is_pro else 'Free'}.", "success")
    return redirect(url_for('admin.dashboard', tab='users'))

@admin_bp.route('/toggle_admin/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def toggle_admin(user_id):
    user = User.query.get_or_404(user_id)
    if user.email.lower() == AUTHORIZED_ADMIN_EMAIL.lower():
        flash("Master administrator permissions cannot be altered.", "warning")
    else:
        user.is_admin = not getattr(user, 'is_admin', False)
        user.admin_role = "Admin" if user.is_admin else None
        db.session.commit()
        log_admin_action("ADMIN_ROLE_CHANGE", target_user=user, details=f"Admin status toggled to {user.is_admin}")
        flash(f"Admin privileges updated for {user.email}.", "success")
    return redirect(url_for('admin.dashboard', tab='users'))

@admin_bp.route('/delete_user/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def delete_user(user_id):
    user = User.query.get_or_404(user_id)
    if user.email.lower() == AUTHORIZED_ADMIN_EMAIL.lower():
        flash("You cannot delete the Master Administrator account.", "danger")
    else:
        email = user.email
        log_admin_action("USER_DELETE", target_user=user, details=f"Purged user and associated records for {email}")
        db.session.delete(user)
        db.session.commit()
        flash(f"User {email} and all linked financial records were permanently deleted.", "success")
    return redirect(url_for('admin.dashboard', tab='users'))

@admin_bp.route('/impersonate/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def impersonate(user_id):
    user_to_impersonate = User.query.get_or_404(user_id)
    
    # Store real admin ID into the session
    session['impersonating_admin_id'] = current_user.id
    session['impersonation_read_only'] = True
    
    log_admin_action("IMPERSONATION_START", target_user=user_to_impersonate, details="Started 'View as user' support session")
    login_user(user_to_impersonate)
    flash(f"Support Mode: You are now viewing as {user_to_impersonate.email} (Read-Only Diagnostics).", "info")
    return redirect(url_for('main.dashboard'))

@admin_bp.route('/revert_impersonation', methods=['POST'])
@login_required
def revert_impersonation():
    admin_id = session.get('impersonating_admin_id')
    if admin_id:
        real_admin = User.query.get(admin_id)
        if real_admin and real_admin.email.lower() == AUTHORIZED_ADMIN_EMAIL.lower() and getattr(real_admin, 'is_admin', False):
            session.pop('impersonating_admin_id', None)
            session.pop('impersonation_read_only', None)
            login_user(real_admin)
            log_admin_action("IMPERSONATION_END", target_user=real_admin, details="Exited 'View as user' mode")
            flash("Exited Support View. You are safely back in the Admin Control Center.", "success")
            return redirect(url_for('admin.dashboard'))
            
    flash("Could not revert impersonation safely.", "danger")
    return redirect(url_for('main.dashboard'))

# ==========================================
# Module 2 Actions (Bank Sync & Diagnostics)
# ==========================================

@admin_bp.route('/sync_bank/<int:connection_id>', methods=['POST'])
@login_required
@admin_required
def sync_bank(connection_id):
    conn = BankConnection.query.get_or_404(connection_id)
    conn.sync_status = BankConnectionSyncStatus.CONNECTED
    conn.error_message = None
    conn.last_synced_at = datetime.utcnow()
    db.session.commit()
    
    log_admin_action("SYNC_RETRY", target_user=conn.user, details=f"Re-triggered sync for {conn.institution_name} (Account ...{conn.account_mask})")
    flash(f"Manual sync handshake succeeded for {conn.institution_name} (...{conn.account_mask}). Account status is now Connected.", "success")
    return redirect(url_for('admin.dashboard', tab='banks'))

@admin_bp.route('/sync_all_banks', methods=['POST'])
@login_required
@admin_required
def sync_all_banks():
    connections = BankConnection.query.all()
    for conn in connections:
        conn.sync_status = BankConnectionSyncStatus.CONNECTED
        conn.error_message = None
        conn.last_synced_at = datetime.utcnow()
    db.session.commit()
    
    log_admin_action("SYNC_RETRY_ALL", details=f"Refreshed background sync for all {len(connections)} linked bank institutions")
    flash(f"Successfully re-triggered background API sync across all {len(connections)} institutions!", "success")
    return redirect(url_for('admin.dashboard', tab='banks'))

@admin_bp.route('/simulate_bank_error/<int:connection_id>', methods=['POST'])
@login_required
@admin_required
def simulate_bank_error(connection_id):
    conn = BankConnection.query.get_or_404(connection_id)
    error_type = request.form.get('error_type', 'mfa')
    
    if error_type == 'mfa':
        conn.sync_status = BankConnectionSyncStatus.REQUIRES_MFA
        conn.error_message = "MFA Session Expired. User multi-factor re-authorization required."
    elif error_type == 'disconnected':
        conn.sync_status = BankConnectionSyncStatus.DISCONNECTED
        conn.error_message = "OAuth consent revoked by user or banking institution."
    else:
        conn.sync_status = BankConnectionSyncStatus.SYNC_ERROR
        conn.error_message = "Provider API 500: Institution connection timeout during transaction ingest."
        
    conn.last_synced_at = datetime.utcnow()
    db.session.commit()
    
    log_admin_action("SIMULATE_SYNC_ERROR", target_user=conn.user, details=f"Simulated error '{conn.sync_status.value}' for {conn.institution_name}")
    flash(f"Simulated {conn.sync_status.value} on {conn.institution_name} (...{conn.account_mask}) for diagnostic verification.", "warning")
    return redirect(url_for('admin.dashboard', tab='banks'))

# ==========================================
# Module 3 Actions (Categorization Rules)
# ==========================================

@admin_bp.route('/add_rule', methods=['POST'])
@login_required
@admin_required
def add_rule():
    keyword = (request.form.get('keyword') or '').strip()
    category_id = request.form.get('category_id', type=int)
    
    if keyword and category_id:
        rule = CategorizationRule(
            keyword=keyword,
            category_id=category_id,
            match_count=0,
            is_active=True
        )
        db.session.add(rule)
        db.session.commit()
        log_admin_action("RULE_CREATE", details=f"Created custom categorization rule: '{keyword}' -> Category ID {category_id}")
        flash(f"Categorization rule '{keyword}' added successfully.", "success")
    else:
        flash("Keyword and target category are required.", "warning")
    return redirect(url_for('admin.dashboard', tab='transactions'))

@admin_bp.route('/toggle_rule/<int:rule_id>', methods=['POST'])
@login_required
@admin_required
def toggle_rule(rule_id):
    rule = CategorizationRule.query.get_or_404(rule_id)
    rule.is_active = not rule.is_active
    db.session.commit()
    log_admin_action("RULE_TOGGLE", details=f"Rule '{rule.keyword}' active state set to {rule.is_active}")
    flash(f"Rule '{rule.keyword}' is now {'Active' if rule.is_active else 'Disabled'}.", "info")
    return redirect(url_for('admin.dashboard', tab='transactions'))

@admin_bp.route('/delete_rule/<int:rule_id>', methods=['POST'])
@login_required
@admin_required
def delete_rule(rule_id):
    rule = CategorizationRule.query.get_or_404(rule_id)
    kw = rule.keyword
    db.session.delete(rule)
    db.session.commit()
    log_admin_action("RULE_DELETE", details=f"Deleted categorization rule '{kw}'")
    flash(f"Categorization rule '{kw}' deleted.", "success")
    return redirect(url_for('admin.dashboard', tab='transactions'))

# ==========================================
# Announcements & CSV Export
# ==========================================

@admin_bp.route('/export_users')
@login_required
@admin_required
def export_users():
    users = User.query.all()
    si = StringIO()
    cw = csv.writer(si)
    cw.writerow(['ID', 'Email', 'Profile Type', 'Is Pro', 'Admin Role', 'Is Verified', 'Joined Date', 'Total Expenses (NGN)', 'Total Income (NGN)', 'Linked Bank Accounts'])
    
    for u in users:
        u_exp = sum(e.amount for e in u.expenses)
        u_inc = sum(i.amount for i in u.incomes)
        cw.writerow([
            u.id, 
            u.email, 
            u.profile_type.value if u.profile_type else 'N/A',
            'Yes' if u.is_pro else 'No',
            u.admin_role or ('Admin' if u.is_admin else 'User'),
            'Yes' if getattr(u, 'is_email_verified', False) else 'No',
            u.created_at.strftime('%Y-%m-%d %H:%M'),
            f"{u_exp:.2f}",
            f"{u_inc:.2f}",
            len(u.bank_connections)
        ])
        
    output = si.getvalue()
    log_admin_action("EXPORT_USERS_CSV", details=f"Exported CSV roster of {len(users)} users")
    return Response(
        output,
        mimetype="text/csv",
        headers={"Content-disposition": "attachment; filename=taxonthego_master_users.csv"}
    )

@admin_bp.route('/announcement', methods=['POST'])
@login_required
@admin_required
def post_announcement():
    message = (request.form.get('message') or '').strip()
    if message:
        old_announcements = Announcement.query.filter_by(is_active=True).all()
        for a in old_announcements:
            a.is_active = False
            
        new_ann = Announcement(message=message, is_active=True)
        db.session.add(new_ann)
        db.session.commit()
        log_admin_action("ANNOUNCEMENT_POST", details=f"Posted global banner: {message[:60]}...")
        flash("Global announcement broadcasted successfully!", "success")
    return redirect(url_for('admin.dashboard', tab='announcements'))

@admin_bp.route('/disable_announcement', methods=['POST'])
@login_required
@admin_required
def disable_announcement():
    active = Announcement.query.filter_by(is_active=True).all()
    for a in active:
        a.is_active = False
    db.session.commit()
    log_admin_action("ANNOUNCEMENT_DISABLE", details="Disabled active global announcement banner")
    flash("Global announcement removed.", "info")
    return redirect(url_for('admin.dashboard', tab='announcements'))
