from typing import Any, Dict

from fastapi import APIRouter, Query

from app.core.config import settings
from app.db.session import db

router = APIRouter(tags=["datasets"])


@router.post("/resample/run")
def run_resample() -> Dict[str, Any]:
    return {"result": db.resample_all_devices(settings.resample_intervals)}


@router.get("/devices/{device_id}/dataset/forecast")
def forecast_dataset(
    device_id: str,
    interval_seconds: int = Query(60, ge=10, le=600),
    lookback: int = Query(10, ge=3, le=120),
    horizon_1_min: int = Query(10, ge=1, le=120),
    horizon_2_min: int = Query(20, ge=1, le=180),
    limit: int = Query(200, ge=1, le=5000),
) -> Dict[str, Any]:
    rows = db.build_forecast_dataset(
        device_id=device_id,
        interval_seconds=interval_seconds,
        lookback=lookback,
        horizon_minutes=(horizon_1_min, horizon_2_min),
    )
    return {"count": len(rows), "rows": rows[:limit]}


@router.get("/devices/{device_id}/dataset/habit")
def habit_dataset(
    device_id: str,
    interval_seconds: int = Query(30, ge=10, le=600),
    window_minutes_before: int = Query(10, ge=1, le=120),
    window_minutes_after: int = Query(5, ge=1, le=120),
    limit: int = Query(200, ge=1, le=5000),
) -> Dict[str, Any]:
    rows = db.build_habit_dataset(
        device_id=device_id,
        interval_seconds=interval_seconds,
        window_minutes_before=window_minutes_before,
        window_minutes_after=window_minutes_after,
    )
    return {"count": len(rows), "rows": rows[:limit]}
