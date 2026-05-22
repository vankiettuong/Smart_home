# Tutorial chay du an Smart Home AIoT V1

Tai lieu nay huong dan chay end-to-end ba module:

- `Backend_AIOT_module_V1`: nhan MQTT, luu SQLite, tao dataset, publish setpoint ML.
- `ML_module_V1`: train Random Forest, poll telemetry, du doan forecast va setpoint.
- `aiot_firmware_v3`: firmware ESP32 doc cam bien, dieu khien relay/quat, gui telemetry va control event.

## 1. Luong chay tong the

```text
ESP32 firmware
  | MQTT telemetry, control-events, devicetwin
  v
Backend
  | HTTP latest telemetry + forecast/habit datasets
  v
ML service
  | HTTP POST /ml/recommendations
  v
Backend
  | MQTT devices/<device_id>/ml-setpoint
  v
ESP32 firmware -> cap nhat setpoint, dieu khien relay va quat
```

Du an co hai bai toan ML:

1. Forecast nhiet do/do am sau 10 phut va 20 phut.
2. Du doan `setpoint_dynamic` theo user va ngu canh thoi gian.

## 2. Cau truc thu muc

```text
Smart_Home_AIOT_V1/
├── Backend_AIOT_module_V1/
├── ML_module_V1/
├── aiot_firmware_v3/
│   └── aiot_firmware_v3.ino
├── README.md
└── TUTORIAL.md
```

Mo terminal tai root:

```bash
cd /home/Smart_Home_AIOT_V1
```

## 3. Dieu kien truoc khi chay

Can co:

- Python va pip.
- Mot MQTT broker ma backend va ESP32 cung truy cap duoc.
- ESP32 da noi DHT22, relay va mach dieu khien quat PWM.
- Arduino IDE hoac PlatformIO de nap firmware.

Firmware hien gia dinh:

| Thanh phan | Gia tri mac dinh |
|---|---|
| Sensor | DHT22 |
| DHT pin | GPIO 4 |
| Relay pin | GPIO 26 |
| Fan PWM pin | GPIO 25 |
| Relay | active-low |
| Telemetry interval | 10 giay |

Neu phan cung khac, sua cau hinh dau file
`aiot_firmware_v3/aiot_firmware_v3.ino` truoc khi nap.

## 4. Chon quy uoc thoi gian va user

Backend va ML luu timestamp theo UTC. Feature thoi gian cua model dung:

- `hour_sin`
- `hour_cos`
- `day_period`: `day` hoac `night`

Backend va ML phai dung cung cau hinh:

```bash
FEATURE_UTC_OFFSET_HOURS=7
DAY_START_HOUR=6
NIGHT_START_HOUR=18
DEFAULT_USER_ID=anonymous
```

Vi du tren dung cho gio Viet Nam UTC+7. Neu de backend la `7` nhung ML la
`0`, model train va live inference se nhin thoi gian khac nhau.

Setpoint ca nhan hoa theo `user_id`. App command nen gui `user_id` that:

```json
{"source":"app","user_id":"user-a","mode":"auto","setpoint":28.5}
```

Neu khong co `user_id`, model dung `anonymous`.

## 5. Cai Python dependencies

Nen dung hai virtual environment rieng vi backend va ML co requirements rieng.

Backend:

```bash
cd /home/Smart_Home_AIOT_V1/Backend_AIOT_module_V1
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
deactivate
```

ML:

```bash
cd /home/Smart_Home_AIOT_V1/ML_module_V1
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
deactivate
```

## 6. Cau hinh va nap firmware ESP32

Mo file:

```text
/home/Smart_Home_AIOT_V1/aiot_firmware_v3/aiot_firmware_v3.ino
```

Sua cac bien:

```cpp
const char *WIFI_SSID = "CHANGE_ME_WIFI_SSID";
const char *WIFI_PASSWORD = "CHANGE_ME_WIFI_PASSWORD";

const char *MQTT_HOST = "CHANGE_ME_MQTT_HOST";
const uint16_t MQTT_PORT = 8883;
const char *MQTT_USERNAME = "CHANGE_ME_MQTT_USERNAME";
const char *MQTT_PASSWORD = "CHANGE_ME_MQTT_PASSWORD";

const char *DEVICE_ID = "esp32-room-a";
```

Neu dung broker local khong TLS:

```cpp
const uint16_t MQTT_PORT = 1883;
#define USE_MQTT_TLS 0
```

Neu dung TLS nhu HiveMQ prototype, firmware dang co:

```cpp
#define USE_MQTT_TLS 1
#define MQTT_TLS_INSECURE 1
```

Che do `MQTT_TLS_INSECURE` phu hop demo, khong nen giu cho production vi ESP32
khong verify certificate cua broker.

Cai Arduino libraries:

- ArduinoJson
- PubSubClient
- DHT sensor library by Adafruit
- Adafruit Unified Sensor

Nap firmware, mo Serial Monitor baud `115200`, kiem tra:

- WiFi ket noi.
- MQTT ket noi.
- DHT co reading hop le.
- Firmware subscribe `devices/esp32-room-a/ml-setpoint`.
- Firmware subscribe `devices/esp32-room-a/command`.

## 7. Chay backend

Mo terminal backend:

```bash
cd /home/Smart_Home_AIOT_V1/Backend_AIOT_module_V1
. .venv/bin/activate
export DB_PATH=smart_home.db
export MQTT_HOST=CHANGE_ME_MQTT_HOST
export MQTT_PORT=8883
export MQTT_USERNAME=CHANGE_ME_MQTT_USERNAME
export MQTT_PASSWORD=CHANGE_ME_MQTT_PASSWORD
export FEATURE_UTC_OFFSET_HOURS=7
export DAY_START_HOUR=6
export NIGHT_START_HOUR=18
export DEFAULT_USER_ID=anonymous
uvicorn run:app --host 0.0.0.0 --port 8000 --reload
```

Backend se:

- subscribe `devices/+/telemetry`
- subscribe `devices/+/control-events`
- subscribe `devices/+/devicetwin`
- resample telemetry 30 giay va 60 giay
- expose HTTP API cho ML

Kiem tra backend:

```bash
curl http://localhost:8000/health
curl http://localhost:8000/devices
```

Khi ESP32 da gui telemetry, kiem tra:

```bash
curl http://localhost:8000/devices/esp32-room-a/telemetry/latest
```

## 8. Chay ML service

Mo terminal ML:

```bash
cd /home/Smart_Home_AIOT_V1/ML_module_V1
. .venv/bin/activate
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

ML startup se thu train model tu dataset dang co. Neu DB chua du du lieu, log
`Not enough ... samples` la binh thuong o lan chay dau.

Kiem tra ML:

```bash
curl http://localhost:8100/health
curl http://localhost:8100/devices/esp32-room-a/cache/status
```

## 9. MQTT topics quan trong

Voi `device_id=esp32-room-a`:

| Topic | Producer | Consumer | Muc dich |
|---|---|---|---|
| `devices/esp32-room-a/telemetry` | firmware | backend | sensor va trang thai output |
| `devices/esp32-room-a/control-events` | firmware/app | backend | hanh vi user de train setpoint |
| `devices/esp32-room-a/devicetwin` | firmware | backend | trang thai hien tai |
| `devices/esp32-room-a/command` | app/test client | firmware | setpoint, feedback, manual control |
| `devices/esp32-room-a/ml-setpoint` | backend | firmware | recommendation tu ML |

## 10. Gui lenh user cho firmware

App hoac MQTT client gui lenh vao:

```text
devices/esp32-room-a/command
```

### Doi setpoint user o auto mode

```json
{
  "source": "app",
  "user_id": "user-a",
  "mode": "auto",
  "setpoint": 28.5
}
```

Firmware se:

1. Doi active user thanh `user-a`.
2. Cap nhat setpoint.
3. Publish `setpoint_change` vao `control-events`.
4. Gui telemetry sau do co `user_id=user-a`.

### Feedback comfort

```json
{
  "source": "app",
  "user_id": "user-a",
  "feedback": "too_hot"
}
```

Feedback hop le:

- `too_hot`
- `comfortable`
- `too_cold`

### Manual control

```json
{
  "source": "app",
  "user_id": "user-a",
  "mode": "manual",
  "fan_pwm": 180,
  "relay": true
}
```

Dung app command that de train preference. Khong danh dau automation thanh
`source=app`, neu khong model se hoc hanh vi cua he thong thay vi user.

## 11. Du lieu can thu truoc khi train

### Forecast 10 phut va 20 phut

Telemetry can co:

- `temp_ma`, `hum_ma`
- `setpoint_current`
- `fan_pwm_actual`
- `lamp_actual` hien dang dai dien cho relay binary output
- `mode`
- timestamp hop le

Backend build forecast rows tu telemetry resample 60 giay. Cau hinh hien tai
can lich su lookback 10 phut va label tuong lai toi 20 phut. Thu it nhat khoang
70 phut telemetry lien tuc de qua nguong train toi thieu; du lieu nhieu khung
gio va nhieu muc output se tot hon.

### Setpoint theo user

Backend build habit rows tu:

- telemetry truoc event user
- `setpoint_change`
- comfort feedback
- `user_id`
- feature gio trong ngay va `day_period`

Can it nhat 20 habit samples dung duoc de code train setpoint. Mot event user
co the bi bo qua neu truoc event khong co du telemetry.

## 12. Kiem tra dataset backend

Chay resample tay khi can debug:

```bash
curl -X POST http://localhost:8000/resample/run
```

Xem forecast dataset:

```bash
curl "http://localhost:8000/devices/esp32-room-a/dataset/forecast?interval_seconds=60&lookback=10&horizon_1_min=10&horizon_2_min=20&limit=3"
```

Forecast rows nen co:

- `hour_sin`
- `hour_cos`
- `day_period`
- `target_temp_plus_10m`
- `target_temp_plus_20m`

Xem habit dataset:

```bash
curl "http://localhost:8000/devices/esp32-room-a/dataset/habit?interval_seconds=30&limit=3"
```

Habit rows nen co:

- `user_id`
- `hour_sin`
- `hour_cos`
- `day_period`
- `event_type`
- `label`
- `setpoint_mean_before`

## 13. Train model

Train mot device:

```bash
curl -X POST http://localhost:8100/devices/esp32-room-a/train
```

Train tat ca device ML thay duoc:

```bash
curl -X POST http://localhost:8100/train
```

Khi train thanh cong, response co dang:

```json
{
  "device_id": "esp32-room-a",
  "forecast": {"trained": true},
  "setpoint": {"trained": true}
}
```

Neu setpoint chua train duoc ma forecast train duoc, van co the debug forecast
rieng. Hai model khong can cung du du lieu o cung thoi diem.

## 14. Chay recommendation va vong dieu khien

Goi recommendation thu cong cho user:

```bash
curl "http://localhost:8100/devices/esp32-room-a/recommendation?user_id=user-a"
```

Hoac de worker ML tu dong:

1. Firmware publish telemetry moi.
2. ML poll latest telemetry tu backend.
3. ML tao recommendation.
4. ML POST recommendation ve backend.
5. Backend publish `devices/esp32-room-a/ml-setpoint`.
6. Firmware nhan `setpoint_dynamic`, ve auto mode va dieu khien quat/relay.

Kiem tra recommendation backend da luu:

```bash
curl http://localhost:8000/devices/esp32-room-a/ml-recommendation/latest
```

Neu model setpoint chua san sang, ML van co the gui fallback
`DEFAULT_SETPOINT`. Day la duong fallback, khong phai preference da hoc.

## 15. Debug nhanh

### Backend khong thay device

Kiem tra:

- ESP32 co publish telemetry khong.
- Backend va ESP32 co vao cung MQTT broker khong.
- Topic firmware co dung `devices/<device_id>/telemetry` khong.
- MQTT username/password/TLS port co khop khong.

### Habit dataset trong

Kiem tra:

- command user co `source=app`.
- command co `user_id`.
- da co telemetry truoc event it nhat vai bucket 30 giay.
- backend da resample telemetry 30 giay.

### Forecast dataset trong

Kiem tra:

- telemetry co `temp_ma` va `hum_ma`.
- telemetry du dai de co future label 10/20 phut.
- backend da resample 60 giay.

### Day/night khong dung voi thuc te

Kiem tra bien moi truong cua ca backend va ML:

```bash
FEATURE_UTC_OFFSET_HOURS
DAY_START_HOUR
NIGHT_START_HOUR
```

Phai restart backend va ML sau khi doi cac bien nay.

### Firmware khong nhan setpoint ML

Kiem tra:

- backend response recommendation co `publish_success=true`.
- firmware subscribe topic `devices/<device_id>/ml-setpoint`.
- `DEVICE_ID` firmware trung voi device trong backend/ML.

## 16. Thu tu chay khuyen nghi

1. Cau hinh va nap firmware.
2. Chay backend.
3. Xac nhan backend nhan telemetry.
4. Chay ML.
5. Gui app commands co `user_id`.
6. Thu telemetry va user events.
7. Kiem tra dataset backend.
8. Train ML.
9. Goi recommendation thu cong.
10. Kiem tra setpoint quay lai ESP32 qua MQTT.

