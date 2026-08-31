from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.database import engine
from src.models import Order


with Session(engine) as db:
    invalid_order = Order(
        customer_name=None,
        customer_phone="0700000000",
        address="Nairobi",
        item_description="Test Package",
    )

    db.add(invalid_order)

    try:
        db.commit()
        print("FAIL: Order without customer name was accepted.")
    except IntegrityError:
        db.rollback()
        print("PASS: Missing customer name was rejected.")