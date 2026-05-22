from typing import Optional
from pydantic import BaseModel, Field


class TelemetryIn(BaseModel):
    device_id: str = Field(..., examples=["esp32-room-a"])
    user_id: Optional[str] = Field(default=None, examples=["user-a"])
    ts: Optional[str] = None
    temp_raw: Optional[float] = None
    hum_raw: Optional[float] = None
    temp_ma: Optional[float] = None
    hum_ma: Optional[float] = None
    mode: Optional[str] = Field(default="auto", examples=["auto", "manual"])
    setpoint_current: Optional[float] = None
    fan_pwm_cmd: Optional[int] = None
    fan_pwm_actual: Optional[int] = None
    lamp_cmd: Optional[int] = None
    lamp_actual: Optional[int] = None
    control_source: Optional[str] = Field(default="device")
    event_flag: Optional[int] = 0
