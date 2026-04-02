"""
Simple MQTT Home Security Dashboard
Real-time monitoring and historical data charts
With AES-256-GCM encryption for all data
"""

import tkinter as tk
from tkinter import ttk
import json
import ssl
import base64
from paho.mqtt import client as mqtt_client
from Crypto.Cipher import AES
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure


# Configuration
BROKER = "broker.hivemq.com"
PORT = 8883
AES_KEY = bytes.fromhex("dd75fc2d686e27a660a25fb5dfa94910e0e9bb4a40f3fe8e89178f93b5de2222")
CHART_TIMEOUT_SEC = 15  # Timeout for chart loading


# ========== DECRYPTION FUNCTIONS ==========

def decrypt(payload):
    """Decrypt AES-256-GCM encrypted integer value (for realtime data)."""
    raw = base64.b64decode(payload)
    nonce = raw[:16]
    tag = raw[-16:]
    ciphertext = raw[16:-16]
    
    cipher = AES.new(AES_KEY, AES.MODE_GCM, nonce=nonce)
    plaintext = cipher.decrypt_and_verify(ciphertext, tag)
    return int(plaintext.decode("utf-8"))


def decrypt_json(payload):
    """Decrypt AES-256-GCM encrypted JSON data (for chart data)."""
    raw = base64.b64decode(payload)
    nonce = raw[:16]
    tag = raw[-16:]
    ciphertext = raw[16:-16]
    
    cipher = AES.new(AES_KEY, AES.MODE_GCM, nonce=nonce)
    plaintext = cipher.decrypt_and_verify(ciphertext, tag)
    
    return json.loads(plaintext.decode("utf-8"))


# ========== MAIN DASHBOARD CLASS ==========

class Dashboard(tk.Tk):
    """Main dashboard window."""
    
    def __init__(self):
        super().__init__()
        self.title("Home Security Dashboard")
        self.geometry("1000x700")
        self.minsize(900, 650)  # Minimum window size
        
        self.mqtt_client = None
        self.connected = False
        
        # Sensor data storage
        self.sensor_values = {"flame": 0, "gas": 0, "water": 0, "light": 0}
        
        # Chart loading timeout
        self.chart_timeout_id = None
        
        self.build_ui()
    
    def build_ui(self):
        """Build user interface."""
        # Top bar with connection button
        top_frame = tk.Frame(self, bg="#f0f0f0", height=60)
        top_frame.pack(fill="x")
        top_frame.pack_propagate(False)
        
        tk.Label(top_frame, text="Home Security Dashboard", font=("Arial", 14, "bold"), 
                bg="#f0f0f0").pack(side="left", padx=20)
        
        self.status_label = tk.Label(top_frame, text="Disconnected", fg="red", 
                                     font=("Arial", 11, "bold"), bg="#f0f0f0")
        self.status_label.pack(side="left", padx=20)
        
        self.connect_btn = tk.Button(top_frame, text="Connect", command=self.toggle_connection, 
                                     width=12, bg="#4CAF50", fg="white", 
                                     font=("Arial", 10, "bold"), activebackground="#45a049")
        self.connect_btn.pack(side="right", padx=20, pady=12)
        
        # Tabs with larger font
        style = ttk.Style()
        style.configure('TNotebook.Tab', font=('Arial', 11), padding=[20, 10])
        
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Realtime tab
        realtime_frame = tk.Frame(self.notebook)
        self.notebook.add(realtime_frame, text="Realtime")
        self.build_realtime_tab(realtime_frame)
        
        # Analysis tab with scrolling
        analysis_container = tk.Frame(self.notebook)
        self.notebook.add(analysis_container, text="Analysis")
        
        # Create canvas for scrolling
        canvas = tk.Canvas(analysis_container)
        scrollbar = ttk.Scrollbar(analysis_container, orient="vertical", command=canvas.yview)
        self.analysis_frame = tk.Frame(canvas)
        
        self.analysis_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=self.analysis_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        self.build_analysis_tab(self.analysis_frame)
    
    def build_realtime_tab(self, parent):
        """Build realtime monitoring tab."""
        # Title
        tk.Label(parent, text="Real-time Sensor Data", font=("Arial", 16, "bold")).pack(pady=20)
        
        # Sensor displays
        self.sensor_labels = {}
        sensors = [
            ("Flame Sensor", "flame", "#FF5252"),
            ("Gas Sensor", "gas", "#FFC107"),
            ("Water Sensor", "water", "#2196F3"),
            ("Light Sensor", "light", "#4CAF50")
        ]
        
        for name, key, color in sensors:
            frame = tk.Frame(parent, bg="white", relief="solid", bd=1)
            frame.pack(fill="x", padx=50, pady=10)
            
            tk.Label(frame, text=name, font=("Arial", 12, "bold"), bg="white").pack(
                anchor="w", padx=20, pady=(15, 5)
            )
            
            value_label = tk.Label(frame, text="Waiting for data...", font=("Arial", 14), 
                                  bg="white", fg="gray")
            value_label.pack(anchor="w", padx=20, pady=(0, 15))
            
            self.sensor_labels[key] = value_label
    
    def build_analysis_tab(self, parent):
        """Build analysis/charts tab."""
        # Controls
        control_frame = tk.Frame(parent, bg="white", relief="solid", bd=1)
        control_frame.pack(fill="x", padx=20, pady=20)
        
        inner_control = tk.Frame(control_frame, bg="white")
        inner_control.pack(padx=15, pady=15)
        
        tk.Label(inner_control, text="Time Range:", font=("Arial", 11, "bold"), 
                bg="white").pack(side="left", padx=10)
        
        self.time_var = tk.StringVar(value="24h")
        times = [("24 Hours", "24h"), ("30 Days", "30d"), ("12 Months", "12m")]
        
        for text, val in times:
            tk.Radiobutton(inner_control, text=text, variable=self.time_var, value=val,
                          font=("Arial", 10), bg="white").pack(side="left", padx=8)
        
        self.load_btn = tk.Button(inner_control, text="Load Charts", command=self.load_charts,
                                  bg="#2196F3", fg="white", font=("Arial", 10, "bold"),
                                  width=12, activebackground="#1976D2")
        self.load_btn.pack(side="left", padx=15)
        
        self.chart_status = tk.Label(inner_control, text="", fg="gray", font=("Arial", 10),
                                     bg="white")
        self.chart_status.pack(side="left", padx=10)
        
        # Charts container with fixed size
        self.charts_frame = tk.Frame(parent)
        self.charts_frame.pack(fill="both", expand=True, padx=20, pady=10)
        
        # Create empty charts
        self.charts = {}
        colors = {"flame": "#FF5252", "gas": "#FFC107", "water": "#2196F3"}
        
        for i, sensor in enumerate(["flame", "gas", "water"]):
            chart_container = tk.Frame(self.charts_frame, bg="white", relief="solid", bd=1)
            chart_container.pack(fill="x", pady=8)
            
            fig = Figure(figsize=(9, 3), dpi=80)
            ax = fig.add_subplot(111)
            ax.text(0.5, 0.5, f"{sensor.capitalize()} - Click 'Load Charts' to view data", 
                   ha="center", va="center", fontsize=12, color="gray")
            ax.axis("off")
            
            canvas = FigureCanvasTkAgg(fig, chart_container)
            canvas.draw()
            canvas.get_tk_widget().pack(fill="both", expand=True, padx=10, pady=10)
            
            self.charts[sensor] = (fig, ax, canvas, colors[sensor])
    
    def toggle_connection(self):
        """Connect or disconnect from MQTT."""
        if self.connected:
            self.disconnect()
        else:
            self.connect()
    
    def connect(self):
        """Connect to MQTT broker."""
        self.mqtt_client = mqtt_client.Client(
            client_id=f"Dashboard_{id(self)}",
            callback_api_version=mqtt_client.CallbackAPIVersion.VERSION1
        )
        self.mqtt_client.tls_set(cert_reqs=ssl.CERT_REQUIRED, tls_version=ssl.PROTOCOL_TLS)
        self.mqtt_client.on_connect = self.on_connect
        self.mqtt_client.on_message = self.on_message
        
        try:
            self.mqtt_client.connect(BROKER, PORT)
            self.mqtt_client.loop_start()
        except Exception as e:
            self.status_label.config(text=f"Error: {e}", fg="red")
    
    def disconnect(self):
        """Disconnect from MQTT."""
        if self.mqtt_client:
            self.mqtt_client.loop_stop()
            self.mqtt_client.disconnect()
        
        self.connected = False
        self.status_label.config(text="Disconnected", fg="red")
        self.connect_btn.config(text="Connect", bg="#4CAF50")  # Green for Connect
        
        for label in self.sensor_labels.values():
            label.config(text="Waiting for data...", fg="gray")
    
    def on_connect(self, client, userdata, flags, rc):
        """Handle successful connection."""
        if rc == 0:
            self.connected = True
            self.status_label.config(text="Connected (Encrypted)", fg="green")
            self.connect_btn.config(text="Disconnect", bg="#F44336")  # Red for Disconnect
            
            # Subscribe to realtime data
            client.subscribe("smarthome/security/sensors/#")
            print("Connected and subscribed (AES-256-GCM encryption active)")
        else:
            self.status_label.config(text=f"Failed (code {rc})", fg="red")
    
    def on_message(self, client, userdata, msg):
        """Handle incoming MQTT messages."""
        try:
            sensor = msg.topic.split("/")[-1]
            
            # Realtime data (encrypted integer)
            if sensor in self.sensor_values:
                value = decrypt(msg.payload.decode())
                self.sensor_values[sensor] = value
                self.update_sensor_display(sensor, value)
            
            # Chart response (encrypted JSON)
            elif msg.topic == "smarthome/security/charts/response":
                self.handle_chart_response(msg.payload.decode())
        
        except Exception as e:
            print(f"Message error: {e}")
    
    def update_sensor_display(self, sensor, value):
        """Update sensor value in UI."""
        if sensor not in self.sensor_labels:
            return
        
        # Determine status color
        if sensor == "flame":
            color = "green" if value >= 800 else "orange" if value >= 400 else "red"
            status = "Good" if value >= 800 else "Warning" if value >= 400 else "DANGER"
        elif sensor == "gas":
            color = "green" if value <= 150 else "orange" if value <= 500 else "red"
            status = "Good" if value <= 150 else "Warning" if value <= 500 else "DANGER"
        elif sensor == "water":
            color = "green" if value <= 150 else "orange" if value <= 500 else "red"
            status = "Dry" if value <= 150 else "Warning" if value <= 500 else "WET"
        else:  # light
            color = "green" if value >= 512 else "orange"
            status = "Bright" if value >= 512 else "Dark"
        
        self.sensor_labels[sensor].config(text=f"{status} - Value: {value}", fg=color)
    
    def load_charts(self):
        """Request chart data from server."""
        if not self.connected:
            self.chart_status.config(text="Not connected", fg="red")
            return
        
        self.chart_status.config(text="Loading...", fg="orange")
        self.load_btn.config(state="disabled")
        
        # Cancel previous timeout if exists
        if self.chart_timeout_id:
            self.after_cancel(self.chart_timeout_id)
        
        # Set timeout
        self.chart_timeout_id = self.after(CHART_TIMEOUT_SEC * 1000, self.chart_load_timeout)
        
        # Subscribe to chart responses
        self.mqtt_client.subscribe("smarthome/security/charts/response")
        
        # Store chart data
        self.chart_data = {}
        
        # Request data for each sensor
        time_range = self.time_var.get()
        for sensor in ["flame", "gas", "water"]:
            request = json.dumps({"sensor": sensor, "range": time_range})
            self.mqtt_client.publish("smarthome/security/charts/request", request)
    
    def chart_load_timeout(self):
        """Handle chart loading timeout."""
        if len(self.chart_data) < 3:
            self.chart_status.config(text="Timeout - Server not responding", fg="red")
            self.load_btn.config(state="normal")
            print("Chart loading timeout")
    
    def handle_chart_response(self, data):
        """Process encrypted chart data response."""
        try:
            # Decrypt JSON response
            response = decrypt_json(data)
            
            # Check for errors
            if "error" in response:
                print(f"Chart error: {response['error']}")
                self.chart_status.config(text=f"Error: {response['error']}", fg="red")
                self.load_btn.config(state="normal")
                return
            
            sensor = response.get("sensor")
            points = response.get("points", [])
            
            if sensor and points:
                self.chart_data[sensor] = points
                
                # Update chart
                self.update_chart(sensor, points)
                
                # Check if all charts loaded
                if len(self.chart_data) == 3:
                    # Cancel timeout
                    if self.chart_timeout_id:
                        self.after_cancel(self.chart_timeout_id)
                        self.chart_timeout_id = None
                    
                    self.chart_status.config(text="Charts loaded successfully (encrypted)", fg="green")
                    self.load_btn.config(state="normal")
        
        except Exception as e:
            print(f"Decryption error: {e}")
            self.chart_status.config(text="Decryption failed", fg="red")
            self.load_btn.config(state="normal")
    
    def update_chart(self, sensor, points):
        """Update chart with data."""
        if sensor not in self.charts:
            return
        
        fig, ax, canvas, color = self.charts[sensor]
        
        # Extract values
        values = [p["avg"] for p in points]
        labels = [p.get("label", "") for p in points]
        
        # Clear and plot
        ax.clear()
        ax.plot(values, linewidth=2.5, color=color)
        ax.set_title(f"{sensor.capitalize()} Sensor", fontweight="bold", fontsize=13)
        ax.set_ylabel("Value", fontsize=10)
        ax.grid(True, alpha=0.3)
        
        # Set labels (show every nth to avoid crowding)
        step = max(1, len(labels) // 10)
        ax.set_xticks(range(0, len(labels), step))
        ax.set_xticklabels(labels[::step], rotation=45, ha="right", fontsize=9)
        
        fig.tight_layout()
        canvas.draw()


if __name__ == "__main__":
    app = Dashboard()
    app.mainloop()
