from paho.mqtt import client as mqtt_client
from database import init_db, save_to_db

# ========== MQTT SETTINGS ==========
BROKER = "broker.hivemq.com"
PORT = 1883
BASE_TOPIC = "smarthome/security/sensors/#"
CLIENT_ID = "security-subscriber-storage"


# ---------- MQTT callbacks ----------
def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("Connected to MQTT broker")
        client.subscribe(BASE_TOPIC)
        print(f"Subscribed to {BASE_TOPIC}")
    else:
        print(f"Connection failed with code {rc}")


def on_message(client, userdata, msg):
    sensor = msg.topic.split("/")[-1]
    value = msg.payload.decode()

    print(f"{sensor} → {value}")

    try:
        save_to_db(sensor, int(value))
        print("Saved to database\n")
    except ValueError:
        print("Invalid value received\n")


# ---------- MAIN ----------
def main():
    init_db()

    client = mqtt_client.Client(
        client_id=CLIENT_ID,
        callback_api_version=mqtt_client.CallbackAPIVersion.VERSION1
    )

    client.on_connect = on_connect
    client.on_message = on_message

    print("Connecting to MQTT broker...")
    client.connect(BROKER, PORT)

    client.loop_forever()


if __name__ == "__main__":  
    main()