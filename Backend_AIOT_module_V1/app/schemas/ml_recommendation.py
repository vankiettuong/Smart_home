
from typing import Optional

from pydantic import BaseModel, Field


class MLRecommendationIn(BaseModel):
    device_id: str
    user_id: Optional[str] = None
    ts: Optional[str] = None
    setpoint_dynamic: Optional[float] = None
    pred_temp_plus_10m: Optional[float] = None
    pred_hum_plus_10m: Optional[float] = None
    pred_temp_plus_20m: Optional[float] = None
    pred_hum_plus_20m: Optional[float] = None
    control_hint: Optional[str] = Field(default='hold', examples=['cool_more', 'cool_less_or_heat_more', 'hold'])
    model_version: Optional[str] = Field(default='rf_v1')
    source_service: Optional[str] = Field(default='ml_service')
