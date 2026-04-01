import sqlite3
import ssl
import base64
from datetime import datetime
from paho.mqtt import client as mqtt_client
from Crypto.Cipher import AES

# ========== MQTT SETTINGS ==========
BROKER = "broker.hivemq.com"
PORT = 8883                             # Standard port
BASE_TOPIC = "smarthome/security/sensors/#"
CLIENT_ID = "security-subscriber-storage"

# ========== ENCRYPTION SETTINGS ==========
# ⚠️ IMPORTANT: Must be IDENTICAL to the key in MQTT_Sender_Home.py
AES_KEY = bytes.fromhex("dd75fc2d686e27a660a25fb5dfa94910e0e9bb4a40f3fe8e89178f93b5de2222")

# ========== DATABASE ==========
DB_NAME = "smarthome_security.db"


# ========== DECRYPTION ==========
def decrypt(payload: str) -> int:
    """
    Decrypts a Base64-encoded AES-256-GCM payload back to an integer.
    Raises ValueError if the message has been tampered with (tag mismatch).
    Format expected: Base64(nonce[16] + ciphertext + tag[16])
    """
    raw = base64.b64decode(payload)

    nonce      = raw[:16]
    tag        = raw[-16:]
    ciphertext = raw[16:-16]

    cipher = AES.new(AES_KEY, AES.MODE_GCM, nonce=nonce)
    plaintext = cipher.decrypt_and_verify(ciphertext, tag)  # raises ValueError if tampered

    return int(plaintext.decode("utf-8"))


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

    print(f"{sensor} → (encrypted payload received)")

    try:
        value = decrypt(raw_payload)
        print(f"Decrypted value: {value}")
        save_to_db(sensor, value)
        print("Saved to database\n")

    except ValueError as e:
        # GCM tag mismatch — message was tampered with or key is wrong
        print(f"Decryption/integrity check failed for {sensor}: {e}\n")
    except Exception as e:
        print(f"Unexpected error processing {sensor}: {e}\n")


# ========== MQTT SETUP ==========
def main():
    init_db()

    client = mqtt_client.Client(
        client_id=CLIENT_ID,
        callback_api_version=mqtt_client.CallbackAPIVersion.VERSION1
    )

    # Enable TLS
    client.tls_set(cert_reqs=ssl.CERT_REQUIRED, tls_version=ssl.PROTOCOL_TLS)

    client.on_connect = on_connect
    client.on_message = on_message

    print("Connecting to MQTT broker (port 1883)...")
    client.connect(BROKER, PORT)

    client.loop_forever()


if __name__ == "__main__":
    main()
