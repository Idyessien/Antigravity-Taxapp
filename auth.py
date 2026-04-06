from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user
from models import db, User, ProfileType, IndividualSubType, Industry
from extensions import bcrypt

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
        flash('Account created! You can now login.')
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
                login_user(user)
                return redirect(url_for('main.dashboard'))
            else:
                flash('Login Unsuccessful. Please check email and password')
        else:
            flash('Login Unsuccessful. Please check email and password')
    return render_template('auth/login.html')

@auth.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('main.index')) # Assuming main.index exists
