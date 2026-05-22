import os
from dataclasses import dataclass, field
from typing import List


@dataclass(frozen=True)
class Settings:
    db_path: str = os.getenv("DB_PATH", "smart_home.db")
    mqtt_host: str = os.getenv("MQTT_HOST", "f7381aec847c405591c40af0e3305262.s1.eu.hivemq.cloud")
    mqtt_port: int = int(os.getenv("MQTT_PORT", "8883"))
    mqtt_username: str = os.getenv("MQTT_USERNAME", "User12345")
    mqtt_password: str = os.getenv("MQTT_PASSWORD", "Broker123")
    mqtt_topic_telemetry: str = os.getenv("MQTT_TOPIC_TELEMETRY", "devices/+/telemetry")
    mqtt_topic_control_events: str = os.getenv("MQTT_TOPIC_CONTROL_EVENTS", "devices/+/control-events")
    mqtt_topic_device_twin: str = os.getenv("MQTT_TOPIC_DEVICE_TWIN", "devices/+/devicetwin")
    mqtt_topic_ml_setpoint_template: str = os.getenv("MQTT_TOPIC_ML_SETPOINT_TEMPLATE", "devices/{device_id}/ml-setpoint")
    default_user_id: str = os.getenv("DEFAULT_USER_ID", "anonymous")
    feature_utc_offset_hours: float = float(os.getenv("FEATURE_UTC_OFFSET_HOURS", "0"))
    day_start_hour: int = int(os.getenv("DAY_START_HOUR", "6"))
    night_start_hour: int = int(os.getenv("NIGHT_START_HOUR", "18"))
    resample_intervals: List[int] = field(default_factory=lambda: [30, 60])
    resample_loop_period_seconds: int = int(os.getenv("RESAMPLE_LOOP_PERIOD_SECONDS", "20"))


settings = Settings()
