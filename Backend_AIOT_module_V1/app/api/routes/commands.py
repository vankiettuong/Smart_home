from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException

from app.core.config import settings
from app.core.time_utils import utc_now
from app.db.session import db
from app.schemas.control_event import ControlEventIn
from app.schemas.device_command import DeviceCommandIn
from app.services.mqtt_bridge import MQTTBridge

router = APIRouter(prefix="/devices", tags=["commands"])

_mqtt_bridge: MQTTBridge | None = None


def bind_mqtt_bridge(mqtt_bridge: MQTTBridge) -> None:
    global _mqtt_bridge
    _mqtt_bridge = mqtt_bridge


@router.post("/{device_id}/command")
def send_device_command(device_id: str, item: DeviceCommandIn) -> Dict[str, Any]:
    command_payload = _build_command_payload(item)
    if not any(
        value is not None
        for value in (item.user_id, item.mode, item.setpoint, item.fan_pwm, item.relay, item.feedback)
    ):
        raise HTTPException(status_code=400, detail="Command must include user_id, mode, setpoint, fan_pwm, relay, or feedback")

    topic = settings.mqtt_topic_command_template.format(device_id=device_id)
    stored_events = _store_control_events(device_id, item)

    publish_skipped = _is_feedback_only(item)
    publish_success = False
    if not publish_skipped and _mqtt_bridge is not None:
        publish_success = _mqtt_bridge.publish_json(topic=topic, payload=command_payload, qos=1, retain=False)

    return {
        "status": "accepted",
        "device_id": device_id,
        "published_topic": topic,
        "publish_skipped": publish_skipped,
        "publish_success": publish_success,
        "stored_events": stored_events,
        "payload": command_payload,
    }


def _build_command_payload(item: DeviceCommandIn) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "source": item.source,
        "ts": utc_now().isoformat(),
    }
    if item.user_id:
        payload["user_id"] = item.user_id
    if item.mode is not None:
        payload["mode"] = item.mode
    if item.setpoint is not None:
        payload["setpoint"] = item.setpoint
    if item.fan_pwm is not None:
        payload["fan_pwm"] = item.fan_pwm
    if item.relay is not None:
        payload["relay"] = item.relay
    if item.feedback is not None:
        payload["feedback"] = item.feedback
    return payload


def _is_feedback_only(item: DeviceCommandIn) -> bool:
    return (
        item.feedback is not None
        and item.mode is None
        and item.setpoint is None
        and item.fan_pwm is None
        and item.relay is None
    )


def _store_control_events(device_id: str, item: DeviceCommandIn) -> List[Dict[str, Any]]:
    events: List[ControlEventIn] = []

    is_user_activation_only = (
        item.user_id is not None
        and item.mode is None
        and item.setpoint is None
        and item.fan_pwm is None
        and item.relay is None
        and item.feedback is None
    )
    if is_user_activation_only:
        events.append(
            ControlEventIn(
                device_id=device_id,
                user_id=item.user_id,
                event_type="active_user_change",
                new_value=item.user_id,
                trigger_source=item.source,
            )
        )

    if item.mode is not None:
        events.append(
            ControlEventIn(
                device_id=device_id,
                user_id=item.user_id,
                event_type="mode_change",
                new_value=item.mode,
                trigger_source=item.source,
            )
        )

    if item.setpoint is not None:
        events.append(
            ControlEventIn(
                device_id=device_id,
                user_id=item.user_id,
                event_type="setpoint_change",
                new_value=f"{item.setpoint:.2f}",
                trigger_source=item.source,
            )
        )

    if item.fan_pwm is not None:
        events.append(
            ControlEventIn(
                device_id=device_id,
                user_id=item.user_id,
                event_type="fan_pwm_change",
                new_value=str(item.fan_pwm),
                trigger_source=item.source,
            )
        )

    if item.relay is not None:
        events.append(
            ControlEventIn(
                device_id=device_id,
                user_id=item.user_id,
                event_type="manual_override",
                new_value="relay_on" if item.relay else "relay_off",
                trigger_source=item.source,
            )
        )

    if item.feedback is not None:
        feedback_value = {"too_hot": 1, "comfortable": 0, "too_cold": -1}[item.feedback]
        events.append(
            ControlEventIn(
                device_id=device_id,
                user_id=item.user_id,
                event_type="comfort_feedback",
                new_value=item.feedback,
                trigger_source=item.source,
                user_feedback=feedback_value,
            )
        )

    stored: List[Dict[str, Any]] = []
    for event in events:
        db.insert_control_event(event)
        stored.append(
            {
                "event_type": event.event_type,
                "new_value": event.new_value,
                "user_feedback": event.user_feedback,
            }
        )
    return stored
