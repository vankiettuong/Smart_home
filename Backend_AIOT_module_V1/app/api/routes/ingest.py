from typing import Dict

from fastapi import APIRouter

from app.db.session import db
from app.schemas.control_event import ControlEventIn
from app.schemas.device_twin import DeviceTwinIn
from app.schemas.telemetry import TelemetryIn

router = APIRouter(prefix="/ingest", tags=["ingest"])


@router.post("/telemetry")
def ingest_telemetry(item: TelemetryIn) -> Dict[str, str]:
    db.insert_telemetry(item)
    return {"status": "stored"}


@router.post("/control-event")
def ingest_control_event(item: ControlEventIn) -> Dict[str, str]:
    db.insert_control_event(item)
    return {"status": "stored"}


@router.post("/device-twin")
def ingest_device_twin(item: DeviceTwinIn) -> Dict[str, str]:
    db.upsert_device_twin(item)
    return {"status": "stored"}
