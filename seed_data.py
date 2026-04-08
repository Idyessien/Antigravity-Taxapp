from app import app, db
from models import Category, CategoryTarget

def seed_categories():
    """
    Populate database with specific expense categories requested by User.
    This script adds them if they don't exist.
    """
    with app.app_context():
        # Clear existing categories to ensure strict alignment with user request
        num_deleted = Category.query.delete()
        db.session.commit()
        print(f"Cleared {num_deleted} existing categories.")

        # Exact list from User Request
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
            # --- Investment (System Only) ---
            # Replaced specific types with one generic category for automation
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
            # Check existence by name and target
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
        print(f"Done. Added {added_count} new categories.")

if __name__ == "__main__":
    seed_categories()
