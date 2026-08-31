from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.database import engine
from src.models import User


with Session(engine) as db:
    duplicate_rider = User(
        name="Another Rider",
        phone="0712345678",
        role="rider",
    )

    db.add(duplicate_rider)

    try:
        db.commit()
        print("FAIL: Duplicate phone number was accepted.")
    except IntegrityError:
        db.rollback()
        print("PASS: Duplicate phone number was rejected.")