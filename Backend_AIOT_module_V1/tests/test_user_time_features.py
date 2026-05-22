import sqlite3
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

from app.core.time_utils import utc_now
from app.db.database import Database
from app.schemas.control_event import ControlEventIn
from app.schemas.telemetry import TelemetryIn


class UserTimeFeatureTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db = Database(str(Path(self.temp_dir.name) / "backend.db"))

    def tearDown(self):
        self.temp_dir.cleanup()

    def _insert_telemetry(self, ts, user_id="user-a"):
        self.db.insert_telemetry(
            TelemetryIn(
                device_id="esp32-room-a",
                user_id=user_id,
                ts=ts.isoformat(),
                temp_ma=30.0,
                hum_ma=65.0,
                mode="auto",
                setpoint_current=29.0,
                fan_pwm_actual=120,
                lamp_actual=1,
            )
        )

    def test_habit_dataset_keeps_user_id_and_day_period(self):
        event_ts = utc_now().replace(microsecond=0)
        for offset_seconds in (120, 90, 60, 30):
            self._insert_telemetry(event_ts - timedelta(seconds=offset_seconds))

        self.db.resample_device("esp32-room-a", 30)
        self.db.insert_control_event(
            ControlEventIn(
                device_id="esp32-room-a",
                user_id="user-a",
                ts=event_ts.isoformat(),
                event_type="setpoint_change",
                old_value="29.0",
                new_value="28.5",
                trigger_source="app",
            )
        )

        rows = self.db.build_habit_dataset("esp32-room-a", interval_seconds=30)

        self.assertEqual(rows[0]["user_id"], "user-a")
        self.assertIn(rows[0]["day_period"], {"day", "night"})
        self.assertIn("hour_sin", rows[0])
        self.assertIn("hour_cos", rows[0])

    def test_forecast_dataset_has_day_period(self):
        current_ts = utc_now().replace(microsecond=0)
        for offset_minutes in range(7, 0, -1):
            self._insert_telemetry(current_ts - timedelta(minutes=offset_minutes))

        self.db.resample_device("esp32-room-a", 60)
        rows = self.db.build_forecast_dataset(
            "esp32-room-a",
            interval_seconds=60,
            lookback=3,
            horizon_minutes=(1, 2),
        )

        self.assertTrue(rows)
        self.assertIn(rows[0]["day_period"], {"day", "night"})
        self.assertIn("hour_sin", rows[0])
        self.assertIn("hour_cos", rows[0])


class UserColumnMigrationTest(unittest.TestCase):
    def test_existing_tables_gain_user_columns(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "old.db"
            with sqlite3.connect(db_path) as conn:
                conn.executescript(
                    """
                    CREATE TABLE telemetry_raw (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        device_id TEXT NOT NULL,
                        ts TEXT NOT NULL
                    );
                    CREATE TABLE control_events (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        device_id TEXT NOT NULL,
                        ts TEXT NOT NULL
                    );
                    CREATE TABLE ml_recommendations (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        device_id TEXT NOT NULL,
                        ts TEXT NOT NULL
                    );
                    """
                )

            Database(str(db_path))

            with sqlite3.connect(db_path) as conn:
                for table_name in ("telemetry_raw", "control_events", "ml_recommendations"):
                    columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table_name})")}
                    self.assertIn("user_id", columns)


if __name__ == "__main__":
    unittest.main()
