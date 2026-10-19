# To make the first admin account
# python create_admin.py admin@example.com MyPassword123
import sys

import app.models as models 
from auth import hash_password
from database import Base, SessionLocal, engine
from app.models import User

if len(sys.argv) < 3:
    print("usage: python create_admin.py <email> <password> [full name]")
    sys.exit(1)

email = sys.argv[1].lower()
password = sys.argv[2]
name = sys.argv[3] if len(sys.argv) > 3 else "Admin"

Base.metadata.create_all(bind=engine)
db = SessionLocal()

user = db.query(User).filter(User.email == email).first()
if user:
    user.role = "admin"
    print(f"{email} already existed, made them admin")
else:
    db.add(User(email=email, full_name=name, hashed_password=hash_password(password), role="admin"))
    print(f"created admin {email}")

db.commit()
db.close()
