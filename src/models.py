from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from sqlalchemy import Column, DateTime, Enum as SqlEnum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class OrderStatus(str, Enum):
    LOGGED = "logged"
    ASSIGNED = "assigned"
    PICKED_UP = "picked_up"
    EN_ROUTE = "en_route"
    DELIVERED = "delivered"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True)
    customer_name = Column(String(100), nullable=False)
    customer_phone = Column(String(30), nullable=False)
    address = Column(Text, nullable=False)
    item_description = Column(Text, nullable=False)
    status = Column(
        SqlEnum(
            OrderStatus,
            values_callable=lambda status_values: [status.value for status in status_values],
            native_enum=False,
            length=20,
        ),
        nullable=False,
        default=OrderStatus.LOGGED,
    )
    rider_id = Column(String(50), nullable=True)
    created_at = Column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    status_logs = relationship(
        "StatusLog",
        back_populates="order",
        cascade="all, delete-orphan",
        order_by="StatusLog.created_at",
    )


class StatusLog(Base):
    __tablename__ = "status_logs"

    id = Column(Integer, primary_key=True)
    order_id = Column(
        ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status = Column(
        SqlEnum(
            OrderStatus,
            values_callable=lambda status_values: [status.value for status in status_values],
            native_enum=False,
            length=20,
        ),
        nullable=False,
    )
    changed_by = Column(String(50), nullable=True)
    created_at = Column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    order = relationship("Order", back_populates="status_logs")
