from typing import Literal, Optional

from pydantic import BaseModel, Field


class DeviceCommandIn(BaseModel):
    user_id: Optional[str] = Field(default=None, examples=["user-a"])
    source: str = Field(default="dashboard", examples=["dashboard"])
    mode: Optional[Literal["auto", "manual"]] = None
    setpoint: Optional[float] = Field(default=None, ge=27.0, le=32.0)
    fan_pwm: Optional[int] = Field(default=None, ge=0, le=255)
    relay: Optional[bool] = None
    feedback: Optional[Literal["too_hot", "comfortable", "too_cold"]] = None
