from typing import Optional

from fastapi import APIRouter, Query

from app.dependencies import ml_service

router = APIRouter(tags=["recommendations"])


@router.get("/devices/{device_id}/recommendation")
def recommendation(device_id: str, user_id: Optional[str] = Query(default=None)):
    return ml_service.recommend(device_id, user_id=user_id)
