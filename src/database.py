import sqlite3
from pathlib import Path
from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker

DATABASE_PATH = Path(__file__).resolve().parent / "reflex.db"
SQLALCHEMY_DATABASE_URL = f"sqlite:///{DATABASE_PATH.as_posix()}"

# Create SQLite engine
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False}
)

# Enforce SQLite PRAGMAs on every connection
@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    if isinstance(dbapi_connection, sqlite3.Connection):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys = ON;")
        cursor.execute("PRAGMA journal_mode = WAL;")
        cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()