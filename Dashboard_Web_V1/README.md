# Dashboard_Web_V1

Dashboard static cho dự án Smart Home AIoT.

Chạy Backend rồi mở:

```bash
cd /home/Smart_Home_AIOT_V1/Backend_AIOT_module_V1
/home/Smart_Home_AIOT_V1/.venv/bin/uvicorn run:app --host 0.0.0.0 --port 8000 --reload
```

Truy cập:

```text
http://localhost:8000/dashboard/
```

Dashboard dùng các API:

- `GET /devices`
- `GET /devices/{device_id}/summary`
- `GET /devices/{device_id}/ml-recommendation/latest?user_id=...`
- `POST /devices/{device_id}/command`

Khung `Dự đoán ML` hiển thị `setpoint_dynamic`,
`pred_temp_plus_10m`, `pred_hum_plus_10m`, `pred_temp_plus_20m`,
và `pred_hum_plus_20m` từ recommendation mới nhất mà ML service đã lưu vào
Backend. ML service mặc định train từ CSV mô phỏng.

Feedback chỉ lưu vào Backend khi bấm một trong ba nút `Quá nóng`,
`Thoải mái`, `Quá lạnh`; không cần gửi MQTT. Với cấu hình mặc định hiện tại,
ML train từ dữ liệu mô phỏng nên feedback thật không tham gia huấn luyện.
