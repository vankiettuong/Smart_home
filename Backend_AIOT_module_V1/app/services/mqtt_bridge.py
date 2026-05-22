import json
from dataclasses import dataclass
from typing import Any, Optional

try:
    import paho.mqtt.client as mqtt
except Exception:
    mqtt = None  # pragma: no cover

from app.core.config import settings
from app.db.database import Database
from app.schemas.control_event import ControlEventIn
from app.schemas.device_twin import DeviceTwinIn
from app.schemas.telemetry import TelemetryIn


@dataclass
class MQTTBridge:
    db: Database
    client: Optional[Any] = None

    def start(self) -> None:
        if mqtt is None:
            print("[MQTT] paho-mqtt not installed. MQTT subscriber disabled.")
            return

        self.client = mqtt.Client()
        if settings.mqtt_username:
            self.client.username_pw_set(settings.mqtt_username, settings.mqtt_password)
            
        if settings.mqtt_port == 8883:
            self.client.tls_set()

        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self.client.connect_async(settings.mqtt_host, settings.mqtt_port, keepalive=30)
        self.client.loop_start()
        print(f"[MQTT] Connecting to {settings.mqtt_host}:{settings.mqtt_port}")

    def _on_connect(self, client, userdata, flags, rc):
        print(f"[MQTT] Connected with rc={rc}")
        client.subscribe(settings.mqtt_topic_telemetry, qos=1)
        client.subscribe(settings.mqtt_topic_control_events, qos=1)
        client.subscribe(settings.mqtt_topic_device_twin, qos=1)

    def _on_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
        except Exception as exc:
            print(f"[MQTT] Invalid JSON on topic={msg.topic}: {exc}")
            return

        topic = msg.topic
        try:
            if self._match_topic(topic, settings.mqtt_topic_telemetry):
                self.db.insert_telemetry(TelemetryIn(**payload))
            elif self._match_topic(topic, settings.mqtt_topic_control_events):
                self.db.insert_control_event(ControlEventIn(**payload))
            elif self._match_topic(topic, settings.mqtt_topic_device_twin):
                self.db.upsert_device_twin(DeviceTwinIn(**payload))
            else:
                print(f"[MQTT] Unhandled topic: {topic}")
        except Exception as exc:
            print(f"[MQTT] Error processing topic={topic}: {exc}")

    @staticmethod
    def _match_topic(real_topic: str, pattern: str) -> bool:
        real_parts = real_topic.split("/")
        pattern_parts = pattern.split("/")
        if len(real_parts) != len(pattern_parts):
            return False
        for rp, pp in zip(real_parts, pattern_parts):
            if pp == "+":
                continue
            if rp != pp:
                return False
        return True

    def publish_json(self, topic: str, payload: dict, qos: int = 1, retain: bool = False) -> bool:
        if self.client is None:
            print(f"[MQTT] Publish skipped because client is not ready. topic={topic}")
            return False
        try:
            message = json.dumps(payload, ensure_ascii=False)
            result = self.client.publish(topic, message, qos=qos, retain=retain)
            return result.rc == 0
        except Exception as exc:
            print(f"[MQTT] Publish failed topic={topic}: {exc}")
            return False

    def publish_ml_setpoint(self, device_id: str, payload: dict, qos: int = 1, retain: bool = False) -> bool:
        topic = settings.mqtt_topic_ml_setpoint_template.format(device_id=device_id)
        return self.publish_json(topic=topic, payload=payload, qos=qos, retain=retain)