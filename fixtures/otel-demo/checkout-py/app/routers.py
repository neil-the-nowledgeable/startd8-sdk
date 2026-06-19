# GENERATED from prisma/schema.prisma — do not edit by hand; regenerate via `startd8 generate backend`.
# startd8-artifact: fastapi-routers
# Source of truth: the Prisma schema.
# schema-sha256: b914136a55bbc023ec648d2a29986a918c88b6e70d55d4300cd1a0e7725e70ba

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from .db import get_session
from .tables import PlaceOrderSession, PlaceOrderSessionCreate, PlaceOrderSessionRead, PlaceOrderSessionUpdate


placeordersession_router = APIRouter(prefix="/placeordersession", tags=["placeordersession"])


@placeordersession_router.get("/")
def list_placeordersession(session: Session = Depends(get_session)) -> list[PlaceOrderSessionRead]:
    return list(session.exec(select(PlaceOrderSession)).all())


@placeordersession_router.post("/")
def create_placeordersession(item: PlaceOrderSessionCreate, session: Session = Depends(get_session)) -> PlaceOrderSessionRead:
    obj = PlaceOrderSession(**item.model_dump())
    session.add(obj)
    session.commit()
    session.refresh(obj)
    return obj


@placeordersession_router.get("/{item_id}")
def get_placeordersession(item_id: str, session: Session = Depends(get_session)) -> PlaceOrderSessionRead:
    obj = session.get(PlaceOrderSession, item_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="PlaceOrderSession not found")
    return obj


@placeordersession_router.patch("/{item_id}")
def update_placeordersession(
    item_id: str, data: PlaceOrderSessionUpdate, session: Session = Depends(get_session)
) -> PlaceOrderSessionRead:
    obj = session.get(PlaceOrderSession, item_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="PlaceOrderSession not found")
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(obj, key, value)
    session.add(obj)
    session.commit()
    session.refresh(obj)
    return obj


@placeordersession_router.delete("/{item_id}")
def delete_placeordersession(item_id: str, session: Session = Depends(get_session)) -> dict:
    obj = session.get(PlaceOrderSession, item_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="PlaceOrderSession not found")
    session.delete(obj)
    session.commit()
    return {"ok": True}


all_routers = [placeordersession_router]
