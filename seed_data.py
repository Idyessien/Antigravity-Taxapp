from app import app, db
from models import Category, CategoryTarget, User, ProfileType, BankConnection, BankConnectionSyncStatus, CategorizationRule, AuditLog
from extensions import bcrypt
from datetime import datetime, timedelta

def seed_categories():
    """
    Populate database with categories and initial diagnostic seeds.
    """
    with app.app_context():
        # 1. Seed Expense Categories
        categories = [
            # --- Housing ---
            {"name": "Rent (Annual/Monthly)", "group": "Housing", "target": CategoryTarget.INDIVIDUAL},
            {"name": "Estate/Security Dues", "group": "Housing", "target": CategoryTarget.INDIVIDUAL},
            {"name": "Land Use Charge / Tenement Rate", "group": "Housing", "target": CategoryTarget.INDIVIDUAL},
            
            # --- Transportation ---
            {"name": "Petrol/Diesel (Vehicle)", "group": "Transportation", "target": CategoryTarget.INDIVIDUAL},
            {"name": "Public Transport (Danfo, BRT, Keke)", "group": "Transportation", "target": CategoryTarget.INDIVIDUAL},
            {"name": "Car license and Insurance", "group": "Transportation", "target": CategoryTarget.INDIVIDUAL},
            {"name": "Ride-Hailing (Uber, Bolt, Indrive etc)", "group": "Transportation", "target": CategoryTarget.INDIVIDUAL},
            {"name": "Vehicle Maintenance", "group": "Transportation", "target": CategoryTarget.INDIVIDUAL},
            
            # --- Utilities ---
            {"name": "Electricity", "group": "Utilities", "target": CategoryTarget.INDIVIDUAL},
            {"name": "Water", "group": "Utilities", "target": CategoryTarget.INDIVIDUAL},
            {"name": "Cooking Gas", "group": "Utilities", "target": CategoryTarget.INDIVIDUAL},
            {"name": "Cable TV/ Streaming", "group": "Utilities", "target": CategoryTarget.INDIVIDUAL},
            {"name": "Internet/ Data", "group": "Utilities", "target": CategoryTarget.INDIVIDUAL},
            
            # --- Household & Food ---
            {"name": "School Fees/Creche", "group": "Household & Food", "target": CategoryTarget.INDIVIDUAL},
            {"name": "Food", "group": "Household & Food", "target": CategoryTarget.INDIVIDUAL},
            {"name": "Clothing & Personal self care", "group": "Household & Food", "target": CategoryTarget.INDIVIDUAL},
            {"name": "Toiletries", "group": "Household & Food", "target": CategoryTarget.INDIVIDUAL},
            {"name": "Gifts", "group": "Household & Food", "target": CategoryTarget.INDIVIDUAL},
            {"name": "Tithe/Charity", "group": "Household & Food", "target": CategoryTarget.INDIVIDUAL},
            {"name": "Subscription Services (icloud, apps etc)", "group": "Household & Food", "target": CategoryTarget.INDIVIDUAL},
            {"name": "Gym Membership", "group": "Household & Food", "target": CategoryTarget.INDIVIDUAL},
            
            # --- Health & Medical ---
            {"name": "Health Insurance", "group": "Health & Medical", "target": CategoryTarget.INDIVIDUAL},
            {"name": "Medical Expenses (Prescriptions etc)", "group": "Health & Medical", "target": CategoryTarget.INDIVIDUAL},
            
            # --- Investment ---
            {"name": "Investments & Savings", "group": "Investment", "target": CategoryTarget.INDIVIDUAL},

            # --- BUSINESS CATEGORIES (Nigerian Context) ---
            # OpEx & Facility
            {"name": "Office Rent", "group": "Facility", "target": CategoryTarget.BUSINESS},
            {"name": "Diesel/Fuel (Generator/Vehicle)", "group": "Facility", "target": CategoryTarget.BUSINESS},
            {"name": "Electricity (Office)", "group": "Facility", "target": CategoryTarget.BUSINESS},
            {"name": "Internet/Data (Office)", "group": "Facility", "target": CategoryTarget.BUSINESS},
            {"name": "Office Supplies & Consumables", "group": "Facility", "target": CategoryTarget.BUSINESS},
            
            # HR
            {"name": "Salaries & Wages", "group": "HR", "target": CategoryTarget.BUSINESS},
            {"name": "Staff Training", "group": "HR", "target": CategoryTarget.BUSINESS},
            {"name": "Pension Contribution (Employer)", "group": "HR", "target": CategoryTarget.BUSINESS},
            
            # Compliance & Gov
            {"name": "CAC Filing Fees", "group": "Compliance", "target": CategoryTarget.BUSINESS},
            {"name": "FIRS/State Tax Payments", "group": "Compliance", "target": CategoryTarget.BUSINESS},
            {"name": "Levies & LG Charges", "group": "Compliance", "target": CategoryTarget.BUSINESS},
            
            # Operations
            {"name": "Marketing & Ads", "group": "Operations", "target": CategoryTarget.BUSINESS},
            {"name": "Logistics & Delivery", "group": "Operations", "target": CategoryTarget.BUSINESS},
            {"name": "Professional Services (Legal/Accounting)", "group": "Operations", "target": CategoryTarget.BUSINESS},
            {"name": "Bank Charges", "group": "Operations", "target": CategoryTarget.BUSINESS},
            {"name": "Software & Subscriptions", "group": "Operations", "target": CategoryTarget.BUSINESS},

            # --- CORPORATE SPECIFIC (Nigeria) ---
            {"name": "Directors' Remuneration / Fees", "group": "Governance", "target": CategoryTarget.BUSINESS},
            {"name": "Auditors' Remuneration", "group": "Governance", "target": CategoryTarget.BUSINESS},
            {"name": "Industrial Training Fund (ITF) Levy", "group": "Compliance", "target": CategoryTarget.BUSINESS},
            {"name": "NSITF Contribution", "group": "HR", "target": CategoryTarget.BUSINESS},
            {"name": "Corporate Social Responsibility (CSR)", "group": "Operations", "target": CategoryTarget.BUSINESS},
            {"name": "Expatriate Quota / immigration Fees", "group": "Compliance", "target": CategoryTarget.BUSINESS},
        ]
        
        print("Seeding Categories...")
        added_count = 0
        for cat_data in categories:
            existing = Category.query.filter_by(name=cat_data["name"], target_profile=cat_data["target"]).first()
            if not existing:
                cat = Category(
                    name=cat_data["name"],
                    group=cat_data["group"],
                    target_profile=cat_data["target"]
                )
                db.session.add(cat)
                added_count += 1
        db.session.commit()
        print(f"Categories seeded: {added_count} new.")

        # 2. Seed Master Admin Account
        admin_email = "idyessien101@gmail.com"
        master_admin = User.query.filter_by(email=admin_email).first()
        if not master_admin:
            pwd_hash = bcrypt.generate_password_hash("Admin2026!").decode('utf-8')
            master_admin = User(
                email=admin_email,
                password_hash=pwd_hash,
                profile_type=ProfileType.INDIVIDUAL,
                is_admin=True,
                admin_role="Admin",
                is_email_verified=True,
                is_pro=True
            )
            db.session.add(master_admin)
            db.session.commit()
            print(f"Created Master Admin user: {admin_email}")
        else:
            master_admin.is_admin = True
            master_admin.admin_role = "Admin"
            master_admin.is_email_verified = True
            db.session.commit()

        # 3. Seed Sample Bank Connections for Diagnostics
        if master_admin and not master_admin.bank_connections:
            banks = [
                {
                    "institution_name": "Guaranty Trust Bank (GTBank)",
                    "account_type": "Corporate Checking",
                    "account_mask": "4821",
                    "sync_status": BankConnectionSyncStatus.CONNECTED,
                    "error_message": None,
                    "provider": "Mono API",
                    "last_synced_at": datetime.utcnow()
                },
                {
                    "institution_name": "Zenith Bank Plc",
                    "account_type": "Savings",
                    "account_mask": "9014",
                    "sync_status": BankConnectionSyncStatus.REQUIRES_MFA,
                    "error_message": "MFA Session Expired. User hardware token re-auth required.",
                    "provider": "Plaid",
                    "last_synced_at": datetime.utcnow() - timedelta(hours=3)
                },
                {
                    "institution_name": "Access Bank",
                    "account_type": "Domiciliary (USD)",
                    "account_mask": "3109",
                    "sync_status": BankConnectionSyncStatus.SYNC_ERROR,
                    "error_message": "Institution connection timeout (HTTP 504 Gateway Error).",
                    "provider": "Mono API",
                    "last_synced_at": datetime.utcnow() - timedelta(days=1)
                },
                {
                    "institution_name": "Chase Bank NA",
                    "account_type": "Business Platinum",
                    "account_mask": "7720",
                    "sync_status": BankConnectionSyncStatus.CONNECTED,
                    "error_message": None,
                    "provider": "Plaid Sandbox",
                    "last_synced_at": datetime.utcnow() - timedelta(minutes=15)
                }
            ]
            for b in banks:
                conn = BankConnection(
                    user_id=master_admin.id,
                    institution_name=b["institution_name"],
                    account_type=b["account_type"],
                    account_mask=b["account_mask"],
                    sync_status=b["sync_status"],
                    error_message=b["error_message"],
                    api_provider=b["provider"],
                    last_synced_at=b["last_synced_at"]
                )
                db.session.add(conn)
            db.session.commit()
            print("Seeded diagnostic bank connections.")

        # 4. Seed Custom Categorization Rules
        if CategorizationRule.query.count() == 0:
            software_cat = Category.query.filter_by(name="Software & Subscriptions").first()
            ride_cat = Category.query.filter_by(name="Ride-Hailing (Uber, Bolt, Indrive etc)").first()
            fuel_cat = Category.query.filter_by(name="Petrol/Diesel (Vehicle)").first()
            food_cat = Category.query.filter_by(name="Food").first()
            
            rules = [
                {"keyword": "Uber", "cat_id": ride_cat.id if ride_cat else 1, "matches": 14},
                {"keyword": "Bolt", "cat_id": ride_cat.id if ride_cat else 1, "matches": 8},
                {"keyword": "AWS Cloud", "cat_id": software_cat.id if software_cat else 1, "matches": 5},
                {"keyword": "GitHub", "cat_id": software_cat.id if software_cat else 1, "matches": 3},
                {"keyword": "TotalEnergies Fuel", "cat_id": fuel_cat.id if fuel_cat else 1, "matches": 22},
                {"keyword": "Shoprite Supermarket", "cat_id": food_cat.id if food_cat else 1, "matches": 31},
            ]
            for r in rules:
                crule = CategorizationRule(
                    keyword=r["keyword"],
                    category_id=r["cat_id"],
                    match_count=r["matches"],
                    is_active=True
                )
                db.session.add(crule)
            db.session.commit()
            print("Seeded custom categorization rules.")

        # 5. Seed Initial Audit Logs
        if AuditLog.query.count() == 0:
            initial_logs = [
                {
                    "action": "SYSTEM_INIT",
                    "details": "Initialized Admin Control Center modules & diagnostic ledger",
                    "target_email": None,
                    "time": datetime.utcnow() - timedelta(hours=5)
                },
                {
                    "action": "SYNC_RETRY",
                    "details": "Triggered Plaid/Mono health diagnostics handshake",
                    "target_email": "idyessien101@gmail.com",
                    "time": datetime.utcnow() - timedelta(hours=2)
                },
                {
                    "action": "RULE_CREATE",
                    "details": "Created automated keyword rules for transit & cloud expenses",
                    "target_email": None,
                    "time": datetime.utcnow() - timedelta(minutes=45)
                }
            ]
            for l in initial_logs:
                alog = AuditLog(
                    admin_id=master_admin.id if master_admin else 1,
                    admin_email=admin_email,
                    admin_role="Admin",
                    action=l["action"],
                    target_user_email=l["target_email"],
                    details=l["details"],
                    ip_address="127.0.0.1",
                    timestamp=l["time"]
                )
                db.session.add(alog)
            db.session.commit()
            print("Seeded initial audit logs.")

if __name__ == "__main__":
    seed_categories()
