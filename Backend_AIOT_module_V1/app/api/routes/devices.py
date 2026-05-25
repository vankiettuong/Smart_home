from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query

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


@router.get("/{device_id}/devicetwin/latest")
def latest_device_twin(device_id: str) -> Dict[str, Any]:
    row = db.latest_device_twin(device_id)
    if not row:
        raise HTTPException(status_code=404, detail="No device twin for device")
    return row


@router.get("/{device_id}/summary")
def device_summary(device_id: str) -> Dict[str, Any]:
    latest = db.latest_telemetry(device_id)
    twin = db.latest_device_twin(device_id)
    forecast_samples = db.count_forecast_samples(
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
        "device_twin": twin,
        "forecast_samples": forecast_samples,
        "habit_samples": len(habit_rows),
    }



@router.get("/{device_id}/ml-recommendation/latest")
def latest_ml_recommendation(
    device_id: str,
    user_id: Optional[str] = Query(default=None),
) -> Dict[str, Any]:
    row = db.latest_ml_recommendation(device_id, user_id=user_id)
    if not row:
        raise HTTPException(status_code=404, detail="No ML recommendation for device")
    return row
