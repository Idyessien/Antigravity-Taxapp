from app import app, db
from models import User
import sys

def elevate_user(email):
    with app.app_context():
        user = User.query.filter_by(email=email).first()
        if not user:
            print(f"Error: User with email '{email}' not found.")
            print("Please ensure this user has successfully registered an account first.")
            return
        
        user.is_admin = True
        user.is_email_verified = True # Force verify their email automatically 
        db.session.commit()
        print("+" + "-"*50)
        print(f"| SUCCESS! ")
        print(f"| The account: {email}")
        print(f"| is now an Admin and has been completely verified.")
        print("+" + "-"*50)

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python make_admin.py <your_email>")
        print("Example: python make_admin.py john@example.com")
    else:
        elevate_user(sys.argv[1])
