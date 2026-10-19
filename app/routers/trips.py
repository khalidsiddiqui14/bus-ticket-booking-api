from datetime import date, datetime, time, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

import app.config
import app.schemas
from app.auth import check_role, get_current_user
from app.database import get_db, utc_now
from app.models import Booking, Bus, Location, Payment, Route, RouteStop, Trip, TripSeat, User
from app.utils import booking_to_dict, can_manage_operator, release_expired_bookings, to_utc

router = APIRouter(prefix="/trips", tags=["trips"])


@router.post("", response_model=app.schemas.TripOut, status_code=201)
def create_trip(data: app.schemas.TripCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    check_role(user, "operator", "admin")

    bus = db.query(Bus).filter(Bus.id == data.bus_id).first()
    if not bus:
        raise HTTPException(status_code=404, detail="Bus not found")
    if not can_manage_operator(user, bus.operator):
        raise HTTPException(status_code=403, detail="This isn't your bus")
    if not db.query(Route).filter(Route.id == data.route_id).first():
        raise HTTPException(status_code=404, detail="Route not found")

    departure = to_utc(data.departure_time)
    arrival = to_utc(data.arrival_time)
    if arrival <= departure:
        raise HTTPException(status_code=422, detail="Arrival has to be after departure")
    if departure <= utc_now():
        raise HTTPException(status_code=400, detail="Departure time must be in the future")

    # same bus can't be on two trips at once
    clash = db.query(Trip).filter(
        Trip.bus_id == bus.id,
        Trip.status == "scheduled",
        Trip.departure_time < arrival,
        Trip.arrival_time > departure,
    ).first()
    if clash:
        raise HTTPException(status_code=409, detail=f"Bus is already on trip {clash.id} at that time")

    trip = Trip(route_id=data.route_id, bus_id=bus.id, departure_time=departure,
                arrival_time=arrival, base_fare=data.base_fare, status="scheduled")

    # copy every seat of the bus into trip_seats - these are what customers book
    for seat in bus.seats:
        price = data.base_fare
        if seat.position == "window":
            price = price + data.window_premium
        trip.seats.append(TripSeat(seat_id=seat.id, price=price, status="available"))

    db.add(trip)
    db.commit()
    db.refresh(trip)
    return trip


@router.get("/search", response_model=list[app.schemas.SearchResult])
def search_trips(origin: str = Query(min_length=1), destination: str = Query(min_length=1),
                 travel_date: date = Query(alias="date"), db: Session = Depends(get_db)):
    release_expired_bookings(db)

    # the date the user picks is a local date, so work out where that day starts/ends in UTC
    day_start = datetime.combine(travel_date, time.min) - timedelta(minutes=app.config.LOCAL_TIME_OFFSET_MINUTES)
    day_end = day_start + timedelta(days=1)

    results = []
    # 1) all stops in the origin city
    origin_stops = db.query(RouteStop).join(Location).filter(Location.city.ilike(origin)).all()
    for o_stop in origin_stops:
        # 2) does the same route reach the destination city AFTER this stop?
        d_stop = (
            db.query(RouteStop).join(Location)
            .filter(RouteStop.route_id == o_stop.route_id,
                    Location.city.ilike(destination),
                    RouteStop.stop_order > o_stop.stop_order)
            .first()
        )
        if not d_stop:
            continue

        # 3) trips on this route around that day. we look back 2 days because on long routes
        #    the bus might have left the day before it reaches this stop
        trips = db.query(Trip).filter(
            Trip.route_id == o_stop.route_id,
            Trip.status == "scheduled",
            Trip.departure_time >= day_start - timedelta(days=2),
            Trip.departure_time < day_end,
        ).all()

        for trip in trips:
            board_time = trip.departure_time + timedelta(minutes=o_stop.minutes_from_origin)
            if board_time < day_start or board_time >= day_end or board_time <= utc_now():
                continue
            available = db.query(TripSeat).filter(TripSeat.trip_id == trip.id,
                                                  TripSeat.status == "available").count()
            results.append({
                "trip_id": trip.id,
                "operator_name": trip.bus.operator.name,
                "bus_type": trip.bus.bus_type,
                "amenities": trip.bus.amenities or [],
                "route_name": trip.route.name,
                "boarding_stop_id": o_stop.id,
                "dropping_stop_id": d_stop.id,
                "departure_time": board_time,
                "arrival_time": trip.departure_time + timedelta(minutes=d_stop.minutes_from_origin),
                "duration_minutes": d_stop.minutes_from_origin - o_stop.minutes_from_origin,
                "starting_fare": min(s.price for s in trip.seats),
                "available_seats": available,
            })

    results.sort(key=lambda r: r["departure_time"])
    return results


@router.get("/{trip_id}", response_model=app.schemas.TripDetail)
def get_trip(trip_id: int, db: Session = Depends(get_db)):
    release_expired_bookings(db)
    trip = db.query(Trip).filter(Trip.id == trip_id).first()
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")
    available = db.query(TripSeat).filter(TripSeat.trip_id == trip.id, TripSeat.status == "available").count()
    return {
        "id": trip.id,
        "route_id": trip.route_id,
        "bus_id": trip.bus_id,
        "departure_time": trip.departure_time,
        "arrival_time": trip.arrival_time,
        "base_fare": trip.base_fare,
        "status": trip.status,
        "route": trip.route,
        "available_seats": available,
    }


@router.get("/{trip_id}/seats", response_model=list[app.schemas.TripSeatOut])
def get_seat_map(trip_id: int, db: Session = Depends(get_db)):
    release_expired_bookings(db)  # so seats from unpaid bookings show as free again
    trip = db.query(Trip).filter(Trip.id == trip_id).first()
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")

    seat_map = []
    for ts in trip.seats:
        seat_map.append({
            "trip_seat_id": ts.id,
            "seat_number": ts.seat.seat_number,
            "deck": ts.seat.deck,
            "position": ts.seat.position,
            "row_no": ts.seat.row_no,
            "col_no": ts.seat.col_no,
            "price": ts.price,
            "status": ts.status,
        })
    return seat_map


@router.post("/{trip_id}/cancel", response_model=app.schemas.TripOut)
def cancel_trip(trip_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    check_role(user, "operator", "admin")
    trip = db.query(Trip).filter(Trip.id == trip_id).first()
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")
    if not can_manage_operator(user, trip.bus.operator):
        raise HTTPException(status_code=403, detail="This isn't your trip")
    if trip.status != "scheduled":
        raise HTTPException(status_code=409, detail=f"Trip is already {trip.status}")

    try:
        trip.status = "cancelled"
        bookings = db.query(Booking).filter(Booking.trip_id == trip.id,
                                            Booking.status.in_(["pending", "confirmed"])).all()
        for booking in bookings:
            # our fault, not the customer's -> full refund for paid bookings
            if booking.status == "confirmed":
                db.add(Payment(booking_id=booking.id, amount=booking.total_amount, kind="refund",
                               status="success", method="original", idempotency_key=f"refund-{booking.id}"))
            booking.status = "cancelled"
            booking.cancelled_at = utc_now()

        for ts in trip.seats:
            ts.status = "available"
            ts.booking_id = None
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="Something went wrong cancelling the trip")

    db.refresh(trip)
    return trip


@router.get("/{trip_id}/manifest", response_model=list[app.schemas.BookingOut])
def get_manifest(trip_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    # list of confirmed passengers - the operator uses this for boarding
    check_role(user, "operator", "admin")
    trip = db.query(Trip).filter(Trip.id == trip_id).first()
    if not trip:
        raise HTTPException(status_code=404, detail="Trip not found")
    if not can_manage_operator(user, trip.bus.operator):
        raise HTTPException(status_code=403, detail="This isn't your trip")

    bookings = db.query(Booking).filter(Booking.trip_id == trip_id, Booking.status == "confirmed") \
        .order_by(Booking.id).all()
    return [booking_to_dict(b) for b in bookings]
