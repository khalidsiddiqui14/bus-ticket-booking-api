from sqlalchemy import (
    JSON, Boolean, Column, DateTime, Float, ForeignKey, Integer, Numeric, String, UniqueConstraint
)
from sqlalchemy.orm import relationship
from app.database import Base, utc_now

# Status values used around the app (just strings to keep it simple):
#   user.role:        customer / operator / admin
#   trip.status:      scheduled / cancelled
#   trip_seat.status: available / held / booked
#   booking.status:   pending / confirmed / cancelled / expired
#   payment.kind:     charge / refund     payment.status: initiated / success / failed


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    full_name = Column(String(120), nullable=False)
    phone = Column(String(20))
    hashed_password = Column(String(255), nullable=False)
    role = Column(String(20), default="customer", nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=utc_now)


class Operator(Base):
    __tablename__ = "operators"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(120), unique=True, nullable=False)
    contact_email = Column(String(255))
    contact_phone = Column(String(20))
    owner_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=utc_now)

    buses = relationship("Bus", back_populates="operator")


class Bus(Base):
    __tablename__ = "buses"

    id = Column(Integer, primary_key=True, index=True)
    operator_id = Column(Integer, ForeignKey("operators.id"), nullable=False, index=True)
    registration_number = Column(String(20), unique=True, nullable=False)
    bus_type = Column(String(20), nullable=False)  # seater, sleeper, ac_seater, ac_sleeper
    total_seats = Column(Integer, nullable=False)
    amenities = Column(JSON, default=list)
    created_at = Column(DateTime, default=utc_now)

    operator = relationship("Operator", back_populates="buses")
    seats = relationship("Seat", back_populates="bus", cascade="all, delete-orphan", order_by="Seat.id")


class Seat(Base):
    __tablename__ = "seats"
    __table_args__ = (UniqueConstraint("bus_id", "seat_number"),)

    id = Column(Integer, primary_key=True, index=True)
    bus_id = Column(Integer, ForeignKey("buses.id"), nullable=False)
    seat_number = Column(String(10), nullable=False)
    deck = Column(String(10), default="lower")  # lower / upper
    position = Column(String(10), nullable=False)  # window / aisle / middle
    row_no = Column(Integer, nullable=False)
    col_no = Column(Integer, nullable=False)

    bus = relationship("Bus", back_populates="seats")


class Location(Base):
    __tablename__ = "locations"
    __table_args__ = (UniqueConstraint("name", "city"),)

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(120), nullable=False) 
    city = Column(String(80), nullable=False, index=True)
    state = Column(String(80))


class Route(Base):
    __tablename__ = "routes"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(160), nullable=False)
    distance_km = Column(Float)

    stops = relationship("RouteStop", back_populates="route", cascade="all, delete-orphan",
                         order_by="RouteStop.stop_order")


class RouteStop(Base):
    # stop_order 0 = starting point, the highest one = final destination
    __tablename__ = "route_stops"
    __table_args__ = (
        UniqueConstraint("route_id", "stop_order"),
        UniqueConstraint("route_id", "location_id"),
    )

    id = Column(Integer, primary_key=True, index=True)
    route_id = Column(Integer, ForeignKey("routes.id"), nullable=False, index=True)
    location_id = Column(Integer, ForeignKey("locations.id"), nullable=False, index=True)
    stop_order = Column(Integer, nullable=False)
    minutes_from_origin = Column(Integer, default=0)  # used to work out the time at each stop

    route = relationship("Route", back_populates="stops")
    location = relationship("Location")


class Trip(Base):
    __tablename__ = "trips"

    id = Column(Integer, primary_key=True, index=True)
    route_id = Column(Integer, ForeignKey("routes.id"), nullable=False, index=True)
    bus_id = Column(Integer, ForeignKey("buses.id"), nullable=False, index=True)
    departure_time = Column(DateTime, nullable=False, index=True)
    arrival_time = Column(DateTime, nullable=False)
    base_fare = Column(Numeric(10, 2), nullable=False)  # Numeric
    status = Column(String(20), default="scheduled")
    created_at = Column(DateTime, default=utc_now)

    route = relationship("Route")
    bus = relationship("Bus")
    seats = relationship("TripSeat", back_populates="trip", cascade="all, delete-orphan", order_by="TripSeat.id")


class TripSeat(Base):
    # one row per seat per trip
    # the unique constraint makes sure a seat can only exist once on a trip
    __tablename__ = "trip_seats"
    __table_args__ = (UniqueConstraint("trip_id", "seat_id"),)

    id = Column(Integer, primary_key=True, index=True)
    trip_id = Column(Integer, ForeignKey("trips.id"), nullable=False, index=True)
    seat_id = Column(Integer, ForeignKey("seats.id"), nullable=False)
    price = Column(Numeric(10, 2), nullable=False)
    status = Column(String(20), default="available")
    booking_id = Column(Integer, ForeignKey("bookings.id"), nullable=True)

    trip = relationship("Trip", back_populates="seats")
    seat = relationship("Seat")


class Booking(Base):
    __tablename__ = "bookings"

    id = Column(Integer, primary_key=True, index=True)
    pnr = Column(String(10), unique=True, index=True, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    trip_id = Column(Integer, ForeignKey("trips.id"), nullable=False, index=True)
    status = Column(String(20), default="pending")
    total_amount = Column(Numeric(10, 2), nullable=False)
    expires_at = Column(DateTime)  # seats are held until this time, then released if not paid
    boarding_stop_id = Column(Integer, ForeignKey("route_stops.id"), nullable=False)
    dropping_stop_id = Column(Integer, ForeignKey("route_stops.id"), nullable=False)
    created_at = Column(DateTime, default=utc_now)
    cancelled_at = Column(DateTime)

    trip = relationship("Trip")
    passengers = relationship("Passenger", back_populates="booking", cascade="all, delete-orphan",
                              order_by="Passenger.id")
    payments = relationship("Payment", back_populates="booking", order_by="Payment.id")


class Passenger(Base):
    __tablename__ = "passengers"

    id = Column(Integer, primary_key=True, index=True)
    booking_id = Column(Integer, ForeignKey("bookings.id"), nullable=False, index=True)
    trip_seat_id = Column(Integer, ForeignKey("trip_seats.id"), nullable=False)
    name = Column(String(120), nullable=False)
    age = Column(Integer, nullable=False)
    gender = Column(String(10), nullable=False)

    booking = relationship("Booking", back_populates="passengers")
    trip_seat = relationship("TripSeat")


class Payment(Base):
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True, index=True)
    booking_id = Column(Integer, ForeignKey("bookings.id"), nullable=False, index=True)
    amount = Column(Numeric(10, 2), nullable=False)
    kind = Column(String(10), default="charge")
    status = Column(String(20), default="initiated")
    method = Column(String(30))
    idempotency_key = Column(String(64), unique=True, nullable=False)  # stops double charging on retries
    provider_ref = Column(String(64))
    created_at = Column(DateTime, default=utc_now)

    booking = relationship("Booking", back_populates="payments")