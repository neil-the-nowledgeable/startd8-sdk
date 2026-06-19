"""SQLAlchemy models mirroring accounting/Entities.cs (Step 1)."""
from __future__ import annotations

import os

from sqlalchemy import Float, ForeignKey, Integer, String, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker


class Base(DeclarativeBase):
    pass


class OrderEntity(Base):
    __tablename__ = "orders"

    id: Mapped[str] = mapped_column(String, primary_key=True)


class OrderItemEntity(Base):
    __tablename__ = "order_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[str] = mapped_column(String, ForeignKey("orders.id"))
    product_id: Mapped[str] = mapped_column(String)
    quantity: Mapped[int] = mapped_column(Integer)
    item_cost_currency_code: Mapped[str] = mapped_column(String)
    item_cost_units: Mapped[int] = mapped_column(Integer)
    item_cost_nanos: Mapped[int] = mapped_column(Integer)


class ShippingEntity(Base):
    __tablename__ = "shipping"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[str] = mapped_column(String, ForeignKey("orders.id"))
    shipping_tracking_id: Mapped[str] = mapped_column(String)
    shipping_cost_currency_code: Mapped[str] = mapped_column(String)
    shipping_cost_units: Mapped[int] = mapped_column(Integer)
    shipping_cost_nanos: Mapped[int] = mapped_column(Integer)
    street_address: Mapped[str] = mapped_column(String)
    city: Mapped[str] = mapped_column(String)
    state: Mapped[str] = mapped_column(String)
    country: Mapped[str] = mapped_column(String)
    zip_code: Mapped[str] = mapped_column(String)


def session_factory():
    conn = os.environ.get("DB_CONNECTION_STRING") or os.environ.get("DATABASE_URL")
    if not conn:
        return None
    engine = create_engine(conn)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)
