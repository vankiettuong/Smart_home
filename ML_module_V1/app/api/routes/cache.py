from fastapi import APIRouter

from app.core.config import FORECAST_INTERVAL_SECONDS, HABIT_INTERVAL_SECONDS
from app.dependencies import ml_service

router = APIRouter(tags=["cache"])


@router.get("/devices/{device_id}/cache/status")
def cache_status(device_id: str):
    history_60 = ml_service._build_bucketed_history(device_id, FORECAST_INTERVAL_SECONDS)
    history_30 = ml_service._build_bucketed_history(device_id, HABIT_INTERVAL_SECONDS)
    return {
        "device_id": device_id,
        "raw_cache_size": len(ml_service.raw_cache.get(device_id, [])),
        "bucket_count_60s": len(history_60),
        "bucket_count_30s": len(history_30),
        "forecast_model_loaded": device_id in ml_service.forecast_models,
        "setpoint_model_loaded": device_id in ml_service.setpoint_models,
    }
