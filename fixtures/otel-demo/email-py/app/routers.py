# GENERATED from prisma/schema.prisma — do not edit by hand; regenerate via `startd8 generate backend`.
# startd8-artifact: fastapi-routers
# Source of truth: the Prisma schema.
# schema-sha256: 0b898e5f7f7f45151610a0e3830b0b5c32150ec8cc732b449b0d0ea40e8ce102

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from .db import get_session
from .tables import OrderConfirmation, OrderConfirmationCreate, OrderConfirmationRead, OrderConfirmationUpdate


orderconfirmation_router = APIRouter(prefix="/orderconfirmation", tags=["orderconfirmation"])


@orderconfirmation_router.get("/")
def list_orderconfirmation(session: Session = Depends(get_session)) -> list[OrderConfirmationRead]:
    return list(session.exec(select(OrderConfirmation)).all())


@orderconfirmation_router.post("/")
def create_orderconfirmation(item: OrderConfirmationCreate, session: Session = Depends(get_session)) -> OrderConfirmationRead:
    obj = OrderConfirmation(**item.model_dump())
    session.add(obj)
    session.commit()
    session.refresh(obj)
    return obj


@orderconfirmation_router.get("/{item_id}")
def get_orderconfirmation(item_id: str, session: Session = Depends(get_session)) -> OrderConfirmationRead:
    obj = session.get(OrderConfirmation, item_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="OrderConfirmation not found")
    return obj


@orderconfirmation_router.patch("/{item_id}")
def update_orderconfirmation(
    item_id: str, data: OrderConfirmationUpdate, session: Session = Depends(get_session)
) -> OrderConfirmationRead:
    obj = session.get(OrderConfirmation, item_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="OrderConfirmation not found")
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(obj, key, value)
    session.add(obj)
    session.commit()
    session.refresh(obj)
    return obj


@orderconfirmation_router.delete("/{item_id}")
def delete_orderconfirmation(item_id: str, session: Session = Depends(get_session)) -> dict:
    obj = session.get(OrderConfirmation, item_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="OrderConfirmation not found")
    session.delete(obj)
    session.commit()
    return {"ok": True}


all_routers = [orderconfirmation_router]
