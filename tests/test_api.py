# Tests that go through the whole app like a real client would.
# Run with:  pytest -q
import os

os.environ["DATABASE_URL"] = "sqlite:///./test.db"  # use a separate db for tests (set before importing the app!)

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.auth import hash_password
from app.database import Base, SessionLocal, engine, utc_now
from main import app
from app.models import Booking, User

client = TestClient(app)
API = "/api/v1"


@pytest.fixture(autouse=True)
def fresh_db():
    # wipe and recreate all tables before every test
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield


def make_user(email, role):
    db = SessionLocal()
    db.add(User(email=email, full_name=email.split("@")[0], hashed_password=hash_password("password123"), role=role))
    db.commit()
    db.close()


def login(email):
    r = client.post(f"{API}/auth/login", data={"username": email, "password": "password123"})
    assert r.status_code == 200, r.text
    return {"Authorization": "Bearer " + r.json()["access_token"]}


def setup_data():
    """Creates admin, operator, customer, 3 cities, a route, a 4 seat bus and a trip in 2 days."""
    make_user("admin@test.io", "admin")
    admin = login("admin@test.io")

    # operator signs up as a normal user and then the admin promotes them
    r = client.post(f"{API}/auth/register", json={"email": "op@test.io", "full_name": "Op", "password": "password123"})
    assert r.status_code == 201
    op_id = r.json()["id"]
    r = client.patch(f"{API}/users/{op_id}/role", json={"role": "operator"}, headers=admin)
    assert r.status_code == 200 and r.json()["role"] == "operator"
    op = login("op@test.io")

    client.post(f"{API}/auth/register", json={"email": "cust@test.io", "full_name": "Cust", "password": "password123"})
    cust = login("cust@test.io")

    loc_ids = []
    for name, city in [("Kashmere Gate ISBT", "Delhi"), ("Sindhi Camp", "Jaipur"), ("Bani Park", "Ajmer")]:
        r = client.post(f"{API}/locations", json={"name": name, "city": city}, headers=admin)
        assert r.status_code == 201, r.text
        loc_ids.append(r.json()["id"])

    r = client.post(f"{API}/routes", headers=admin, json={
        "name": "Delhi - Jaipur - Ajmer", "distance_km": 400,
        "stops": [{"location_id": loc_ids[0], "minutes_from_origin": 0},
                  {"location_id": loc_ids[1], "minutes_from_origin": 300},
                  {"location_id": loc_ids[2], "minutes_from_origin": 420}],
    })
    assert r.status_code == 201, r.text
    route = r.json()

    r = client.post(f"{API}/operators", headers=admin, json={"name": "Royal Travels", "owner_user_id": op_id})
    assert r.status_code == 201, r.text
    operator = r.json()

    r = client.post(f"{API}/operators/{operator['id']}/buses", headers=op,
                    json={"registration_number": "rj14ab1234", "bus_type": "ac_seater", "total_seats": 4})
    assert r.status_code == 201, r.text
    bus = r.json()

    dep = (datetime.now(timezone.utc) + timedelta(days=2)).replace(hour=15, minute=30, second=0, microsecond=0)
    r = client.post(f"{API}/trips", headers=op, json={
        "route_id": route["id"], "bus_id": bus["id"],
        "departure_time": dep.isoformat(), "arrival_time": (dep + timedelta(minutes=420)).isoformat(),
        "base_fare": "800.00", "window_premium": "50.00",
    })
    assert r.status_code == 201, r.text
    trip = r.json()

    return {"admin": admin, "op": op, "cust": cust, "route": route, "operator": operator,
            "bus": bus, "trip": trip, "dep": dep}


def get_seats(trip_id):
    r = client.get(f"{API}/trips/{trip_id}/seats")
    assert r.status_code == 200
    return r.json()


def book(d, seat_ids):
    stops = d["route"]["stops"]
    return client.post(f"{API}/bookings", headers=d["cust"], json={
        "trip_id": d["trip"]["id"],
        "boarding_stop_id": stops[0]["id"],
        "dropping_stop_id": stops[1]["id"],
        "passengers": [{"trip_seat_id": s, "name": f"P{s}", "age": 30, "gender": "female"} for s in seat_ids],
    })


def test_health_and_me():
    assert client.get("/health").json() == {"status": "ok"}
    d = setup_data()
    assert client.get(f"{API}/users/me", headers=d["cust"]).json()["email"] == "cust@test.io"


def test_register_duplicate_email_and_bad_login():
    client.post(f"{API}/auth/register", json={"email": "a@test.io", "full_name": "A", "password": "password123"})
    r = client.post(f"{API}/auth/register", json={"email": "a@test.io", "full_name": "A", "password": "password123"})
    assert r.status_code == 409
    r = client.post(f"{API}/auth/login", data={"username": "a@test.io", "password": "wrongpass"})
    assert r.status_code == 401


def test_read_endpoints_for_master_data():
    d = setup_data()
    assert len(client.get(f"{API}/locations").json()) == 3
    assert len(client.get(f"{API}/locations", params={"city": "jaipur"}).json()) == 1
    assert len(client.get(f"{API}/routes").json()) == 1
    assert len(client.get(f"{API}/routes/{d['route']['id']}").json()["stops"]) == 3
    assert client.get(f"{API}/operators/{d['operator']['id']}", headers=d["cust"]).json()["name"] == "Royal Travels"
    assert len(client.get(f"{API}/operators/{d['operator']['id']}/buses", headers=d["op"]).json()) == 1
    bus = client.get(f"{API}/buses/{d['bus']['id']}").json()
    assert bus["registration_number"] == "RJ14AB1234" and len(bus["seats"]) == 4

    trip = client.get(f"{API}/trips/{d['trip']['id']}").json()
    assert trip["available_seats"] == 4
    assert trip["route"]["name"] == "Delhi - Jaipur - Ajmer"


def test_search():
    d = setup_data()
    local_date = (d["dep"] + timedelta(minutes=330)).date().isoformat()
    r = client.get(f"{API}/trips/search", params={"origin": "delhi", "destination": "Jaipur", "date": local_date})
    assert r.status_code == 200, r.text
    results = r.json()
    assert len(results) == 1
    assert results[0]["duration_minutes"] == 300
    assert results[0]["available_seats"] == 4
    assert Decimal(results[0]["starting_fare"]) == Decimal("800.00")

    # wrong direction shouldn't find anything
    r = client.get(f"{API}/trips/search", params={"origin": "Jaipur", "destination": "Delhi", "date": local_date})
    assert r.json() == []


def test_full_booking_flow():
    d = setup_data()
    seats = get_seats(d["trip"]["id"])
    window = [s for s in seats if s["position"] == "window"][0]
    aisle = [s for s in seats if s["position"] == "aisle"][0]

    r = book(d, [window["trip_seat_id"], aisle["trip_seat_id"]])
    assert r.status_code == 201, r.text
    booking = r.json()
    assert booking["status"] == "pending"
    assert Decimal(booking["total_amount"]) == Decimal("1650.00")  # 850 window + 800 aisle

    # failed payment -> still pending
    r = client.post(f"{API}/bookings/{booking['id']}/payments",
                    headers={**d["cust"], "Idempotency-Key": "attempt-0001"}, json={"simulate_failure": True})
    assert r.status_code == 201 and r.json()["status"] == "pending"

    # good payment -> confirmed. sending the same key again shouldn't charge twice
    headers = {**d["cust"], "Idempotency-Key": "attempt-0002"}
    r = client.post(f"{API}/bookings/{booking['id']}/payments", headers=headers, json={})
    assert r.status_code == 201 and r.json()["status"] == "confirmed"
    r = client.post(f"{API}/bookings/{booking['id']}/payments", headers=headers, json={})
    assert r.status_code == 200
    successful_charges = [p for p in r.json()["payments"] if p["kind"] == "charge" and p["status"] == "success"]
    assert len(successful_charges) == 1

    statuses = {s["trip_seat_id"]: s["status"] for s in get_seats(d["trip"]["id"])}
    assert statuses[window["trip_seat_id"]] == "booked"

    # the other read endpoints
    assert client.get(f"{API}/bookings/{booking['id']}", headers=d["cust"]).status_code == 200
    assert client.get(f"{API}/bookings/pnr/{booking['pnr']}", headers=d["cust"]).status_code == 200
    assert len(client.get(f"{API}/bookings", headers=d["cust"]).json()) == 1
    manifest = client.get(f"{API}/trips/{d['trip']['id']}/manifest", headers=d["op"]).json()
    assert manifest[0]["pnr"] == booking["pnr"]

    # cancel 2 days before -> 90% refund and seats are free again
    r = client.post(f"{API}/bookings/{booking['id']}/cancel", headers=d["cust"])
    assert r.status_code == 200 and r.json()["status"] == "cancelled"
    refund = [p for p in r.json()["payments"] if p["kind"] == "refund"][0]
    assert Decimal(refund["amount"]) == Decimal("1485.00")
    assert all(s["status"] == "available" for s in get_seats(d["trip"]["id"]))


def test_no_double_booking():
    d = setup_data()
    seats = get_seats(d["trip"]["id"])
    first, second = seats[0]["trip_seat_id"], seats[1]["trip_seat_id"]
    assert book(d, [first]).status_code == 201
    assert book(d, [first]).status_code == 409
    # if one of the seats is taken, none of them should get booked
    assert book(d, [second, first]).status_code == 409
    assert get_seats(d["trip"]["id"])[1]["status"] == "available"


def test_unpaid_booking_expires():
    d = setup_data()
    seat = get_seats(d["trip"]["id"])[0]["trip_seat_id"]
    booking = book(d, [seat]).json()

    # pretend the 10 minutes have passed
    db = SessionLocal()
    db.query(Booking).filter(Booking.id == booking["id"]).update({"expires_at": utc_now() - timedelta(seconds=1)})
    db.commit()
    db.close()

    assert get_seats(d["trip"]["id"])[0]["status"] == "available"
    assert client.get(f"{API}/bookings/{booking['id']}", headers=d["cust"]).json()["status"] == "expired"
    r = client.post(f"{API}/bookings/{booking['id']}/payments",
                    headers={**d["cust"], "Idempotency-Key": "too-late-1"}, json={})
    assert r.status_code == 409
    assert book(d, [seat]).status_code == 201  # someone else can take it now


def test_permissions():
    d = setup_data()
    client.post(f"{API}/auth/register", json={"email": "other@test.io", "full_name": "O", "password": "password123"})
    other = login("other@test.io")
    booking = book(d, [get_seats(d["trip"]["id"])[0]["trip_seat_id"]]).json()

    assert client.get(f"{API}/bookings/{booking['id']}", headers=other).status_code == 403
    assert client.post(f"{API}/locations", json={"name": "x", "city": "y"}, headers=d["cust"]).status_code == 403
    assert client.post(f"{API}/trips/{d['trip']['id']}/cancel", headers=d["cust"]).status_code == 403
    assert client.get(f"{API}/users/me").status_code == 401


def test_bus_cant_be_on_two_trips_at_once():
    d = setup_data()
    dep = d["dep"] + timedelta(hours=2)
    r = client.post(f"{API}/trips", headers=d["op"], json={
        "route_id": d["route"]["id"], "bus_id": d["bus"]["id"],
        "departure_time": dep.isoformat(), "arrival_time": (dep + timedelta(hours=5)).isoformat(),
        "base_fare": "500",
    })
    assert r.status_code == 409


def test_cancel_trip_refunds_everyone():
    d = setup_data()
    seat = get_seats(d["trip"]["id"])[0]["trip_seat_id"]
    booking = book(d, [seat]).json()
    client.post(f"{API}/bookings/{booking['id']}/payments", headers={**d["cust"], "Idempotency-Key": "pay-12345"}, json={})

    r = client.post(f"{API}/trips/{d['trip']['id']}/cancel", headers=d["op"])
    assert r.status_code == 200 and r.json()["status"] == "cancelled"
    b = client.get(f"{API}/bookings/{booking['id']}", headers=d["cust"]).json()
    assert b["status"] == "cancelled"
    assert [Decimal(p["amount"]) for p in b["payments"] if p["kind"] == "refund"] == [Decimal("850.00")]
    assert book(d, [seat]).status_code == 409  # can't book a cancelled trip
