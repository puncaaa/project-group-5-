import serial
import json
import time
import ssl
from paho.mqtt import client as mqtt_client

# ========== SERIAL SETTINGS ==========
SERIAL_PORT = "COM3"      # Check port in Arduino IDE
BAUD_RATE = 9600

# ========== MQTT SETTINGS ==========
BROKER = "broker.hivemq.com"
PORT = 1883                         # Standard MQTT port
BASE_TOPIC = "smarthome/security/sensors"
CLIENT_ID = f"security-publisher-{int(time.time())}"


# ========== MQTT CONNECT ==========
def connect_mqtt() -> mqtt_client.Client:
    client = mqtt_client.Client(
        client_id=CLIENT_ID,
        callback_api_version=mqtt_client.CallbackAPIVersion.VERSION1
    )

    client.connect(BROKER, PORT)
    return client


# ========== MAIN ==========
def main():
    print("Connecting to security controller (Arduino)...")
    ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
    time.sleep(2)  # Arduino reset delay

    print("Connecting to MQTT broker...")
    mqtt = connect_mqtt()

    print("Security monitoring started\n")

    while True:
        try:
            line = ser.readline().decode("utf-8").strip()

            if not line:
                continue

            print(f"Sensor frame: {line}")

            data = json.loads(line)

            # Publish each sensor value as a plain string
            mqtt.publish(f"{BASE_TOPIC}/flame", str(data["flame"]))
            mqtt.publish(f"{BASE_TOPIC}/gas",   str(data["gas"]))
            mqtt.publish(f"{BASE_TOPIC}/water", str(data["water"]))
            mqtt.publish(f"{BASE_TOPIC}/light", str(data["light"]))

            print("Published to MQTT:")
            print(f"   Flame  → {data['flame']}")
            print(f"   Gas    → {data['gas']}")
            print(f"   Water  → {data['water']}")
            print(f"   Light  → {data['light']}\n")

        except json.JSONDecodeError:
            print("Invalid sensor data format")
        except KeyboardInterrupt:
            print("\nSecurity system stopped")
            break
        except Exception as e:
            print(f"Runtime error: {e}")

    ser.close()


if __name__ == "__main__":
    main()
