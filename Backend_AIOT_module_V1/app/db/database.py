import sqlite3
import threading
from datetime import timedelta
from typing import Any, Dict, List, Optional, Tuple

from app.core.config import settings
from app.core.helpers import majority, maybe_float, maybe_int
from app.core.time_utils import cyclic_hour_features, day_period, floor_time, parse_ts, utc_now
from app.schemas.control_event import ControlEventIn
from app.schemas.device_twin import DeviceTwinIn
from app.schemas.ml_recommendation import MLRecommendationIn
from app.schemas.telemetry import TelemetryIn


class Database:
    def __init__(self, path: str) -> None:
        self.path = path
        self._lock = threading.Lock()
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                PRAGMA journal_mode=WAL;

                CREATE TABLE IF NOT EXISTS telemetry_raw (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    device_id TEXT NOT NULL,
                    user_id TEXT,
                    ts TEXT NOT NULL,
                    temp_raw REAL,
                    hum_raw REAL,
                    temp_ma REAL,
                    hum_ma REAL,
                    mode TEXT,
                    setpoint_current REAL,
                    fan_pwm_cmd INTEGER,
                    fan_pwm_actual INTEGER,
                    lamp_cmd INTEGER,
                    lamp_actual INTEGER,
                    control_source TEXT,
                    event_flag INTEGER DEFAULT 0
                );
                CREATE INDEX IF NOT EXISTS idx_telemetry_raw_device_ts
                    ON telemetry_raw(device_id, ts);

                CREATE TABLE IF NOT EXISTS control_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    device_id TEXT NOT NULL,
                    user_id TEXT,
                    ts TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    old_value TEXT,
                    new_value TEXT,
                    trigger_source TEXT,
                    user_feedback INTEGER
                );
                CREATE INDEX IF NOT EXISTS idx_control_events_device_ts
                    ON control_events(device_id, ts);

                CREATE TABLE IF NOT EXISTS device_twin (
                    device_id TEXT PRIMARY KEY,
                    ts TEXT NOT NULL,
                    fan_pwm_actual INTEGER,
                    lamp_actual INTEGER,
                    mode_actual TEXT,
                    setpoint_actual REAL
                );

                CREATE TABLE IF NOT EXISTS ml_recommendations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    device_id TEXT NOT NULL,
                    user_id TEXT,
                    ts TEXT NOT NULL,
                    setpoint_dynamic REAL,
                    pred_temp_plus_10m REAL,
                    pred_hum_plus_10m REAL,
                    pred_temp_plus_20m REAL,
                    pred_hum_plus_20m REAL,
                    control_hint TEXT,
                    model_version TEXT,
                    source_service TEXT,
                    published_topic TEXT,
                    publish_success INTEGER DEFAULT 0
                );
                CREATE INDEX IF NOT EXISTS idx_ml_recommendations_device_ts
                    ON ml_recommendations(device_id, ts);

                CREATE TABLE IF NOT EXISTS telemetry_resampled (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    device_id TEXT NOT NULL,
                    bucket_start TEXT NOT NULL,
                    interval_seconds INTEGER NOT NULL,
                    temp_mean REAL,
                    temp_min REAL,
                    temp_max REAL,
                    hum_mean REAL,
                    hum_min REAL,
                    hum_max REAL,
                    temp_raw_count INTEGER,
                    hum_raw_count INTEGER,
                    fan_pwm_mean REAL,
                    fan_pwm_max REAL,
                    lamp_on_ratio REAL,
                    mode_majority TEXT,
                    setpoint_mean REAL,
                    UNIQUE(device_id, bucket_start, interval_seconds)
                );
                CREATE INDEX IF NOT EXISTS idx_telemetry_resampled_device_bucket
                    ON telemetry_resampled(device_id, interval_seconds, bucket_start);
                """
            )
            self._ensure_column(conn, "telemetry_raw", "user_id", "TEXT")
            self._ensure_column(conn, "control_events", "user_id", "TEXT")
            self._ensure_column(conn, "ml_recommendations", "user_id", "TEXT")
            conn.commit()

    @staticmethod
    def _ensure_column(conn: sqlite3.Connection, table_name: str, column_name: str, ddl: str) -> None:
        columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table_name})")}
        if column_name not in columns:
            conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {ddl}")

    def insert_telemetry(self, item: TelemetryIn) -> None:
        ts = parse_ts(item.ts).isoformat()
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO telemetry_raw (
                    device_id, user_id, ts, temp_raw, hum_raw, temp_ma, hum_ma,
                    mode, setpoint_current, fan_pwm_cmd, fan_pwm_actual,
                    lamp_cmd, lamp_actual, control_source, event_flag
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item.device_id,
                    item.user_id,
                    ts,
                    item.temp_raw,
                    item.hum_raw,
                    item.temp_ma,
                    item.hum_ma,
                    item.mode,
                    item.setpoint_current,
                    item.fan_pwm_cmd,
                    item.fan_pwm_actual,
                    item.lamp_cmd,
                    item.lamp_actual,
                    item.control_source,
                    item.event_flag,
                ),
            )
            conn.commit()

    def insert_control_event(self, item: ControlEventIn) -> None:
        ts = parse_ts(item.ts).isoformat()
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO control_events (
                    device_id, user_id, ts, event_type, old_value, new_value,
                    trigger_source, user_feedback
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item.device_id,
                    item.user_id,
                    ts,
                    item.event_type,
                    item.old_value,
                    item.new_value,
                    item.trigger_source,
                    item.user_feedback,
                ),
            )
            conn.commit()

    def upsert_device_twin(self, item: DeviceTwinIn) -> None:
        ts = parse_ts(item.ts).isoformat()
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO device_twin (
                    device_id, ts, fan_pwm_actual, lamp_actual,
                    mode_actual, setpoint_actual
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(device_id) DO UPDATE SET
                    ts=excluded.ts,
                    fan_pwm_actual=excluded.fan_pwm_actual,
                    lamp_actual=excluded.lamp_actual,
                    mode_actual=excluded.mode_actual,
                    setpoint_actual=excluded.setpoint_actual
                """,
                (
                    item.device_id,
                    ts,
                    item.fan_pwm_actual,
                    item.lamp_actual,
                    item.mode_actual,
                    item.setpoint_actual,
                ),
            )
            conn.commit()

    def insert_ml_recommendation(
        self,
        item: MLRecommendationIn,
        published_topic: Optional[str] = None,
        publish_success: bool = False,
    ) -> int:
        ts = parse_ts(item.ts).isoformat()
        with self._lock, self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO ml_recommendations (
                    device_id, user_id, ts, setpoint_dynamic,
                    pred_temp_plus_10m, pred_hum_plus_10m,
                    pred_temp_plus_20m, pred_hum_plus_20m,
                    control_hint, model_version, source_service,
                    published_topic, publish_success
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item.device_id,
                    item.user_id,
                    ts,
                    item.setpoint_dynamic,
                    item.pred_temp_plus_10m,
                    item.pred_hum_plus_10m,
                    item.pred_temp_plus_20m,
                    item.pred_hum_plus_20m,
                    item.control_hint,
                    item.model_version,
                    item.source_service,
                    published_topic,
                    1 if publish_success else 0,
                ),
            )
            conn.commit()
            return int(cursor.lastrowid)

    def latest_ml_recommendation(self, device_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM ml_recommendations
                WHERE device_id = ?
                ORDER BY ts DESC, id DESC
                LIMIT 1
                """,
                (device_id,),
            ).fetchone()
            return dict(row) if row else None

    def latest_telemetry(self, device_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM telemetry_raw
                WHERE device_id = ?
                ORDER BY ts DESC
                LIMIT 1
                """,
                (device_id,),
            ).fetchone()
            return dict(row) if row else None

    def list_devices(self) -> List[str]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT DISTINCT device_id FROM telemetry_raw
                UNION
                SELECT DISTINCT device_id FROM control_events
                UNION
                SELECT DISTINCT device_id FROM device_twin
                UNION
                SELECT DISTINCT device_id FROM ml_recommendations
                ORDER BY device_id
                """
            ).fetchall()
            return [row[0] for row in rows]

    def resample_device(self, device_id: str, interval_seconds: int, since_minutes: int = 180) -> int:
        now = utc_now()
        since_dt = now - timedelta(minutes=since_minutes)
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM telemetry_raw
                WHERE device_id = ? AND ts >= ?
                ORDER BY ts ASC
                """,
                (device_id, since_dt.isoformat()),
            ).fetchall()

            buckets: Dict[str, List[sqlite3.Row]] = {}
            for row in rows:
                dt = parse_ts(row["ts"])
                bucket_start = floor_time(dt, interval_seconds).isoformat()
                buckets.setdefault(bucket_start, []).append(row)

            written = 0
            for bucket_start, items in buckets.items():
                temp_values = [maybe_float(x["temp_ma"]) for x in items if maybe_float(x["temp_ma"]) is not None]
                hum_values = [maybe_float(x["hum_ma"]) for x in items if maybe_float(x["hum_ma"]) is not None]
                fan_values = [maybe_float(x["fan_pwm_actual"]) for x in items if maybe_float(x["fan_pwm_actual"]) is not None]
                lamp_values = [maybe_int(x["lamp_actual"]) for x in items if maybe_int(x["lamp_actual"]) is not None]
                mode_values = [x["mode"] for x in items if x["mode"]]
                setpoint_values = [maybe_float(x["setpoint_current"]) for x in items if maybe_float(x["setpoint_current"]) is not None]

                conn.execute(
                    """
                    INSERT INTO telemetry_resampled (
                        device_id, bucket_start, interval_seconds,
                        temp_mean, temp_min, temp_max,
                        hum_mean, hum_min, hum_max,
                        temp_raw_count, hum_raw_count,
                        fan_pwm_mean, fan_pwm_max,
                        lamp_on_ratio, mode_majority, setpoint_mean
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(device_id, bucket_start, interval_seconds) DO UPDATE SET
                        temp_mean=excluded.temp_mean,
                        temp_min=excluded.temp_min,
                        temp_max=excluded.temp_max,
                        hum_mean=excluded.hum_mean,
                        hum_min=excluded.hum_min,
                        hum_max=excluded.hum_max,
                        temp_raw_count=excluded.temp_raw_count,
                        hum_raw_count=excluded.hum_raw_count,
                        fan_pwm_mean=excluded.fan_pwm_mean,
                        fan_pwm_max=excluded.fan_pwm_max,
                        lamp_on_ratio=excluded.lamp_on_ratio,
                        mode_majority=excluded.mode_majority,
                        setpoint_mean=excluded.setpoint_mean
                    """,
                    (
                        device_id,
                        bucket_start,
                        interval_seconds,
                        sum(temp_values) / len(temp_values) if temp_values else None,
                        min(temp_values) if temp_values else None,
                        max(temp_values) if temp_values else None,
                        sum(hum_values) / len(hum_values) if hum_values else None,
                        min(hum_values) if hum_values else None,
                        max(hum_values) if hum_values else None,
                        len(temp_values),
                        len(hum_values),
                        sum(fan_values) / len(fan_values) if fan_values else None,
                        max(fan_values) if fan_values else None,
                        sum(lamp_values) / len(lamp_values) if lamp_values else None,
                        majority(mode_values),
                        sum(setpoint_values) / len(setpoint_values) if setpoint_values else None,
                    ),
                )
                written += 1

            conn.commit()
            return written

    def resample_all_devices(self, intervals: List[int]) -> Dict[str, Dict[int, int]]:
        result: Dict[str, Dict[int, int]] = {}
        for device_id in self.list_devices():
            result[device_id] = {}
            for interval in intervals:
                result[device_id][interval] = self.resample_device(device_id, interval)
        return result

    def _fetch_resampled(self, device_id: str, interval_seconds: int) -> List[sqlite3.Row]:
        with self._connect() as conn:
            return conn.execute(
                """
                SELECT * FROM telemetry_resampled
                WHERE device_id = ? AND interval_seconds = ?
                ORDER BY bucket_start ASC
                """,
                (device_id, interval_seconds),
            ).fetchall()

    def build_forecast_dataset(
        self,
        device_id: str,
        interval_seconds: int = 60,
        lookback: int = 10,
        horizon_minutes: Tuple[int, int] = (10, 20),
    ) -> List[Dict[str, Any]]:
        rows = self._fetch_resampled(device_id, interval_seconds)
        if not rows:
            return []

        horizon_steps = tuple(max(1, int((h * 60) / interval_seconds)) for h in horizon_minutes)
        max_h = max(horizon_steps)

        result: List[Dict[str, Any]] = []
        for idx in range(lookback - 1, len(rows) - max_h):
            current = rows[idx]
            current_dt = parse_ts(current["bucket_start"])
            hour_sin, hour_cos = cyclic_hour_features(
                current_dt,
                settings.feature_utc_offset_hours,
            )
            sample: Dict[str, Any] = {
                "device_id": device_id,
                "bucket_start": current["bucket_start"],
                "interval_seconds": interval_seconds,
                "temp_now": current["temp_mean"],
                "hum_now": current["hum_mean"],
                "fan_pwm_now": current["fan_pwm_mean"],
                "lamp_on_ratio_now": current["lamp_on_ratio"],
                "mode_now": current["mode_majority"],
                "setpoint_now": current["setpoint_mean"],
                "hour_sin": hour_sin,
                "hour_cos": hour_cos,
                "day_period": day_period(
                    current_dt,
                    settings.feature_utc_offset_hours,
                    settings.day_start_hour,
                    settings.night_start_hour,
                ),
            }
            for lag in range(lookback):
                source = rows[idx - lag]
                sample[f"temp_lag_{lag}"] = source["temp_mean"]
                sample[f"hum_lag_{lag}"] = source["hum_mean"]
                sample[f"fan_pwm_lag_{lag}"] = source["fan_pwm_mean"]
                sample[f"lamp_ratio_lag_{lag}"] = source["lamp_on_ratio"]
            for horizon_min, horizon_step in zip(horizon_minutes, horizon_steps):
                future = rows[idx + horizon_step]
                sample[f"target_temp_plus_{horizon_min}m"] = future["temp_mean"]
                sample[f"target_hum_plus_{horizon_min}m"] = future["hum_mean"]
            result.append(sample)
        return result

    def build_habit_dataset(
        self,
        device_id: str,
        interval_seconds: int = 30,
        window_minutes_before: int = 10,
        window_minutes_after: int = 5,
    ) -> List[Dict[str, Any]]:
        rows = self._fetch_resampled(device_id, interval_seconds)
        if not rows:
            return []

        with self._connect() as conn:
            events = conn.execute(
                """
                SELECT * FROM control_events
                WHERE device_id = ?
                ORDER BY ts ASC
                """,
                (device_id,),
            ).fetchall()

        result: List[Dict[str, Any]] = []
        for event in events:
            if event["trigger_source"] != "app":
                continue
            event_dt = parse_ts(event["ts"])
            before_start = event_dt - timedelta(minutes=window_minutes_before)
            after_end = event_dt + timedelta(minutes=window_minutes_after)
            before = [r for r in rows if before_start <= parse_ts(r["bucket_start"]) < event_dt]
            after = [r for r in rows if event_dt <= parse_ts(r["bucket_start"]) <= after_end]
            if len(before) < 3:
                continue

            temp_before = [r["temp_mean"] for r in before if r["temp_mean"] is not None]
            hum_before = [r["hum_mean"] for r in before if r["hum_mean"] is not None]
            fan_before = [r["fan_pwm_mean"] for r in before if r["fan_pwm_mean"] is not None]
            lamp_before = [r["lamp_on_ratio"] for r in before if r["lamp_on_ratio"] is not None]
            setpoint_before = [r["setpoint_mean"] for r in before if r["setpoint_mean"] is not None]
            if not temp_before:
                continue

            hour_sin, hour_cos = cyclic_hour_features(
                event_dt,
                settings.feature_utc_offset_hours,
            )
            label = self._infer_habit_label(event)
            sample = {
                "device_id": device_id,
                "user_id": event["user_id"] or settings.default_user_id,
                "event_id": event["id"],
                "event_ts": event["ts"],
                "event_type": event["event_type"],
                "trigger_source": event["trigger_source"],
                "label": label,
                "user_feedback": event["user_feedback"],
                "temp_mean_before": sum(temp_before) / len(temp_before),
                "temp_min_before": min(temp_before),
                "temp_max_before": max(temp_before),
                "hum_mean_before": sum(hum_before) / len(hum_before) if hum_before else None,
                "fan_pwm_mean_before": sum(fan_before) / len(fan_before) if fan_before else None,
                "lamp_ratio_before": sum(lamp_before) / len(lamp_before) if lamp_before else None,
                "setpoint_mean_before": sum(setpoint_before) / len(setpoint_before) if setpoint_before else None,
                "mode_majority_before": majority([r["mode_majority"] for r in before if r["mode_majority"]]),
                "hour_sin": hour_sin,
                "hour_cos": hour_cos,
                "day_period": day_period(
                    event_dt,
                    settings.feature_utc_offset_hours,
                    settings.day_start_hour,
                    settings.night_start_hour,
                ),
            }
            if after:
                temp_after = [r["temp_mean"] for r in after if r["temp_mean"] is not None]
                hum_after = [r["hum_mean"] for r in after if r["hum_mean"] is not None]
                sample["temp_mean_after"] = sum(temp_after) / len(temp_after) if temp_after else None
                sample["hum_mean_after"] = sum(hum_after) / len(hum_after) if hum_after else None
            result.append(sample)
        return result

    @staticmethod
    def _infer_habit_label(event: sqlite3.Row) -> str:
        if event["user_feedback"] == -1:
            return "too_cold"
        if event["user_feedback"] == 1:
            return "too_hot"
        if event["user_feedback"] == 0:
            return "comfortable"
        event_type = (event["event_type"] or "").lower()
        new_value = (event["new_value"] or "").lower()
        if "fan" in event_type or "pwm" in event_type:
            return "prefer_cooler"
        if "lamp" in event_type or new_value in {"lamp_on", "heat_on"}:
            return "prefer_warmer"
        if event_type == "setpoint_change":
            return "setpoint_adjustment"
        return "manual_override"
