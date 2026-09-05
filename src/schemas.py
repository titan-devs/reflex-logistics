from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict

from .models import OrderStatus


class OrderCreate(BaseModel):
    customer_name: str
    customer_phone: str
    address: str
    item_description: str


class OrderOut(BaseModel):
    id: int
    customer_name: str
    customer_phone: str
    address: str
    item_description: str
    status: OrderStatus
    rider_id: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)


class OrderDetailOut(OrderOut):
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class AssignRequest(BaseModel):
    rider_id: int


class StatusUpdate(BaseModel):
    status: OrderStatus


class SyncPayload(BaseModel):
    order_id: int
    status: OrderStatus
    changed_by: Optional[int] = None