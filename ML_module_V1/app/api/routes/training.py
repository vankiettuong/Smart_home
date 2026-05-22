from fastapi import APIRouter

from app.dependencies import ml_service

router = APIRouter(tags=["training"])


@router.post("/train")
def train_all():
    return ml_service.train_all()


@router.post("/devices/{device_id}/train")
def train_device(device_id: str):
    return ml_service.train_device(device_id)


@router.post("/poll")
def poll_once():
    return ml_service.poll_latest_once()
