"""
Demo launcher — starts all SmartHome Security services in separate windows.

Run from the project root:
    python run_all.py

Opens four titled Command Prompt windows, one per service:
    1. Subscriber + Storage  — receives readings, stores to SQLite
    2. Chart Service         — serves historical chart data on demand
    3. Sensor Publisher      — reads Arduino via USB, publishes encrypted readings
    4. Dashboard             — Tkinter GUI (Realtime + Analysis tabs)

Startup order matters: Subscriber and Chart Service connect to the broker
before Publisher starts sending data, and before Dashboard tries to load charts.

Ctrl+C in this window does NOT stop the services — close each window
individually, or end them all from Task Manager.
"""

import subprocess
import sys
import time
import os


def open_service(title: str, module: str) -> subprocess.Popen:
    """
    Launch a Python module in a new titled Command Prompt window.

    Args:
        title:  Window title shown in the taskbar.
        module: Dotted module path (e.g. 'ui.dashboard').

    Returns:
        The Popen handle for the new process.
    """
    project_root = os.path.dirname(os.path.abspath(__file__))
    # Build as a single string — required for 'start' with shell=True.
    # Quoting the title is mandatory: 'start' treats the first unquoted
    # single-word argument as a filename, not a window title.
    cmd = f'start "{title}" cmd /k "{sys.executable}" -m {module}'
    return subprocess.Popen(cmd, shell=True, cwd=project_root)


def main() -> None:
    print("=" * 55)
    print("  SmartHome Security System — Demo Launcher")
    print("=" * 55)

    services = [
        ("Subscriber + Storage", "services.subscriber"),
        ("Chart Service",        "services.chart_service"),
        ("Sensor Publisher",     "services.publisher"),
        ("Dashboard",            "ui.dashboard"),
    ]

    for title, module in services:
        print(f"  Starting {title}...")
        open_service(title, module)
        time.sleep(2)   # Stagger startup so each service connects before the next launches.

    print()
    print("  All services started in separate windows.")
    print("  Close each window individually to stop a service.")
    print("=" * 55)


if __name__ == "__main__":
    main()
