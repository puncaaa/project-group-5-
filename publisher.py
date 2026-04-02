import serial
import json
import time
import ssl
import base64
import os
from paho.mqtt import client as mqtt_client
from Crypto.Cipher import AES

# ========== SERIAL SETTINGS ==========
SERIAL_PORT = "COM3"      # Check port in Arduino IDE
BAUD_RATE = 9600

# ========== MQTT SETTINGS ==========
BROKER = "broker.hivemq.com"
PORT = 8883                         # TLS port
BASE_TOPIC = "smarthome/security/sensors"
CLIENT_ID = f"security-publisher-{int(time.time())}"

# ========== ENCRYPTION SETTINGS ==========
# IMPORTANT: This key must be IDENTICAL in both scripts (32 bytes = AES-256)
# You can generate a new one with: os.urandom(32).hex()
# Then paste the same hex string in both files
AES_KEY = bytes.fromhex("dd75fc2d686e27a660a25fb5dfa94910e0e9bb4a40f3fe8e89178f93b5de2222")


# ========== ENCRYPTION ==========
def encrypt(value: int) -> str:
    """
    Encrypts an integer sensor value using AES-256-GCM.
    Returns a Base64-encoded string in the format: nonce:ciphertext:tag
    A fresh random 16-byte nonce is generated for every message.
    """
    nonce = os.urandom(16)
    cipher = AES.new(AES_KEY, AES.MODE_GCM, nonce=nonce)
    plaintext = str(value).encode("utf-8")
    ciphertext, tag = cipher.encrypt_and_digest(plaintext)

    # Pack nonce + ciphertext + auth tag into one Base64 string
    payload = base64.b64encode(nonce + ciphertext + tag).decode("utf-8")
    return payload


# ========== MQTT CONNECT (TLS) ==========
def connect_mqtt() -> mqtt_client.Client:
    client = mqtt_client.Client(
        client_id=CLIENT_ID,
        callback_api_version=mqtt_client.CallbackAPIVersion.VERSION1
    )

    # Enable TLS — uses system CA certificates to verify HiveMQ's certificate
    client.tls_set(cert_reqs=ssl.CERT_REQUIRED, tls_version=ssl.PROTOCOL_TLS)

    client.connect(BROKER, PORT)
    return client


# ========== MAIN ==========
def main():
    print("Connecting to security controller (Arduino)...")
    ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
    time.sleep(2)  # Arduino reset delay

    print("Connecting to MQTT broker (TLS port 8883)...")
    mqtt = connect_mqtt()

    print("Security monitoring started (AES-256-GCM + TLS)\n")

    while True:
        try:
            line = ser.readline().decode("utf-8").strip()

            if not line:
                continue

            print(f"Sensor frame: {line}")

            data = json.loads(line)

            # Encrypt each sensor value individually before publishing
            mqtt.publish(f"{BASE_TOPIC}/flame", encrypt(data["flame"]))
            mqtt.publish(f"{BASE_TOPIC}/gas",   encrypt(data["gas"]))
            mqtt.publish(f"{BASE_TOPIC}/water", encrypt(data["water"]))
            mqtt.publish(f"{BASE_TOPIC}/light", encrypt(data["light"]))

            print("Published (encrypted) to MQTT:")
            print(f"Flame  → {data['flame']}  (sent as ciphertext)")
            print(f"Gas    → {data['gas']}  (sent as ciphertext)")
            print(f"Water  → {data['water']}  (sent as ciphertext)")
            print(f"Light  → {data['light']}  (sent as ciphertext)\n")

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
