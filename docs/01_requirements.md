# Step 1 - Figuring out what we need

Before writing any code I listed who uses the app and what they need to do.

## Users

- **Customer** - searches buses, picks seats, books, pays, cancels
- **Operator** - a bus company. Adds their buses and schedules trips
- **Admin** - us. Adds cities/bus stands, routes and operator companies

## Features (MVP)

1. Sign up / log in (JWT). Three roles: customer, operator, admin
2. Admin adds locations (bus stands) and routes (a list of stops in order)
3. Admin adds operator companies, operators add buses with a seat layout
4. Operators schedule trips (route + bus + times + fare)
5. Search trips by from city, to city and date. Should also work for stops in the middle of a route (Delhi -> Jaipur on a Delhi-Jaipur-Ajmer bus)
6. Show the seat map with which seats are free
7. Book seats with passenger details. Seats are **held for 10 min** until you pay
8. Pay for the booking. Retrying the same payment must not charge twice
9. Cancel a booking before the bus leaves and get a refund (90% if 24h+ before, otherwise 50%)
10. Operator can cancel a whole trip, then everyone gets a full refund
11. Every booking gets a PNR code

## Things that really matter

- **Never sell the same seat twice.** This is the big one, see [04_how_booking_works.md](04_how_booking_works.md)
- Money stored as `Numeric`, not float (floats give you rounding errors)
- Passwords hashed with bcrypt