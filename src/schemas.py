from enum import Enum
from typing import Optional
from pydantic import BaseModel, ConfigDict

class OrderStatus(str, Enum):
    LOGGED = "Logged"
    ASSIGNED = "Assigned"
    PICKED_UP = "Picked Up"
    EN_ROUTE = "En Route"
    DELIVERED = "Delivered"

class OrderCreate(BaseModel):
    shop_id: Optional[int] = None
    customer_id: Optional[int] = None
    customer_name: Optional[str] = None
    customer_phone: Optional[str] = None
    item_description: str
    delivery_address: str
    dispatch_mode: Optional[str] = "pending"

class AssignRequest(BaseModel):
    assigned_rider_id: int
    assigned_by_user_id: Optional[int] = None


class RiderCreate(BaseModel):
    first_name: str
    last_name: str
    phone_number: str
    vehicle_type: Optional[str] = None
    status: str = "available"


class RiderStatusUpdate(BaseModel):
    status: str


class SessionStart(BaseModel):
    name: str


class SessionResponse(BaseModel):
    user_id: int
    first_name: str
    last_name: str
    display_name: str
    initials: str

class StatusUpdate(BaseModel):
    status: OrderStatus

class SyncPayload(BaseModel):
    order_id: int
    status: OrderStatus
    changed_by: str

class OrderResponse(BaseModel):
    order_id: int
    shop_id: int
    customer_id: int
    assigned_rider_id: Optional[int] = None
    assigned_by_user_id: Optional[int] = None
    item_description: str
    delivery_address: str
    status: OrderStatus
    dispatch_mode: str
    created_at: str
    assigned_at: Optional[str] = None
    confirmed_at: Optional[str] = None
    customer_name: Optional[str] = None
    rider_name: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class RiderResponse(BaseModel):
    rider_id: int
    user_id: int
    name: str
    initials: str
    vehicle_type: Optional[str] = None
    status: str
    jobs_today: int = 0


class OrderLogResponse(BaseModel):
    log_id: int
    order_id: int
    previous_status: Optional[str] = None
    new_status: str
    triggered_by: str
    timestamp: str

    model_config = ConfigDict(from_attributes=True)