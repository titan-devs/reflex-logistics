import sqlite3

db = sqlite3.connect("reflex_logistics.db")

tables = db.execute(
    "SELECT name FROM sqlite_master "
    "WHERE type='table' ORDER BY name"
).fetchall()

print("Tables:")
for table in tables:
    print(f" - {table[0]}")

db.close()