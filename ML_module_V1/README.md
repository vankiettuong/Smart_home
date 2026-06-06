# Smart Home ML RF Service (Modular)

Dịch vụ Machine Learning dùng Random Forest để:

- dự báo nhiệt độ/độ ẩm sau 10 và 20 phút
- suy ra `setpoint_dynamic` từ dữ liệu hành vi người dùng mô phỏng
- polling dữ liệu telemetry mới nhất từ backend
- tự huấn luyện lại định kỳ

## Cài đặt

```bash
pip install -r requirements.txt
uvicorn run:app --host 0.0.0.0 --port 8100 --reload
```

## Biến môi trường

- `BACKEND_BASE_URL=http://localhost:8000`
- `DEVICE_IDS=esp32-room-a,esp32-room-b`
- `RECOMMEND_USER_IDS=user-a,user-b`
- `POLL_SECONDS=2`
- `AUTO_RECOMMEND_ON_POLL=true`
- `DEFAULT_USER_ID=anonymous`
- `FEATURE_UTC_OFFSET_HOURS=0`
- `DAY_START_HOUR=6`
- `NIGHT_START_HOUR=18`
- `BACKGROUND_AUTOTRAIN_SECONDS=900`
- `FORECAST_INTERVAL_SECONDS=60`
- `HABIT_INTERVAL_SECONDS=30`

## API chính

- `GET /health`
- `POST /train`
- `POST /devices/{device_id}/train`
- `POST /poll`
- `GET /devices/{device_id}/recommendation`
- `GET /devices/{device_id}/cache/status`
