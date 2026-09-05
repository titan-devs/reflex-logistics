from pathlib import Path
from typing import List, Optional
from uuid import uuid4

from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

import models
import schemas
from database import engine, get_db, migrate_legacy_orders

migrate_legacy_orders()
models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="Reflex API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Valid forward-only status transitions. This is the 'state locking' /
# 'what happens when two things happen at once' answer: an order can
# only move forward one step at a time, and only from the state it's
# actually in — so a rider double-tapping 'Delivered' or a stale app
# resubmitting an old status can't corrupt the record.
VALID_TRANSITIONS = {
    models.OrderStatus.LOGGED: {models.OrderStatus.ASSIGNED},
    models.OrderStatus.ASSIGNED: {models.OrderStatus.PICKED_UP},
    models.OrderStatus.PICKED_UP: {models.OrderStatus.EN_ROUTE},
    models.OrderStatus.EN_ROUTE: {models.OrderStatus.DELIVERED},
    models.OrderStatus.DELIVERED: set(),
}


def _log_status(db: Session, order: models.Order, status: models.OrderStatus,
                 changed_by: Optional[str]):
    order.status = status
    db.add(models.StatusLog(order_id=order.id, status=status, changed_by=changed_by))


def _rider_out(db: Session, rider: models.Rider):
    name = f"{rider.first_name} {rider.last_name}".strip()
    jobs = db.query(models.Order).filter(
        models.Order.rider_id == str(rider.rider_id),
        models.Order.status != models.OrderStatus.DELIVERED,
    ).count()
    return schemas.RiderOut(
        rider_id=rider.rider_id,
        name=name,
        initials="".join(part[0] for part in name.split()).upper(),
        vehicle_type=rider.vehicle_type,
        status=rider.status,
        jobs_today=jobs,
    )


@app.post("/session", response_model=schemas.SessionOut)
def start_session(payload: schemas.SessionStart, db: Session = Depends(get_db)):
    parts = payload.name.strip().split()
    first_name = parts[0]
    last_name = " ".join(parts[1:]) or "Operator"
    user = db.query(models.User).filter(
        models.User.first_name == first_name,
        models.User.last_name == last_name,
        models.User.role == "retailer",
    ).first()
    if not user:
        user = models.User(
            first_name=first_name,
            last_name=last_name,
            phone_number=f"session-{uuid4().hex}",
            role="retailer",
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    display_name = f"{user.first_name} {user.last_name}"
    return schemas.SessionOut(
        user_id=user.user_id,
        first_name=user.first_name,
        last_name=user.last_name,
        display_name=display_name,
        initials="".join(part[0] for part in display_name.split()).upper(),
    )


# ---------------------------------------------------------------------
# Retailer: log a new delivery request
# ---------------------------------------------------------------------
@app.post("/orders", response_model=schemas.OrderOut, status_code=201)
def create_order(payload: schemas.OrderCreate, db: Session = Depends(get_db)):
    order = models.Order(
        customer_name=payload.customer_name,
        customer_phone=payload.customer_phone,
        address=payload.address,
        item_description=payload.item_description,
        status=models.OrderStatus.LOGGED,
    )
    db.add(order)
    db.commit()
    db.refresh(order)
    _log_status(db, order, models.OrderStatus.LOGGED, changed_by="retailer")
    db.commit()
    return order


# ---------------------------------------------------------------------
# Dispatcher: list requests, optionally filtered by status/rider
# ---------------------------------------------------------------------
@app.get("/orders", response_model=List[schemas.OrderOut])
def list_orders(
    status: Optional[models.OrderStatus] = None,
    rider_id: Optional[str] = None,
    db: Session = Depends(get_db),
):
    query = db.query(models.Order)
    if status:
        query = query.filter(models.Order.status == status)
    if rider_id:
        query = query.filter(models.Order.rider_id == rider_id)
    return query.order_by(models.Order.created_at.desc()).all()


@app.get("/orders/{order_id}", response_model=schemas.OrderDetailOut)
def get_order(order_id: int, db: Session = Depends(get_db)):
    order = db.query(models.Order).get(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return order


# ---------------------------------------------------------------------
# Dispatcher: assign a rider to an open request
# ---------------------------------------------------------------------
@app.post("/orders/{order_id}/assign", response_model=schemas.OrderOut)
def assign_rider(order_id: int, payload: schemas.AssignRequest, db: Session = Depends(get_db)):
    order = db.query(models.Order).get(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if order.status != models.OrderStatus.LOGGED:
        raise HTTPException(
            status_code=409,
            detail=f"Order is '{order.status.value}', can only assign from 'logged'",
        )
    rider_id = payload.assigned_rider_id or payload.rider_id
    if rider_id is None:
        raise HTTPException(status_code=422, detail="A rider is required")
    rider = db.query(models.Rider).filter(models.Rider.rider_id == int(rider_id)).first()
    if not rider or rider.status != "available":
        raise HTTPException(status_code=409, detail="Rider is not available")
    order.rider_id = str(rider.rider_id)
    rider.status = "on_delivery"
    _log_status(db, order, models.OrderStatus.ASSIGNED, changed_by="dispatcher")
    db.commit()
    db.refresh(order)
    return order


# ---------------------------------------------------------------------
# Rider: update status on their assigned delivery
# ---------------------------------------------------------------------
@app.patch("/orders/{order_id}/status", response_model=schemas.OrderOut)
def update_status(order_id: int, payload: schemas.StatusUpdate, db: Session = Depends(get_db)):
    order = db.query(models.Order).get(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    allowed_next = VALID_TRANSITIONS.get(order.status, set())
    if payload.status not in allowed_next:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Invalid transition: '{order.status.value}' -> "
                f"'{payload.status.value}'. Allowed: "
                f"{[s.value for s in allowed_next] or 'none'}"
            ),
        )
    _log_status(db, order, payload.status, changed_by=order.rider_id)
    db.commit()
    db.refresh(order)
    return order


# ---------------------------------------------------------------------
# Rider: convenience view of "my deliveries"
# ---------------------------------------------------------------------
@app.get("/riders/{rider_id}/orders", response_model=List[schemas.OrderOut])
def rider_orders(rider_id: str, db: Session = Depends(get_db)):
    return (
        db.query(models.Order)
        .filter(models.Order.rider_id == rider_id)
        .order_by(models.Order.created_at.desc())
        .all()
    )


# ---------------------------------------------------------------------
# Sync engine: simulated endpoint for offline/queued payloads coming
# back in (e.g. a rider's phone was offline and now flushes queued
# status updates). This is the 'polling vs WebSockets' trade-off stand-in.
# ---------------------------------------------------------------------
@app.post("/sync", response_model=schemas.OrderOut)
def sync_payload(payload: schemas.SyncPayload, db: Session = Depends(get_db)):
    order = db.query(models.Order).get(payload.order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    allowed_next = VALID_TRANSITIONS.get(order.status, set())
    if payload.status not in allowed_next:
        # Same-state resubmission (e.g. duplicate queued payload) is a
        # no-op, not an error -- that's what makes sync safe to retry.
        if payload.status == order.status:
            return order
        raise HTTPException(
            status_code=409,
            detail=(
                f"Stale or out-of-order sync payload: cannot go from "
                f"'{order.status.value}' to '{payload.status.value}'"
            ),
        )
    _log_status(db, order, payload.status, changed_by=payload.changed_by)
    db.commit()
    db.refresh(order)
    return order


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/riders", response_model=List[schemas.RiderOut])
def list_riders(db: Session = Depends(get_db)):
    return [_rider_out(db, rider) for rider in db.query(models.Rider).order_by(models.Rider.first_name).all()]


@app.post("/riders", response_model=schemas.RiderOut, status_code=201)
def create_rider(payload: schemas.RiderCreate, db: Session = Depends(get_db)):
    if db.query(models.Rider).filter(models.Rider.phone_number == payload.phone_number).first():
        raise HTTPException(status_code=409, detail="A rider with this phone number already exists")
    rider = models.Rider(
        first_name=payload.first_name.strip(),
        last_name=payload.last_name.strip(),
        phone_number=payload.phone_number.strip(),
        vehicle_type=payload.vehicle_type,
        status=payload.status,
    )
    db.add(rider)
    db.commit()
    db.refresh(rider)
    return _rider_out(db, rider)


@app.patch("/riders/{rider_id}/status", response_model=schemas.RiderOut)
def update_rider_status(rider_id: int, payload: schemas.RiderStatusUpdate, db: Session = Depends(get_db)):
    rider = db.query(models.Rider).get(rider_id)
    if not rider:
        raise HTTPException(status_code=404, detail="Rider not found")
    if payload.status == "offline" and db.query(models.Order).filter(
        models.Order.rider_id == str(rider_id),
        models.Order.status.in_([
            models.OrderStatus.ASSIGNED,
            models.OrderStatus.PICKED_UP,
            models.OrderStatus.EN_ROUTE,
        ]),
    ).count():
        raise HTTPException(status_code=409, detail="Rider has an active delivery")
    rider.status = payload.status
    db.commit()
    db.refresh(rider)
    return _rider_out(db, rider)


@app.get("/activity")
def activity(db: Session = Depends(get_db)):
    return [
        {
            "log_id": log.id,
            "order_id": log.order_id,
            "new_status": log.status.value,
            "triggered_by": log.changed_by or "system",
            "timestamp": log.created_at.isoformat(),
        }
        for log in db.query(models.StatusLog).order_by(models.StatusLog.created_at.desc()).limit(50).all()
    ]


frontend_dir = Path(__file__).resolve().parent / "static"

if frontend_dir.exists():
    app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")
