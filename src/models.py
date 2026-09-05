import enum
from datetime import datetime
from typing import Optional
from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from database import Base


class OrderStatus(str, enum.Enum):
    LOGGED = "Logged"
    ASSIGNED = "Assigned"
    PICKED_UP = "Picked Up"
    EN_ROUTE = "En Route"
    DELIVERED = "Delivered"


class User(Base):
    __tablename__ = "users"

    user_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    phone_number: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[str] = mapped_column(
        Text, nullable=False, default=lambda: datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    )

    __table_args__ = (
        CheckConstraint("role IN ('retailer', 'dispatcher', 'rider')", name="check_user_role"),
        Index("idx_users_role", "role"),
    )


class Shop(Base):
    __tablename__ = "shops"

    shop_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    retailer_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False
    )
    shop_name: Mapped[str] = mapped_column(String(100), nullable=False)
    location_address: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[str] = mapped_column(
        Text, nullable=False, default=lambda: datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    )

    __table_args__ = (
        Index("idx_shops_retailer_id", "retailer_id"),
    )


class Customer(Base):
    __tablename__ = "customers"

    customer_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    customer_name: Mapped[str] = mapped_column(String(100), nullable=False)
    customer_phone: Mapped[str] = mapped_column(String(20), nullable=False)
    default_delivery_address: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[str] = mapped_column(
        Text, nullable=False, default=lambda: datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    )

    __table_args__ = (
        Index("idx_customers_phone", "customer_phone"),
    )


class Rider(Base):
    __tablename__ = "riders"

    rider_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False
    )
    vehicle_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="offline", nullable=False)
    updated_at: Mapped[str] = mapped_column(
        Text, nullable=False, default=lambda: datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    )

    __table_args__ = (
        CheckConstraint("status IN ('available', 'on_delivery', 'offline')", name="check_rider_status"),
        Index("idx_riders_status", "status"),
        Index("idx_riders_user_id", "user_id"),
    )


class Order(Base):
    __tablename__ = "orders"

    order_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    shop_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("shops.shop_id", ondelete="CASCADE"), nullable=False
    )
    customer_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("customers.customer_id", ondelete="RESTRICT"), nullable=False
    )
    assigned_rider_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("riders.rider_id", ondelete="SET NULL"), nullable=True
    )
    assigned_by_user_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True
    )
    item_description: Mapped[str] = mapped_column(Text, nullable=False)
    delivery_address: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(30), default=OrderStatus.LOGGED.value, nullable=False)
    dispatch_mode: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)

    created_at: Mapped[str] = mapped_column(
        Text, nullable=False, default=lambda: datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    )
    assigned_at: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    confirmed_at: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    __table_args__ = (
        CheckConstraint(
            "status IN ('Logged', 'Assigned', 'Picked Up', 'En Route', 'Delivered')",
            name="check_order_status"
        ),
        CheckConstraint(
            "dispatch_mode IN ('manual', 'auto_timeout', 'pending')",
            name="check_dispatch_mode"
        ),
        Index("idx_orders_status_created", "status", "created_at"),
        Index("idx_orders_shop_id", "shop_id"),
        Index("idx_orders_assigned_rider_id", "assigned_rider_id"),
    )


class OrderLog(Base):
    __tablename__ = "order_logs"

    log_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("orders.order_id", ondelete="CASCADE"), nullable=False
    )
    previous_status: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    new_status: Mapped[str] = mapped_column(String(30), nullable=False)
    triggered_by: Mapped[str] = mapped_column(String(100), nullable=False)
    timestamp: Mapped[str] = mapped_column(
        Text, nullable=False, default=lambda: datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    )

    __table_args__ = (
        Index("idx_order_logs_order_id", "order_id"),
    )