from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from sqlalchemy.orm import DeclarativeBase
import enum
from datetime import datetime

class Base(DeclarativeBase):
    pass

db = SQLAlchemy(model_class=Base)

class ProfileType(enum.Enum):
    INDIVIDUAL = "Individual"
    SMALL_BUSINESS = "Small Business"
    CORPORATION = "Corporation"

class IndividualSubType(enum.Enum):
    STUDENT = "Student"
    PAYE = "PAYE"

class Industry(enum.Enum):
    TECHNOLOGY = "Technology"
    AGRICULTURE = "Agriculture"
    RETAIL_TRADE = "Retail & Trade"
    PROFESSIONAL_SERVICES = "Professional Services"
    OIL_GAS = "Oil and Gas"
    MANUFACTURING = "Manufacturing"
    TRANSPORTATION_LOGISTICS = "Transportation & Logistics"
    FINANCIAL_SERVICES = "Financial Services"
    HOSPITALITY_INFRASTRUCTURE = "Hospitality & Infrastructure"
    MEDIA_COMMUNICATIONS = "Media & Communications"
    GENERAL = "General"

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    
    profile_type = db.Column(db.Enum(ProfileType, values_callable=lambda x: [e.value for e in x]), nullable=False)
    
    # Individual specific
    individual_subtype = db.Column(db.Enum(IndividualSubType), nullable=True)
    
    # Business specific
    industry = db.Column(db.Enum(Industry), nullable=True)
    turnover_estimate = db.Column(db.Float, default=0.0)
    
    # Pro feature
    is_pro = db.Column(db.Boolean, default=False)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    incomes = db.relationship('Income', backref='user', lazy=True)
    expenses = db.relationship('Expense', backref='user', lazy=True, cascade="all, delete-orphan")
    categories = db.relationship('Category', backref='user', lazy=True)
    settings = db.relationship('UserSetting', backref='user', uselist=False, lazy=True)

    def __repr__(self):
        return f'<User {self.email}>'

class IncomeType(enum.Enum):
    SALARY = "Salary"
    SIDE_GIG = "Side Gig"
    GIFT = "Gift"
    INVESTMENT = "Investment"
    BROUGHT_FORWARD = "Brought Forward"
    TERMINATION_BENEFIT = "Termination Benefit"
    OTHER = "Other"

class Currency(enum.Enum):
    NGN = "NGN"
    USD = "USD"

class Income(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    
    source_name = db.Column(db.String(100), nullable=True) # e.g., "Primary Job"
    income_type = db.Column(db.Enum(IncomeType, values_callable=lambda x: [e.value for e in x]), nullable=False, default=IncomeType.SALARY)
    
    amount = db.Column(db.Float, nullable=False)
    currency = db.Column(db.Enum(Currency), default=Currency.NGN)
    
    description = db.Column(db.String(200), nullable=True)
    
    # Tax details
    gross_vs_net = db.Column(db.String(10), default="Gross") # "Gross" or "Net"
    tax_already_deducted = db.Column(db.Float, default=0.0)
    is_taxable = db.Column(db.Boolean, default=True) # Gifts = False
    
    date = db.Column(db.DateTime, default=datetime.utcnow)

class CategoryTarget(enum.Enum):
    INDIVIDUAL = "Individual"
    BUSINESS = "Business"
    BOTH = "Both"

class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True) # Null for system default categories
    
    name = db.Column(db.String(100), nullable=False)
    group = db.Column(db.String(50), nullable=True) # Utilities, Transport, OPEX, etc.
    
    is_custom = db.Column(db.Boolean, default=False)
    is_custom = db.Column(db.Boolean, default=False)
    target_profile = db.Column(db.Enum(CategoryTarget), default=CategoryTarget.BOTH)
    is_capex = db.Column(db.Boolean, default=False) # For Business logic
    
    # Relationship
    expenses = db.relationship('Expense', backref='category', lazy=True)

class Expense(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey('category.id'), nullable=False)
    
    amount = db.Column(db.Float, nullable=False)
    description = db.Column(db.String(250), nullable=True)
    date = db.Column(db.DateTime, default=datetime.utcnow)
    
    is_vat_deductible = db.Column(db.Boolean, default=False)

class AssetType(enum.Enum):
    BOND = "Bond"
    STOCK = "Stock"
    CRYPTO = "Crypto"
    CASH = "Cash"

class InvestmentSubType(enum.Enum):
    GOVT = "Government" # FGN Bonds, Treasury Bills
    CORPORATE = "Corporate"
    NONE = "None"

class FundingSource(enum.Enum):
    EXISTING = "Brought Forward (Existing)"
    INCOME = "Purchased from Income"

class Investment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    
    asset_type = db.Column(db.Enum(AssetType, values_callable=lambda x: [e.value for e in x]), nullable=False)
    sub_type = db.Column(db.Enum(InvestmentSubType, values_callable=lambda x: [e.value for e in x]), default=InvestmentSubType.NONE)
    name = db.Column(db.String(100), nullable=True) # e.g., "FGN Bond 2028"
    
    # Value Tracking
    total_value = db.Column(db.Float, default=0.0)
    annual_gain = db.Column(db.Float, default=0.0) # Dividends / Coupons
    
    # CGT Tracking (For Sold Assets)
    disposal_proceeds = db.Column(db.Float, default=0.0) 
    chargeable_gains = db.Column(db.Float, default=0.0)
    
    # Funding Logic (Two Truths)
    funding_source = db.Column(db.Enum(FundingSource), default=FundingSource.EXISTING)
    expense_id = db.Column(db.Integer, db.ForeignKey('expense.id'), nullable=True)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Budget(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey('category.id'), nullable=False)
    monthly_limit = db.Column(db.Float, default=0.0)
    
    category = db.relationship('Category', backref='budget')

class UserSetting(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), unique=True, nullable=False)
    
    # Store settings as JSON string or individual columns
    # For "Hide-able Tabs", we can store a list of hidden groups
    hidden_category_groups = db.Column(db.String(500), default="") # Comma-separated or JSON
    theme = db.Column(db.String(20), default="light") # 'light' or 'dark'
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class DocumentType(enum.Enum):
    RENT_RECEIPT = "Rent Receipt"
    SCHOOL_FEES = "School Fees Invoice"
    DONATION_RECEIPT = "Donation Receipt"
    TAX_CLEARANCE = "Tax Clearance Certificate"
    WHT_NOTE = "WHT Credit Note"
    OTHER = "Other"

class Document(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    
    filename = db.Column(db.String(255), nullable=False)
    file_type = db.Column(db.Enum(DocumentType), default=DocumentType.OTHER)
    file_path = db.Column(db.String(500), nullable=False) # Local path or S3 URL
    
    is_self_reported_certified = db.Column(db.Boolean, default=False) # "I certify this is true"
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)

class TaxDeadline(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    
    title = db.Column(db.String(100), nullable=False) # e.g., "PAYE Remittance"
    due_date = db.Column(db.Date, nullable=False)
    is_completed = db.Column(db.Boolean, default=False)
    description = db.Column(db.String(200), nullable=True)

class WHTCredit(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    
    amount = db.Column(db.Float, nullable=False)
    payer_name = db.Column(db.String(100), nullable=True) # Who deducted it?
    description = db.Column(db.String(200), nullable=True)
    date_received = db.Column(db.Date, default=datetime.utcnow)
    
    # Evidence
    document_id = db.Column(db.Integer, db.ForeignKey('document.id'), nullable=True)
    
    is_utilized = db.Column(db.Boolean, default=False) # Has it been used to offset tax?
    is_final_tax = db.Column(db.Boolean, default=False) # If True, cannot be used to offset other taxes.

class Debtor(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), nullable=True)
    phone = db.Column(db.String(20), nullable=True)
    
    # Relationship
    invoices = db.relationship('Invoice', backref='debtor', lazy=True)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class InvoiceStatus(enum.Enum):
    DRAFT = "Draft"
    SENT = "Sent"
    PAID = "Paid"
    OVERDUE = "Overdue"

class Invoice(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    debtor_id = db.Column(db.Integer, db.ForeignKey('debtor.id'), nullable=False)
    
    invoice_number = db.Column(db.String(50), nullable=False) # e.g. INV-001
    date_issued = db.Column(db.Date, default=datetime.utcnow)
    due_date = db.Column(db.Date, nullable=False)
    
    status = db.Column(db.Enum(InvoiceStatus), default=InvoiceStatus.DRAFT)
    
    total_amount = db.Column(db.Float, default=0.0)
    
    items = db.relationship('InvoiceItem', backref='invoice', lazy=True, cascade="all, delete-orphan")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class InvoiceItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    invoice_id = db.Column(db.Integer, db.ForeignKey('invoice.id'), nullable=False)
    
    description = db.Column(db.String(200), nullable=False)
    quantity = db.Column(db.Integer, default=1)
    unit_price = db.Column(db.Float, nullable=False)
    amount = db.Column(db.Float, nullable=False) # Qty * Price

class SavingsGoal(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    
    name = db.Column(db.String(100), nullable=False)
    target_amount = db.Column(db.Float, nullable=False)
    current_amount = db.Column(db.Float, default=0.0)
    deadline = db.Column(db.Date, nullable=True)
    
    is_achieved = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

