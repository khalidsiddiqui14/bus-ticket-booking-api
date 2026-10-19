# Bus operators (companies) and their buses
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import app.schemas
from app.auth import check_role, get_current_user
from app.database import get_db
from app.models import Bus, Operator, Seat, User
from app.utils import can_manage_operator

router = APIRouter(tags=["operators & buses"])


@router.post("/operators", response_model=app.schemas.OperatorOut, status_code=201)
def create_operator(data: app.schemas.OperatorCreate, db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)):
    check_role(user, "admin")

    owner = db.query(User).filter(User.id == data.owner_user_id).first()
    if not owner:
        raise HTTPException(status_code=404, detail="Owner user not found")
    if owner.role != "operator":
        raise HTTPException(status_code=400, detail="Owner must have the 'operator' role")

    operator = Operator(name=data.name, contact_email=data.contact_email,
                        contact_phone=data.contact_phone, owner_user_id=owner.id)
    try:
        db.add(operator)
        db.commit()
        db.refresh(operator)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Operator name already taken")
    return operator


@router.get("/operators/{operator_id}", response_model=app.schemas.OperatorOut)
def get_operator(operator_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    operator = db.query(Operator).filter(Operator.id == operator_id).first()
    if not operator:
        raise HTTPException(status_code=404, detail="Operator not found")
    return operator


@router.post("/operators/{operator_id}/buses", response_model=app.schemas.BusDetail, status_code=201)
def add_bus(operator_id: int, data: app.schemas.BusCreate, db: Session = Depends(get_db),
            user: User = Depends(get_current_user)):
    check_role(user, "operator", "admin")
    operator = db.query(Operator).filter(Operator.id == operator_id).first()
    if not operator:
        raise HTTPException(status_code=404, detail="Operator not found")
    if not can_manage_operator(user, operator):
        raise HTTPException(status_code=403, detail="This isn't your operator")

    seats = []
    if data.seats:
        # custom layout sent by the client
        numbers = [s.seat_number for s in data.seats]
        if len(numbers) != len(set(numbers)):
            raise HTTPException(status_code=422, detail="Seat numbers must be unique")
        for s in data.seats:
            seats.append(Seat(seat_number=s.seat_number, deck=s.deck, position=s.position,
                              row_no=s.row_no, col_no=s.col_no))
    elif data.total_seats:
        # no layout given -> make a normal 2+2 bus. columns 0 and 3 are the window seats
        for i in range(data.total_seats):
            row = i // 4
            col = i % 4
            position = "window" if col in (0, 3) else "aisle"
            seats.append(Seat(seat_number=str(i + 1), deck="lower", position=position, row_no=row, col_no=col))
    else:
        raise HTTPException(status_code=422, detail="Send either total_seats or a seats list")

    bus = Bus(
        operator_id=operator.id,
        registration_number=data.registration_number.upper(),
        bus_type=data.bus_type,
        amenities=data.amenities,
        total_seats=len(seats),
        seats=seats,
    )
    try:
        db.add(bus)
        db.commit()
        db.refresh(bus)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="A bus with this registration number already exists")
    return bus


@router.get("/operators/{operator_id}/buses", response_model=list[app.schemas.BusOut])
def list_buses(operator_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    check_role(user, "operator", "admin")
    operator = db.query(Operator).filter(Operator.id == operator_id).first()
    if not operator:
        raise HTTPException(status_code=404, detail="Operator not found")
    if not can_manage_operator(user, operator):
        raise HTTPException(status_code=403, detail="This isn't your operator")
    return db.query(Bus).filter(Bus.operator_id == operator_id).order_by(Bus.id).all()


@router.get("/buses/{bus_id}", response_model=app.schemas.BusDetail)
def get_bus(bus_id: int, db: Session = Depends(get_db)):
    bus = db.query(Bus).filter(Bus.id == bus_id).first()
    if not bus:
        raise HTTPException(status_code=404, detail="Bus not found")
    return bus
