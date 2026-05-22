# Smart Home AIoT V1

This root contains the three cooperating modules:

- `Backend_AIOT_module_V1`: MQTT ingest, datasets, recommendation storage, and MQTT setpoint publish.
- `ML_module_V1`: Random Forest forecast and per-user setpoint recommendation service.
- `aiot_firmware_v3`: ESP32 firmware that publishes telemetry and control events.

## Personalization and time features

- Setpoint training uses `user_id` from app control events and live inference uses
  `user_id` from latest telemetry or `GET /devices/{device_id}/recommendation?user_id=...`.
- If telemetry or events do not identify a user, the modules use
  `DEFAULT_USER_ID=anonymous`.
- Forecast and setpoint datasets both include cyclical hour features
  `hour_sin`/`hour_cos` and categorical `day_period` (`day` or `night`).
- Timestamps remain UTC. Set `FEATURE_UTC_OFFSET_HOURS` in both backend and ML
  so time-of-day features use the local deployment hour. For UTC+7, use `7`.
- `DAY_START_HOUR` defaults to `6` and `NIGHT_START_HOUR` defaults to `18`.

## User data flow

App commands sent to firmware should include the active user:

```json
{"source":"app","user_id":"user-a","mode":"auto","setpoint":28.5}
```

Firmware publishes that `user_id` in telemetry and in user control events.
The backend stores it, the setpoint dataset exposes it, and ML includes it as a
categorical model feature.
