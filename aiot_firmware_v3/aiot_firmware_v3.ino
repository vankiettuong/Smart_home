/*
  ESP32 AIoT firmware for Backend_AIOT_module_V1 and ML_module_V1.

  Required Arduino libraries:
  - ArduinoJson by Benoit Blanchon
  - PubSubClient by Nick O'Leary
  - DHT sensor library by Adafruit
  - Adafruit Unified Sensor

  MQTT flow:
  - Publish telemetry to devices/<device_id>/telemetry every 10 seconds.
  - Publish device state to devices/<device_id>/devicetwin.
  - Subscribe to ML setpoint on devices/<device_id>/ml-setpoint.
  - Subscribe to app/device commands on devices/<device_id>/command.
  - Publish app commands as control events on devices/<device_id>/control-events.

  Relay state is mapped to backend fields lamp_cmd/lamp_actual because the
  current backend schema stores one binary output under those field names.

  Example app commands to devices/<device_id>/command:
  {"source":"app","user_id":"user-a","mode":"auto","setpoint":28.5}
  {"source":"app","user_id":"user-a","mode":"manual","fan_pwm":180,"relay":true}
  {"source":"app","user_id":"user-a","feedback":"too_hot"}
*/

#include <Arduino.h>
#include <ArduinoJson.h>
#include <DHT.h>
#include <PubSubClient.h>
#include <WiFi.h>
#include <WiFiClient.h>
#include <WiFiClientSecure.h>
#include <esp_arduino_version.h>
#include <math.h>
#include <string.h>
#include <time.h>

// ---------- User configuration ----------

const char *WIFI_SSID = "abc";
const char *WIFI_PASSWORD = "12345678";
//const char *WIFI_SSID = "Hai Dang";
//const char *WIFI_PASSWORD = "Dang241005";


const char *MQTT_HOST = "f7381aec847c405591c40af0e3305262.s1.eu.hivemq.cloud";
const uint16_t MQTT_PORT = 8883;
const char *MQTT_USERNAME = "User12345";
const char *MQTT_PASSWORD = "Broker123";

const char *DEVICE_ID = "esp32-room-a";
const char *MQTT_CLIENT_PREFIX = "aiot-fw-v3-";

// Set to 0 for a local non-TLS broker such as port 1883.
#define USE_MQTT_TLS 1

// Prototype TLS mode. Set this to 0 and install the broker root CA for
// production so the ESP32 verifies the broker certificate.
#define MQTT_TLS_INSECURE 1

const int DHT_PIN = 4;
#define DHT_TYPE DHT22

const int RELAY_PIN = 26;
const bool RELAY_ACTIVE_LOW = false;

// Fan PWM must drive a fan PWM input or a proper transistor/MOSFET driver.
const int FAN_PWM_PIN = 25;
const uint8_t FAN_PWM_CHANNEL = 0;
const uint32_t FAN_PWM_FREQUENCY_HZ = 25000;
const uint8_t FAN_PWM_BITS = 8;
const int FAN_PWM_MAX = 255;
const int FAN_PWM_AUTO_MIN = 80;

const float DEFAULT_SETPOINT_C = 29.5;
const float MIN_SETPOINT_C = 27.0;
const float MAX_SETPOINT_C = 32.0;
const float RELAY_ON_DELTA_C = 0.35;
const float RELAY_OFF_DELTA_C = 0.15;
// Set false if this relay drives a cooling compressor instead of a lamp/heater.
const bool RELAY_AUTO_ON_WHEN_BELOW_SETPOINT = true;

const uint32_t SENSOR_INTERVAL_MS = 10000;
const uint32_t TELEMETRY_INTERVAL_MS = 10000;
const uint32_t DEVICE_TWIN_INTERVAL_MS = 30000;
const uint32_t MQTT_RECONNECT_INTERVAL_MS = 5000;
const size_t MOVING_AVERAGE_WINDOW = 6;

// UTC time keeps backend and ML timestamps consistent.
const long GMT_OFFSET_SECONDS = 0;
const int DAYLIGHT_OFFSET_SECONDS = 0;
const char *NTP_SERVER_1 = "pool.ntp.org";
const char *NTP_SERVER_2 = "time.nist.gov";

// ---------- Runtime state ----------

#if USE_MQTT_TLS
WiFiClientSecure networkClient;
#else
WiFiClient networkClient;
#endif

PubSubClient mqttClient(networkClient);
DHT dht(DHT_PIN, DHT_TYPE);

String telemetryTopic;
String controlEventTopic;
String deviceTwinTopic;
String mlSetpointTopic;
String commandTopic;

enum ControlMode {
  MODE_AUTO,
  MODE_MANUAL
};

ControlMode controlMode = MODE_AUTO;
String controlSource = "device";
String lastControlHint = "hold";
String activeUserId = "anonymous";

float setpointCurrentC = DEFAULT_SETPOINT_C;
float tempRawC = NAN;
float humRawPercent = NAN;
float tempMovingAverageC = NAN;
float humMovingAveragePercent = NAN;
bool hasValidSensorReading = false;

float tempWindow[MOVING_AVERAGE_WINDOW] = {0};
float humWindow[MOVING_AVERAGE_WINDOW] = {0};
size_t movingAverageCount = 0;
size_t movingAverageIndex = 0;

bool relayCommand = false;
bool relayActual = false;
int fanPwmCommand = 0;
int fanPwmActual = 0;
int pendingEventFlag = 0;

uint32_t lastSensorMs = 0;
uint32_t lastTelemetryMs = 0;
uint32_t lastDeviceTwinMs = 0;
uint32_t lastMqttReconnectMs = 0;

// ---------- Forward declarations ----------

void mqttCallback(char *topic, byte *payload, unsigned int length);
void publishDeviceTwin();
void publishControlEvent(
    const char *eventType,
    const String &oldValue,
    const String &newValue,
    const char *triggerSource,
    int userFeedback);

// ---------- Small helpers ----------

float clampFloat(float value, float minValue, float maxValue) {
  if (value < minValue) {
    return minValue;
  }
  if (value > maxValue) {
    return maxValue;
  }
  return value;
}

int clampPwm(int value) {
  if (value < 0) {
    return 0;
  }
  if (value > FAN_PWM_MAX) {
    return FAN_PWM_MAX;
  }
  return value;
}

const char *modeName() {
  return controlMode == MODE_AUTO ? "auto" : "manual";
}

bool hasClockTime() {
  const time_t now = time(nullptr);
  return now > 1700000000;
}

void addTimestamp(JsonDocument &doc) {
  if (!hasClockTime()) {
    return;
  }

  time_t now = time(nullptr);
  struct tm utcTime;
  gmtime_r(&now, &utcTime);

  char timestamp[25];
  strftime(timestamp, sizeof(timestamp), "%Y-%m-%dT%H:%M:%SZ", &utcTime);
  doc["ts"] = timestamp;
}

bool publishJson(const String &topic, JsonDocument &doc, bool retained = false) {
  if (!mqttClient.connected()) {
    return false;
  }

  char output[1024];
  const size_t length = serializeJson(doc, output, sizeof(output));
  if (length == 0 || length >= sizeof(output)) {
    Serial.println("[MQTT] JSON payload overflow.");
    return false;
  }

  const bool ok = mqttClient.publish(topic.c_str(), output, retained);
  Serial.printf("[MQTT] publish %s -> %s\n", topic.c_str(), ok ? "ok" : "failed");
  return ok;
}

// ---------- Hardware output ----------

void writeRelay(bool enabled) {
  relayCommand = enabled;
  relayActual = enabled;
  const bool gpioHigh = RELAY_ACTIVE_LOW ? !enabled : enabled;
  digitalWrite(RELAY_PIN, gpioHigh ? HIGH : LOW);
  Serial.printf(
      "[RELAY] logical=%s pin=%d gpio=%s\n",
      enabled ? "ON" : "OFF",
      RELAY_PIN,
      gpioHigh ? "HIGH" : "LOW");
}

void configureFanPwm() {
#if ESP_ARDUINO_VERSION_MAJOR >= 3
  ledcAttachChannel(FAN_PWM_PIN, FAN_PWM_FREQUENCY_HZ, FAN_PWM_BITS, FAN_PWM_CHANNEL);
#else
  ledcSetup(FAN_PWM_CHANNEL, FAN_PWM_FREQUENCY_HZ, FAN_PWM_BITS);
  ledcAttachPin(FAN_PWM_PIN, FAN_PWM_CHANNEL);
#endif
}

void writeFanPwm(int pwm) {
  fanPwmCommand = clampPwm(pwm);
  fanPwmActual = fanPwmCommand;
#if ESP_ARDUINO_VERSION_MAJOR >= 3
  ledcWriteChannel(FAN_PWM_CHANNEL, fanPwmActual);
#else
  ledcWrite(FAN_PWM_CHANNEL, fanPwmActual);
#endif
}

void applyAutomaticControl() {
  if (controlMode != MODE_AUTO || !hasValidSensorReading) {
    return;
  }

  const float tempForControl = isnan(tempMovingAverageC) ? tempRawC : tempMovingAverageC;
  const float errorC = tempForControl - setpointCurrentC;
  const float relayDemandC = RELAY_AUTO_ON_WHEN_BELOW_SETPOINT ? -errorC : errorC;

  if (relayDemandC >= RELAY_ON_DELTA_C) {
    writeRelay(true);
  } else if (relayDemandC <= -RELAY_OFF_DELTA_C) {
    writeRelay(false);
  }

  int pwm = 0;
  if (errorC > 0.0) {
    const float scaled = clampFloat(errorC / 3.0, 0.0, 1.0);
    pwm = FAN_PWM_AUTO_MIN + (int)((FAN_PWM_MAX - FAN_PWM_AUTO_MIN) * scaled);
  }
  writeFanPwm(pwm);
}

// ---------- Sensor and moving average ----------

void updateMovingAverage(float tempC, float humidityPercent) {
  tempWindow[movingAverageIndex] = tempC;
  humWindow[movingAverageIndex] = humidityPercent;
  movingAverageIndex = (movingAverageIndex + 1) % MOVING_AVERAGE_WINDOW;
  if (movingAverageCount < MOVING_AVERAGE_WINDOW) {
    movingAverageCount++;
  }

  float tempSum = 0.0;
  float humSum = 0.0;
  for (size_t i = 0; i < movingAverageCount; i++) {
    tempSum += tempWindow[i];
    humSum += humWindow[i];
  }
  tempMovingAverageC = tempSum / movingAverageCount;
  humMovingAveragePercent = humSum / movingAverageCount;
}

void readSensor() {
  const float humidity = dht.readHumidity();
  const float temperature = dht.readTemperature();
  if (isnan(humidity) || isnan(temperature)) {
    Serial.println("[DHT] read failed; keeping last valid reading.");
    return;
  }

  tempRawC = temperature;
  humRawPercent = humidity;
  updateMovingAverage(tempRawC, humRawPercent);
  hasValidSensorReading = true;

  Serial.printf(
      "[DHT] raw %.2f C %.2f %% | ma %.2f C %.2f %%\n",
      tempRawC,
      humRawPercent,
      tempMovingAverageC,
      humMovingAveragePercent);
}

// ---------- Backend MQTT payloads ----------

void publishTelemetry() {
  if (!hasValidSensorReading) {
    Serial.println("[TELEMETRY] skipped until a valid DHT reading exists.");
    return;
  }

  StaticJsonDocument<768> doc;
  doc["device_id"] = DEVICE_ID;
  doc["user_id"] = activeUserId;
  addTimestamp(doc);
  doc["temp_raw"] = tempRawC;
  doc["hum_raw"] = humRawPercent;
  doc["temp_ma"] = tempMovingAverageC;
  doc["hum_ma"] = humMovingAveragePercent;
  doc["mode"] = modeName();
  doc["setpoint_current"] = setpointCurrentC;
  doc["fan_pwm_cmd"] = fanPwmCommand;
  doc["fan_pwm_actual"] = fanPwmActual;
  doc["lamp_cmd"] = relayCommand ? 1 : 0;
  doc["lamp_actual"] = relayActual ? 1 : 0;
  doc["control_source"] = controlSource;
  doc["event_flag"] = pendingEventFlag;

  if (publishJson(telemetryTopic, doc)) {
    pendingEventFlag = 0;
  }
}

void publishDeviceTwin() {
  StaticJsonDocument<384> doc;
  doc["device_id"] = DEVICE_ID;
  addTimestamp(doc);
  doc["fan_pwm_actual"] = fanPwmActual;
  doc["lamp_actual"] = relayActual ? 1 : 0;
  doc["mode_actual"] = modeName();
  doc["setpoint_actual"] = setpointCurrentC;
  publishJson(deviceTwinTopic, doc, true);
}

void publishControlEvent(
    const char *eventType,
    const String &oldValue,
    const String &newValue,
    const char *triggerSource,
    int userFeedback) {
  StaticJsonDocument<512> doc;
  doc["device_id"] = DEVICE_ID;
  doc["user_id"] = activeUserId;
  addTimestamp(doc);
  doc["event_type"] = eventType;

  if (oldValue.length() > 0) {
    doc["old_value"] = oldValue;
  }
  if (newValue.length() > 0) {
    doc["new_value"] = newValue;
  }
  doc["trigger_source"] = triggerSource;
  if (userFeedback >= -1 && userFeedback <= 1) {
    doc["user_feedback"] = userFeedback;
  }

  publishJson(controlEventTopic, doc);
}

// ---------- Incoming commands ----------

void applyMlSetpoint(JsonDocument &doc) {
  if (!doc["setpoint_dynamic"].is<float>() && !doc["setpoint_dynamic"].is<int>()) {
    Serial.println("[ML] message without setpoint_dynamic ignored.");
    return;
  }

  if (doc["user_id"].is<const char *>()) {
    const String recommendedUserId = doc["user_id"].as<String>();
    if (recommendedUserId.length() > 0) {
      activeUserId = recommendedUserId;
    }
  }

  setpointCurrentC = clampFloat(doc["setpoint_dynamic"].as<float>(), MIN_SETPOINT_C, MAX_SETPOINT_C);
  lastControlHint = doc["control_hint"] | "hold";
  controlSource = "ml";
  pendingEventFlag = 1;

  if (controlMode == MODE_MANUAL) {
    publishDeviceTwin();
    Serial.printf(
        "[ML] setpoint %.2f C stored, manual mode kept\n",
        setpointCurrentC);
    return;
  }

  controlMode = MODE_AUTO;
  applyAutomaticControl();
  publishDeviceTwin();

  Serial.printf(
      "[ML] setpoint %.2f C, hint=%s\n",
      setpointCurrentC,
      lastControlHint.c_str());
}

void publishFeedbackEvent(const String &feedback, const char *source) {
  int value = 99;
  if (feedback == "too_hot") {
    value = 1;
  } else if (feedback == "comfortable") {
    value = 0;
  } else if (feedback == "too_cold") {
    value = -1;
  }

  if (value >= -1 && value <= 1) {
    publishControlEvent("comfort_feedback", "", feedback, source, value);
    pendingEventFlag = 1;
  }
}

void applyCommand(JsonDocument &doc) {
  const char *source = doc["source"] | "app";
  const bool fromApp = strcmp(source, "app") == 0;

  if (doc["user_id"].is<const char *>()) {
    const String requestedUserId = doc["user_id"].as<String>();
    if (requestedUserId.length() > 0) {
      activeUserId = requestedUserId;
    }
  }

  if (doc["feedback"].is<const char *>()) {
    publishFeedbackEvent(doc["feedback"].as<String>(), source);
  }

  if (doc["mode"].is<const char *>()) {
    const String requestedMode = doc["mode"].as<String>();
    const String oldMode = modeName();
    if (requestedMode == "auto") {
      controlMode = MODE_AUTO;
      controlSource = source;
      applyAutomaticControl();
    } else if (requestedMode == "manual") {
      controlMode = MODE_MANUAL;
      controlSource = source;
    }

    if (fromApp && oldMode != modeName()) {
      publishControlEvent("mode_change", oldMode, modeName(), source, 99);
      pendingEventFlag = 1;
    }
  }

  if (doc["setpoint"].is<float>() || doc["setpoint"].is<int>()) {
    const float oldSetpoint = setpointCurrentC;
    setpointCurrentC = clampFloat(doc["setpoint"].as<float>(), MIN_SETPOINT_C, MAX_SETPOINT_C);
    controlSource = source;

    if (fromApp && fabs(oldSetpoint - setpointCurrentC) >= 0.01) {
      publishControlEvent(
          "setpoint_change",
          String(oldSetpoint, 2),
          String(setpointCurrentC, 2),
          source,
          99);
      pendingEventFlag = 1;
    }
  }

  if (controlMode == MODE_MANUAL) {
    if (doc["fan_pwm"].is<int>()) {
      const int oldFanPwm = fanPwmActual;
      writeFanPwm(doc["fan_pwm"].as<int>());
      controlSource = source;
      if (fromApp && oldFanPwm != fanPwmActual) {
        publishControlEvent(
            "fan_pwm_change",
            String(oldFanPwm),
            String(fanPwmActual),
            source,
            99);
        pendingEventFlag = 1;
      }
    }

    if (doc["relay"].is<bool>()) {
      const bool oldRelay = relayActual;
      writeRelay(doc["relay"].as<bool>());
      controlSource = source;
      if (fromApp && oldRelay != relayActual) {
        publishControlEvent(
            "manual_override",
            oldRelay ? "relay_on" : "relay_off",
            relayActual ? "relay_on" : "relay_off",
            source,
            99);
        pendingEventFlag = 1;
      }
    }
  } else {
    applyAutomaticControl();
  }

  publishDeviceTwin();
}

void mqttCallback(char *topic, byte *payload, unsigned int length) {
  String message;
  message.reserve(length + 1);
  for (unsigned int i = 0; i < length; i++) {
    message += (char)payload[i];
  }

  StaticJsonDocument<1024> doc;
  const DeserializationError error = deserializeJson(doc, message);
  if (error) {
    Serial.printf("[MQTT] invalid JSON on %s: %s\n", topic, error.c_str());
    return;
  }

  const String incomingTopic = String(topic);
  if (incomingTopic == mlSetpointTopic) {
    applyMlSetpoint(doc);
  } else if (incomingTopic == commandTopic) {
    applyCommand(doc);
  }
}

// ---------- Network connection ----------

void connectWifi() {
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  Serial.printf("[WIFI] connecting to %s", WIFI_SSID);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.printf("\n[WIFI] connected, ip=%s\n", WiFi.localIP().toString().c_str());

  configTime(GMT_OFFSET_SECONDS, DAYLIGHT_OFFSET_SECONDS, NTP_SERVER_1, NTP_SERVER_2);
}

void configureMqttNetwork() {
#if USE_MQTT_TLS && MQTT_TLS_INSECURE
  networkClient.setInsecure();
#endif
  mqttClient.setServer(MQTT_HOST, MQTT_PORT);
  mqttClient.setCallback(mqttCallback);
  mqttClient.setBufferSize(1024);
}

String buildMqttClientId() {
  String clientId = MQTT_CLIENT_PREFIX;
  clientId += DEVICE_ID;
  clientId += "-";
  clientId += String((uint32_t)(ESP.getEfuseMac() & 0xFFFFFFFF), HEX);
  return clientId;
}

void ensureMqttConnected() {
  if (mqttClient.connected()) {
    return;
  }

  const uint32_t nowMs = millis();
  if (lastMqttReconnectMs != 0 &&
      nowMs - lastMqttReconnectMs < MQTT_RECONNECT_INTERVAL_MS) {
    return;
  }
  lastMqttReconnectMs = nowMs;

  const String clientId = buildMqttClientId();
  Serial.printf("[MQTT] connecting as %s\n", clientId.c_str());
  const bool connected = mqttClient.connect(
      clientId.c_str(),
      MQTT_USERNAME,
      MQTT_PASSWORD);

  if (!connected) {
    Serial.printf("[MQTT] connect failed, state=%d\n", mqttClient.state());
    return;
  }

  mqttClient.subscribe(mlSetpointTopic.c_str(), 1);
  mqttClient.subscribe(commandTopic.c_str(), 1);
  Serial.printf("[MQTT] subscribed %s\n", mlSetpointTopic.c_str());
  Serial.printf("[MQTT] subscribed %s\n", commandTopic.c_str());
  publishDeviceTwin();
}

void buildTopics() {
  const String prefix = String("devices/") + DEVICE_ID + "/";
  telemetryTopic = prefix + "telemetry";
  controlEventTopic = prefix + "control-events";
  deviceTwinTopic = prefix + "devicetwin";
  mlSetpointTopic = prefix + "ml-setpoint";
  commandTopic = prefix + "command";
}

// ---------- Arduino lifecycle ----------

void setup() {
  Serial.begin(115200);
  delay(200);

  pinMode(RELAY_PIN, OUTPUT);
  writeRelay(false);
  configureFanPwm();
  writeFanPwm(0);

  dht.begin();
  buildTopics();
  connectWifi();
  configureMqttNetwork();

  // Prime telemetry with the first sensor read instead of waiting 10 seconds.
  readSensor();
  applyAutomaticControl();
  lastSensorMs = millis();
}

void loop() {
  if (WiFi.status() != WL_CONNECTED) {
    connectWifi();
  }

  ensureMqttConnected();
  mqttClient.loop();

  const uint32_t nowMs = millis();
  if (nowMs - lastSensorMs >= SENSOR_INTERVAL_MS) {
    lastSensorMs = nowMs;
    readSensor();
    applyAutomaticControl();
  }

  if (nowMs - lastTelemetryMs >= TELEMETRY_INTERVAL_MS) {
    lastTelemetryMs = nowMs;
    publishTelemetry();
  }

  if (nowMs - lastDeviceTwinMs >= DEVICE_TWIN_INTERVAL_MS) {
    lastDeviceTwinMs = nowMs;
    publishDeviceTwin();
  }
}
