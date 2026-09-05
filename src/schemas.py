from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from models import OrderStatus


class OrderCreate(BaseModel):
    customer_name: str = Field(min_length=1, max_length=100)
    customer_phone: str = Field(min_length=1, max_length=30)
    address: str = Field(min_length=1)
    item_description: str = Field(min_length=1)


class AssignRequest(BaseModel):
    rider_id: str = Field(min_length=1, max_length=50)


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


class OrderDetailOut(OrderOut):
    status_logs: list[StatusLogOut] = Field(default_factory=list)