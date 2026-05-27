
from typing import Any, Dict, Optional

from fastapi import APIRouter

from app.core.config import settings
from app.db.session import db
from app.schemas.ml_recommendation import MLRecommendationIn
from app.services.mqtt_bridge import MQTTBridge

router = APIRouter(prefix="/ml", tags=["ml"])


def bind_mqtt_bridge(mqtt_bridge: MQTTBridge) -> None:
    global _mqtt_bridge
    _mqtt_bridge = mqtt_bridge


_mqtt_bridge: MQTTBridge | None = None


@router.post("/recommendations")
def create_ml_recommendation(item: MLRecommendationIn) -> Dict[str, Any]:
    topic = settings.mqtt_topic_ml_setpoint_template.format(device_id=item.device_id)
    active_user_id = active_user_for_device(item.device_id)
    payload = {
        "device_id": item.device_id,
        "user_id": item.user_id,
        "ts": item.ts,
        "setpoint_dynamic": item.setpoint_dynamic,
        "control_hint": item.control_hint,
        "forecast": {
            "temp_plus_10m": item.pred_temp_plus_10m,
            "hum_plus_10m": item.pred_hum_plus_10m,
            "temp_plus_20m": item.pred_temp_plus_20m,
            "hum_plus_20m": item.pred_hum_plus_20m,
        },
        "model_version": item.model_version,
        "source_service": item.source_service,
    }
    skip_reason = ml_publish_skip_reason(item.device_id, item.user_id, active_user_id)
    publish_skipped = skip_reason is not None
    publish_success = False
    if not publish_skipped and _mqtt_bridge is not None:
        publish_success = _mqtt_bridge.publish_ml_setpoint(item.device_id, payload)

    recommendation_id = db.insert_ml_recommendation(
        item=item,
        published_topic=topic,
        publish_success=publish_success,
    )
    return {
        "status": "stored",
        "recommendation_id": recommendation_id,
        "published_topic": topic,
        "publish_skipped": publish_skipped,
        "skip_reason": skip_reason,
        "active_user_id": active_user_id,
        "publish_success": publish_success,
        "esp32_subscribe_topic": topic,
        "payload_example": payload,
    }


def ml_publish_skip_reason(device_id: str, user_id: Optional[str], active_user_id: Optional[str]) -> Optional[str]:
    if device_is_in_manual_mode(device_id):
        return "device_in_manual_mode"
    if user_id and active_user_id and str(user_id) != str(active_user_id):
        return "inactive_user"
    return None


def active_user_for_device(device_id: str) -> Optional[str]:
    latest_event = db.latest_user_control_event(device_id)
    if latest_event and latest_event.get("user_id"):
        return str(latest_event["user_id"])

    latest = db.latest_user_telemetry(device_id) or {}
    if latest.get("user_id"):
        return str(latest["user_id"])

    return None


def device_is_in_manual_mode(device_id: str) -> bool:
    mode_event = db.latest_control_event(device_id, event_type="mode_change")
    if mode_event and mode_event.get("new_value") in {"auto", "manual"}:
        return mode_event["new_value"] == "manual"

    twin = db.latest_device_twin(device_id) or {}
    latest = db.latest_telemetry(device_id) or {}
    mode = twin.get("mode_actual") or latest.get("mode")
    return mode == "manual"
