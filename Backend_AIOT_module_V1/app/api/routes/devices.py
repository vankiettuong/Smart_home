from typing import Any, Dict

from fastapi import APIRouter, HTTPException

from app.db.session import db

router = APIRouter(prefix="/devices", tags=["devices"])


@router.get("")
def devices() -> Dict[str, Any]:
    return {"devices": db.list_devices()}


@router.get("/{device_id}/telemetry/latest")
def latest_telemetry(device_id: str) -> Dict[str, Any]:
    row = db.latest_telemetry(device_id)
    if not row:
        raise HTTPException(status_code=404, detail="No telemetry for device")
    return row


@router.get("/{device_id}/summary")
def device_summary(device_id: str) -> Dict[str, Any]:
    latest = db.latest_telemetry(device_id)
    forecast_rows = db.build_forecast_dataset(
        device_id=device_id,
        interval_seconds=60,
        lookback=10,
        horizon_minutes=(10, 20),
    )
    habit_rows = db.build_habit_dataset(
        device_id=device_id,
        interval_seconds=30,
        window_minutes_before=10,
        window_minutes_after=5,
    )
    return {
        "device_id": device_id,
        "latest": latest,
        "forecast_samples": len(forecast_rows),
        "habit_samples": len(habit_rows),
    }



@router.get("/{device_id}/ml-recommendation/latest")
def latest_ml_recommendation(device_id: str) -> Dict[str, Any]:
    row = db.latest_ml_recommendation(device_id)
    if not row:
        raise HTTPException(status_code=404, detail="No ML recommendation for device")
    return row
