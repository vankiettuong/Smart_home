from fastapi import APIRouter

from app.core.config import (
    BACKEND_BASE_URL,
    DEVICE_IDS,
    FORECAST_INTERVAL_SECONDS,
    FORECAST_LOOKBACK,
    HABIT_INTERVAL_SECONDS,
)
from app.dependencies import backend_client

router = APIRouter(tags=["health"])


@router.get("/health")
def health():
    return {
        "status": "ok",
        "backend": BACKEND_BASE_URL,
        "devices": DEVICE_IDS or backend_client.get_devices(),
        "forecast_interval_seconds": FORECAST_INTERVAL_SECONDS,
        "habit_interval_seconds": HABIT_INTERVAL_SECONDS,
        "lookback": FORECAST_LOOKBACK,
    }
