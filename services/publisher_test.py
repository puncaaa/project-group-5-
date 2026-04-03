"""
Sensor Publisher — Test / Simulation Mode (no Arduino required)

Drop-in replacement for services/publisher.py for testing without hardware.

Differences from the real publisher:
  - Reads from a software sensor simulator instead of USB serial.
  - Cycles through SAFE -> WARNING -> EMERGENCY states every 3 seconds each.
  - Publish interval is configurable (default: 2 s, same as production).

Usage — run from the project root exactly like the real publisher:
    python run_publisher_test.py
"""

import time
from datetime import datetime

from config.settings import MQTT, SENSOR, DATABASE
from core.crypto import CIPHER
from services.base_service import MqttService


# ── Cycle configuration ────────────────────────────────────────────────────────

PHASE_DURATION = 3.0   # seconds per phase (safe / warning / emergency)


class SensorSimulator:
    """
    Cycles all sensors through SAFE -> WARNING -> EMERGENCY phases,
    each lasting PHASE_DURATION seconds, then repeats.
    """

    def __init__(self) -> None:
        self._start_time = time.time()

    def _current_phase(self) -> str:
        """Return 'safe', 'warning', or 'emergency' based on elapsed time."""
        elapsed = (time.time() - self._start_time) % (PHASE_DURATION * 3)
        if elapsed < PHASE_DURATION:
            return "safe"
        elif elapsed < PHASE_DURATION * 2:
            return "warning"
        else:
            return "emergency"

    def next_frame(self) -> dict:
        """Return one complete sensor frame matching the current phase."""
        phase = self._current_phase()
        print(f"  [Phase: {phase.upper()}]")

        if phase == "safe":
            return {
                "flame": 900,   # high ADC = no flame
                "gas":   70,    # low ADC = clean air
                "water": 35,    # low ADC = dry
                "light": 0,     # light on
            }
        elif phase == "warning":
            return {
                "flame": 550,   # between emergency threshold and safe → warning
                "gas":   350,   # between safe and emergency threshold → warning
                "water": 300,   # between safe and emergency threshold → warning
                "light": 1,
            }
        else:  # emergency
            return {
                "flame": 200,   # below emergency threshold → flame detected
                "gas":   700,   # above emergency threshold → gas present
                "water": 700,   # above emergency threshold → water detected
                "light": 1,
            }

    @staticmethod
    def status_label(sensor: str, value: int) -> str:
        """
        Return a SAFE / WARNING / EMERGENCY label for console output.

        Emergency boundaries are read from DATABASE.threshold_for() — the
        single source of truth in settings.py — to satisfy DRY across the
        whole system. No threshold values are duplicated here.

        Args:
            sensor: Sensor name key (e.g. 'flame', 'gas').
            value:  Raw ADC integer value.

        Returns:
            Human-readable status string for console logging.
        """
        if sensor == "light":
            return "ON" if value == 0 else "off"

        threshold = DATABASE.threshold_for(sensor)
        if threshold is None:
            return "?"

        if sensor == "flame":
            # Flame: low ADC = danger (emergency below threshold).
            if value <= threshold:  return "*** EMERGENCY ***"
            if value < 600:         return "warning"
            return "safe"
        else:
            # Gas / Water: high ADC = danger (emergency above threshold).
            if value >= threshold:  return "*** EMERGENCY ***"
            if value > 350:         return "warning"
            return "safe"


# ── Service ────────────────────────────────────────────────────────────────────

class SimulatedSensorPublisher(MqttService):
    """
    Publishes simulated sensor readings over MQTT with AES-256-GCM + TLS.

    Identical wire format and QoS to the real SensorPublisher — the
    subscriber, chart service, and dashboard need no changes.
    """

    def __init__(self) -> None:
        super().__init__("publisher")
        self._simulator = SensorSimulator()

    # ── MqttService interface ──────────────────────────────────────────────────

    def run(self) -> None:
        """Connect and publish frames continuously at the configured interval."""
        self._connect()
        self._client.loop_start()

        print(f"{self!r} started — SIMULATION MODE (no Arduino needed)\n")
        print(f"  Publish interval : {SENSOR.publish_interval}s")
        print(f"  Phase duration   : {PHASE_DURATION}s each (safe -> warning -> emergency)")
        print(f"  Broker           : {MQTT.broker}:{MQTT.port} (TLS + AES-256-GCM)")
        print(f"  Sensors          : {sorted(SENSOR.valid_sensors)}\n")

        try:
            while True:
                self._publish_frame()
                time.sleep(SENSOR.publish_interval)
        except KeyboardInterrupt:
            print(f"\n{self!r} stopped.")
        finally:
            self._disconnect()

    def on_connect(self, client, userdata, flags, rc: int) -> None:
        if rc == 0:
            print(f"{self!r} connected to broker.\n")
        else:
            print(f"{self!r} connection failed (code {rc}).")

    def on_message(self, client, userdata, msg) -> None:
        """Publisher does not subscribe to any topics; no-op."""

    # ── Private ────────────────────────────────────────────────────────────────

    def _publish_frame(self) -> None:
        """Generate one simulated frame, encrypt each value, and publish at QoS 1."""
        frame = self._simulator.next_frame()

        print(f"[{datetime.now():%H:%M:%S}] Simulated frame: {frame}")

        for sensor, value in frame.items():
            if not SENSOR.is_valid(sensor):
                continue
            self._client.publish(
                MQTT.sensor_topic(sensor),
                CIPHER.encrypt_int(value),
                qos=MQTT.qos_sensor,
            )

        print(f"  Published (encrypted) — QoS {MQTT.qos_sensor}")
        for sensor, value in frame.items():
            status = SensorSimulator.status_label(sensor, value)
            print(f"    {sensor:<6} -> {value:>4}  [{status}]")
        print()


# ── Entry point ────────────────────────────────────────────────────────────────

def main() -> None:
    """Instantiate and run the simulated publisher."""
    SimulatedSensorPublisher().run()


if __name__ == "__main__":
    main()
