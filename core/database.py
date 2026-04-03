"""
SQLite database layer for the SmartHome Security system.

DatabaseManager encapsulates all schema management, sensor writes,
and time-series queries behind a clean object interface.

Design notes:
  - Every public method opens a fresh connection and closes it on exit,
    making the object safe to share across threads.
  - Private query helpers are @staticmethod where they do not reference
    instance state, signalling clearly that they are pure data functions.
  - The module-level singleton DB is the only instance used by services.
"""

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta

from config.settings import DATABASE


class DatabaseManager:
    """
    Manages the SmartHome Security SQLite database.

    Responsibilities:
      - Schema initialisation (idempotent; safe to call on every startup).
      - Writing sensor readings.
      - Querying aggregated time-series data for chart generation.
    """

    def __init__(self, db_path: str) -> None:
        """
        Args:
            db_path: Filesystem path to the SQLite database file.
        """
        self._db_path = db_path

    # ── Schema ─────────────────────────────────────────────────────────────────

    def init_schema(self) -> None:
        """Create all tables if they do not already exist (idempotent)."""
        with self._connection() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS sensors (
                    sensor_id   INTEGER PRIMARY KEY AUTOINCREMENT,
                    sensor_name TEXT    UNIQUE NOT NULL
                );

                CREATE TABLE IF NOT EXISTS sensor_data (
                    id        INTEGER PRIMARY KEY AUTOINCREMENT,
                    sensor_id INTEGER NOT NULL,
                    value     INTEGER NOT NULL,
                    timestamp TEXT    NOT NULL,
                    FOREIGN KEY(sensor_id) REFERENCES sensors(sensor_id)
                );
            """)

    # ── Write ──────────────────────────────────────────────────────────────────

    def save_reading(self, sensor: str, value: int) -> None:
        """
        Persist one sensor reading to the database.

        Args:
            sensor: Sensor name key (e.g. 'flame', 'gas').
            value:  Decrypted integer reading.
        """
        with self._connection() as conn:
            cursor    = conn.cursor()
            sensor_id = self._get_or_create_sensor(cursor, sensor)
            now       = datetime.now().isoformat()

            cursor.execute(
                "INSERT INTO sensor_data (sensor_id, value, timestamp) VALUES (?, ?, ?)",
                (sensor_id, value, now),
            )

    # ── Read ───────────────────────────────────────────────────────────────────

    def query_chart_data(self, sensor: str, range_value) -> dict:
        """
        Return aggregated time-series data for a sensor.

        Args:
            sensor:      Sensor name key.
            range_value: One of '24h', '30d', '12m', or a dict
                         {"from": "YYYY-MM-DD", "to": "YYYY-MM-DD"}.

        Returns:
            Dict with keys sensor, range, unit, points — or {"error": ...}.
        """
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT sensor_id FROM sensors WHERE sensor_name = ?", (sensor,)
            )
            row = cursor.fetchone()
            if row is None:
                return {"error": f"Unknown sensor: {sensor}"}

            sensor_id = row[0]

            # Dispatch table maps range string to (query_method, unit_label).
            dispatch = {
                "24h": (self._query_hours,  "hour"),
                "30d": (self._query_days,   "day"),
                "12m": (self._query_months, "month"),
            }

            if isinstance(range_value, dict):
                # Validate date strings before use.
                try:
                    date_from = range_value["from"]
                    date_to   = range_value["to"]
                    dt_from   = datetime.fromisoformat(date_from)
                    dt_to     = datetime.fromisoformat(date_to)
                except (KeyError, ValueError, TypeError) as exc:
                    return {"error": f"Invalid custom range: {exc}"}

                # Reject reversed ranges instead of silently returning empty data.
                if dt_from > dt_to:
                    return {"error": "date 'from' must not be after 'to'"}

                rows = self._query_custom(cursor, sensor_id, date_from, date_to)
                unit = "custom"
            elif range_value in dispatch:
                query_fn, unit = dispatch[range_value]
                rows = query_fn(cursor, sensor_id)
            else:
                return {"error": f"Unknown range: {range_value}"}

        return {
            "sensor": sensor,
            "range":  range_value,
            "unit":   unit,
            "points": self._build_points(rows),
        }

    # ── Private helpers ────────────────────────────────────────────────────────

    @contextmanager
    def _connection(self):
        """
        Context manager that opens a connection, yields it, commits on success,
        rolls back on exception, and always closes the connection.

        Fixes the resource leak present when using sqlite3.connect() directly
        as a context manager (which commits/rolls back but does not close).
        """
        conn = sqlite3.connect(self._db_path)
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    @staticmethod
    def _get_or_create_sensor(cursor: sqlite3.Cursor, sensor: str) -> int:
        """Insert sensor name if absent; return its integer sensor_id."""
        cursor.execute(
            "INSERT OR IGNORE INTO sensors (sensor_name) VALUES (?)", (sensor,)
        )
        cursor.execute(
            "SELECT sensor_id FROM sensors WHERE sensor_name = ?", (sensor,)
        )
        return cursor.fetchone()[0]

    @staticmethod
    def _query_hours(cursor: sqlite3.Cursor, sensor_id: int) -> list:
        """Query the last 24 hours of readings, grouped by hour."""
        since = (datetime.now() - timedelta(hours=24)).isoformat()
        cursor.execute("""
            SELECT
                strftime('%H:00', timestamp) AS label,
                AVG(value),
                MIN(value),
                MAX(value)
            FROM sensor_data
            WHERE sensor_id = ? AND timestamp >= ?
            GROUP BY strftime('%Y-%m-%d %H', timestamp)
            ORDER BY timestamp
        """, (sensor_id, since))
        return cursor.fetchall()

    @staticmethod
    def _query_days(cursor: sqlite3.Cursor, sensor_id: int) -> list:
        """Query the last 30 days of readings, grouped by day."""
        since = (datetime.now() - timedelta(days=30)).isoformat()
        cursor.execute("""
            SELECT
                strftime('%d.%m', timestamp) AS label,
                AVG(value),
                MIN(value),
                MAX(value)
            FROM sensor_data
            WHERE sensor_id = ? AND timestamp >= ?
            GROUP BY strftime('%Y-%m-%d', timestamp)
            ORDER BY timestamp
        """, (sensor_id, since))
        return cursor.fetchall()

    @staticmethod
    def _query_months(cursor: sqlite3.Cursor, sensor_id: int) -> list:
        """Query the last 12 months of readings, grouped by month."""
        since = (datetime.now() - timedelta(days=365)).isoformat()
        cursor.execute("""
            SELECT
                strftime('%m.%Y', timestamp) AS label,
                AVG(value),
                MIN(value),
                MAX(value)
            FROM sensor_data
            WHERE sensor_id = ? AND timestamp >= ?
            GROUP BY strftime('%Y-%m', timestamp)
            ORDER BY timestamp
        """, (sensor_id, since))
        return cursor.fetchall()

    @staticmethod
    def _query_custom(
        cursor: sqlite3.Cursor, sensor_id: int, date_from: str, date_to: str
    ) -> list:
        """
        Query an arbitrary date range with automatically selected grouping:
          <= 3 days  -> hourly buckets
          <= 90 days -> daily buckets
          otherwise  -> monthly buckets

        Precondition: date_from and date_to are valid ISO strings with
        date_from <= date_to (validated by the caller, query_chart_data).
        """
        delta = (
            datetime.fromisoformat(date_to) - datetime.fromisoformat(date_from)
        ).days

        if delta <= 3:
            group_fmt, label_fmt = "%Y-%m-%d %H", "%H:00"
        elif delta <= 90:
            group_fmt, label_fmt = "%Y-%m-%d", "%d.%m"
        else:
            group_fmt, label_fmt = "%Y-%m", "%m.%Y"

        cursor.execute(f"""
            SELECT
                strftime('{label_fmt}', timestamp) AS label,
                AVG(value),
                MIN(value),
                MAX(value)
            FROM sensor_data
            WHERE sensor_id = ? AND timestamp BETWEEN ? AND ?
            GROUP BY strftime('{group_fmt}', timestamp)
            ORDER BY timestamp
        """, (sensor_id, date_from, date_to))
        return cursor.fetchall()

    @staticmethod
    def _build_points(rows: list) -> list:
        """Convert raw DB result rows into JSON-serialisable point dicts."""
        return [
            {"label": row[0], "avg": round(row[1], 1), "min": row[2], "max": row[3]}
            for row in rows
        ]

    def __repr__(self) -> str:
        return f"DatabaseManager(db_path={self._db_path!r})"


# ── Module-level singleton ─────────────────────────────────────────────────────
# Services import DB directly; do not instantiate DatabaseManager elsewhere.

DB = DatabaseManager(DATABASE.db_name)
