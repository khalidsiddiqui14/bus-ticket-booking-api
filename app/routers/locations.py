# Locations (bus stands) and routes. Only admins can create these.
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import app.schemas
from app.auth import check_role, get_current_user
from app.database import get_db
from app.models import Location, Route, RouteStop, User

router = APIRouter(tags=["locations & routes"])


@router.post("/locations", response_model=app.schemas.LocationOut, status_code=201)
def create_location(data: app.schemas.LocationCreate, db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)):
    check_role(user, "admin")
    location = Location(name=data.name, city=data.city, state=data.state)
    try:
        db.add(location)
        db.commit()
        db.refresh(location)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="This location already exists in that city")
    return location


@router.get("/locations", response_model=list[app.schemas.LocationOut])
def list_locations(city: Optional[str] = None, db: Session = Depends(get_db)):
    query = db.query(Location)
    if city:
        query = query.filter(Location.city.ilike(city))
    return query.order_by(Location.city, Location.name).all()


@router.post("/routes", response_model=app.schemas.RouteOut, status_code=201)
def create_route(data: app.schemas.RouteCreate, db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)):
    check_role(user, "admin")

    # basic sanity checks on the stops
    if len(data.stops) < 2:
        raise HTTPException(status_code=422, detail="A route needs at least 2 stops")
    location_ids = [s.location_id for s in data.stops]
    if len(location_ids) != len(set(location_ids)):
        raise HTTPException(status_code=422, detail="Same location can't be in a route twice")
    if data.stops[0].minutes_from_origin != 0:
        raise HTTPException(status_code=422, detail="First stop should have minutes_from_origin = 0")
    for i in range(1, len(data.stops)):
        if data.stops[i].minutes_from_origin <= data.stops[i - 1].minutes_from_origin:
            raise HTTPException(status_code=422, detail="minutes_from_origin has to go up at every stop")

    for loc_id in location_ids:
        if not db.query(Location).filter(Location.id == loc_id).first():
            raise HTTPException(status_code=404, detail=f"Location {loc_id} not found")

    route = Route(name=data.name, distance_km=data.distance_km)
    for i, stop in enumerate(data.stops):
        route.stops.append(RouteStop(location_id=stop.location_id, stop_order=i,
                                     minutes_from_origin=stop.minutes_from_origin))
    db.add(route)
    db.commit()
    db.refresh(route)
    return route


@router.get("/routes", response_model=list[app.schemas.RouteOut])
def list_routes(db: Session = Depends(get_db)):
    return db.query(Route).order_by(Route.id).all()


@router.get("/routes/{route_id}", response_model=app.schemas.RouteOut)
def get_route(route_id: int, db: Session = Depends(get_db)):
    route = db.query(Route).filter(Route.id == route_id).first()
    if not route:
        raise HTTPException(status_code=404, detail="Route not found")
    return route
