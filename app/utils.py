# Small helper functions used by more than one route file
import random
from datetime import timezone

from app.models import Booking, TripSeat
from app.database import utc_now

PNR_CHARS = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # left out 0/O and 1/I so people don't mix them up


def generate_pnr(db):
    while True:
        pnr = "".join(random.choice(PNR_CHARS) for _ in range(8))
        if not db.query(Booking).filter(Booking.pnr == pnr).first():
            return pnr


def to_utc(dt):
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def can_manage_operator(user, operator):
    # admins can manage everything, operators only their own company
    if user.role == "admin":
        return True
    return user.role == "operator" and operator.owner_user_id == user.id


def release_expired_bookings(db):
    #Pending bookings that weren't paid in time -> mark expired and free up their seats
    expired = db.query(Booking).filter(Booking.status == "pending", Booking.expires_at < utc_now()).all()
    for booking in expired:
        rows = (
            db.query(Booking)
            .filter(Booking.id == booking.id, Booking.status == "pending")
            .update({"status": "expired"}, synchronize_session=False)
        )
        if rows == 1:
            db.query(TripSeat).filter(TripSeat.booking_id == booking.id, TripSeat.status == "held").update(
                {"status": "available", "booking_id": None}, synchronize_session=False
            )
    if expired:
        db.commit()
        db.expire_all()  # so already-loaded objects pick up the new statuses


def booking_to_dict(booking):
    return {
        "id": booking.id,
        "pnr": booking.pnr,
        "trip_id": booking.trip_id,
        "status": booking.status,
        "total_amount": booking.total_amount,
        "expires_at": booking.expires_at if booking.status == "pending" else None,
        "boarding_stop_id": booking.boarding_stop_id,
        "dropping_stop_id": booking.dropping_stop_id,
        "created_at": booking.created_at,
        "cancelled_at": booking.cancelled_at,
        "passengers": [
            {
                "trip_seat_id": p.trip_seat_id,
                "seat_number": p.trip_seat.seat.seat_number,
                "name": p.name,
                "age": p.age,
                "gender": p.gender,
            }
            for p in booking.passengers
        ],
        "payments": booking.payments,
    }
