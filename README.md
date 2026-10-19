# Bus Ticket Booking API

Backend for a bus ticket booking app, built with **FastAPI** and **SQLAlchemy**.
You can search buses, pick seats, book, pay (fake gateway for now) and cancel with a refund.

## How I built it (step by step)

1. [Requirements](docs/01_requirements.md) - who uses it and what it needs to do
2. [Database](docs/02_database.md) - tables, ER diagram, why `trip_seats` exists
3. [API](docs/03_api.md) - all the endpoints with examples
4. [How booking works](docs/04_how_booking_works.md) - seat holds, payments, and how double booking is prevented

## Project structure

```
bus_ticket_booking/
├── main.py            # creates the app and plugs in the routers
├── app/
│   ├── auth.py         # password hashing, JWT, get_current_user, check_role
│   ├── config.py       # settings
│   ├── create_admin.py # script to make the first admin
│   ├── database.py     # db engine, session, get_db()
│   ├── models.py       # all the tables
│   ├── schemas.py      # pydantic request/response models
│   └── utils.py        # helpers: PNR generator, expiring old bookings, etc
├── routers/
│   ├── users.py        # register, login, me, change role
│   ├── locations.py    # bus stands + routes
│   ├── operators.py    # bus companies + buses
│   ├── trips.py        # schedule, search, seat map, cancel trip
│   └── bookings.py     # book, pay, cancel
├── tests/test_api.py
├── .env                # local settings
└── requirements.txt
```

## Running it

```bash
python -m venv .venv
.venv\Scripts\activate          # on mac/linux: source .venv/bin/activate
pip install -r requirements.txt
python create_admin.py admin@example.com ChangeMe123
uvicorn main:app --reload
```

Then open http://127.0.0.1:8000/docs, click **Authorize** and log in as the admin.

Change the settings in `.env` (database URL, secret key, how long seats are held, refund % ...).
**Change `SECRET_KEY` before deploying anywhere!**

## Trying the whole flow

1. Register a user for the bus company, then as admin call `PATCH /users/{id}/role` with `{"role": "operator"}`
2. Admin: add some `/locations`, a `/routes` with the stops in order, and an `/operators` company
3. Operator: add a bus (`POST /operators/{id}/buses` with `total_seats: 40`), then `POST /trips`
4. Customer: register -> `GET /trips/search` -> `GET /trips/{id}/seats` -> `POST /bookings` -> `POST /bookings/{id}/payments`