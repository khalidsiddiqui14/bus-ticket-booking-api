# Step 3 - API endpoints

Everything is under `/api/`. Swagger docs at http://127.0.0.1:8000/docs once the server is running.

Auth: log in with `POST /auth/login` (form fields `username` = email, `password`), then send
`Authorization: Bearer <token>` on the other requests. In Swagger just click **Authorize**.

Errors come back as `{"detail": "..."}` with the usual codes: 400 bad request, 401 not logged in,
403 not allowed, 404 not found, 409 conflict (seat taken, wrong status etc), 422 validation error.

## Users (`routers/users.py`)
| Method | URL | Who | What |
|---|---|---|---|
| POST | `/auth/register` | anyone | sign up (always as customer) |
| POST | `/auth/login` | anyone | get a token |
| GET | `/users/me` | logged in | your profile |
| PATCH | `/users/{id}/role` | admin | change someone's role |

## Locations & routes (`routers/locations.py`)
| Method | URL | Who | What |
|---|---|---|---|
| POST | `/locations` | admin | add a bus stand |
| GET | `/locations?city=` | anyone | list bus stands |
| POST | `/routes` | admin | add a route with its stops in order |
| GET | `/routes` and `/routes/{id}` | anyone | see routes |

## Operators & buses (`routers/operators.py`)
| Method | URL | Who | What |
|---|---|---|---|
| POST | `/operators` | admin | add a bus company |
| GET | `/operators/{id}` | logged in | company details |
| POST | `/operators/{id}/buses` | that operator / admin | add a bus. Send `total_seats` for an automatic 2+2 layout or a `seats` list |
| GET | `/operators/{id}/buses` | that operator / admin | list their buses |
| GET | `/buses/{id}` | anyone | bus with its seats |

## Trips (`routers/trips.py`)
| Method | URL | Who | What |
|---|---|---|---|
| POST | `/trips` | operator / admin | schedule a trip (won't let one bus do two trips at the same time) |
| GET | `/trips/search?origin=Delhi&destination=Jaipur&date=2026-11-01` | anyone | search |
| GET | `/trips/{id}` | anyone | trip details + free seats count |
| GET | `/trips/{id}/seats` | anyone | seat map |
| POST | `/trips/{id}/cancel` | operator / admin | cancel the trip, refund everyone |
| GET | `/trips/{id}/manifest` | operator / admin | passenger list for boarding |

## Bookings (`routers/bookings.py`)
| Method | URL | Who | What |
|---|---|---|---|
| POST | `/bookings` | logged in | hold seats, booking is `pending` for 10 min |
| GET | `/bookings` | logged in | my bookings |
| GET | `/bookings/{id}` | owner / admin | one booking |
| GET | `/bookings/pnr/{pnr}` | owner / admin | find by PNR |
| POST | `/bookings/{id}/payments` | owner | pay. Needs an `Idempotency-Key` header |
| POST | `/bookings/{id}/cancel` | owner / admin | cancel + refund if paid |

## Example: booking two seats

```http
POST /api/bookings
Authorization: Bearer eyJ...

{
  "trip_id": 7,
  "boarding_stop_id": 21,
  "dropping_stop_id": 22,
  "passengers": [
    {"trip_seat_id": 301, "name": "Asha Verma", "age": 31, "gender": "female"},
    {"trip_seat_id": 302, "name": "Ravi Verma", "age": 34, "gender": "male"}
  ]
}
```

Response `201`:
```json
{"id": 55, "pnr": "BX7K2M9Q", "status": "pending", "total_amount": "1650.00",
 "expires_at": "2026-10-19T10:40:00", "passengers": [...], "payments": []}
```

Then pay:
```http
POST /api/bookings/55/payments
Idempotency-Key: checkout-55-attempt-1

{"method": "upi"}
```
That returns the booking with `"status": "confirmed"`. If you send the exact same request again
(e.g. the app timed out and retried) you get `200` and the same result. Nothing is charged twice.

## How search works

1. Find all route stops in the origin city
2. For each, check if the same route has a stop in the destination city further along (`stop_order` is bigger)
3. Get the scheduled trips on that route and work out what time the bus reaches the boarding stop
   (`departure_time + minutes_from_origin`)
4. Keep the ones where that time falls on the date the user picked (in local time)

This does a few queries per route, which is fine for now. If search gets slow it could be
turned into one big join.
