
from typing import Any, Dict

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
    publish_success = False
    if _mqtt_bridge is not None:
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
        "publish_success": publish_success,
        "esp32_subscribe_topic": topic,
        "payload_example": payload,
    }
