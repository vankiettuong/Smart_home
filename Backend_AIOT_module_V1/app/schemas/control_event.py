from typing import Optional
from pydantic import BaseModel, Field


class ControlEventIn(BaseModel):
    device_id: str
    user_id: Optional[str] = Field(default=None, examples=["user-a"])
    ts: Optional[str] = None
    event_type: str = Field(..., examples=["manual_override", "mode_change", "setpoint_change"])
    old_value: Optional[str] = None
    new_value: Optional[str] = None
    trigger_source: str = Field(default="app", examples=["app", "backend", "device"])
    user_feedback: Optional[int] = Field(default=None, ge=-1, le=1)
