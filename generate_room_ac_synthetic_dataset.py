#!/usr/bin/env python3
"""Generate synthetic Vietnamese indoor room AC telemetry, forecast, and user habit data."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import argparse
import math

import numpy as np
import pandas as pd


VIETNAM_TZ = timezone(timedelta(hours=7))


def _local_time_features(timestamp: datetime) -> tuple[float, float, str]:
    local_dt = timestamp.astimezone(VIETNAM_TZ)
    hour = local_dt.hour + local_dt.minute / 60.0
    angle = 2.0 * math.pi * (hour / 24.0)
    period = "day" if 6 <= local_dt.hour < 18 else "night"
    return math.sin(angle), math.cos(angle), period


def _daily_heat_index(local_hour: float) -> float:
    # Peak heat is in the early afternoon, low point is before sunrise.
    return math.sin(2.0 * math.pi * ((local_hour - 8.0) / 24.0))


def _occupancy_level(local_dt: datetime, rng: np.random.Generator) -> float:
    hour = local_dt.hour + local_dt.minute / 60.0
    weekend = local_dt.weekday() >= 5

    if weekend and 8 <= hour < 23:
        base = 0.62
    elif 6 <= hour < 8:
        base = 0.44
    elif 18 <= hour < 23:
        base = 0.82
    elif 12 <= hour < 13.5:
        base = 0.34
    else:
        base = 0.12

    return float(np.clip(base + rng.normal(0, 0.08), 0.0, 1.0))


def simulate_room_ac_telemetry(
    start_time: datetime,
    minutes: int = 14 * 24 * 60,
    temp_mean: float = 28.0,
    hum_mean: float = 55.0,
    rng: np.random.Generator | None = None,
) -> pd.DataFrame:
    rng = rng or np.random.default_rng(42)
    rows = []
    temp = temp_mean + rng.normal(0, 0.18)
    hum = hum_mean + rng.normal(0, 1.0)
    compressor_on = False
    daily_biases = rng.normal(0, 0.12, max(1, math.ceil(minutes / 1440)))

    for minute in range(minutes):
        timestamp = (start_time + timedelta(minutes=minute)).astimezone(VIETNAM_TZ)
        local_hour = timestamp.hour + timestamp.minute / 60.0
        heat = _daily_heat_index(local_hour)
        occupancy = _occupancy_level(timestamp, rng)
        day_bias = daily_biases[min(minute // 1440, len(daily_biases) - 1)]

        outdoor_temp = 30.7 + 4.2 * heat + day_bias + rng.normal(0, 0.18)
        outdoor_hum = 78.0 - 8.0 * heat + rng.normal(0, 1.4)

        if 6 <= local_hour < 18:
            setpoint = temp_mean + 0.18 + day_bias * 0.15
        elif 18 <= local_hour < 23:
            setpoint = temp_mean - 0.12 + day_bias * 0.15
        else:
            setpoint = temp_mean - 0.02 + day_bias * 0.15

        if compressor_on and temp < setpoint - 0.22:
            compressor_on = False
        elif not compressor_on and temp > setpoint + 0.22:
            compressor_on = True

        passive_target = temp_mean + 0.55 * heat + 0.22 * occupancy + day_bias
        cooling = -0.065 if compressor_on else 0.006
        temp += 0.038 * (passive_target - temp) + cooling + rng.normal(0, 0.045)
        temp = float(np.clip(temp, 26.4, 29.7))

        hum_target = hum_mean - 2.3 * heat + 2.2 * occupancy + 0.05 * (outdoor_hum - 78.0)
        dehumidify = -0.045 if compressor_on else 0.012
        hum += 0.032 * (hum_target - hum) + dehumidify + rng.normal(0, 0.22)
        hum = float(np.clip(hum, 45.0, 66.0))

        fan_pwm = float(
            np.clip(
                22.0
                + 34.0 * int(compressor_on)
                + 48.0 * max(0.0, temp - setpoint)
                + rng.normal(0, 4.5),
                0.0,
                100.0,
            )
        )
        lamp_base = 0.08 if 7 <= local_hour < 17 else 0.42
        lamp_on_ratio = float(np.clip(lamp_base * occupancy + rng.normal(0, 0.05), 0.0, 1.0))
        mode = "cool" if compressor_on else "auto"

        rows.append(
            {
                "device_id": "esp32-room-a",
                "bucket_start": timestamp.isoformat(),
                "interval_seconds": 60,
                "temp_mean": round(temp, 2),
                "hum_mean": round(hum, 2),
                "fan_pwm_mean": round(fan_pwm, 2),
                "lamp_on_ratio": round(lamp_on_ratio, 3),
                "mode_majority": mode,
                "setpoint_mean": round(setpoint, 2),
                "ac_compressor_on": int(compressor_on),
                "outdoor_temp_est": round(outdoor_temp, 2),
                "outdoor_hum_est": round(outdoor_hum, 2),
                "occupancy_level": round(occupancy, 3),
            }
        )

    telemetry = pd.DataFrame(rows)
    telemetry["temp_mean"] = np.clip(
        telemetry["temp_mean"] + (temp_mean - telemetry["temp_mean"].mean()),
        26.4,
        29.7,
    ).round(2)
    telemetry["hum_mean"] = np.clip(
        telemetry["hum_mean"] + (hum_mean - telemetry["hum_mean"].mean()),
        45.0,
        66.0,
    ).round(2)
    return telemetry


def build_forecast_dataset(
    telemetry: pd.DataFrame,
    lookback: int = 10,
    horizon_minutes: tuple[int, int] = (10, 20),
    interval_seconds: int = 60,
) -> pd.DataFrame:
    horizon_steps = tuple(max(1, int((h * 60) / interval_seconds)) for h in horizon_minutes)
    max_h = max(horizon_steps)
    samples = []

    for idx in range(lookback - 1, len(telemetry) - max_h):
        current = telemetry.iloc[idx]
        current_dt = datetime.fromisoformat(str(current["bucket_start"]))
        hour_sin, hour_cos, period = _local_time_features(current_dt)
        sample = {
            "device_id": current["device_id"],
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
            "day_period": period,
        }
        for lag in range(lookback):
            source = telemetry.iloc[idx - lag]
            sample[f"temp_lag_{lag}"] = source["temp_mean"]
            sample[f"hum_lag_{lag}"] = source["hum_mean"]
            sample[f"fan_pwm_lag_{lag}"] = source["fan_pwm_mean"]
            sample[f"lamp_ratio_lag_{lag}"] = source["lamp_on_ratio"]

        for horizon_min, horizon_step in zip(horizon_minutes, horizon_steps):
            future = telemetry.iloc[idx + horizon_step]
            sample[f"target_temp_plus_{horizon_min}m"] = future["temp_mean"]
            sample[f"target_hum_plus_{horizon_min}m"] = future["hum_mean"]

        samples.append(sample)

    return pd.DataFrame(samples)


def _find_nearest_telemetry_row(telemetry: pd.DataFrame, timestamp: datetime) -> pd.Series:
    bucket_times = pd.to_datetime(telemetry["bucket_start"])
    idx = int((bucket_times - pd.Timestamp(timestamp)).abs().argmin())
    return telemetry.iloc[idx]


def simulate_user_preference_events(
    telemetry: pd.DataFrame,
    rng: np.random.Generator | None = None,
) -> pd.DataFrame:
    rng = rng or np.random.default_rng(43)
    start_time = datetime.fromisoformat(str(telemetry.iloc[0]["bucket_start"]))
    end_time = datetime.fromisoformat(str(telemetry.iloc[-1]["bucket_start"]))
    total_days = max(1, math.floor((end_time - start_time).total_seconds() / 86400))
    events = []

    daily_slots = [
        ("user-a", 7, 45),
        ("user-b", 8, 30),
        ("user-a", 12, 15),
        ("user-b", 13, 0),
        ("user-a", 18, 45),
        ("user-b", 19, 30),
        ("user-a", 21, 30),
        ("user-b", 22, 15),
    ]

    for day in range(total_days):
        day_start = start_time + timedelta(days=day)
        for user_id, hour, minute in daily_slots:
            event_time = day_start.replace(hour=hour, minute=minute, second=0, microsecond=0)
            event_time += timedelta(minutes=int(rng.integers(-8, 9)))
            if event_time <= start_time + timedelta(minutes=15) or event_time >= end_time - timedelta(minutes=10):
                continue

            nearest = _find_nearest_telemetry_row(telemetry, event_time)
            old_setpoint = float(nearest["setpoint_mean"])
            local_hour = event_time.hour + event_time.minute / 60.0

            if user_id == "user-a":
                # User A prefers a warmer room, so their target setpoint is higher.
                base_target = 29.25 if 6 <= local_hour < 18 else 29.55
                target_setpoint = float(np.clip(base_target + rng.normal(0, 0.12), 28.8, 30.1))
                note = "prefers_warmer"
            else:
                # User B prefers a cooler room, so their target setpoint is lower.
                base_target = 27.35 if 6 <= local_hour < 18 else 27.05
                target_setpoint = float(np.clip(base_target + rng.normal(0, 0.10), 27.0, 27.7))
                note = "prefers_cooler"

            events.append(
                {
                    "device_id": "esp32-room-a",
                    "user_id": user_id,
                    "ts": event_time.isoformat(),
                    "event_type": "setpoint_change",
                    "old_value": round(old_setpoint, 2),
                    "new_value": round(target_setpoint, 2),
                    "trigger_source": "app",
                    "user_feedback": "",
                    "preference_profile": note,
                }
            )

    return pd.DataFrame(events).sort_values("ts").reset_index(drop=True)


def build_habit_dataset(
    telemetry: pd.DataFrame,
    events: pd.DataFrame,
    window_minutes_before: int = 10,
    window_minutes_after: int = 5,
) -> pd.DataFrame:
    telemetry = telemetry.copy()
    telemetry["bucket_dt"] = pd.to_datetime(telemetry["bucket_start"])
    samples = []

    for event_id, event in events.iterrows():
        event_dt = datetime.fromisoformat(str(event["ts"]))
        before_start = event_dt - timedelta(minutes=window_minutes_before)
        after_end = event_dt + timedelta(minutes=window_minutes_after)
        before = telemetry[(telemetry["bucket_dt"] >= pd.Timestamp(before_start)) & (telemetry["bucket_dt"] < pd.Timestamp(event_dt))]
        after = telemetry[(telemetry["bucket_dt"] >= pd.Timestamp(event_dt)) & (telemetry["bucket_dt"] <= pd.Timestamp(after_end))]
        if len(before) < 3:
            continue

        event_type = str(event["event_type"])
        user_feedback = event["user_feedback"]
        label = "setpoint_adjustment" if event_type == "setpoint_change" else "manual_override"
        event_dt_parsed = datetime.fromisoformat(str(event["ts"]))
        hour_sin, hour_cos, period = _local_time_features(event_dt_parsed)

        sample = {
            "device_id": event["device_id"],
            "user_id": event["user_id"],
            "event_id": int(event_id) + 1,
            "event_ts": event["ts"],
            "event_type": event_type,
            "old_value": float(event["old_value"]),
            "new_value": float(event["new_value"]),
            "trigger_source": event["trigger_source"],
            "label": label,
            "user_feedback": user_feedback,
            "temp_mean_before": float(before["temp_mean"].mean()),
            "temp_min_before": float(before["temp_mean"].min()),
            "temp_max_before": float(before["temp_mean"].max()),
            "hum_mean_before": float(before["hum_mean"].mean()),
            "fan_pwm_mean_before": float(before["fan_pwm_mean"].mean()),
            "lamp_ratio_before": float(before["lamp_on_ratio"].mean()),
            "setpoint_mean_before": float(before["setpoint_mean"].mean()),
            "mode_majority_before": before["mode_majority"].mode().iloc[0],
            "hour_sin": hour_sin,
            "hour_cos": hour_cos,
            "day_period": period,
            "target_setpoint": float(event["new_value"]),
            "preference_profile": event["preference_profile"],
        }
        if not after.empty:
            sample["temp_mean_after"] = float(after["temp_mean"].mean())
            sample["hum_mean_after"] = float(after["hum_mean"].mean())
        samples.append(sample)

    return pd.DataFrame(samples)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate synthetic Vietnamese room AC datasets for forecast and user setpoint preference training."
    )
    parser.add_argument("--days", type=float, default=14.0, help="Total number of days to simulate.")
    parser.add_argument("--minutes", type=int, default=None, help="Total number of minutes to simulate. Overrides --days.")
    parser.add_argument("--output-dir", type=Path, default=Path("."), help="Output directory for generated CSV files.")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for reproducible simulation.")
    parser.add_argument("--start", default="2026-05-01T00:00:00+07:00", help="Local Vietnam start timestamp.")
    parser.add_argument("--temp-mean", type=float, default=28.0, help="Target average indoor temperature.")
    parser.add_argument("--hum-mean", type=float, default=55.0, help="Target average indoor humidity.")
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)

    start_time = datetime.fromisoformat(args.start)
    if start_time.tzinfo is None:
        start_time = start_time.replace(tzinfo=VIETNAM_TZ)
    else:
        start_time = start_time.astimezone(VIETNAM_TZ)

    minutes = args.minutes if args.minutes is not None else int(args.days * 24 * 60)
    rng = np.random.default_rng(args.seed)
    telemetry = simulate_room_ac_telemetry(
        start_time,
        minutes=minutes,
        temp_mean=args.temp_mean,
        hum_mean=args.hum_mean,
        rng=rng,
    )
    forecast = build_forecast_dataset(telemetry)
    preference_events = simulate_user_preference_events(telemetry, rng=np.random.default_rng(args.seed + 1))
    habit = build_habit_dataset(telemetry, preference_events)

    telemetry_path = args.output_dir / "synthetic_room_ac_telemetry.csv"
    forecast_path = args.output_dir / "synthetic_room_ac_forecast.csv"
    preference_path = args.output_dir / "synthetic_room_ac_user_preferences.csv"
    habit_path = args.output_dir / "synthetic_room_ac_habit.csv"

    telemetry.to_csv(telemetry_path, index=False)
    forecast.to_csv(forecast_path, index=False)
    preference_events.to_csv(preference_path, index=False)
    habit.to_csv(habit_path, index=False)

    print(f"Wrote {len(telemetry)} telemetry rows to {telemetry_path}")
    print(f"Wrote {len(forecast)} forecast samples to {forecast_path}")
    print(f"Wrote {len(preference_events)} user preference events to {preference_path}")
    print(f"Wrote {len(habit)} habit samples to {habit_path}")


if __name__ == "__main__":
    main()
