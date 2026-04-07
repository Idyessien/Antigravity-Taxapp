from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user
from models import db, User, ProfileType, IndividualSubType, Industry
from extensions import bcrypt, mail
from itsdangerous import URLSafeTimedSerializer
from flask import current_app
from flask_mail import Message
from threading import Thread

def send_async_email(app, msg):
    with app.app_context():
        try:
            mail.send(msg)
        except Exception as e:
            print("Background email error:", str(e))


def generate_confirmation_token(email):
    serializer = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
    return serializer.dumps(email, salt='email-confirm-salt')

def confirm_token(token, expiration=3600):
    serializer = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
    try:
        email = serializer.loads(
            token,
            salt='email-confirm-salt',
            max_age=expiration
        )
    except:
        return False
    return email

def generate_reset_token(email):
    serializer = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
    return serializer.dumps(email, salt='password-reset-salt')

def verify_reset_token(token, expiration=3600):
    serializer = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
    try:
        email = serializer.loads(
            token,
            salt='password-reset-salt',
            max_age=expiration
        )
    except:
        return False
    return email

auth = Blueprint('auth', __name__)

@auth.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        profile_type_val = request.form.get('profile_type')
        
        # Validation checks here (simplified)
        if User.query.filter_by(email=email).first():
            flash('Email already exists')
            return redirect(url_for('auth.register'))
            
        hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')
        
        profile_type = ProfileType(profile_type_val)
        user = User(email=email, password_hash=hashed_password, profile_type=profile_type)
        
        if profile_type != ProfileType.INDIVIDUAL:
            industry = request.form.get('industry')
            if industry:
                user.industry = Industry(industry)
        
        db.session.add(user)
        db.session.commit()
        
        # Send confirmation email
        token = generate_confirmation_token(user.email)
        confirm_url = url_for('auth.confirm_email', token=token, _external=True)
        html = render_template('auth/activate.html', confirm_url=confirm_url)
        subject = "Please confirm your email"
        msg = Message(subject, sender=current_app.config['MAIL_USERNAME'], recipients=[user.email])
        msg.html = html
        
        # Send the email in the background to prevent server lag
        Thread(target=send_async_email, args=(current_app._get_current_object(), msg)).start()
        
        flash('A confirmation email has been sent. Please verify your account to log in.', 'success')
            
        return redirect(url_for('auth.login'))
    return render_template('auth/register.html', 
                           profile_types=ProfileType, 
                           industries=Industry)

@auth.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        user = User.query.filter_by(email=email).first()
        if user:
            # Wrap check_password_hash to catch ValueError (invalid salt/hash format)
            is_valid = False
            try:
                is_valid = bcrypt.check_password_hash(user.password_hash, password)
            except ValueError:
                # Log this error ideally, but for now just treat as invalid login
                pass
                
            if is_valid:
                # Auto-elevate the core creator to Admin to bypass free server limitations.
                # Also handles Render's SQLite wipe issue by re-granting admin on fresh registers.
                if user.email.lower() == 'idyessien101@gmail.com':
                    if not user.is_admin or not user.is_email_verified:
                        user.is_admin = True
                        user.is_email_verified = True
                        db.session.commit()
                        
                if not user.is_email_verified:
                    flash('Please check your email and verify your account first.', 'warning')
                    return redirect(url_for('auth.login'))
                    
                login_user(user)
                return redirect(url_for('main.dashboard'))
            else:
                flash('Login Unsuccessful. Please check email and password')
        else:
            flash('Login Unsuccessful. Please check email and password')
    return render_template('auth/login.html')

@auth.route('/confirm/<token>')
def confirm_email(token):
    try:
        email = confirm_token(token)
    except:
        flash('The confirmation link is invalid or has expired.', 'danger')
        return redirect(url_for('auth.login'))
        
    if not email:
        flash('The confirmation link is invalid or has expired.', 'danger')
        return redirect(url_for('auth.login'))

    user = User.query.filter_by(email=email).first()
    
    if not user:
        flash('Account not found.', 'danger')
        return redirect(url_for('auth.register'))
        
    if user.is_email_verified:
        flash('Account already confirmed. Please login.', 'success')
    else:
        user.is_email_verified = True
        db.session.commit()
        flash('You have confirmed your account. Thanks!', 'success')
        
    return redirect(url_for('auth.login'))

@auth.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('main.index'))

@auth.route('/forgot_password', methods=['GET', 'POST'])
def forgot_password():
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
        
    if request.method == 'POST':
        email = request.form.get('email')
        user = User.query.filter_by(email=email).first()
        
        # We ALWAYS flash this message for security reasons so we don't leak registered emails
        flash('If an account exists with that email, a password reset link has been sent.', 'info')
        
        if user:
            token = generate_reset_token(user.email)
            reset_url = url_for('auth.reset_password', token=token, _external=True)
            html = render_template('auth/reset_email.html', reset_url=reset_url, user=user)
            subject = "Password Reset Request - Antigravity Tax"
            msg = Message(subject, sender=current_app.config['MAIL_USERNAME'], recipients=[user.email])
            msg.html = html
            
            # Send the email in the background to prevent server lag
            Thread(target=send_async_email, args=(current_app._get_current_object(), msg)).start()
                
        return redirect(url_for('auth.login'))
        
    return render_template('auth/forgot_password.html')

@auth.route('/reset_password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
        
    email = verify_reset_token(token)
    if not email:
        flash('The password reset link is invalid or has expired. Please try again.', 'danger')
        return redirect(url_for('auth.forgot_password'))
        
    user = User.query.filter_by(email=email).first()
    if not user:
        flash('Account not found.', 'danger')
        return redirect(url_for('auth.register'))
        
    if request.method == 'POST':
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        
        if password != confirm_password:
            flash('Passwords do not match.', 'danger')
            return redirect(url_for('auth.reset_password', token=token))
            
        hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')
        user.password_hash = hashed_password
        
        # If they reset their password, automatically verify their email to save them a step
        user.is_email_verified = True 
        
        db.session.commit()
        flash('Your password has been successfully updated! You can now log in.', 'success')
        return redirect(url_for('auth.login'))
        
    return render_template('auth/reset_password.html', token=token)
