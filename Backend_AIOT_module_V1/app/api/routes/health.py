from typing import Any, Dict

from fastapi import APIRouter

from app.core.config import settings

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> Dict[str, Any]:
    return {
        "status": "ok",
        "db_path": settings.db_path,
        "mqtt_enabled": True,
        "resample_intervals": settings.resample_intervals,
    }
