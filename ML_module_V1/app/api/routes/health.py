from fastapi import APIRouter

from app.core.config import (
    BACKEND_BASE_URL,
    DEVICE_IDS,
    FORECAST_INTERVAL_SECONDS,
    FORECAST_LOOKBACK,
    HABIT_INTERVAL_SECONDS,
    SYNTHETIC_FORECAST_CSV,
    SYNTHETIC_HABIT_CSV,
    TRAINING_DATA_SOURCE,
)
from app.dependencies import ml_service

router = APIRouter(tags=["health"])


@router.get("/health")
def health():
    device_error = None
    try:
        devices = DEVICE_IDS or ml_service._available_device_ids()
    except Exception as exc:
        devices = []
        device_error = str(exc)

    return {
        "status": "ok",
        "backend": BACKEND_BASE_URL,
        "devices": devices,
        "device_error": device_error,
        "training_data_source": TRAINING_DATA_SOURCE,
        "synthetic_forecast_csv": str(SYNTHETIC_FORECAST_CSV),
        "synthetic_habit_csv": str(SYNTHETIC_HABIT_CSV),
        "forecast_interval_seconds": FORECAST_INTERVAL_SECONDS,
        "habit_interval_seconds": HABIT_INTERVAL_SECONDS,
        "lookback": FORECAST_LOOKBACK,
    }
