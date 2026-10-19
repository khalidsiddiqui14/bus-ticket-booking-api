# Booking flow: hold seats -> pay -> confirmed. Or cancel.
import uuid
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Response
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import app.config
import app.schemas
from app.auth import get_current_user
from app.database import get_db, utc_now
from app.models import Booking, Passenger, Payment, RouteStop, Trip, TripSeat, User
from app.utils import booking_to_dict, generate_pnr, release_expired_bookings

router = APIRouter(prefix="/bookings", tags=["bookings & payments"])


def get_my_booking(db, user, booking_id):
    # fetch a booking and make sure the user is allowed to see it
    booking = db.query(Booking).filter(Booking.id == booking_id).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    if booking.user_id != user.id and user.role != "admin":
        raise HTTPException(status_code=403, detail="Not your booking")
    return booking


@router.post("", response_model=app.schemas.BookingOut, status_code=201)
def create_booking(data: app.schemas.BookingCreate, db: Session = Depends(get_db),
                   user: User = Depends(get_current_user)):
    if len(data.passengers) > app.config.MAX_SEATS_PER_BOOKING:
        raise HTTPException(status_code=422, detail=f"Max {app.config.MAX_SEATS_PER_BOOKING} seats per booking")
    seat_ids = [p.trip_seat_id for p in data.passengers]
    if len(seat_ids) != len(set(seat_ids)):
        raise HTTPException(status_code=422, detail="Same seat picked twice")

    release_expired_bookings(db)  # free up seats from unpaid bookings first

    trip = db.query(Trip).filter(Trip.id == data.trip_id).first()
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")
    if trip.status != "scheduled" or trip.departure_time <= utc_now():
        raise HTTPException(status_code=409, detail="This trip is not open for booking")

    boarding = db.query(RouteStop).filter(RouteStop.id == data.boarding_stop_id).first()
    dropping = db.query(RouteStop).filter(RouteStop.id == data.dropping_stop_id).first()
    if (not boarding or not dropping or boarding.route_id != trip.route_id
            or dropping.route_id != trip.route_id or boarding.stop_order >= dropping.stop_order):
        raise HTTPException(status_code=400, detail="Boarding/dropping stops are wrong for this trip")

    seats = db.query(TripSeat).filter(TripSeat.trip_id == trip.id, TripSeat.id.in_(seat_ids)).all()
    if len(seats) != len(seat_ids):
        raise HTTPException(status_code=400, detail="Some of those seats aren't on this trip")

    total = sum([s.price for s in seats], Decimal("0"))
    booking = Booking(
        pnr=generate_pnr(db),
        user_id=user.id,
        trip_id=trip.id,
        status="pending",
        total_amount=total,
        expires_at=utc_now() + timedelta(minutes=app.config.SEAT_HOLD_MINUTES),
        boarding_stop_id=boarding.id,
        dropping_stop_id=dropping.id,
    )
    for p in data.passengers:
        booking.passengers.append(Passenger(trip_seat_id=p.trip_seat_id, name=p.name, age=p.age, gender=p.gender))

    try:
        db.add(booking)
        db.flush()  # need booking.id for the next step

        # IMPORTANT: grab the seats with one UPDATE that only matches seats that are still
        # "available". If two people try to book the same seat at the same time, only one
        # update can match it - the other one gets fewer rows back and we reject it.
        # (checking status in python first and then saving would NOT be safe)
        updated = (
            db.query(TripSeat)
            .filter(TripSeat.id.in_(seat_ids), TripSeat.trip_id == trip.id, TripSeat.status == "available")
            .update({"status": "held", "booking_id": booking.id}, synchronize_session=False)
        )
        if updated != len(seat_ids):
            db.rollback()  # undoes the booking AND any seats we did grab
            raise HTTPException(status_code=409, detail="One or more seats are no longer available")

        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Could not create booking, please try again")

    db.refresh(booking)
    return booking_to_dict(booking)


@router.get("", response_model=list[app.schemas.BookingOut])
def my_bookings(status_filter: Optional[str] = None, db: Session = Depends(get_db),
                user: User = Depends(get_current_user)):
    release_expired_bookings(db)
    query = db.query(Booking).filter(Booking.user_id == user.id)
    if status_filter:
        query = query.filter(Booking.status == status_filter)
    return [booking_to_dict(b) for b in query.order_by(Booking.id.desc()).all()]


@router.get("/pnr/{pnr}", response_model=app.schemas.BookingOut)
def get_by_pnr(pnr: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    release_expired_bookings(db)
    booking = db.query(Booking).filter(Booking.pnr == pnr.upper()).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    if booking.user_id != user.id and user.role != "admin":
        raise HTTPException(status_code=403, detail="Not your booking")
    return booking_to_dict(booking)


@router.get("/{booking_id}", response_model=app.schemas.BookingOut)
def get_booking(booking_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    release_expired_bookings(db)
    return booking_to_dict(get_my_booking(db, user, booking_id))


@router.post("/{booking_id}/payments", response_model=app.schemas.BookingOut, status_code=201)
def pay_for_booking(booking_id: int, data: app.schemas.PaymentCreate, response: Response,
                    idempotency_key: str = Header(min_length=8, max_length=64),
                    db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    # The client sends a unique Idempotency-Key header per payment attempt. If the same key comes
    # in again (e.g. app retried after a timeout) we just return what happened the first time.
    existing = db.query(Payment).filter(Payment.idempotency_key == idempotency_key).first()
    if existing:
        if existing.booking_id != booking_id:
            raise HTTPException(status_code=409, detail="This Idempotency-Key was already used for another booking")
        response.status_code = 200
        return booking_to_dict(get_my_booking(db, user, booking_id))

    release_expired_bookings(db)
    booking = get_my_booking(db, user, booking_id)
    if booking.status != "pending":
        raise HTTPException(status_code=409, detail=f"Booking is {booking.status}, can't pay for it")

    payment = Payment(booking_id=booking.id, amount=booking.total_amount, kind="charge",
                      status="initiated", method=data.method, idempotency_key=idempotency_key)
    try:
        db.add(payment)
        db.flush()
    except IntegrityError:
        # two requests with the same key at the same time - the other one won, return that
        db.rollback()
        response.status_code = 200
        return booking_to_dict(get_my_booking(db, user, booking_id))

    # ---- fake payment gateway (swap this for Razorpay/Stripe later) ----
    if data.simulate_failure:
        payment.status = "failed"
        db.commit()
        db.refresh(booking)
        return booking_to_dict(booking)  # booking stays pending, user can try again
    payment.provider_ref = "MOCK-" + uuid.uuid4().hex[:16].upper()

    # confirm only if it's still pending and the hold hasn't run out
    rows = (
        db.query(Booking)
        .filter(Booking.id == booking.id, Booking.status == "pending", Booking.expires_at >= utc_now())
        .update({"status": "confirmed"}, synchronize_session=False)
    )
    if rows != 1:
        db.rollback()
        raise HTTPException(status_code=409, detail="Seat hold expired before the payment went through")

    db.query(TripSeat).filter(TripSeat.booking_id == booking.id, TripSeat.status == "held") \
        .update({"status": "booked"}, synchronize_session=False)
    payment.status = "success"
    db.commit()
    db.refresh(booking)
    return booking_to_dict(booking)


@router.post("/{booking_id}/cancel", response_model=app.schemas.BookingOut)
def cancel_booking(booking_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    release_expired_bookings(db)
    booking = get_my_booking(db, user, booking_id)
    if booking.status not in ("pending", "confirmed"):
        raise HTTPException(status_code=409, detail=f"Booking is already {booking.status}")
    if booking.trip.departure_time <= utc_now():
        raise HTTPException(status_code=409, detail="Can't cancel after the bus has left")

    old_status = booking.status
    # same trick as payments - only update if nobody changed it in the meantime
    rows = (
        db.query(Booking)
        .filter(Booking.id == booking.id, Booking.status == old_status)
        .update({"status": "cancelled", "cancelled_at": utc_now()}, synchronize_session=False)
    )
    if rows != 1:
        db.rollback()
        raise HTTPException(status_code=409, detail="Booking changed while cancelling, try again")

    # give the seats back
    db.query(TripSeat).filter(TripSeat.booking_id == booking.id) \
        .update({"status": "available", "booking_id": None}, synchronize_session=False)

    # refund only if they actually paid
    if old_status == "confirmed":
        hours_left = (booking.trip.departure_time - utc_now()).total_seconds() / 3600
        if hours_left >= app.config.FREE_CANCEL_HOURS:
            percent = app.config.REFUND_PERCENT_EARLY
        else:
            percent = app.config.REFUND_PERCENT_LATE
        refund = (booking.total_amount * percent / 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        db.add(Payment(booking_id=booking.id, amount=refund, kind="refund", status="success",
                       method="original", idempotency_key=f"refund-{booking.id}"))

    db.commit()
    db.refresh(booking)
    return booking_to_dict(booking)
