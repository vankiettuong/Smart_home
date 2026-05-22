from typing import Optional
from pydantic import BaseModel


class DeviceTwinIn(BaseModel):
    device_id: str
    ts: Optional[str] = None
    fan_pwm_actual: Optional[int] = None
    lamp_actual: Optional[int] = None
    mode_actual: Optional[str] = None
    setpoint_actual: Optional[float] = None
