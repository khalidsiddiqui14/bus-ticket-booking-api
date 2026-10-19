from datetime import datetime
from decimal import Decimal
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field


# ---------- users ----------

class UserCreate(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=1, max_length=120)
    phone: Optional[str] = None
    password: str = Field(min_length=8, max_length=72)  # bcrypt only looks at 72 bytes anyway


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    full_name: str
    phone: Optional[str]
    role: str
    is_active: bool


class RoleUpdate(BaseModel):
    role: Literal["customer", "operator", "admin"]


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


# ---------- locations & routes ----------

class LocationCreate(BaseModel):
    name: str = Field(min_length=1)
    city: str = Field(min_length=1)
    state: Optional[str] = None


class LocationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    city: str
    state: Optional[str]


class RouteStopIn(BaseModel):
    location_id: int
    minutes_from_origin: int = Field(ge=0)


class RouteCreate(BaseModel):
    name: str = Field(min_length=1)
    distance_km: Optional[float] = None
    stops: List[RouteStopIn]  # in order, first one is the origin


class RouteStopOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    stop_order: int
    minutes_from_origin: int
    location: LocationOut


class RouteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    distance_km: Optional[float]
    stops: List[RouteStopOut]


# ---------- operators & buses ----------

class OperatorCreate(BaseModel):
    name: str = Field(min_length=1)
    contact_email: Optional[EmailStr] = None
    contact_phone: Optional[str] = None
    owner_user_id: int


class OperatorOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    contact_email: Optional[str]
    contact_phone: Optional[str]
    owner_user_id: int


class SeatIn(BaseModel):
    seat_number: str
    deck: Literal["lower", "upper"] = "lower"
    position: Literal["window", "aisle", "middle"]
    row_no: int
    col_no: int


class SeatOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    seat_number: str
    deck: str
    position: str
    row_no: int
    col_no: int


class BusCreate(BaseModel):
    registration_number: str = Field(min_length=3, max_length=20)
    bus_type: Literal["seater", "sleeper", "ac_seater", "ac_sleeper"]
    amenities: List[str] = []
    total_seats: Optional[int] = Field(default=None, gt=0, le=80)
    seats: Optional[List[SeatIn]] = None


class BusOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    operator_id: int
    registration_number: str
    bus_type: str
    total_seats: int
    amenities: List[str]


class BusDetail(BusOut):
    seats: List[SeatOut]


# ---------- trips ----------

class TripCreate(BaseModel):
    route_id: int
    bus_id: int
    departure_time: datetime
    arrival_time: datetime
    base_fare: Decimal = Field(ge=0)
    window_premium: Decimal = Field(default=Decimal("0"), ge=0)  # extra charge for window seats


class TripOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    route_id: int
    bus_id: int
    departure_time: datetime
    arrival_time: datetime
    base_fare: Decimal
    status: str


class TripDetail(TripOut):
    route: RouteOut
    available_seats: int


class SearchResult(BaseModel):
    trip_id: int
    operator_name: str
    bus_type: str
    amenities: List[str]
    route_name: str
    boarding_stop_id: int
    dropping_stop_id: int
    departure_time: datetime  # time when bus reaches the boarding stop
    arrival_time: datetime  # time when it reaches the dropping stop
    duration_minutes: int
    starting_fare: Decimal
    available_seats: int


class TripSeatOut(BaseModel):
    trip_seat_id: int
    seat_number: str
    deck: str
    position: str
    row_no: int
    col_no: int
    price: Decimal
    status: str


# ---------- bookings & payments ----------

class PassengerIn(BaseModel):
    trip_seat_id: int
    name: str = Field(min_length=1)
    age: int = Field(gt=0, lt=120)
    gender: Literal["male", "female", "other"]


class BookingCreate(BaseModel):
    trip_id: int
    boarding_stop_id: int
    dropping_stop_id: int
    passengers: List[PassengerIn] = Field(min_length=1)


class PassengerOut(BaseModel):
    trip_seat_id: int
    seat_number: str
    name: str
    age: int
    gender: str


class PaymentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    amount: Decimal
    kind: str
    status: str
    method: Optional[str]
    provider_ref: Optional[str]
    created_at: datetime


class BookingOut(BaseModel):
    id: int
    pnr: str
    trip_id: int
    status: str
    total_amount: Decimal
    expires_at: Optional[datetime]
    boarding_stop_id: int
    dropping_stop_id: int
    created_at: datetime
    cancelled_at: Optional[datetime]
    passengers: List[PassengerOut]
    payments: List[PaymentOut]


class PaymentCreate(BaseModel):
    method: str = "upi"
    simulate_failure: bool = False
