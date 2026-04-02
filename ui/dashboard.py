"""
Home Security Dashboard

Tkinter GUI providing:
  - Realtime tab: live sensor values with colour-coded status indicators.
  - Analysis tab: historical charts loaded on demand from ChartService.

All MQTT traffic is AES-256-GCM encrypted. TLS is used on port 8883.

QoS levels:
  - Sensor subscription:   QoS 1 - readings must not be silently lost.
  - Chart request publish: QoS 1 - the request must reach ChartService.
  - Chart response sub:    QoS 0 - timeout/retry logic is in the UI.

Classes:
  SensorStatusClassifier  - stateless classifier; maps sensor readings to
                            display colours and status labels.
  Dashboard               - main Tk window; owns MQTT lifecycle and both tabs.
"""

import json
import threading
import time
import tkinter as tk
from tkinter import ttk

from winotify import Notification, audio
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
from paho.mqtt import client as mqtt_client

from config.settings import MQTT, SENSOR, DATABASE
from core.crypto import CIPHER
from services.base_service import build_mqtt_client


class SensorStatusClassifier:
    """
    Classifies a raw sensor reading into a display colour and status label.

    All threshold constants are defined as class-level attributes so they
    are visible and changeable without touching method bodies. Emergency
    thresholds (the danger boundary) are sourced from the DATABASE singleton
    in settings.py - the single source of truth - to avoid duplication.
    Each sensor has its own private @classmethod, dispatched by name through
    classify(). This keeps Dashboard free of nested conditionals and makes
    adding a new sensor a matter of adding one @classmethod here only.
    """

    # Class-level display-only threshold constants.
    # These "safe" boundaries exist only for UI colour banding and are not
    # duplicated elsewhere in the system.
    # Flame: high ADC = no flame (sensor reads high in ambient light).
    _FLAME_SAFE  = 800   # >= 800 -> Good

    # Gas: low ADC = clean air; rising value indicates gas presence.
    _GAS_SAFE    = 150   # <= 150 -> Good

    # Water: low ADC = dry; rising value means water present.
    _WATER_GOOD  = 150   # <= 150 -> Good (dry)

    # Emergency (danger) boundaries are NOT defined here.
    # They are read from DATABASE.threshold_for() - the single source of
    # truth declared in settings.py - to satisfy DRY across the whole system.

    @classmethod
    def classify(cls, sensor: str, value: int) -> tuple:
        """
        Return the (colour, status_text) pair for a sensor reading.

        Dispatches to a per-sensor @classmethod named _classify_<sensor>.
        Falls back to _classify_unknown for any unrecognised sensor name.

        Args:
            sensor: Sensor name key (e.g. 'flame', 'gas').
            value:  Decrypted integer ADC reading.

        Returns:
            Tuple of (Tk colour string, human-readable status label).
        """
        handler = getattr(cls, f"_classify_{sensor}", cls._classify_unknown)
        return handler(value)

    @classmethod
    def _classify_flame(cls, value: int) -> tuple:
        """High ADC = no flame (sensor reads high in ambient light)."""
        danger_threshold = DATABASE.threshold_for("flame")
        if value >= cls._FLAME_SAFE:   return "green",  "Good"
        if value >= danger_threshold:  return "orange", "Warning"
        return "red", "DANGER"

    @classmethod
    def _classify_gas(cls, value: int) -> tuple:
        """Low ADC = clean air; rising value indicates gas presence."""
        danger_threshold = DATABASE.threshold_for("gas")
        if value <= cls._GAS_SAFE:     return "green",  "Good"
        if value <= danger_threshold:  return "orange", "Warning"
        return "red", "DANGER"

    @classmethod
    def _classify_water(cls, value: int) -> tuple:
        """Low ADC = dry; rising value means water present."""
        danger_threshold = DATABASE.threshold_for("water")
        if value <= cls._WATER_GOOD:   return "green",  "Good"
        if value <= danger_threshold:  return "orange", "Warning"
        return "red", "WET"

    @staticmethod
    def _classify_light(value: int) -> tuple:
        """Digital sensor: 0 = light ON (good), 1 = light OFF."""
        return ("green", "On") if value == 0 else ("red", "Off")

    @staticmethod
    def _classify_unknown(_value: int) -> tuple:
        """Fallback for any sensor name not explicitly handled."""
        return "gray", "Unknown"

    def __repr__(self) -> str:
        return "SensorStatusClassifier()"


class Dashboard(tk.Tk):
    """
    Main application window for the SmartHome Security system.

    Responsibilities:
      - Owns and manages the MQTT client lifecycle (connect/disconnect).
      - Routes incoming MQTT messages to the realtime display or chart handler.
      - Builds and maintains the Realtime and Analysis UI tabs.
      - Delegates sensor classification to SensorStatusClassifier.

    The MQTT client is constructed via the shared build_mqtt_client() factory
    from base_service rather than duplicating TLS configuration inline.
    Dashboard extends tk.Tk rather than MqttService because Tkinter's mainloop
    is incompatible with the blocking loop strategies used by the service base
    class (loop_forever / loop_start require a separate thread context).
    """

    # Class-level UI and behaviour constants
    _SENSOR_META: list = [
        ("Flame Sensor", "flame", "#FF5252"),
        ("Gas Sensor",   "gas",   "#FFC107"),
        ("Water Sensor", "water", "#2196F3"),
        ("Light Sensor", "light", "#4CAF50"),
    ]
    _CHART_SENSORS:      list = ["flame", "gas", "water"]
    _CHART_COLORS:       dict = {"flame": "#FF5252", "gas": "#FFC107", "water": "#2196F3"}

    # Minimum seconds that must pass before the same sensor can fire another
    # Windows notification. Prevents alert spam while a sensor stays in emergency.
    _ALERT_COOLDOWN_SEC: int  = 30

    def __init__(self) -> None:
        super().__init__()
        self.title("Home Security Dashboard")
        self.geometry("1000x700")
        self.minsize(900, 650)

        # MQTT state
        self._mqtt:       mqtt_client.Client | None = None
        self._connected:  bool = False

        # Data state
        self._sensor_vals: dict = {s: 0 for _, s, _ in self._SENSOR_META}
        self._chart_data:  dict = {}
        self._timeout_id:  str | None = None

        # Notification cooldown: maps sensor name -> monotonic timestamp of last alert.
        # One notification per sensor per _ALERT_COOLDOWN_SEC window.
        self._last_alert:  dict[str, float] = {}

        # Composed classifier - injected as instance so it can be replaced in tests.
        self._classifier: SensorStatusClassifier = SensorStatusClassifier()

        self._build_ui()

    # Properties

    @property
    def is_connected(self) -> bool:
        """True when the MQTT client is currently connected to the broker."""
        return self._connected

    # UI construction

    def _build_ui(self) -> None:
        """Assemble the top bar and tabbed notebook."""
        self._build_top_bar()
        self._build_notebook()

    def _build_top_bar(self) -> None:
        """Build the header bar containing the title, status label, and connect button."""
        bar = tk.Frame(self, bg="#f0f0f0", height=60)
        bar.pack(fill="x")
        bar.pack_propagate(False)

        tk.Label(
            bar, text="Home Security Dashboard",
            font=("Arial", 14, "bold"), bg="#f0f0f0",
        ).pack(side="left", padx=20)

        self._status_lbl = tk.Label(
            bar, text="Disconnected",
            fg="red", font=("Arial", 11, "bold"), bg="#f0f0f0",
        )
        self._status_lbl.pack(side="left", padx=20)

        self._connect_btn = tk.Button(
            bar, text="Connect", command=self._toggle_connection,
            width=12, bg="#4CAF50", fg="white",
            font=("Arial", 10, "bold"), activebackground="#45a049",
        )
        self._connect_btn.pack(side="right", padx=20, pady=12)

    def _build_notebook(self) -> None:
        """Create the tabbed notebook and populate the Realtime and Analysis tabs."""
        style = ttk.Style()
        style.configure("TNotebook.Tab", font=("Arial", 11), padding=[20, 10])

        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True, padx=10, pady=10)

        realtime_frame = tk.Frame(notebook)
        notebook.add(realtime_frame, text="Realtime")
        self._build_realtime_tab(realtime_frame)

        analysis_container = tk.Frame(notebook)
        notebook.add(analysis_container, text="Analysis")
        self._build_analysis_tab(analysis_container)

    def _build_realtime_tab(self, parent: tk.Frame) -> None:
        """Build the live sensor display panel with one card per sensor."""
        tk.Label(
            parent, text="Real-time Sensor Data",
            font=("Arial", 16, "bold"),
        ).pack(pady=20)

        self._sensor_labels: dict[str, tk.Label] = {}

        for name, key, _ in self._SENSOR_META:
            frame = tk.Frame(parent, bg="white", relief="solid", bd=1)
            frame.pack(fill="x", padx=50, pady=10)

            tk.Label(frame, text=name, font=("Arial", 12, "bold"), bg="white").pack(
                anchor="w", padx=20, pady=(15, 5),
            )
            lbl = tk.Label(
                frame, text="Waiting for data...",
                font=("Arial", 14), bg="white", fg="gray",
            )
            lbl.pack(anchor="w", padx=20, pady=(0, 15))
            self._sensor_labels[key] = lbl

    def _build_analysis_tab(self, parent: tk.Frame) -> None:
        """Build the scrollable analysis tab containing chart controls and panels."""
        canvas    = tk.Canvas(parent)
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        inner     = tk.Frame(canvas)

        inner.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        self._build_chart_controls(inner)
        self._build_chart_panels(inner)

    def _build_chart_controls(self, parent: tk.Frame) -> None:
        """Build the time-range selector and Load Charts button."""
        control_frame = tk.Frame(parent, bg="white", relief="solid", bd=1)
        control_frame.pack(fill="x", padx=20, pady=20)

        inner = tk.Frame(control_frame, bg="white")
        inner.pack(padx=15, pady=15)

        tk.Label(
            inner, text="Time Range:",
            font=("Arial", 11, "bold"), bg="white",
        ).pack(side="left", padx=10)

        self._time_var = tk.StringVar(value="24h")
        for text, val in [("24 Hours", "24h"), ("30 Days", "30d"), ("12 Months", "12m")]:
            tk.Radiobutton(
                inner, text=text, variable=self._time_var, value=val,
                font=("Arial", 10), bg="white",
            ).pack(side="left", padx=8)

        self._load_btn = tk.Button(
            inner, text="Load Charts", command=self._load_charts,
            bg="#2196F3", fg="white", font=("Arial", 10, "bold"),
            width=12, activebackground="#1976D2",
        )
        self._load_btn.pack(side="left", padx=15)

        self._chart_status = tk.Label(
            inner, text="", fg="gray", font=("Arial", 10), bg="white",
        )
        self._chart_status.pack(side="left", padx=10)

    def _build_chart_panels(self, parent: tk.Frame) -> None:
        """Create one matplotlib chart panel per chart sensor."""
        charts_frame = tk.Frame(parent)
        charts_frame.pack(fill="both", expand=True, padx=20, pady=10)

        self._charts: dict[str, tuple] = {}

        for sensor in self._CHART_SENSORS:
            container = tk.Frame(charts_frame, bg="white", relief="solid", bd=1)
            container.pack(fill="x", pady=8)

            fig = Figure(figsize=(9, 3), dpi=80)
            ax  = fig.add_subplot(111)
            ax.text(
                0.5, 0.5,
                f"{sensor.capitalize()} - click 'Load Charts' to view data",
                ha="center", va="center", fontsize=12, color="gray",
            )
            ax.axis("off")

            cv = FigureCanvasTkAgg(fig, container)
            cv.draw()
            cv.get_tk_widget().pack(fill="both", expand=True, padx=10, pady=10)

            self._charts[sensor] = (fig, ax, cv, self._CHART_COLORS[sensor])

    # MQTT connection management

    def _toggle_connection(self) -> None:
        """Connect if disconnected; disconnect if connected."""
        if self._connected:
            self._disconnect()
        else:
            self._connect()

    def _connect(self) -> None:
        """
        Build the MQTT client via the shared factory, configure callbacks,
        and initiate the broker connection.

        Uses build_mqtt_client() from base_service to avoid duplicating the
        TLS setup that all other services share.
        """
        # Disable the button while connecting to prevent the user firing a second
        # connect before the first completes - each attempt spawns a paho thread.
        self._connect_btn.config(state="disabled")
        self._status_lbl.config(text="Connecting...", fg="orange")

        self._mqtt = build_mqtt_client(
            client_id=MQTT.client_ids["dashboard"],
            on_connect=self._on_connect,
            on_message=self._on_message,
        )

        try:
            self._mqtt.connect(MQTT.broker, MQTT.port)
            # loop_start() runs paho in a background thread, keeping Tk mainloop free.
            self._mqtt.loop_start()
        except Exception as exc:
            self._connect_btn.config(state="normal")
            self._status_lbl.config(text=f"Error: {exc}", fg="red")

    def _disconnect(self) -> None:
        """Stop the background MQTT loop and disconnect cleanly."""
        self._connect_btn.config(state="disabled")
        client = self._mqtt
        self._mqtt = None
        self._connected = False

        self._status_lbl.config(text="Disconnected", fg="red")
        self._connect_btn.config(text="Connect", bg="#4CAF50")

        for lbl in self._sensor_labels.values():
            lbl.config(text="Waiting for data...", fg="gray")

        if client:
            # loop_stop() blocks until the paho thread exits - calling it on the
            # main thread causes a deadlock if paho is mid-callback trying to update
            # the UI. Running it in a daemon thread lets both sides finish cleanly.
            threading.Thread(
                target=lambda: (client.loop_stop(), client.disconnect()),
                daemon=True,
            ).start()
            self._connect_btn.config(state="normal")

    # MQTT callbacks

    def _on_connect(self, client, userdata, flags, rc: int) -> None:
        """Subscribe to sensor topics and update UI state on successful connection."""
        if rc == 0:
            self._connected = True
            client.subscribe(MQTT.topics["sensors_wildcard"], qos=MQTT.qos_sensor)
            print(f"{self!r} connected - AES-256-GCM active, QoS {MQTT.qos_sensor}")
            # Marshal UI updates onto the Tk main thread - this callback runs in
            # paho's background thread and direct .config() calls from a foreign
            # thread cause random crashes in Tkinter.
            self.after(0, lambda: (
                self._status_lbl.config(text="Connected (Encrypted)", fg="green"),
                self._connect_btn.config(text="Disconnect", bg="#F44336", state="normal"),
            ))
        else:
            self.after(0, lambda: (
                self._status_lbl.config(text=f"Failed (code {rc})", fg="red"),
                self._connect_btn.config(state="normal"),
            ))

    def _on_message(self, client, userdata, msg) -> None:
        """
        Route an incoming message to the appropriate handler.

        Chart responses are identified by exact topic match; all other
        messages on the sensors wildcard are treated as sensor readings.
        """
        try:
            if msg.topic == MQTT.topics["chart_response"]:
                raw = msg.payload.decode("utf-8")
                print(f"[MQTT IN]  Chart response received on topic: {msg.topic} | Encrypted: {raw[:32]}...")
                # Marshal onto main thread - _handle_chart_response updates Tk widgets.
                self.after(0, lambda r=raw: self._handle_chart_response(r))
                return

            sensor = msg.topic.split("/")[-1]
            if sensor in self._sensor_vals:
                encrypted_payload = msg.payload.decode("utf-8")
                value = CIPHER.decrypt_int(encrypted_payload)
                print(f"[MQTT IN]  Topic: {msg.topic} | Encrypted: {encrypted_payload[:32]}... | Decrypted: {value}")
                self._sensor_vals[sensor] = value
                # Marshal onto main thread - _update_sensor_display updates Tk widgets.
                self.after(0, lambda s=sensor, v=value: self._update_sensor_display(s, v))

        except Exception as exc:
            print(f"Message error: {exc}")

    def _send_emergency_notification(self, sensor: str, value: int) -> None:
        """
        Send a Windows toast notification for an emergency event.

        A per-sensor cooldown (_ALERT_COOLDOWN_SEC) prevents the notification
        from firing repeatedly every 2 s while the sensor stays in the
        emergency state - the alert is raised once and then suppressed until
        the cooldown window expires.

        The winotify call is wrapped in try/except so that any platform or
        permission error cannot propagate upward and crash the Tk callback.

        Args:
            sensor: Sensor name key (e.g. 'flame', 'gas').
            value:  Decrypted integer ADC reading that triggered the alert.
        """
        now  = time.monotonic()
        last = self._last_alert.get(sensor, 0.0)
        if now - last < self._ALERT_COOLDOWN_SEC:
            return  # Cooldown active - suppress repeated alert.
        self._last_alert[sensor] = now

        titles = {
            "flame": "Fire detected!",
            "gas":   "Gas leak detected!",
            "water": "Water leak detected!",
        }

        try:
            toast = Notification(
                app_id="Home Security",
                title=titles.get(sensor, "Emergency!"),
                msg=f"{sensor.capitalize()} sensor triggered! Value: {value}",
                duration="short",
            )
            # Standard Windows notification sound
            toast.set_audio(audio.Default, loop=False)
            toast.show()
        except Exception as exc:
            # Notification failure must not crash the dashboard UI.
            print(f"[Notification] Failed to send alert for {sensor}: {exc}")

    # Realtime display

    def _update_sensor_display(self, sensor: str, value: int) -> None:
        """
        Coordinator: update the sensor card label and check for emergencies.

        Delegates display rendering to _update_display() and emergency
        detection to _check_and_notify_emergency(), keeping each method
        focused on a single responsibility (SRP).
        """
        self._update_display(sensor, value)
        self._check_and_notify_emergency(sensor, value)

    def _update_display(self, sensor: str, value: int) -> None:
        """Classify the reading and update the sensor card label and colour."""
        if sensor not in self._sensor_labels:
            return
        colour, status = self._classifier.classify(sensor, value)

        # Light is a digital sensor (0/1) - showing the raw value adds no meaning.
        if sensor == "light":
            text = status
        else:
            text = f"{status} - Value: {value}"
        self._sensor_labels[sensor].config(text=text, fg=colour)

    def _check_and_notify_emergency(self, sensor: str, value: int) -> None:
        """
        Check whether a reading crosses the configured emergency threshold
        and trigger a Windows notification if so.

        Uses DATABASE.threshold_for() - the single source of truth from
        settings.py - to avoid duplicating threshold values here.

        Emergency direction mirrors subscriber.py:
          - Flame: emergency when BELOW threshold (low ADC = flame detected).
          - Gas, Water: emergency when ABOVE threshold (high ADC = danger).

        Args:
            sensor: Sensor name key (e.g. 'flame', 'gas').
            value:  Decrypted integer ADC reading.
        """
        threshold = DATABASE.threshold_for(sensor)
        if threshold is None:
            return  # No emergency threshold defined for this sensor (e.g. light).

        is_emergency = (
            value <= threshold if sensor == "flame"
            else value >= threshold
        )
        if is_emergency:
            self._send_emergency_notification(sensor, value)

    # Chart loading

    def _load_charts(self) -> None:
        """
        Subscribe to chart responses and publish one request per chart sensor.
        Arms a timeout that fires if ChartService does not respond in time.
        """
        if not self._connected:
            self._chart_status.config(text="Not connected", fg="red")
            return

        self._chart_status.config(text="Loading...", fg="orange")
        self._load_btn.config(state="disabled")
        self._chart_data = {}

        if self._timeout_id:
            self.after_cancel(self._timeout_id)
        self._timeout_id = self.after(
            SENSOR.chart_timeout_sec * 1000, self._on_chart_timeout,
        )

        self._mqtt.subscribe(MQTT.topics["chart_response"], qos=MQTT.qos_chart_response)

        time_range = self._time_var.get()
        for sensor in self._CHART_SENSORS:
            payload = json.dumps({"sensor": sensor, "range": time_range})
            print(f"[MQTT OUT] Chart request published | Topic: {MQTT.topics['chart_request']} | Payload: {payload}")
            self._mqtt.publish(
                MQTT.topics["chart_request"],
                payload,
                qos=MQTT.qos_chart_request,
            )

    def _on_chart_timeout(self) -> None:
        """Handle the case where ChartService does not respond within the timeout."""
        if len(self._chart_data) < len(self._CHART_SENSORS):
            self._chart_status.config(text="Timeout - server not responding", fg="red")
            self._load_btn.config(state="normal")

    def _handle_chart_response(self, raw: str) -> None:
        """
        Decrypt and process one chart response from ChartService.

        Accumulates responses until all chart sensors have replied, then
        cancels the timeout and re-enables the Load Charts button.
        """
        try:
            response = CIPHER.decrypt_json(raw)

            if "error" in response:
                self._chart_status.config(text=f"Error: {response['error']}", fg="red")
                self._load_btn.config(state="normal")
                return

            sensor = response.get("sensor")
            points = response.get("points", [])

            if sensor and points:
                print(f"[MQTT IN]  Chart response decrypted | Sensor: {sensor} | Points received: {len(points)}")
                self._chart_data[sensor] = points
                self._update_chart(sensor, points)

                if len(self._chart_data) == len(self._CHART_SENSORS):
                    if self._timeout_id:
                        self.after_cancel(self._timeout_id)
                        self._timeout_id = None
                    self._chart_status.config(
                        text="Charts loaded successfully (encrypted)", fg="green",
                    )
                    self._load_btn.config(state="normal")

        except Exception as exc:
            print(f"Decryption error: {exc}")
            self._chart_status.config(text="Decryption failed", fg="red")
            self._load_btn.config(state="normal")

    def _update_chart(self, sensor: str, points: list) -> None:
        """Clear and redraw the matplotlib chart for a sensor with new data points."""
        if sensor not in self._charts:
            return

        fig, ax, cv, colour = self._charts[sensor]
        values = [p["avg"]           for p in points]
        labels = [p.get("label", "") for p in points]

        ax.clear()
        ax.plot(values, linewidth=2.5, color=colour)
        ax.set_title(f"{sensor.capitalize()} Sensor", fontweight="bold", fontsize=13)
        ax.set_ylabel("Value", fontsize=10)
        ax.grid(True, alpha=0.3)

        # Limit x-axis tick density to avoid label crowding.
        step = max(1, len(labels) // 10)
        ax.set_xticks(range(0, len(labels), step))
        ax.set_xticklabels(labels[::step], rotation=45, ha="right", fontsize=9)

        fig.tight_layout()
        cv.draw()

    def __repr__(self) -> str:
        status = "connected" if self._connected else "disconnected"
        return f"Dashboard({status})"


# Entry point

def main() -> None:
    """Instantiate and run the service. Entry point for direct execution."""
    Dashboard().mainloop()


if __name__ == "__main__":
    main()
