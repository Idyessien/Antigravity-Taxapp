import os
from flask import Flask
from models import db, User
from extensions import bcrypt
from flask_login import LoginManager
from flask_migrate import Migrate
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev_secret_key')

# Mail Configuration
app.config['MAIL_SERVER'] = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
app.config['MAIL_PORT'] = int(os.environ.get('MAIL_PORT', 587))
app.config['MAIL_USE_TLS'] = os.environ.get('MAIL_USE_TLS', 'True').lower() in ['true', '1', 't']
app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME', 'idyessien101@gmail.com')
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD', '')

# Using SQLite for local dev, compatible with PostgreSQL
import os
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///' + os.path.join(basedir, 'site.db'))
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

from extensions import bcrypt, mail

db.init_app(app)
bcrypt.init_app(app)
mail.init_app(app)
migrate = Migrate(app, db)
login_manager = LoginManager(app)
login_manager.login_view = 'auth.login'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Import routes later
from auth import auth as auth_blueprint
app.register_blueprint(auth_blueprint)
from routes import main as main_blueprint
app.register_blueprint(main_blueprint)
from investment_routes import investment_bp
app.register_blueprint(investment_bp)
from settings_routes import settings_bp
app.register_blueprint(settings_bp)
from compliance_routes import compliance_bp
app.register_blueprint(compliance_bp)
from income_routes import income_bp
app.register_blueprint(income_bp)
from wht_routes import wht_bp
app.register_blueprint(wht_bp)
from business_routes import business_bp
app.register_blueprint(business_bp)
from admin_routes import admin_bp
app.register_blueprint(admin_bp)

@app.context_processor
def inject_announcement():
    try:
        from models import Announcement
        # Get the latest active announcement
        active = Announcement.query.filter_by(is_active=True).order_by(Announcement.created_at.desc()).first()
        return dict(active_announcement=active)
    except:
        return dict(active_announcement=None)

@app.context_processor
def inject_quick_add_data():
    from flask_login import current_user
    try:
        from models import IncomeType, ProfileType, Category, CategoryTarget
        if current_user.is_authenticated:
            ptype = current_user.profile_type
            if ptype == ProfileType.CORPORATION:
                allowed_income_types = [
                    IncomeType.CORE_REVENUE, IncomeType.SUBSIDIARY_DIVIDENDS, IncomeType.CAPITAL_GAINS,
                    IncomeType.ROYALTIES_LICENSING, IncomeType.FOREX_GAINS, IncomeType.INTEREST_INCOME,
                    IncomeType.INVESTMENT, IncomeType.BROUGHT_FORWARD, IncomeType.OTHER
                ]
            elif ptype == ProfileType.SMALL_BUSINESS:
                allowed_income_types = [
                    IncomeType.PRODUCT_SALES, IncomeType.SERVICE_FEES, IncomeType.RENTAL_INCOME, IncomeType.GRANTS,
                    IncomeType.INVESTMENT, IncomeType.BROUGHT_FORWARD, IncomeType.OTHER
                ]
            else: # INDIVIDUAL
                allowed_income_types = [
                    IncomeType.SALARY, IncomeType.SIDE_GIG, IncomeType.GIFT, IncomeType.TERMINATION_BENEFIT,
                    IncomeType.INVESTMENT, IncomeType.BROUGHT_FORWARD, IncomeType.OTHER
                ]
            
            sys_cats = Category.query.filter_by(user_id=None).all()
            user_cats = Category.query.filter_by(user_id=current_user.id).all()
            unique_cats = {c.name.lower(): c for c in (sys_cats + user_cats)}.values()
            
            final_cats = []
            for c in unique_cats:
                if c.target_profile == CategoryTarget.BOTH:
                    final_cats.append(c)
                elif c.target_profile == CategoryTarget.BUSINESS and ptype != ProfileType.INDIVIDUAL:
                    final_cats.append(c)
                elif c.target_profile == CategoryTarget.INDIVIDUAL and ptype == ProfileType.INDIVIDUAL:
                    final_cats.append(c)
            sorted_cats = sorted(final_cats, key=lambda x: (x.group or "Other", x.name))
            
            EMOJI_MAP = {
                "Housing": "🏠",
                "Transportation": "🚗",
                "Utilities": "💡",
                "Household & Food": "🍔",
                "Health & Medical": "💊",
                "Investment": "📈",
                "Facility": "🏢",
                "HR": "👥",
                "Compliance": "⚖️",
                "Operations": "⚙️",
                "Governance": "🏛️",
                "Other": "🛒"
            }
            
            return dict(global_income_types=allowed_income_types, global_expense_categories=sorted_cats, EMOJI_MAP=EMOJI_MAP)
    except:
        pass
    return {}

@app.route('/initdb')
def initdb():
    try:
        db.create_all()
        try:
            from seed_data import seed_categories
            seed_categories()
        except ImportError:
            pass # Failsafe if seed_data is not shipped
        return "Database created and Categories Seeded successfully!"
    except Exception as e:
        import traceback
        return f"Database creation failed:<br><pre>{traceback.format_exc()}</pre>"

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
