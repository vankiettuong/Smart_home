# Smart Home Backend (modular)

Cấu trúc backend được tách thành nhiều file theo kiểu project backend nhiều module:

```text
smart_home_backend_modular/
├── app/
│   ├── api/
│   │   └── routes/
│   │       ├── datasets.py
│   │       ├── devices.py
│   │       ├── health.py
│   │       └── ingest.py
│   ├── core/
│   │   ├── config.py
│   │   ├── helpers.py
│   │   └── time_utils.py
│   ├── db/
│   │   ├── database.py
│   │   └── session.py
│   ├── schemas/
│   │   ├── control_event.py
│   │   ├── device_twin.py
│   │   └── telemetry.py
│   ├── services/
│   │   └── mqtt_bridge.py
│   ├── workers/
│   │   └── resample_worker.py
│   └── main.py
├── requirements.txt
└── run.py
```

## Cài đặt

```bash
pip install -r requirements.txt
```

## Chạy server

```bash
uvicorn run:app --host 0.0.0.0 --port 8000 --reload
```

## MQTT topics

- `devices/<device_id>/telemetry`
- `devices/<device_id>/control-events`
- `devices/<device_id>/devicetwin`

Telemetry and app control events may include `user_id`. The setpoint dataset
uses `user_id` to personalize recommendations; missing IDs fall back to
`DEFAULT_USER_ID=anonymous`.

Time-of-day training features use UTC timestamps with:

- `FEATURE_UTC_OFFSET_HOURS=0`
- `DAY_START_HOUR=6`
- `NIGHT_START_HOUR=18`

Set `FEATURE_UTC_OFFSET_HOURS` to the deployment offset in both backend and ML
so `hour_sin`, `hour_cos`, and `day_period` match local day/night behavior.


## ML recommendation flow

- Backend receives sensor telemetry from MQTT and exposes latest telemetry and
  training datasets over HTTP for the ML service.
- ML service polls new telemetry from backend, runs inference, then posts
  recommendation to `POST /ml/recommendations`.
- Backend stores it in `ml_recommendations`
- Backend publishes MQTT to topic template: `devices/{device_id}/ml-setpoint`

Example ESP32 subscribe topic:

```
devices/esp32-room-a/ml-setpoint
```

Example payload:

```json
{
  "device_id": "esp32-room-a",
  "ts": "2026-05-19T10:20:00Z",
  "setpoint_dynamic": 29.2,
  "control_hint": "cool_more",
  "forecast": {
    "temp_plus_10m": 29.6,
    "hum_plus_10m": 68.1,
    "temp_plus_20m": 29.8,
    "hum_plus_20m": 69.0
  },
  "model_version": "rf_v1",
  "source_service": "ml_service"
}
```
