from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple
import math

UTC = timezone.utc


def utc_now() -> datetime:
    return datetime.now(tz=UTC)


def parse_ts(value: Optional[str]) -> datetime:
    if not value:
        return utc_now()
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def floor_time(dt: datetime, interval_seconds: int) -> datetime:
    epoch = int(dt.timestamp())
    floored = epoch - (epoch % interval_seconds)
    return datetime.fromtimestamp(floored, tz=UTC)


def feature_local_time(dt: datetime, utc_offset_hours: float = 0.0) -> datetime:
    return dt.astimezone(UTC) + timedelta(hours=utc_offset_hours)


def cyclic_hour_features(dt: datetime, utc_offset_hours: float = 0.0) -> Tuple[float, float]:
    local_dt = feature_local_time(dt, utc_offset_hours)
    hour = local_dt.hour + local_dt.minute / 60.0
    angle = 2.0 * math.pi * (hour / 24.0)
    return math.sin(angle), math.cos(angle)


def day_period(
    dt: datetime,
    utc_offset_hours: float = 0.0,
    day_start_hour: int = 6,
    night_start_hour: int = 18,
) -> str:
    local_hour = feature_local_time(dt, utc_offset_hours).hour
    return "day" if day_start_hour <= local_hour < night_start_hour else "night"
