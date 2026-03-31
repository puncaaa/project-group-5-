import sqlite3
from datetime import datetime
from paho.mqtt import client as mqtt_client

# ========== MQTT SETTINGS ==========
BROKER = "broker.hivemq.com"
PORT = 1883                             # Standard port
BASE_TOPIC = "smarthome/security/sensors/#"
CLIENT_ID = "security-subscriber-storage"

# ========== DATABASE ==========
DB_NAME = "smarthome_security.db"


# ========== DATABASE ==========
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


def save_to_db(sensor: str, value: int):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    # Получаем sensor_id (или создаём новый сенсор)
    cursor.execute(
        "INSERT OR IGNORE INTO sensors (sensor_name) VALUES (?)", (sensor,)
    )
    cursor.execute(
        "SELECT sensor_id FROM sensors WHERE sensor_name = ?", (sensor,)
    )
    sensor_id = cursor.fetchone()[0]

    # Теперь вставляем данные по sensor_id
    cursor.execute(
        "INSERT INTO sensor_data (sensor_id, value, timestamp) VALUES (?, ?, ?)",
        (sensor_id, value, datetime.now().isoformat())
    )

    conn.commit()
    conn.close()


# ========== MQTT CALLBACKS ==========
def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("Connected to MQTT broker")
        client.subscribe(BASE_TOPIC)
        print(f"Subscribed to {BASE_TOPIC}")
    else:
        print(f"Connection failed with code {rc}")


def on_message(client, userdata, msg):
    sensor = msg.topic.split("/")[-1]
    raw_payload = msg.payload.decode("utf-8")

    try:
        value = int(raw_payload)
        print(f"{sensor} → {value}")
        save_to_db(sensor, value)
        print("Saved to database\n")

    except ValueError as e:
        print(f"Invalid value for {sensor}: {e}\n")
    except Exception as e:
        print(f"Unexpected error processing {sensor}: {e}\n")


# ========== MQTT SETUP ==========
def main():
    init_db()

    client = mqtt_client.Client(
        client_id=CLIENT_ID,
        callback_api_version=mqtt_client.CallbackAPIVersion.VERSION1
    )

    client.on_connect = on_connect
    client.on_message = on_message

    print("Connecting to MQTT broker (port 1883)...")
    client.connect(BROKER, PORT)

    client.loop_forever()


if __name__ == "__main__":
    main()
