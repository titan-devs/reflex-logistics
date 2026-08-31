from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from src.database import Base
from src.models import User, Order, Assignment, StatusLog, OrderStatus


DATABASE_URL = "sqlite:///./reflex_logistics.db"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
)

Base.metadata.create_all(bind=engine)


with Session(engine) as db:
    rider = User(
        name="Test Rider",
        phone="0712345678",
        role="rider",
    )

    db.add(rider)
    db.commit()
    db.refresh(rider)

    print(f"Created rider: {rider.id} - {rider.name}")

    order = Order(
        customer_name="Test Customer",
        customer_phone="0798765432",
        address="Nairobi CBD",
        item_description="Test Package",
    )

    db.add(order)
    db.commit()
    db.refresh(order)

    print(f"Created order: {order.id} - {order.status}")

    assignment = Assignment(
        order_id=order.id,
        rider_id=rider.id,
    )

    db.add(assignment)
    db.commit()

    print(
        f"Assigned order {order.id} "
        f"to rider {rider.id}"
    )
    