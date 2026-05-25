#!/usr/bin/env python3
"""Load synthetic forecast and user preference CSVs into a simulation SQLite DB."""

from __future__ import annotations

from pathlib import Path
import argparse
import sqlite3
import sys

import pandas as pd


ROOT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = ROOT_DIR / "Backend_AIOT_module_V1"
sys.path.insert(0, str(BACKEND_DIR))

from app.db.database import Database  # noqa: E402


def insert_resampled_rows(conn: sqlite3.Connection, telemetry: pd.DataFrame, interval_seconds: int) -> None:
    rows = []
    for row in telemetry.to_dict("records"):
        rows.append(
            (
                row["device_id"],
                row["bucket_start"],
                interval_seconds,
                row["temp_mean"],
                row["temp_mean"],
                row["temp_mean"],
                row["hum_mean"],
                row["hum_mean"],
                row["hum_mean"],
                1,
                1,
                row["fan_pwm_mean"],
                row["fan_pwm_mean"],
                row["lamp_on_ratio"],
                row["mode_majority"],
                row["setpoint_mean"],
            )
        )

    conn.executemany(
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
        rows,
    )


def insert_raw_rows(conn: sqlite3.Connection, telemetry: pd.DataFrame) -> None:
    rows = []
    for row in telemetry.to_dict("records"):
        rows.append(
            (
                row["device_id"],
                None,
                row["bucket_start"],
                row["temp_mean"],
                row["hum_mean"],
                row["temp_mean"],
                row["hum_mean"],
                row["mode_majority"],
                row["setpoint_mean"],
                int(round(row["fan_pwm_mean"])),
                int(round(row["fan_pwm_mean"])),
                int(row["lamp_on_ratio"] >= 0.5),
                int(row["lamp_on_ratio"] >= 0.5),
                "synthetic",
                0,
            )
        )

    conn.executemany(
        """
        INSERT INTO telemetry_raw (
            device_id, user_id, ts, temp_raw, hum_raw, temp_ma, hum_ma,
            mode, setpoint_current, fan_pwm_cmd, fan_pwm_actual,
            lamp_cmd, lamp_actual, control_source, event_flag
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )


def insert_preference_events(conn: sqlite3.Connection, events: pd.DataFrame) -> None:
    rows = []
    for row in events.to_dict("records"):
        user_feedback = row.get("user_feedback")
        if pd.isna(user_feedback) or user_feedback == "":
            user_feedback = None
        rows.append(
            (
                row["device_id"],
                row["user_id"],
                row["ts"],
                row["event_type"],
                str(row["old_value"]),
                str(row["new_value"]),
                row["trigger_source"],
                user_feedback,
            )
        )

    conn.executemany(
        """
        INSERT INTO control_events (
            device_id, user_id, ts, event_type, old_value, new_value,
            trigger_source, user_feedback
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )


def upsert_device_twin(conn: sqlite3.Connection, telemetry: pd.DataFrame) -> None:
    latest = telemetry.iloc[-1]
    conn.execute(
        """
        INSERT INTO device_twin (
            device_id, ts, fan_pwm_actual, lamp_actual, mode_actual, setpoint_actual
        ) VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(device_id) DO UPDATE SET
            ts=excluded.ts,
            fan_pwm_actual=excluded.fan_pwm_actual,
            lamp_actual=excluded.lamp_actual,
            mode_actual=excluded.mode_actual,
            setpoint_actual=excluded.setpoint_actual
        """,
        (
            latest["device_id"],
            latest["bucket_start"],
            int(round(latest["fan_pwm_mean"])),
            int(latest["lamp_on_ratio"] >= 0.5),
            latest["mode_majority"],
            latest["setpoint_mean"],
        ),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Load synthetic user preference training data into SQLite.")
    parser.add_argument("--db-path", type=Path, default=BACKEND_DIR / "smart_home_userpref_sim.db")
    parser.add_argument("--telemetry-csv", type=Path, default=ROOT_DIR / "synthetic_room_ac_telemetry.csv")
    parser.add_argument("--preferences-csv", type=Path, default=ROOT_DIR / "synthetic_room_ac_user_preferences.csv")
    parser.add_argument("--keep-existing", action="store_true", help="Append data instead of clearing synthetic tables first.")
    args = parser.parse_args()

    args.db_path.parent.mkdir(parents=True, exist_ok=True)
    Database(str(args.db_path))

    telemetry = pd.read_csv(args.telemetry_csv)
    events = pd.read_csv(args.preferences_csv)

    with sqlite3.connect(args.db_path) as conn:
        if not args.keep_existing:
            for table in [
                "telemetry_raw",
                "telemetry_resampled",
                "control_events",
                "device_twin",
                "ml_recommendations",
            ]:
                conn.execute(f"DELETE FROM {table}")

        insert_raw_rows(conn, telemetry)
        insert_resampled_rows(conn, telemetry, interval_seconds=60)
        insert_resampled_rows(conn, telemetry, interval_seconds=30)
        insert_preference_events(conn, events)
        upsert_device_twin(conn, telemetry)
        conn.commit()

    print(f"Loaded {len(telemetry)} telemetry rows into {args.db_path}")
    print(f"Loaded {len(events)} user preference events into {args.db_path}")
    print("Inserted telemetry_resampled buckets for interval_seconds=60 and interval_seconds=30")


if __name__ == "__main__":
    main()
