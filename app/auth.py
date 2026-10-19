from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

import app.config
from app.database import get_db
from app.models import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


def hash_password(password):
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password, hashed):
    return bcrypt.checkpw(password.encode(), hashed.encode())


def create_token(user):
    expire = datetime.now(timezone.utc) + timedelta(minutes=app.config.TOKEN_EXPIRE_MINUTES)
    data = {"sub": str(user.id), "role": user.role, "exp": expire}
    return jwt.encode(data, app.config.SECRET_KEY, algorithm=app.config.ALGORITHM)


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    try:
        payload = jwt.decode(token, app.config.SECRET_KEY, algorithms=[app.config.ALGORITHM])
        user_id = int(payload["sub"])
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token",
                            headers={"WWW-Authenticate": "Bearer"})

    # load the user from db every time so a deactivated user gets kicked out right away
    user = db.query(User).filter(User.id == user_id).first()
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="Invalid or expired token",
                            headers={"WWW-Authenticate": "Bearer"})
    return user


def check_role(user, *roles):
    if user.role not in roles:
        raise HTTPException(status_code=403, detail="You don't have permission to do this")
