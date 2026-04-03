"""
Chart Data Service

Listens for chart data requests on MQTT (TLS), queries the SQLite database
for aggregated time-series data, and publishes the encrypted JSON response.

Inherits shared MQTT client construction and TLS setup from MqttService.

QoS levels:
  - Subscribe to requests at QoS 1: a missed request means a missing chart.
  - Publish responses at QoS 0: the dashboard has its own timeout/retry logic,
    and re-delivering large encrypted JSON payloads wastes broker bandwidth.
"""

import json

from config.settings import MQTT, SENSOR
from core.crypto import CIPHER
from core.database import DB
from services.base_service import MqttService


class ChartService(MqttService):
    """
    Serves aggregated sensor chart data over MQTT.

    Inherits from MqttService:
      - TLS-configured paho client
      - _connect() helper
    """

    def __init__(self) -> None:
        super().__init__("chart_service")

    # ── MqttService interface ──────────────────────────────────────────────────

    def run(self) -> None:
        """Connect and enter the blocking message loop."""
        print(f"{self!r} starting (AES-256-GCM)...")
        self._connect()
        self._client.loop_forever()

    def on_connect(self, client, userdata, flags, rc: int) -> None:
        """Subscribe to chart request topic at QoS 1 on connection."""
        if rc == 0:
            client.subscribe(MQTT.topics["chart_request"], qos=MQTT.qos_chart_request)
            print(
                f"{self!r} connected. "
                f"Listening on {MQTT.topics['chart_request']} — QoS {MQTT.qos_chart_request}\n"
            )
        else:
            print(f"{self!r} connection failed (code {rc}).")

    def on_message(self, client, userdata, msg) -> None:
        """Validate request, query the database, and publish an encrypted response."""
        print("Chart request received")
        result = self._process_request(msg.payload.decode("utf-8"))
        client.publish(
            MQTT.topics["chart_response"],
            CIPHER.encrypt_json(result),
            qos=MQTT.qos_chart_response,
        )
        print(
            f"Sent encrypted response ({len(result.get('points', []))} points) "
            f"to {MQTT.topics['chart_response']}\n"
        )

    # ── Private helpers ────────────────────────────────────────────────────────

    def _process_request(self, raw_payload: str) -> dict:
        """
        Parse and validate an incoming chart request payload.

        Args:
            raw_payload: Raw UTF-8 string from the MQTT message.

        Returns:
            Chart data dict, or {"error": ...} on validation failure.
        """
        try:
            request = json.loads(raw_payload)
            sensor  = request.get("sensor", "").lower()
            range_v = request.get("range")

            if not SENSOR.is_valid(sensor):
                raise ValueError(f"Invalid sensor: '{sensor}'")
            if range_v is None:
                raise ValueError("Missing 'range' field")

            print(f"Sensor: {sensor} | Range: {range_v}")
            return DB.query_chart_data(sensor, range_v)

        except (json.JSONDecodeError, ValueError) as exc:
            print(f"Bad request: {exc}\n")
            return {"error": str(exc)}


# ── Entry point ────────────────────────────────────────────────────────────────

def main() -> None:
    """Instantiate and run the service. Entry point for direct execution."""
    ChartService().run()


if __name__ == "__main__":
    main()
