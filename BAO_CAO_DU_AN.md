# Báo cáo dự án Smart Home AIoT V1

Ngày lập báo cáo: 2026-05-25

## 1. Tóm tắt dự án

Smart Home AIoT V1 là một hệ thống điều hòa/phòng thông minh kết hợp thiết bị IoT, backend thu thập dữ liệu, dịch vụ Machine Learning và dashboard web. Dự án hướng tới vòng lặp điều khiển tự động: ESP32 gửi telemetry lên MQTT, backend lưu và chuẩn hóa dữ liệu, ML service dự báo nhiệt độ/độ ẩm và đề xuất setpoint cá nhân hóa theo người dùng, sau đó backend publish setpoint trở lại thiết bị.

Hệ thống hiện có bốn phần chính:

- `aiot_firmware_v3`: firmware ESP32 đọc cảm biến DHT22, điều khiển relay/quạt PWM, publish telemetry và nhận command qua MQTT.
- `Backend_AIOT_module_V1`: FastAPI backend nhận MQTT/HTTP ingest, lưu SQLite, build dataset, lưu recommendation và publish MQTT command.
- `ML_module_V1`: FastAPI ML service dùng Random Forest để forecast và khuyến nghị `setpoint_dynamic`.
- `Dashboard_Web_V1`: dashboard HTML/CSS/JS tĩnh để xem telemetry, gửi command, ghi feedback và xem recommendation mới nhất.

## 2. Mục tiêu và phạm vi

### 2.1. Mục tiêu

- Giám sát nhiệt độ, độ ẩm, trạng thái relay/quạt và chế độ vận hành của thiết bị phòng.
- Thu thập dữ liệu telemetry và hành vi người dùng để phục vụ huấn luyện mô hình.
- Dự báo nhiệt độ/độ ẩm sau 10 phút và 20 phút.
- Gợi ý setpoint điều hòa theo `user_id`, thời gian trong ngày và lịch sử môi trường.
- Cho phép dashboard gửi lệnh auto/manual, setpoint, PWM, relay và comfort feedback.
- Tạo một luồng khép kín từ thiết bị thật đến ML rồi quay lại thiết bị.

### 2.2. Phạm vi hiện tại

Dự án đã có đủ thành phần prototype end-to-end. Backend và ML chạy như hai service riêng, giao tiếp qua HTTP; backend và firmware giao tiếp qua MQTT. Cơ sở dữ liệu dùng SQLite, phù hợp demo/local deployment. ML mặc định huấn luyện từ dữ liệu CSV mô phỏng, nhưng có thể chuyển sang train từ dataset backend bằng biến môi trường.

## 3. Công nghệ sử dụng

| Thành phần | Công nghệ chính | Vai trò |
|---|---|---|
| Firmware | Arduino/C++, ESP32, DHT22, PubSubClient, ArduinoJson | Đọc cảm biến, điều khiển relay/quạt, MQTT |
| Backend | Python, FastAPI, Pydantic, SQLite, paho-mqtt | API, lưu dữ liệu, MQTT bridge, dataset |
| ML service | Python, FastAPI, pandas, NumPy, scikit-learn | Train Random Forest, polling telemetry, inference |
| Dashboard | HTML, CSS, JavaScript thuần, Canvas | Giao diện giám sát và điều khiển |
| Dữ liệu | CSV mô phỏng, SQLite DB | Telemetry, habit, forecast, recommendation |

## 4. Kiến trúc tổng thể

```text
ESP32 firmware
  | MQTT: telemetry, control-events, devicetwin
  v
Backend FastAPI + SQLite
  | HTTP: latest telemetry, forecast dataset, habit dataset
  v
ML FastAPI service
  | HTTP POST: /ml/recommendations
  v
Backend
  | MQTT: devices/<device_id>/ml-setpoint
  v
ESP32 firmware
```

Dashboard chạy qua `/dashboard/` của backend hoặc mở tĩnh và gọi HTTP về backend. Người dùng thao tác trên dashboard, backend nhận command qua REST, lưu control event và publish MQTT tới topic command của thiết bị.

## 5. Cấu trúc thư mục chính

```text
Smart_Home_AIOT_V1/
├── Backend_AIOT_module_V1/
│   ├── app/
│   │   ├── api/routes/
│   │   ├── core/
│   │   ├── db/
│   │   ├── schemas/
│   │   ├── services/
│   │   └── workers/
│   ├── tests/
│   ├── requirements.txt
│   └── run.py
├── ML_module_V1/
│   ├── app/
│   │   ├── api/routes/
│   │   ├── core/
│   │   ├── models/
│   │   ├── services/
│   │   └── workers/
│   ├── tests/
│   ├── requirements.txt
│   └── run.py
├── Dashboard_Web_V1/
│   ├── index.html
│   ├── styles.css
│   └── app.js
├── aiot_firmware_v3/
│   └── aiot_firmware_v3.ino
├── generate_room_ac_synthetic_dataset.py
├── load_synthetic_userpref_db.py
├── synthetic_room_ac_*.csv
├── README.md
└── TUTORIAL.md
```

## 6. Backend AIoT

### 6.1. Vai trò

Backend là trung tâm nhận, lưu và phân phối dữ liệu. Service này:

- Subscribe MQTT topic telemetry, control events và device twin.
- Cung cấp HTTP ingest dự phòng cho telemetry/control-event/device-twin.
- Lưu dữ liệu vào SQLite.
- Resample telemetry theo các bucket 30 giây và 60 giây.
- Build forecast dataset và habit dataset cho ML.
- Nhận recommendation từ ML, lưu vào DB và publish setpoint qua MQTT.
- Cung cấp API cho dashboard.
- Serve dashboard static tại `/dashboard/`.

### 6.2. Các bảng dữ liệu SQLite

| Bảng | Nội dung |
|---|---|
| `telemetry_raw` | Telemetry thô từ thiết bị: nhiệt độ, độ ẩm, setpoint, mode, PWM, relay, user_id |
| `control_events` | Sự kiện người dùng/app: đổi mode, đổi setpoint, PWM, relay, comfort feedback |
| `device_twin` | Trạng thái mới nhất của thiết bị |
| `telemetry_resampled` | Telemetry đã gom bucket theo interval |
| `ml_recommendations` | Kết quả ML đã lưu và trạng thái publish MQTT |

Backend có cơ chế fallback: nếu telemetry thiếu `temp_ma` hoặc `hum_ma`, hệ thống dùng `temp_raw` và `hum_raw` để lưu/resample. Điều này giúp firmware đơn giản vẫn có thể tạo dataset huấn luyện.

### 6.3. MQTT topics backend sử dụng

| Topic | Hướng | Mục đích |
|---|---|---|
| `devices/+/telemetry` | Firmware -> Backend | Dữ liệu cảm biến và trạng thái điều khiển |
| `devices/+/control-events` | Firmware/App -> Backend | Hành vi người dùng phục vụ học setpoint |
| `devices/+/devicetwin` | Firmware -> Backend | Trạng thái hiện tại của thiết bị |
| `devices/{device_id}/command` | Backend -> Firmware | Lệnh từ dashboard/app |
| `devices/{device_id}/ml-setpoint` | Backend -> Firmware | Setpoint do ML đề xuất |

### 6.4. API backend chính

| Method | Endpoint | Chức năng |
|---|---|---|
| GET | `/health` | Kiểm tra backend, DB path và resample intervals |
| GET | `/devices` | Danh sách thiết bị |
| GET | `/devices/{device_id}/telemetry/latest` | Telemetry mới nhất |
| GET | `/devices/{device_id}/devicetwin/latest` | Device twin mới nhất |
| GET | `/devices/{device_id}/summary` | Tổng hợp telemetry, twin, số mẫu forecast/habit |
| GET | `/devices/{device_id}/ml-recommendation/latest` | Recommendation mới nhất, có thể lọc theo `user_id` |
| POST | `/devices/{device_id}/command` | Gửi command tới thiết bị qua MQTT và lưu control event |
| POST | `/ingest/telemetry` | HTTP ingest telemetry |
| POST | `/ingest/control-event` | HTTP ingest control event |
| POST | `/ingest/device-twin` | HTTP ingest device twin |
| POST | `/resample/run` | Chạy resample thủ công |
| GET | `/devices/{device_id}/dataset/forecast` | Dataset dự báo cho ML |
| GET | `/devices/{device_id}/dataset/habit` | Dataset hành vi/setpoint cho ML |
| POST | `/ml/recommendations` | Nhận recommendation từ ML và publish MQTT |

### 6.5. Luồng command từ dashboard

Dashboard gọi `POST /devices/{device_id}/command` với payload gồm `source`, `user_id`, `mode`, `setpoint`, `fan_pwm`, `relay` hoặc `feedback`. Backend:

1. Tạo payload command.
2. Lưu các `control_events` tương ứng.
3. Nếu payload chỉ có `user_id`, lưu `active_user_change` và publish command nhẹ để ESP32 đổi user active.
4. Nếu chỉ là feedback thì không publish MQTT.
5. Nếu là lệnh điều khiển thì publish tới `devices/{device_id}/command`.
6. Trả về trạng thái `publish_success`, `publish_skipped` và danh sách event đã lưu.

### 6.6. Logic bảo vệ publish ML

Khi ML gửi recommendation vào `/ml/recommendations`, backend luôn lưu recommendation. Backend chỉ publish MQTT nếu thiết bị không ở manual mode và recommendation thuộc user đang active. Recommendation của user khác vẫn được lưu để dashboard xem nhưng không được đẩy xuống ESP32, tránh việc user được ML xử lý sau ghi đè setpoint của user đang chọn.

## 7. ML service

### 7.1. Vai trò

ML service là dịch vụ độc lập dùng Random Forest để:

- Train mô hình forecast nhiệt độ/độ ẩm sau 10 phút và 20 phút.
- Train mô hình setpoint cá nhân hóa theo user.
- Poll telemetry mới nhất từ backend.
- Cache telemetry theo thiết bị.
- Tạo recommendation khi có telemetry mới.
- POST recommendation về backend.
- Tự train lại định kỳ.

### 7.2. Mô hình forecast

Mô hình forecast dùng `MultiOutputRegressor(RandomForestRegressor)` để dự báo bốn target:

- `target_temp_plus_10m`
- `target_hum_plus_10m`
- `target_temp_plus_20m`
- `target_hum_plus_20m`

Feature gồm telemetry hiện tại, các lag theo lookback, trạng thái fan/relay, mode, setpoint và feature thời gian:

- `hour_sin`
- `hour_cos`
- `day_period`

Ngưỡng tối thiểu hiện tại là khoảng 40 mẫu forecast usable.

### 7.3. Mô hình setpoint cá nhân hóa

Mô hình setpoint dùng `RandomForestRegressor` để suy ra `setpoint_dynamic`. Feature chính gồm:

- Nhiệt độ/độ ẩm trước event.
- Fan PWM, relay ratio, setpoint trước event.
- Mode trước event.
- `user_id`.
- `hour_sin`, `hour_cos`, `day_period`.
- `event_type`, `label`.

Nếu CSV/dataset có `target_setpoint`, mô hình dùng trực tiếp. Nếu không, service suy luận target từ `new_value`, `user_feedback` hoặc label như `too_hot`, `too_cold`, `comfortable`.

Ngưỡng tối thiểu hiện tại là khoảng 20 mẫu habit usable.

### 7.4. Recommendation

Endpoint `GET /devices/{device_id}/recommendation` tạo kết quả gồm:

- `setpoint_dynamic`
- nhiệt độ/độ ẩm dự báo sau 10 và 20 phút
- `control_hint`: `cool_more`, `cool_less_or_heat_more` hoặc `hold`
- `model_version`
- `training_source`
- `user_id`

Nếu model hoặc live history chưa đủ, service dùng fallback `DEFAULT_SETPOINT`. Nếu cấu hình `LOG_RECOMMENDATIONS_TO_BACKEND=true`, recommendation được POST về backend.

### 7.5. Worker nền

ML service có hai worker:

- `PollerWorker`: định kỳ gọi backend lấy telemetry mới. Khi có timestamp mới, cache telemetry và có thể tự tạo recommendation.
- `AutoTrainWorker`: định kỳ gọi `train_all()` để huấn luyện lại model.

### 7.6. API ML chính

| Method | Endpoint | Chức năng |
|---|---|---|
| GET | `/health` | Health check, cấu hình dataset và device list |
| POST | `/train` | Train tất cả thiết bị |
| POST | `/devices/{device_id}/train` | Train một thiết bị |
| POST | `/poll` | Poll telemetry một lần |
| GET | `/devices/{device_id}/recommendation` | Tạo recommendation |
| GET | `/devices/{device_id}/cache/status` | Xem trạng thái cache và model loaded |

## 8. Firmware ESP32

### 8.1. Phần cứng mặc định

| Thành phần | Cấu hình |
|---|---|
| Board | ESP32 |
| Sensor | DHT22 |
| DHT pin | GPIO 4 |
| Relay pin | GPIO 26 |
| Fan PWM pin | GPIO 25 |
| PWM frequency | 25 kHz |
| PWM resolution | 8 bit |
| Telemetry interval | 10 giây |
| Device twin interval | 30 giây |

### 8.2. Chức năng firmware

Firmware thực hiện:

- Kết nối Wi-Fi và MQTT.
- Đồng bộ thời gian NTP để tạo timestamp UTC.
- Đọc DHT22 và tính moving average.
- Publish telemetry mỗi 10 giây.
- Publish device twin định kỳ.
- Nhận `ml-setpoint` từ backend.
- Nhận command từ dashboard/app.
- Tự động điều khiển relay/quạt theo sai lệch nhiệt độ so với setpoint.
- Ghi control events khi app đổi mode, setpoint, PWM, relay hoặc feedback.

### 8.3. Auto và manual mode

Ở auto mode, firmware tính `errorC = tempForControl - setpointCurrentC`. Mặc định relay/đèn bật khi nhiệt độ thấp hơn setpoint đủ ngưỡng; nếu relay dùng cho máy nén làm lạnh có thể đổi `RELAY_AUTO_ON_WHEN_BELOW_SETPOINT` thành `false`. Fan PWM vẫn được scale theo sai lệch nhiệt độ nóng hơn setpoint.

Ở manual mode, command từ dashboard có thể đặt trực tiếp `fan_pwm` và `relay`. ML setpoint có thể được lưu nhưng không ép thiết bị rời manual mode nếu backend hoặc firmware đang giữ logic manual.

### 8.4. Lưu ý bảo mật firmware

Firmware có chế độ TLS prototype với `MQTT_TLS_INSECURE`. Chế độ này phù hợp demo nhưng không nên dùng production vì thiết bị không xác minh chứng chỉ broker. Khi triển khai thật cần cài root CA và tắt insecure mode.

## 9. Dashboard web

### 9.1. Vai trò

Dashboard là giao diện vận hành nhanh cho hệ thống. Các chức năng chính:

- Cấu hình Backend API, chọn device và user.
- Hiển thị nhiệt độ, độ ẩm, setpoint, mode và thời gian cập nhật.
- Vẽ chart telemetry gần đây bằng Canvas.
- Gửi command auto/manual/setpoint/fan PWM/relay.
- Gửi comfort feedback: `too_hot`, `comfortable`, `too_cold`.
- Hiển thị ML recommendation mới nhất cho user đang chọn.
- Ghi log trạng thái poll và command.

### 9.2. API dashboard sử dụng

- `GET /devices`
- `GET /devices/{device_id}/summary`
- `GET /devices/{device_id}/ml-recommendation/latest?user_id=...`
- `POST /devices/{device_id}/command`

Dashboard có cơ chế pending command để tạm hiển thị trạng thái vừa gửi trong lúc chờ telemetry/device twin xác nhận từ ESP32.

## 10. Dữ liệu và mô phỏng

### 10.1. CSV mô phỏng

Dự án có script `generate_room_ac_synthetic_dataset.py` tạo dữ liệu phòng điều hòa giả lập theo bối cảnh Việt Nam, gồm:

| File | Số dòng hiện tại | Nội dung |
|---|---:|---|
| `synthetic_room_ac_telemetry.csv` | 20.161 | Telemetry mô phỏng theo phút |
| `synthetic_room_ac_forecast.csv` | 20.132 | Mẫu forecast có lag và target 10/20 phút |
| `synthetic_room_ac_habit.csv` | 105 | Mẫu habit/setpoint theo user |
| `synthetic_room_ac_user_preferences.csv` | 105 | Event preference của user-a/user-b |

Lưu ý: số dòng trên tính cả header CSV theo `wc -l`; số bản ghi dữ liệu xấp xỉ số dòng trừ 1.

### 10.2. SQLite DB hiện có

Kiểm tra cục bộ ngày 2026-05-25 cho thấy:

| DB | telemetry_raw | telemetry_resampled | control_events | device_twin | ml_recommendations |
|---|---:|---:|---:|---:|---:|
| `smart_home.db` | 3.213 | 1.060 | 77 | 1 | 930 |
| `smart_home_userpref_sim.db` | 20.338 | 40.411 | 109 | 1 | 291 |
| `smart_home_sim.db` | 0 | 20.160 | 0 | 0 | 0 |

Các DB này cho thấy dự án đã có dữ liệu thử nghiệm, dữ liệu mô phỏng và recommendation được lưu lại.

### 10.3. Luồng feature thời gian

Backend và ML cùng sử dụng:

- `FEATURE_UTC_OFFSET_HOURS`
- `DAY_START_HOUR`
- `NIGHT_START_HOUR`
- `DEFAULT_USER_ID`

Timestamp vẫn lưu theo UTC, còn feature giờ trong ngày được dịch theo offset deployment. Nếu backend và ML dùng offset khác nhau, model có thể học/inference sai day-night context.

## 11. Hướng dẫn chạy hệ thống

### 11.1. Backend

```bash
cd /home/Smart_Home_AIOT_V1/Backend_AIOT_module_V1
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt

export DB_PATH=smart_home.db
export MQTT_HOST=<mqtt-host>
export MQTT_PORT=8883
export MQTT_USERNAME=<mqtt-username>
export MQTT_PASSWORD=<mqtt-password>
export FEATURE_UTC_OFFSET_HOURS=7
export DAY_START_HOUR=6
export NIGHT_START_HOUR=18
export DEFAULT_USER_ID=anonymous

uvicorn run:app --host 0.0.0.0 --port 8000 --reload
```

Kiểm tra:

```bash
curl http://localhost:8000/health
curl http://localhost:8000/devices
```

### 11.2. ML service

```bash
cd /home/Smart_Home_AIOT_V1/ML_module_V1
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt

export BACKEND_BASE_URL=http://localhost:8000
export DEVICE_IDS=esp32-room-a
export AUTO_RECOMMEND_ON_POLL=true
export POLL_SECONDS=2
export FEATURE_UTC_OFFSET_HOURS=7
export DAY_START_HOUR=6
export NIGHT_START_HOUR=18
export DEFAULT_USER_ID=anonymous

uvicorn run:app --host 0.0.0.0 --port 8100 --reload
```

Kiểm tra:

```bash
curl http://localhost:8100/health
curl http://localhost:8100/devices/esp32-room-a/cache/status
```

### 11.3. Dashboard

Khi backend chạy, truy cập:

```text
http://localhost:8000/dashboard/
```

### 11.4. Firmware

Mở `aiot_firmware_v3/aiot_firmware_v3.ino`, cấu hình Wi-Fi, MQTT broker, port, username/password, `DEVICE_ID`, TLS mode và chân phần cứng. Sau đó nạp bằng Arduino IDE hoặc PlatformIO.

## 12. Kiểm thử hiện có

Dự án có unit test cho backend và ML:

- `Backend_AIOT_module_V1/tests/test_raw_fallback.py`: kiểm tra fallback từ raw telemetry sang moving average khi thiếu `temp_ma`/`hum_ma`.
- `Backend_AIOT_module_V1/tests/test_user_time_features.py`: kiểm tra `user_id`, `hour_sin`, `hour_cos`, `day_period` trong habit/forecast dataset và migration thêm cột `user_id`.
- `ML_module_V1/tests/test_poll_recommendation_flow.py`: kiểm tra poll telemetry mới, tạo recommendation và tránh gửi lặp khi timestamp không đổi.

Các test này tập trung đúng vào các rủi ro quan trọng: chất lượng dữ liệu đầu vào, feature thời gian/user và luồng recommendation tự động.

## 13. Đánh giá hiện trạng

### 13.1. Điểm mạnh

- Kiến trúc module rõ ràng: firmware, backend, ML, dashboard tách riêng.
- Có luồng end-to-end hoàn chỉnh từ thiết bị đến ML và quay lại thiết bị.
- Backend hỗ trợ cả MQTT ingest và HTTP ingest, tiện debug.
- Dataset forecast/habit được build có cấu trúc tốt cho ML.
- Có cá nhân hóa theo `user_id`.
- Có feature thời gian dạng cyclical, phù hợp mô hình cây và tránh coi giờ là biến tuyến tính đơn giản.
- Có dữ liệu mô phỏng đủ lớn để demo ML khi chưa có thiết bị thật.
- Dashboard đủ chức năng vận hành prototype.
- Có test cho những thay đổi dữ liệu quan trọng.

### 13.2. Hạn chế

- SQLite phù hợp prototype nhưng chưa phù hợp production nhiều thiết bị/nhiều người dùng.
- Cấu hình broker và thông tin nhạy cảm còn có thể bị hard-code trong code mẫu; nên chuyển toàn bộ sang biến môi trường hoặc secret manager.
- Firmware đang có tùy chọn TLS insecure cho demo.
- ML model hiện lưu trong RAM, chưa có model registry/persistence rõ ràng.
- ML mặc định train từ synthetic CSV, feedback thật từ dashboard chưa tự động tham gia huấn luyện nếu không đổi `TRAINING_DATA_SOURCE`.
- Dashboard chưa có authentication/authorization.
- Backend chưa có phân quyền API, rate limit hoặc validation bảo mật ở mức production.
- Chưa có CI/CD, linting và test runner tập trung tại root.
- Các file DB, WAL/SHM và `__pycache__` đang nằm trong workspace; nên loại khỏi version control bằng `.gitignore` nếu dùng Git.

## 14. Rủi ro kỹ thuật

| Rủi ro | Ảnh hưởng | Khuyến nghị |
|---|---|---|
| Sai lệch timezone giữa backend và ML | Recommendation sai theo khung ngày/đêm | Đồng bộ env `FEATURE_UTC_OFFSET_HOURS`, thêm health check so sánh cấu hình |
| MQTT mất kết nối | Không nhận telemetry hoặc không gửi command | Thêm retry/backoff, metrics và alert |
| ML chưa đủ dữ liệu | Fallback setpoint, recommendation ít cá nhân hóa | Hiển thị rõ trạng thái model/data readiness trên dashboard |
| Manual mode bị ghi đè | Trải nghiệm người dùng xấu | Giữ logic skip publish khi manual, test thêm ở backend |
| Sensor lỗi hoặc dữ liệu thiếu | Dataset kém, forecast sai | Validate range, lọc outlier, đánh dấu quality flag |
| Hard-coded credentials | Lộ thông tin triển khai | Dùng `.env`, secret manager, không commit credentials |
| SQLite tăng kích thước | Chậm query và khó backup | Chuyển PostgreSQL/TimescaleDB khi scale |

## 15. Đề xuất phát triển tiếp

### 15.1. Ngắn hạn

- Thêm `.gitignore` cho `.venv`, `__pycache__`, `*.db`, `*.db-wal`, `*.db-shm`.
- Tách cấu hình mẫu thành `.env.example`, bỏ thông tin thật khỏi source.
- Thêm endpoint/model status để dashboard biết model đã train đủ hay đang fallback.
- Thêm test cho `device_is_in_manual_mode` và `POST /devices/{device_id}/command`.
- Thêm script chạy test toàn bộ repo.
- Ghi rõ chế độ demo/synthetic trong dashboard.

### 15.2. Trung hạn

- Lưu model đã train ra file hoặc object storage để service restart không mất model.
- Thêm tracking metric MAE/R2 theo phiên train và hiển thị trên dashboard.
- Cho phép feedback thật tham gia incremental retraining hoặc batch retraining.
- Bổ sung authentication cho dashboard/API.
- Thêm logging có cấu trúc và metrics Prometheus/OpenTelemetry.
- Chuẩn hóa schema command/recommendation thành tài liệu OpenAPI/JSON Schema dùng chung cho firmware/app.

### 15.3. Dài hạn

- Chuyển database sang PostgreSQL/TimescaleDB nếu triển khai nhiều phòng/thiết bị.
- Thiết kế multi-tenant/multi-home nếu cần quản lý nhiều nhà.
- Dùng model registry, experiment tracking và versioning dữ liệu.
- Thêm OTA firmware update.
- Tối ưu thuật toán điều khiển bằng PID/MPC hoặc policy learning sau khi có dữ liệu thật đủ lớn.
- Triển khai production với Docker Compose/Kubernetes, TLS đầy đủ, secrets và backup tự động.

## 16. Kết luận

Smart Home AIoT V1 là một prototype khá hoàn chỉnh cho bài toán điều hòa thông minh có cá nhân hóa. Dự án đã có firmware, backend, ML service, dashboard, dữ liệu mô phỏng, database thử nghiệm và unit test. Điểm nổi bật là luồng dữ liệu end-to-end rõ ràng, dataset ML được xây từ telemetry/control event và recommendation có thể quay lại thiết bị qua MQTT.

Để tiến tới môi trường production, dự án cần tập trung vào bảo mật cấu hình, persistence cho model, quan sát hệ thống, quản lý dữ liệu thật, authentication và hạ tầng triển khai. Với nền tảng hiện tại, dự án phù hợp để demo, thử nghiệm thuật toán điều khiển, thu thập dữ liệu người dùng và mở rộng dần thành hệ thống Smart Home AIoT thực tế.
