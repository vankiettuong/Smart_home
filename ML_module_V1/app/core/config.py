import os
from datetime import timezone

UTC = timezone.utc
BACKEND_BASE_URL = os.getenv("BACKEND_BASE_URL", "http://localhost:8000")
DEVICE_IDS = [x.strip() for x in os.getenv("DEVICE_IDS", "").split(",") if x.strip()]
POLL_SECONDS = int(os.getenv("POLL_SECONDS", "2"))
AUTO_RECOMMEND_ON_POLL = os.getenv("AUTO_RECOMMEND_ON_POLL", "true").lower() == "true"
CACHE_MAXLEN = int(os.getenv("CACHE_MAXLEN", "4000"))
MIN_SETPOINT = float(os.getenv("MIN_SETPOINT", "27.0"))
MAX_SETPOINT = float(os.getenv("MAX_SETPOINT", "32.0"))
DEFAULT_SETPOINT = float(os.getenv("DEFAULT_SETPOINT", "29.5"))
DEFAULT_USER_ID = os.getenv("DEFAULT_USER_ID", "anonymous")
FEATURE_UTC_OFFSET_HOURS = float(os.getenv("FEATURE_UTC_OFFSET_HOURS", "0"))
DAY_START_HOUR = int(os.getenv("DAY_START_HOUR", "6"))
NIGHT_START_HOUR = int(os.getenv("NIGHT_START_HOUR", "18"))
FORECAST_INTERVAL_SECONDS = int(os.getenv("FORECAST_INTERVAL_SECONDS", "60"))
FORECAST_LOOKBACK = int(os.getenv("FORECAST_LOOKBACK", "10"))
HABIT_INTERVAL_SECONDS = int(os.getenv("HABIT_INTERVAL_SECONDS", "30"))
HORIZON_1_MIN = int(os.getenv("HORIZON_1_MIN", "10"))
HORIZON_2_MIN = int(os.getenv("HORIZON_2_MIN", "20"))
N_ESTIMATORS = int(os.getenv("N_ESTIMATORS", "300"))
RANDOM_STATE = int(os.getenv("RANDOM_STATE", "42"))
BACKGROUND_AUTOTRAIN_SECONDS = int(os.getenv("BACKGROUND_AUTOTRAIN_SECONDS", "900"))
LOG_RECOMMENDATIONS_TO_BACKEND = os.getenv("LOG_RECOMMENDATIONS_TO_BACKEND", "true").lower() == "true"
