import sqlite3
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

from app.core.time_utils import utc_now
from app.db.database import Database
from app.schemas.telemetry import TelemetryIn


class RawTelemetryFallbackTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "backend.db"
        self.db = Database(str(self.db_path))

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_insert_telemetry_falls_back_to_raw_when_smoothed_missing(self):
        self.db.insert_telemetry(
            TelemetryIn(
                device_id="esp32-room-a",
                ts=utc_now().isoformat(),
                temp_raw=30.4,
                hum_raw=65.2,
            )
        )

        latest = self.db.latest_telemetry("esp32-room-a")

        self.assertEqual(latest["temp_raw"], 30.4)
        self.assertEqual(latest["hum_raw"], 65.2)
        self.assertEqual(latest["temp_ma"], 30.4)
        self.assertEqual(latest["hum_ma"], 65.2)

    def test_resample_falls_back_for_existing_raw_only_rows(self):
        base_ts = (utc_now() - timedelta(minutes=5)).replace(second=0, microsecond=0)
        with sqlite3.connect(self.db_path) as conn:
            for index in range(3):
                ts = (base_ts + timedelta(minutes=index)).isoformat()
                conn.execute(
                    """
                    INSERT INTO telemetry_raw (
                        device_id, ts, temp_raw, hum_raw, mode
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    ("esp32-room-a", ts, 30.0 + index, 60.0 + index, "auto"),
                )
            conn.commit()

        self.db.resample_device("esp32-room-a", 60)

        rows = self.db.build_forecast_dataset(
            "esp32-room-a",
            interval_seconds=60,
            lookback=1,
            horizon_minutes=(1, 1),
        )

        self.assertTrue(rows)
        self.assertIsNotNone(rows[0]["temp_now"])
        self.assertIsNotNone(rows[0]["hum_now"])
        self.assertIsNotNone(rows[0]["target_temp_plus_1m"])
        self.assertIsNotNone(rows[0]["target_hum_plus_1m"])


if __name__ == "__main__":
    unittest.main()
