from fastapi import FastAPI

import app.models
from app.database import Base, engine
from app.routers import bookings, locations, operators, trips
from app.routers import users

#creates any tables that don't exist
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Bus Ticket Booking API", version="0.1.0")

app.include_router(users.router, prefix="/api")
app.include_router(locations.router, prefix="/api")
app.include_router(operators.router, prefix="/api")
app.include_router(trips.router, prefix="/api")
app.include_router(bookings.router, prefix="/api")

@app.get("/health")
def health():
    return {"status": "ok"}