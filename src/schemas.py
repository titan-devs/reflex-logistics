from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from models import OrderStatus


class OrderCreate(BaseModel):
    customer_name: str = Field(min_length=1, max_length=100)
    customer_phone: str = Field(min_length=1, max_length=30)
    address: str = Field(min_length=1)
    item_description: str = Field(min_length=1)


class AssignRequest(BaseModel):
    rider_id: str | None = Field(default=None, min_length=1, max_length=50)
    assigned_rider_id: int | None = None


class StatusUpdate(BaseModel):
    status: OrderStatus


class SyncPayload(StatusUpdate):
    order_id: int
    changed_by: str | None = Field(default=None, max_length=50)


class StatusLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    status: OrderStatus
    changed_by: str | None
    created_at: datetime


class OrderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    customer_name: str
    customer_phone: str
    address: str
    item_description: str
    status: OrderStatus
    rider_id: str | None
    created_at: datetime


class RiderCreate(BaseModel):
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    phone_number: str = Field(min_length=1, max_length=30)
    vehicle_type: str | None = Field(default=None, max_length=50)
    status: str = Field(default="available", pattern="^(available|offline)$")


class RiderStatusUpdate(BaseModel):
    status: str = Field(pattern="^(available|offline)$")


class RiderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    rider_id: int
    name: str
    initials: str
    vehicle_type: str | None
    status: str
    jobs_today: int = 0


class SessionStart(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class SessionOut(BaseModel):
    user_id: int
    first_name: str
    last_name: str
    display_name: str
    initials: str


class OrderDetailOut(OrderOut):
    status_logs: list[StatusLogOut] = Field(default_factory=list)
