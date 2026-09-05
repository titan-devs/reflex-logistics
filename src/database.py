from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session, sessionmaker


DATABASE_URL = f"sqlite:///{Path(__file__).with_name('reflex.db')}"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def migrate_legacy_orders():
    """Move the pre-Reflex order table into the current minimal schema."""
    inspector = inspect(engine)
    if "orders" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("orders")}
    from models import Base
    if "id" not in columns:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE orders RENAME TO orders_legacy"))

        Base.metadata.create_all(bind=engine)

        legacy_columns = {column["name"] for column in inspect(engine).get_columns("orders_legacy")}
        def source(column, fallback):
            return column if column in legacy_columns else fallback

        with engine.begin() as connection:
            connection.execute(text(f"""
                INSERT INTO orders
                    (customer_name, customer_phone, address, item_description, status, rider_id, created_at)
                SELECT
                    {source('customer_name', "'Unknown customer'")},
                    {source('customer_phone', "''")},
                    {source('address', source('delivery_address', "''"))},
                    {source('item_description', "'Unspecified item'")},
                    CASE {source('status', "'logged'")}
                        WHEN 'Logged' THEN 'logged'
                        WHEN 'Assigned' THEN 'assigned'
                        WHEN 'Picked Up' THEN 'picked_up'
                        WHEN 'En Route' THEN 'en_route'
                        WHEN 'Delivered' THEN 'delivered'
                        ELSE {source('status', "'logged'")}
                    END,
                    CAST({source('rider_id', "NULL")} AS VARCHAR(50)),
                    {source('created_at', "CURRENT_TIMESTAMP")}
                FROM orders_legacy
            """))

    inspector = inspect(engine)
    if "riders" in inspector.get_table_names():
        rider_columns = {column["name"] for column in inspector.get_columns("riders")}
        if "first_name" not in rider_columns:
            with engine.begin() as connection:
                connection.execute(text("ALTER TABLE riders RENAME TO riders_legacy"))
            Base.metadata.create_all(bind=engine)
            with engine.begin() as connection:
                connection.execute(text("""
                    INSERT INTO riders
                        (first_name, last_name, phone_number, vehicle_type, status, created_at)
                    SELECT
                        COALESCE(users.first_name, 'Unknown'),
                        COALESCE(users.last_name, 'Rider'),
                        COALESCE(users.phone_number, 'legacy-' || riders_legacy.rider_id),
                        riders_legacy.vehicle_type,
                        CASE riders_legacy.status
                            WHEN 'on_delivery' THEN 'on_delivery'
                            WHEN 'offline' THEN 'offline'
                            ELSE 'available'
                        END,
                        CURRENT_TIMESTAMP
                    FROM riders_legacy
                    LEFT JOIN users ON users.user_id = riders_legacy.user_id
                """))


def get_db():
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()