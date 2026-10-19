from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import app.schemas
from app.auth import check_role, create_token, get_current_user, hash_password, verify_password
from app.database import get_db
from app.models import User

router = APIRouter(tags=["auth & users"])


@router.post("/auth/register", response_model=app.schemas.UserOut, status_code=201)
def register(data: app.schemas.UserCreate, db: Session = Depends(get_db)):
    # anyone who signs up is a customer. an admin can change the role later
    user = User(
        email=data.email.lower(),
        full_name=data.full_name,
        phone=data.phone,
        hashed_password=hash_password(data.password),
        role="customer",
    )
    try:
        db.add(user)
        db.commit()
        db.refresh(user)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Email already registered")
    return user


@router.post("/auth/login", response_model=app.schemas.Token)
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    # OAuth2 form sends the email in the "username" field
    user = db.query(User).filter(User.email == form.username.lower()).first()
    if not user or not verify_password(form.password, user.hashed_password) or not user.is_active:
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    return {"access_token": create_token(user), "token_type": "bearer"}


@router.get("/users/me", response_model=app.schemas.UserOut)
def get_me(user: User = Depends(get_current_user)):
    return user


@router.patch("/users/{user_id}/role", response_model=app.schemas.UserOut)
def change_role(user_id: int, data: app.schemas.RoleUpdate, db: Session = Depends(get_db),
                current_user: User = Depends(get_current_user)):
    check_role(current_user, "admin")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.role = data.role
    db.commit()
    db.refresh(user)
    return user
