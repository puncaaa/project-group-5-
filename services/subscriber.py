"""
Sensor Subscriber / Storage Service

Subscribes to all sensor topics over MQTT (TLS), decrypts each payload
with AES-256-GCM, persists the reading to the SQLite database, and
detects emergency conditions based on configured thresholds.

Inherits shared MQTT client construction and TLS setup from MqttService.
QoS 1 on the subscription matches the publisher's QoS 1, ensuring the
broker delivers each reading at least once before acknowledging.
"""

from config.settings import MQTT, DATABASE
from core.crypto import CIPHER
from core.database import DB
from services.base_service import MqttService


class SensorSubscriber(MqttService):
    """
    Receives, decrypts, stores sensor data, and checks emergency thresholds.

    Inherits from MqttService:
      - TLS-configured paho client
      - _connect() helper
    """

    def __init__(self) -> None:
        super().__init__("subscriber")
        DB.init_schema()

    # ── MqttService interface ──────────────────────────────────────────────────

    def run(self) -> None:
        """Connect and enter the blocking message loop."""
        self._connect()
        self._client.loop_forever()

    def on_connect(self, client, userdata, flags, rc: int) -> None:
        """Subscribe to the sensor wildcard topic at QoS 1 on connection."""
        if rc == 0:
            client.subscribe(MQTT.topics["sensors_wildcard"], qos=MQTT.qos_sensor)
            print(
                f"{self!r} connected. "
                f"Subscribed to {MQTT.topics['sensors_wildcard']} — QoS {MQTT.qos_sensor}"
            )
        else:
            print(f"{self!r} connection failed (code {rc}).")

    def on_message(self, client, userdata, msg) -> None:
        """Decrypt the payload, write the reading to the database, and check thresholds."""
        sensor = msg.topic.split("/")[-1]
        print(f"{sensor} -> (encrypted payload received)")
        try:
            value = CIPHER.decrypt_int(msg.payload.decode("utf-8"))
            print(f"Decrypted value: {value}")
            DB.save_reading(sensor, value)
            print("Saved to database")
            self._check_emergency(sensor, value)
            print()
        except ValueError as exc:
            print(f"Decryption/integrity check failed for {sensor}: {exc}\n")
        except Exception as exc:
            print(f"Unexpected error processing {sensor}: {exc}\n")

    # ── Private helpers ────────────────────────────────────────────────────────

    @staticmethod
    def _check_emergency(sensor: str, value: int) -> None:
        """
        Check whether a reading crosses its configured emergency threshold
        and print an alert if so.

        Flame: high ADC = safe, low ADC = danger → emergency when BELOW threshold.
        Gas, Water: low ADC = safe, high ADC = danger → emergency when ABOVE threshold.

        Args:
            sensor: Sensor name key (e.g. 'flame', 'gas').
            value:  Decrypted integer reading.
        """
        threshold = DATABASE.threshold_for(sensor)
        if threshold is None:
            return

        is_emergency = (
            value <= threshold if sensor == "flame"
            else value >= threshold
        )
        if is_emergency:
            print(f"EMERGENCY: {sensor} = {value} (threshold {threshold})")


# ── Entry point ────────────────────────────────────────────────────────────────

def main() -> None:
    """Instantiate and run the service. Entry point for direct execution."""
    SensorSubscriber().run()


if __name__ == "__main__":
    main()
