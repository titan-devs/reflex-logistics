from datetime import datetime
from pathlib import Path
from typing import List, Optional
from uuid import uuid4

from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select
from sqlalchemy.orm import Session

import models
import schemas
from database import SessionLocal, engine, get_db

# Create DB tables
models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="Reflex API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _ensure_workspace(db: Session):
    retailer = db.scalar(select(models.User).where(models.User.phone_number == "+254700000000"))
    if not retailer:
        retailer = models.User(
            first_name="Workspace", last_name="Owner", phone_number="+254700000000", role="retailer"
        )
        db.add(retailer)
        db.flush()
    shop = db.scalar(select(models.Shop).where(models.Shop.retailer_id == retailer.user_id))
    if not shop:
        db.add(models.Shop(
            retailer_id=retailer.user_id,
            shop_name="Kilimani Hub",
            location_address="Kilimani, Nairobi",
        ))
    db.commit()


with SessionLocal() as startup_db:
    _ensure_workspace(startup_db)

VALID_TRANSITIONS = {
    models.OrderStatus.LOGGED: {models.OrderStatus.ASSIGNED},
    models.OrderStatus.ASSIGNED: {models.OrderStatus.PICKED_UP},
    models.OrderStatus.PICKED_UP: {models.OrderStatus.EN_ROUTE},
    models.OrderStatus.EN_ROUTE: {models.OrderStatus.DELIVERED},
    models.OrderStatus.DELIVERED: set(),
}


@app.post("/session", response_model=schemas.SessionResponse)
def start_session(payload: schemas.SessionStart, db: Session = Depends(get_db)):
    name_parts = payload.name.strip().split()
    if not name_parts:
        raise HTTPException(status_code=422, detail="Name is required")
    first_name = name_parts[0]
    last_name = " ".join(name_parts[1:]) or "Operator"
    user = db.scalar(select(models.User).where(
        models.User.first_name == first_name,
        models.User.last_name == last_name,
        models.User.role == "retailer",
    ))
    if not user:
        user = models.User(
            first_name=first_name,
            last_name=last_name,
            phone_number=f"session-{uuid4().hex[:12]}",
            role="retailer",
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    display_name = f"{user.first_name} {user.last_name}".strip()
    return schemas.SessionResponse(
        user_id=user.user_id,
        first_name=user.first_name,
        last_name=user.last_name,
        display_name=display_name,
        initials="".join(part[0] for part in display_name.split() if part).upper(),
    )


def _log_status_transition(
    db: Session,
    order: models.Order,
    new_status: models.OrderStatus,
    triggered_by: str
):
    previous_status = order.status
    now_iso = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

    # Update status & timestamps
    order.status = new_status.value
    if new_status == models.OrderStatus.ASSIGNED:
        order.assigned_at = now_iso
    elif new_status == models.OrderStatus.DELIVERED:
        order.confirmed_at = now_iso
        if order.assigned_rider_id:
            rider = db.get(models.Rider, order.assigned_rider_id)
            if rider:
                rider.status = "available"
                rider.updated_at = now_iso

    # Insert audit entry into order_logs
    log_entry = models.OrderLog(
        order_id=order.order_id,
        previous_status=previous_status if isinstance(previous_status, str) else previous_status.value,
        new_status=new_status.value,
        triggered_by=triggered_by,
        timestamp=now_iso
    )
    db.add(log_entry)


def _order_response(db: Session, order: models.Order):
    customer = db.get(models.Customer, order.customer_id)
    rider = db.get(models.Rider, order.assigned_rider_id) if order.assigned_rider_id else None
    rider_user = db.get(models.User, rider.user_id) if rider else None
    response = schemas.OrderResponse.model_validate(order)
    response.customer_name = customer.customer_name if customer else None
    response.rider_name = f"{rider_user.first_name} {rider_user.last_name}" if rider_user else None
    return response


def _rider_response(db: Session, rider: models.Rider, user: models.User):
    jobs = db.scalar(select(func.count(models.Order.order_id)).where(
        models.Order.assigned_rider_id == rider.rider_id,
        models.Order.status != models.OrderStatus.DELIVERED.value,
    )) or 0
    name = f"{user.first_name} {user.last_name}".strip()
    return schemas.RiderResponse(
        rider_id=rider.rider_id,
        user_id=user.user_id,
        name=name,
        initials="".join(part[0] for part in name.split() if part).upper(),
        vehicle_type=rider.vehicle_type,
        status=rider.status,
        jobs_today=jobs,
    )


@app.post("/orders", response_model=schemas.OrderResponse, status_code=status.HTTP_201_CREATED)
def create_order(payload: schemas.OrderCreate, db: Session = Depends(get_db)):
    shop_id = payload.shop_id
    if shop_id is None:
        shop_id = db.scalar(select(models.Shop.shop_id).order_by(models.Shop.shop_id.asc()))
    if not shop_id or not db.get(models.Shop, shop_id):
        raise HTTPException(status_code=404, detail="Shop not found")

    customer_id = payload.customer_id
    if customer_id is None:
        if not payload.customer_name or not payload.customer_phone:
            raise HTTPException(status_code=422, detail="Customer name and phone are required")
        customer = models.Customer(
            customer_name=payload.customer_name,
            customer_phone=payload.customer_phone,
            default_delivery_address=payload.delivery_address,
        )
        db.add(customer)
        db.flush()
        customer_id = customer.customer_id
    elif not db.get(models.Customer, customer_id):
        raise HTTPException(status_code=404, detail="Customer not found")

    order = models.Order(
        shop_id=shop_id,
        customer_id=customer_id,
        item_description=payload.item_description,
        delivery_address=payload.delivery_address,
        dispatch_mode=payload.dispatch_mode or "pending",
        status=models.OrderStatus.LOGGED.value
    )
    db.add(order)
    db.commit()
    db.refresh(order)

    _log_status_transition(db, order, models.OrderStatus.LOGGED, triggered_by="retailer")
    db.commit()
    db.refresh(order)
    return _order_response(db, order)


@app.get("/orders", response_model=List[schemas.OrderResponse])
def list_orders(
    order_status: Optional[models.OrderStatus] = None,
    rider_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    stmt = select(models.Order)
    if order_status:
        stmt = stmt.where(models.Order.status == order_status.value)
    if rider_id:
        stmt = stmt.where(models.Order.assigned_rider_id == rider_id)
    
    stmt = stmt.order_by(models.Order.created_at.asc())
    return [_order_response(db, order) for order in db.scalars(stmt).all()]


@app.get("/orders/{order_id}", response_model=schemas.OrderResponse)
def get_order(order_id: int, db: Session = Depends(get_db)):
    order = db.get(models.Order, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return _order_response(db, order)


@app.post("/orders/{order_id}/assign", response_model=schemas.OrderResponse)
def assign_rider(
    order_id: int, 
    payload: schemas.AssignRequest, 
    db: Session = Depends(get_db)
):
    order = db.get(models.Order, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
        
    if order.status != models.OrderStatus.LOGGED.value:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Order status is '{order.status}'. Orders can only be assigned from 'Logged' status.",
        )
        
    rider = db.get(models.Rider, payload.assigned_rider_id)
    if not rider:
        raise HTTPException(status_code=404, detail="Rider not found")

    order.assigned_rider_id = payload.assigned_rider_id
    assigned_by_user_id = payload.assigned_by_user_id or db.scalar(
        select(models.User.user_id)
        .where(models.User.role.in_(["dispatcher", "retailer"]))
        .order_by(models.User.user_id.asc())
    )
    order.assigned_by_user_id = assigned_by_user_id
    order.dispatch_mode = "manual"
    rider.status = "on_delivery"
    rider.updated_at = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    
    _log_status_transition(
        db, order, models.OrderStatus.ASSIGNED, triggered_by=f"dispatcher:{assigned_by_user_id}"
    )
    db.commit()
    db.refresh(order)
    return _order_response(db, order)


@app.patch("/orders/{order_id}/status", response_model=schemas.OrderResponse)
def update_status(
    order_id: int, 
    payload: schemas.StatusUpdate, 
    db: Session = Depends(get_db)
):
    order = db.get(models.Order, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    # Match raw string to Enum key
    current_enum = models.OrderStatus(order.status)
    allowed_next = VALID_TRANSITIONS.get(current_enum, set())
    
    if payload.status not in allowed_next:
        allowed_vals = [s.value for s in allowed_next]
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Invalid transition '{order.status}' -> '{payload.status.value}'. Allowed transitions: {allowed_vals or 'none'}"
        )

    actor = f"rider:{order.assigned_rider_id}" if order.assigned_rider_id else "system"
    _log_status_transition(db, order, models.OrderStatus(payload.status.value), triggered_by=actor)
    db.commit()
    db.refresh(order)
    return _order_response(db, order)


@app.get("/riders/{rider_id}/orders", response_model=List[schemas.OrderResponse])
def rider_orders(rider_id: int, db: Session = Depends(get_db)):
    stmt = (
        select(models.Order)
        .where(models.Order.assigned_rider_id == rider_id)
        .order_by(models.Order.created_at.desc())
    )
    return [_order_response(db, order) for order in db.scalars(stmt).all()]


@app.post("/sync", response_model=schemas.OrderResponse)
def sync_payload(payload: schemas.SyncPayload, db: Session = Depends(get_db)):
    order = db.get(models.Order, payload.order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    current_enum = models.OrderStatus(order.status)
    allowed_next = VALID_TRANSITIONS.get(current_enum, set())
    
    if payload.status == current_enum:
        return _order_response(db, order)

    if payload.status not in allowed_next:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Stale sync payload: cannot transition from '{order.status}' to '{payload.status.value}'"
        )

    _log_status_transition(
        db, order, models.OrderStatus(payload.status.value), triggered_by=payload.changed_by
    )
    db.commit()
    db.refresh(order)
    return _order_response(db, order)


@app.get("/riders", response_model=List[schemas.RiderResponse])
def list_riders(db: Session = Depends(get_db)):
    rows = db.execute(
        select(models.Rider, models.User)
        .join(models.User, models.User.user_id == models.Rider.user_id)
        .order_by(models.User.first_name.asc())
    ).all()
    result = []
    for rider, user in rows:
        result.append(_rider_response(db, rider, user))
    return result


@app.post("/riders", response_model=schemas.RiderResponse, status_code=status.HTTP_201_CREATED)
def create_rider(payload: schemas.RiderCreate, db: Session = Depends(get_db)):
    if payload.status not in {"available", "offline"}:
        raise HTTPException(status_code=422, detail="New riders must be available or offline")
    existing = db.scalar(select(models.User).where(models.User.phone_number == payload.phone_number))
    if existing:
        raise HTTPException(status_code=409, detail="A user with this phone number already exists")
    user = models.User(
        first_name=payload.first_name.strip(),
        last_name=payload.last_name.strip(),
        phone_number=payload.phone_number.strip(),
        role="rider",
    )
    db.add(user)
    db.flush()
    rider = models.Rider(user_id=user.user_id, vehicle_type=payload.vehicle_type, status=payload.status)
    db.add(rider)
    db.commit()
    db.refresh(rider)
    return _rider_response(db, rider, user)


@app.patch("/riders/{rider_id}/status", response_model=schemas.RiderResponse)
def update_rider_status(
    rider_id: int, payload: schemas.RiderStatusUpdate, db: Session = Depends(get_db)
):
    if payload.status not in {"available", "offline"}:
        raise HTTPException(status_code=422, detail="Rider status must be available or offline")
    rider = db.get(models.Rider, rider_id)
    if not rider:
        raise HTTPException(status_code=404, detail="Rider not found")
    active_jobs = db.scalar(select(func.count(models.Order.order_id)).where(
        models.Order.assigned_rider_id == rider_id,
        models.Order.status.in_([
            models.OrderStatus.ASSIGNED.value,
            models.OrderStatus.PICKED_UP.value,
            models.OrderStatus.EN_ROUTE.value,
        ]),
    )) or 0
    if active_jobs:
        raise HTTPException(status_code=409, detail="Rider with an active job cannot go offline")
    rider.status = payload.status
    rider.updated_at = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    db.commit()
    return _rider_response(db, rider, db.get(models.User, rider.user_id))


@app.get("/orders/{order_id}/logs", response_model=List[schemas.OrderLogResponse])
def order_logs(order_id: int, db: Session = Depends(get_db)):
    if not db.get(models.Order, order_id):
        raise HTTPException(status_code=404, detail="Order not found")
    return db.scalars(select(models.OrderLog).where(
        models.OrderLog.order_id == order_id
    ).order_by(models.OrderLog.timestamp.desc())).all()


@app.get("/activity", response_model=List[schemas.OrderLogResponse])
def activity(db: Session = Depends(get_db)):
    return db.scalars(select(models.OrderLog).order_by(
        models.OrderLog.timestamp.desc(), models.OrderLog.log_id.desc()
    ).limit(20)).all()


@app.get("/health")
def health():
    return {"status": "ok"}


frontend_dir = Path(__file__).resolve().parent.parent / "frontend"

if frontend_dir.exists():
    app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")