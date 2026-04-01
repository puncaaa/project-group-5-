import sqlite3
import ssl
import json
import base64
import os
from datetime import datetime, timedelta
from paho.mqtt import client as mqtt_client
from Crypto.Cipher import AES

# ========== MQTT SETTINGS ==========
BROKER    = "broker.hivemq.com"
PORT      = 8883
CLIENT_ID = "security-chart-service"

REQUEST_TOPIC  = "smarthome/security/charts/request"
RESPONSE_TOPIC = "smarthome/security/charts/response"

# ========== ENCRYPTION ==========
AES_KEY = bytes.fromhex("dd75fc2d686e27a660a25fb5dfa94910e0e9bb4a40f3fe8e89178f93b5de2222")

# ========== DATABASE ==========
DB_NAME = "smarthome_security.db"

VALID_SENSORS = {"flame", "gas", "water", "light"}


# ========== ENCRYPTION FUNCTION ==========

def encrypt_json(data: dict) -> str:
    """
    Encrypt JSON data using AES-256-GCM.
    Returns Base64-encoded encrypted payload.
    """
    nonce = os.urandom(16)
    cipher = AES.new(AES_KEY, AES.MODE_GCM, nonce=nonce)
    plaintext = json.dumps(data, ensure_ascii=False).encode("utf-8")
    ciphertext, tag = cipher.encrypt_and_digest(plaintext)
    
    # Pack: nonce + ciphertext + tag
    payload = base64.b64encode(nonce + ciphertext + tag).decode("utf-8")
    return payload


# ========== DB QUERIES ==========

def query_hours(cursor, sensor_id: int) -> list:
    """Last 24 hours, grouped by each hour."""
    since = (datetime.now() - timedelta(hours=24)).isoformat()
    cursor.execute("""
        SELECT
            strftime('%H:00', timestamp)  AS label,
            AVG(value)                    AS avg,
            MIN(value)                    AS min,
            MAX(value)                    AS max
        FROM sensor_data
        WHERE sensor_id = ? AND timestamp >= ?
        GROUP BY strftime('%Y-%m-%d %H', timestamp)
        ORDER BY timestamp
    """, (sensor_id, since))
    return cursor.fetchall()


def query_days(cursor, sensor_id: int) -> list:
    """Last 30 days, grouped by each day."""
    since = (datetime.now() - timedelta(days=30)).isoformat()
    cursor.execute("""
        SELECT
            strftime('%d.%m', timestamp)  AS label,
            AVG(value)                    AS avg,
            MIN(value)                    AS min,
            MAX(value)                    AS max
        FROM sensor_data
        WHERE sensor_id = ? AND timestamp >= ?
        GROUP BY strftime('%Y-%m-%d', timestamp)
        ORDER BY timestamp
    """, (sensor_id, since))
    return cursor.fetchall()


def query_months(cursor, sensor_id: int) -> list:
    """Last 12 months, grouped by each month."""
    since = (datetime.now() - timedelta(days=365)).isoformat()
    cursor.execute("""
        SELECT
            strftime('%m.%Y', timestamp)  AS label,
            AVG(value)                    AS avg,
            MIN(value)                    AS min,
            MAX(value)                    AS max
        FROM sensor_data
        WHERE sensor_id = ? AND timestamp >= ?
        GROUP BY strftime('%Y-%m', timestamp)
        ORDER BY timestamp
    """, (sensor_id, since))
    return cursor.fetchall()


def query_custom(cursor, sensor_id: int, date_from: str, date_to: str) -> list:
    """
    Arbitrary date range.
    Grouping is selected automatically based on the range width:
      - up to 3 days  -> by hour
      - up to 90 days -> by day
      - otherwise     -> by month
    """
    dt_from = datetime.fromisoformat(date_from)
    dt_to   = datetime.fromisoformat(date_to)
    delta   = (dt_to - dt_from).days

    if delta <= 3:
        group_fmt = '%Y-%m-%d %H'
        label_fmt = '%H:00'
    elif delta <= 90:
        group_fmt = '%Y-%m-%d'
        label_fmt = '%d.%m'
    else:
        group_fmt = '%Y-%m'
        label_fmt = '%m.%Y'

    cursor.execute(f"""
        SELECT
            strftime('{label_fmt}', timestamp) AS label,
            AVG(value)                         AS avg,
            MIN(value)                         AS min,
            MAX(value)                         AS max
        FROM sensor_data
        WHERE sensor_id = ? AND timestamp BETWEEN ? AND ?
        GROUP BY strftime('{group_fmt}', timestamp)
        ORDER BY timestamp
    """, (sensor_id, date_from, date_to))
    return cursor.fetchall()


def build_points(rows: list) -> list:
    """Converts raw DB rows into a list of dicts for JSON serialization."""
    return [
        {
            "label": row[0],
            "avg":   round(row[1], 1),
            "min":   row[2],
            "max":   row[3],
        }
        for row in rows
    ]


def get_chart_data(sensor: str, range_value) -> dict:
    """
    Main query function.
    range_value is either a string ('24h' / '30d' / '12m')
    or a dict {"from": "2025-01-01", "to": "2025-03-01"} for a custom range.
    Returns a dict ready for JSON serialization.
    """
    conn   = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    # Look up sensor_id by name
    cursor.execute("SELECT sensor_id FROM sensors WHERE sensor_name = ?", (sensor,))
    row = cursor.fetchone()

    if row is None:
        conn.close()
        return {"error": f"Unknown sensor: {sensor}"}

    sensor_id = row[0]

    # Select the appropriate query based on the requested range
    if range_value == "24h":
        rows = query_hours(cursor, sensor_id)
        unit = "hour"
    elif range_value == "30d":
        rows = query_days(cursor, sensor_id)
        unit = "day"
    elif range_value == "12m":
        rows = query_months(cursor, sensor_id)
        unit = "month"
    elif isinstance(range_value, dict):
        rows = query_custom(
            cursor, sensor_id,
            range_value["from"],
            range_value["to"]
        )
        unit = "custom"
    else:
        conn.close()
        return {"error": f"Unknown range: {range_value}"}

    conn.close()

    return {
        "sensor": sensor,
        "range":  range_value,
        "unit":   unit,
        "points": build_points(rows)
    }


# ========== MQTT CALLBACKS ==========

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("Chart service connected to MQTT broker")
        client.subscribe(REQUEST_TOPIC)
        print(f"Listening for requests on: {REQUEST_TOPIC}\n")
    else:
        print(f"Connection failed with code: {rc}")


def on_message(client, userdata, msg):
    print("Chart request received")

    try:
        request = json.loads(msg.payload.decode("utf-8"))
        sensor  = request.get("sensor", "").lower()
        range_v = request.get("range")

        # Validate incoming request fields
        if sensor not in VALID_SENSORS:
            raise ValueError(f"Invalid sensor: '{sensor}'")
        if range_v is None:
            raise ValueError("Missing 'range' field")

        print(f"Sensor: {sensor} | Range: {range_v}")

        result = get_chart_data(sensor, range_v)

        # Encrypt the response
        encrypted_payload = encrypt_json(result)

        client.publish(RESPONSE_TOPIC, json.dumps(result))
        print(f"Sent response ({len(result.get('points', []))} points) to {RESPONSE_TOPIC}\n")

    except (json.JSONDecodeError, ValueError) as e:
        # Return encrypted error response
        error_data = {"error": str(e)}
        error_payload = encrypt_json(error_data)
        client.publish(RESPONSE_TOPIC, error_payload)
        print(f"Bad request: {e}\n")

    except Exception as e:
        print(f"Unexpected error: {e}\n")


# ========== MAIN ==========

def main():
    client = mqtt_client.Client(
        client_id=CLIENT_ID,
        callback_api_version=mqtt_client.CallbackAPIVersion.VERSION1
    )
    client.tls_set(tls_version=ssl.PROTOCOL_TLS)
    client.on_connect = on_connect
    client.on_message = on_message

    print("Starting encrypted chart service (AES-256-GCM)...")
    client.connect(BROKER, PORT)
    client.loop_forever()


if __name__ == "__main__":
    main()
