"""
Abstract base class for all MQTT services.

MqttService centralises the repeated TLS client setup, connection,
and loop management that would otherwise be copy-pasted across
SensorPublisher, SensorSubscriber, and ChartService.

Module-level factory:
  build_mqtt_client() — constructs a TLS-configured paho client with
  arbitrary callbacks. Allows Dashboard (which cannot inherit MqttService
  due to Tkinter mainloop constraints) to reuse the same TLS setup without
  duplicating configuration code.

Subclasses must implement:
  - on_connect()  — called by paho when the broker acknowledges connection.
  - on_message()  — called by paho for every received message.
  - run()         — entry point; defines blocking or threaded loop strategy.
"""

import ssl
from abc import ABC, abstractmethod

from paho.mqtt import client as mqtt_client

from config.settings import MQTT


def build_mqtt_client(
    client_id: str,
    on_connect=None,
    on_message=None,
) -> mqtt_client.Client:
    """
    Construct and return a TLS-configured paho MQTT client.

    This module-level factory exposes the shared TLS setup used internally
    by MqttService._build_client() so that non-subclass consumers (e.g.
    Dashboard, which extends tk.Tk) can obtain a correctly configured client
    without duplicating the ssl and paho boilerplate.

    Args:
        client_id:  Unique MQTT client identifier string.
        on_connect: Optional callback assigned to client.on_connect.
        on_message: Optional callback assigned to client.on_message.

    Returns:
        Configured paho Client with TLS enabled and callbacks wired.
    """
    client = mqtt_client.Client(
        client_id=client_id,
        callback_api_version=mqtt_client.CallbackAPIVersion.VERSION1,
    )
    client.tls_set(cert_reqs=ssl.CERT_REQUIRED, tls_version=ssl.PROTOCOL_TLS)
    if on_connect is not None:
        client.on_connect = on_connect
    if on_message is not None:
        client.on_message = on_message
    return client


class MqttService(ABC):
    """
    Abstract base for MQTT-connected services.

    Provides:
      - Shared TLS client construction (_build_client).
      - Convenience connect/disconnect helpers.
      - Abstract interface enforced on all subclasses.
    """

    def __init__(self, client_id_key: str) -> None:
        """
        Args:
            client_id_key: Key into MQTT.client_ids (e.g. 'publisher').
        """
        self._client_id: str             = MQTT.client_ids[client_id_key]
        self._client: mqtt_client.Client = self._build_client()

    # ── Abstract interface ─────────────────────────────────────────────────────

    @abstractmethod
    def run(self) -> None:
        """Start the service. Implementations decide blocking vs threaded."""

    @abstractmethod
    def on_connect(self, client, userdata, flags, rc: int) -> None:
        """Called by paho when broker connection is acknowledged."""

    @abstractmethod
    def on_message(self, client, userdata, msg) -> None:
        """Called by paho for every message received on subscribed topics."""

    # ── Shared helpers (inherited by all subclasses) ───────────────────────────

    def _build_client(self) -> mqtt_client.Client:
        """
        Construct and configure a paho MQTT client with TLS.

        Delegates to the module-level build_mqtt_client() factory so that
        the TLS logic lives in exactly one place and is reusable by both
        MqttService subclasses and non-subclass consumers such as Dashboard.

        Returns:
            Configured client with on_connect and on_message wired to self.
        """
        return build_mqtt_client(
            client_id=self._client_id,
            on_connect=self.on_connect,
            on_message=self.on_message,
        )

    def _connect(self) -> None:
        """Connect to the configured broker."""
        print(f"{self.__class__.__name__}: connecting to {MQTT.broker}:{MQTT.port} (TLS)...")
        self._client.connect(MQTT.broker, MQTT.port)

    def _disconnect(self) -> None:
        """Stop loop and disconnect cleanly."""
        self._client.loop_stop()
        self._client.disconnect()

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(client_id={self._client_id!r})"
