"""
Central configuration for the SmartHome Security system.

All configuration is expressed as frozen dataclasses so that:
  - Values are immutable at runtime (no accidental mutation).
  - Each config domain has typed methods for safe access.
  - __repr__ is controlled to prevent key material appearing in logs.

Module-level singletons (MQTT, CRYPTO, DATABASE, SENSOR) are imported
directly by services — no service instantiates a config class itself.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class MqttConfig:
    """Immutable MQTT broker, topic, and QoS configuration."""

    broker: str
    port: int
    client_ids: dict
    topics: dict

    # QoS levels:
    #   1 — at-least-once:   sensor readings and chart requests must not be lost.
    #   0 — fire-and-forget: chart responses; dashboard has its own timeout/retry.
    qos_sensor: int
    qos_chart_request: int
    qos_chart_response: int

    def sensor_topic(self, sensor_name: str) -> str:
        """Return the full MQTT publish topic for a named sensor."""
        return f"{self.topics['sensors_base']}/{sensor_name}"

    def __repr__(self) -> str:
        return f"MqttConfig(broker={self.broker!r}, port={self.port})"


@dataclass(frozen=True)
class CryptoConfig:
    """Immutable AES-256-GCM encryption configuration."""

    aes_key: bytes

    def __repr__(self) -> str:
        # Never expose key material in logs or debug output.
        return "CryptoConfig(aes_key=<redacted>)"


@dataclass(frozen=True)
class DatabaseConfig:
    """Immutable SQLite database and emergency threshold configuration."""

    db_name: str
    # Emergency thresholds: None means no threshold check applies for that sensor.
    thresholds: dict

    def threshold_for(self, sensor: str) -> "int | None":
        """Return the emergency trigger threshold for a sensor, or None."""
        return self.thresholds.get(sensor)

    def __repr__(self) -> str:
        return f"DatabaseConfig(db_name={self.db_name!r})"


@dataclass(frozen=True)
class SensorConfig:
    """Immutable sensor simulation, validation, and timing configuration."""

    valid_sensors: frozenset
    ranges: dict
    publish_interval: float
    chart_timeout_sec: int

    def is_valid(self, sensor: str) -> bool:
        """Return True if the sensor name is in the recognised set."""
        return sensor in self.valid_sensors

    def range_for(self, sensor: str) -> tuple:
        """Return the (min, max) ADC simulation range for a named sensor."""
        return self.ranges[sensor]

    def __repr__(self) -> str:
        return f"SensorConfig(sensors={set(self.valid_sensors)!r})"


# ── Module-level singletons ────────────────────────────────────────────────────
# Import these in services; do not instantiate the dataclasses directly.

MQTT = MqttConfig(
    broker="broker.hivemq.com",
    port=8883,
    client_ids={
        "publisher":     "security-publisher",
        "subscriber":    "security-subscriber-storage",
        "chart_service": "security-chart-service",
        "dashboard":     "security-dashboard",
    },
    topics={
        "sensors_base":     "smarthome/security/sensors",
        "sensors_wildcard": "smarthome/security/sensors/#",
        "chart_request":    "smarthome/security/charts/request",
        "chart_response":   "smarthome/security/charts/response",
    },
    qos_sensor=1,
    qos_chart_request=1,
    qos_chart_response=0,
)

CRYPTO = CryptoConfig(
    aes_key=bytes.fromhex(
        "dd75fc2d686e27a660a25fb5dfa94910e0e9bb4a40f3fe8e89178f93b5de2222"
    ),
)

DATABASE = DatabaseConfig(
    db_name="smarthome_security.db",
    thresholds={
        "flame": 400,   # Emergency if value BELOW threshold (flame detected)
        "gas":   500,   # Emergency if value ABOVE threshold (gas present)
        "water": 500,   # Emergency if value ABOVE threshold (water detected)
        "light": None,  # Digital on/off — no emergency threshold applies
    },
)

SENSOR = SensorConfig(
    valid_sensors=frozenset({"flame", "gas", "water", "light"}),
    ranges={
        "flame": (0, 1023),
        "gas":   (0, 1023),
        "water": (0, 1023),
        "light": (0, 1),
    },
    publish_interval=2.0,
    chart_timeout_sec=15,
)
