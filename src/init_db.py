from src.database import Base, engine
from src import models

Base.metadata.create_all(bind=engine)

print("Database tables created successfully.")