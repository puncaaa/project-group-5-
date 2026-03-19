import sqlite3
from datetime import datetime

DB_NAME = "smarthome_security.db"


# ---------- Database setup ----------
def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS sensors (
        sensor_id INTEGER PRIMARY KEY AUTOINCREMENT,
        sensor_name TEXT UNIQUE NOT NULL
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS sensor_data (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sensor_id INTEGER NOT NULL,
        value INTEGER NOT NULL,
        timestamp TEXT NOT NULL,
        FOREIGN KEY(sensor_id) REFERENCES sensors(sensor_id)
    )
    """)

    conn.commit()
    conn.close()


# ---------- Get or create sensor ----------
def get_sensor_id(sensor_name):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute(
        "SELECT sensor_id FROM sensors WHERE sensor_name=?",
        (sensor_name,)
    )

    result = cursor.fetchone()

    if result:
        sensor_id = result[0]
    else:
        cursor.execute(
            "INSERT INTO sensors (sensor_name) VALUES (?)",
            (sensor_name,)
        )
        sensor_id = cursor.lastrowid

    conn.commit()
    conn.close()

    return sensor_id


# ---------- Save data ----------
def save_to_db(sensor_name, value):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    sensor_id = get_sensor_id(sensor_name)

    cursor.execute(
        "INSERT INTO sensor_data (sensor_id, value, timestamp) VALUES (?, ?, ?)",
        (sensor_id, value, datetime.now().isoformat())
    )

    conn.commit()
    conn.close()