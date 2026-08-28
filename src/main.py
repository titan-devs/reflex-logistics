from typing import List, Optional

from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session

import models
import schemas
from database import engine, get_db

models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="Reflex API", version="0.1.0")

# Valid forward-only status transitions. This is the 'state locking' /
# 'what happens when two things happen at once' answer: an order can
# only move forward one step at a time, and only from the state it's
# actually in — so a rider double-tapping 'Delivered' or a stale app
# resubmitting an old status can't corrupt the record.
VALID_TRANSITIONS = {
    models.OrderStatus.LOGGED: {models.OrderStatus.ASSIGNED},
    models.OrderStatus.ASSIGNED: {models.OrderStatus.PICKED_UP},
    models.OrderStatus.PICKED_UP: {models.OrderStatus.DELIVERED},
    models.OrderStatus.DELIVERED: set(),
}


def _log_status(db: Session, order: models.Order, status: models.OrderStatus,
                 changed_by: Optional[str]):
    order.status = status
    db.add(models.StatusLog(order_id=order.id, status=status, changed_by=changed_by))


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
    order.rider_id = payload.rider_id
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
