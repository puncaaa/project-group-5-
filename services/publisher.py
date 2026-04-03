"""
Sensor Publisher Service

Reads a JSON sensor frame from an Arduino over USB serial and publishes
each sensor value as an AES-256-GCM encrypted payload over MQTT with
TLS (port 8883).

Inherits shared MQTT client construction and TLS setup from MqttService.
QoS 1 is used for all sensor publishes: at-least-once delivery guarantees
that no reading is silently lost between the publisher and the subscriber.

Serial frame format expected from Arduino (one line per interval):
    {"flame": 412, "gas": 203, "water": 0, "light": 1}
"""

import json
import time

import serial

from config.settings import MQTT, SENSOR
from core.crypto import CIPHER
from services.base_service import MqttService

# ── Serial configuration ───────────────────────────────────────────────────────
# Adjust SERIAL_PORT to match the port shown in Arduino IDE (e.g. "COM4", "/dev/ttyUSB0").
SERIAL_PORT = "COM3"
BAUD_RATE   = 9600


class SensorPublisher(MqttService):
    """
    Reads live sensor readings from an Arduino over USB serial and publishes
    them to the MQTT broker.

    Inherits from MqttService:
      - TLS-configured paho client
      - _connect() / _disconnect() helpers
    """

    def __init__(self) -> None:
        super().__init__("publisher")
        self._serial: serial.Serial | None = None

    # ── MqttService interface ──────────────────────────────────────────────────

    def run(self) -> None:
        """Open serial port, connect to broker, and publish frames continuously."""
        print(f"Connecting to Arduino on {SERIAL_PORT} at {BAUD_RATE} baud...")
        self._serial = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
        time.sleep(2)  # Wait for Arduino reset after serial open.

        self._connect()
        self._client.loop_start()

        print(f"{self!r} started — Arduino serial (AES-256-GCM + TLS)\n")
        try:
            while True:
                self._publish_frame()
        except KeyboardInterrupt:
            print(f"\n{self!r} stopped.")
        finally:
            self._disconnect()
            if self._serial and self._serial.is_open:
                self._serial.close()

    def on_connect(self, client, userdata, flags, rc: int) -> None:
        """Log connection result; publishing is pull-based so no subscribe needed."""
        if rc == 0:
            print(f"{self!r} connected.")
        else:
            print(f"{self!r} connection failed (code {rc}).")

    def on_message(self, client, userdata, msg) -> None:
        """Publisher does not subscribe to any topics; this is a no-op."""

    # ── Private helpers ────────────────────────────────────────────────────────

    def _read_frame(self) -> dict | None:
        """
        Read one line from the serial port and parse it as a JSON sensor frame.

        Returns:
            Dict of sensor readings, or None if the line is empty or malformed.
        """
        line = self._serial.readline().decode("utf-8").strip()
        if not line:
            return None
        try:
            return json.loads(line)
        except json.JSONDecodeError:
            print(f"Invalid serial data (skipped): {line!r}")
            return None

    def _publish_frame(self) -> None:
        """Read one frame from Arduino, encrypt each value, and publish at QoS 1."""
        frame = self._read_frame()
        if frame is None:
            return

        print(f"Arduino sensor frame: {frame}")

        for sensor, value in frame.items():
            if not SENSOR.is_valid(sensor):
                continue
            self._client.publish(
                MQTT.sensor_topic(sensor),
                CIPHER.encrypt_int(value),
                qos=MQTT.qos_sensor,
            )

        print(f"Published (encrypted) to MQTT — QoS {MQTT.qos_sensor}:")
        for sensor, value in frame.items():
            print(f"  {sensor:<6} -> {value}  (sent as ciphertext)")
        print()


# ── Entry point ────────────────────────────────────────────────────────────────

def main() -> None:
    """Instantiate and run the service. Entry point for direct execution."""
    SensorPublisher().run()


if __name__ == "__main__":
    main()
