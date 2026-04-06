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
