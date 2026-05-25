const elements = {
  apiBaseInput: document.querySelector("#apiBaseInput"),
  deviceSelect: document.querySelector("#deviceSelect"),
  userIdInput: document.querySelector("#userIdInput"),
  refreshButton: document.querySelector("#refreshButton"),
  connectionDot: document.querySelector("#connectionDot"),
  connectionText: document.querySelector("#connectionText"),
  tempValue: document.querySelector("#tempValue"),
  tempSource: document.querySelector("#tempSource"),
  humValue: document.querySelector("#humValue"),
  humSource: document.querySelector("#humSource"),
  setpointValue: document.querySelector("#setpointValue"),
  setpointSource: document.querySelector("#setpointSource"),
  modeValue: document.querySelector("#modeValue"),
  lastSeenValue: document.querySelector("#lastSeenValue"),
  sensorChart: document.querySelector("#sensorChart"),
  setpointInput: document.querySelector("#setpointInput"),
  setpointButton: document.querySelector("#setpointButton"),
  fanPwmInput: document.querySelector("#fanPwmInput"),
  fanPwmValue: document.querySelector("#fanPwmValue"),
  relayInput: document.querySelector("#relayInput"),
  manualApplyButton: document.querySelector("#manualApplyButton"),
  mlSetpointValue: document.querySelector("#mlSetpointValue"),
  mlTemp10Value: document.querySelector("#mlTemp10Value"),
  mlHum10Value: document.querySelector("#mlHum10Value"),
  mlTemp20Value: document.querySelector("#mlTemp20Value"),
  mlHum20Value: document.querySelector("#mlHum20Value"),
  mlMeta: document.querySelector("#mlMeta"),
  eventLog: document.querySelector("#eventLog"),
};

const LOCAL_BACKEND_PORT = "8000";
const COMMAND_CONFIRM_WINDOW_MS = 45000;
const POLL_ERROR_LOG_COOLDOWN_MS = 15000;

const state = {
  apiBase: "",
  deviceId: "esp32-room-a",
  userId: "user-a",
  mode: "auto",
  setpoint: 29.5,
  fanPwm: 0,
  relay: false,
  samples: [],
  pollTimer: null,
  pendingCommand: null,
  lastPollError: { message: "", at: 0 },
};

function defaultApiBase() {
  if (window.location.protocol === "file:") {
    return "http://localhost:8000";
  }

  if (isServedFromBackend()) {
    return window.location.origin;
  }

  if (isLocalHostname(window.location.hostname) && window.location.port !== LOCAL_BACKEND_PORT) {
    return `http://${window.location.hostname}:${LOCAL_BACKEND_PORT}`;
  }

  return window.location.origin;
}

function initialize() {
  state.apiBase = storedApiBase();
  state.deviceId = localStorage.getItem("dashboard.deviceId") || state.deviceId;
  state.userId = localStorage.getItem("dashboard.userId") || state.userId;

  elements.apiBaseInput.value = state.apiBase;
  elements.userIdInput.value = state.userId;
  elements.fanPwmValue.value = String(state.fanPwm);

  bindEvents();
  refreshDevices();
  startPolling();
  drawChart();
}

function bindEvents() {
  elements.refreshButton.addEventListener("click", () => {
    saveSettings();
    refreshDevices();
    pollNow();
  });

  elements.apiBaseInput.addEventListener("change", () => {
    saveSettings();
    refreshDevices();
    pollNow();
  });

  elements.deviceSelect.addEventListener("change", () => {
    state.deviceId = elements.deviceSelect.value || state.deviceId;
    localStorage.setItem("dashboard.deviceId", state.deviceId);
    pollNow();
  });

  elements.userIdInput.addEventListener("change", () => {
    state.userId = elements.userIdInput.value.trim() || "anonymous";
    elements.userIdInput.value = state.userId;
    localStorage.setItem("dashboard.userId", state.userId);
    pollNow();
  });

  document.querySelectorAll(".mode-button").forEach((button) => {
    button.addEventListener("click", () => {
      sendCommand({ mode: button.dataset.mode });
    });
  });

  elements.setpointButton.addEventListener("click", () => {
    const setpoint = Number(elements.setpointInput.value);
    if (!Number.isFinite(setpoint)) {
      logEvent("Setpoint không hợp lệ", "error");
      return;
    }
    sendCommand({ setpoint });
  });

  elements.fanPwmInput.addEventListener("input", () => {
    elements.fanPwmValue.value = elements.fanPwmInput.value;
  });

  elements.manualApplyButton.addEventListener("click", () => {
    sendCommand({
      mode: "manual",
      fan_pwm: Number(elements.fanPwmInput.value),
      relay: elements.relayInput.checked,
    });
  });

  document.querySelectorAll(".feedback-button").forEach((button) => {
    button.addEventListener("click", () => {
      sendCommand({ feedback: button.dataset.feedback });
    });
  });

  window.addEventListener("resize", drawChart);
}

function saveSettings() {
  state.apiBase = normalizeApiBase(elements.apiBaseInput.value || defaultApiBase());
  state.userId = elements.userIdInput.value.trim() || "anonymous";
  elements.apiBaseInput.value = state.apiBase;
  elements.userIdInput.value = state.userId;
  localStorage.setItem("dashboard.apiBase", state.apiBase);
  localStorage.setItem("dashboard.userId", state.userId);
}

function normalizeApiBase(value) {
  return value.trim().replace(/\/+$/, "");
}

function storedApiBase() {
  const saved = localStorage.getItem("dashboard.apiBase");
  if (!saved) {
    return defaultApiBase();
  }

  const normalized = normalizeApiBase(saved);
  if (isCurrentLocalFrontendOrigin(normalized)) {
    return defaultApiBase();
  }
  return normalized;
}

function isServedFromBackend() {
  const pathname = window.location.pathname || "";
  return window.location.protocol !== "file:" && pathname.replace(/\/+$/, "").startsWith("/dashboard");
}

function isLocalHostname(hostname) {
  return ["localhost", "127.0.0.1", "0.0.0.0", "::1", "[::1]"].includes(hostname);
}

function isCurrentLocalFrontendOrigin(value) {
  try {
    const url = new URL(value);
    return (
      !isServedFromBackend() &&
      normalizeApiBase(value) === normalizeApiBase(window.location.origin) &&
      isLocalHostname(url.hostname) &&
      url.port !== LOCAL_BACKEND_PORT
    );
  } catch {
    return false;
  }
}

async function refreshDevices() {
  saveSettings();
  try {
    const data = await apiGet("/devices");
    const devices = Array.isArray(data.devices) ? data.devices : [];
    if (!devices.includes(state.deviceId)) {
      devices.unshift(state.deviceId);
    }
    renderDeviceOptions(devices);
    setConnection("online", "Kết nối Backend OK");
    clearPollError();
  } catch (error) {
    renderDeviceOptions([state.deviceId]);
    setConnection("offline", "Không kết nối được Backend");
    logPollError(error.message);
  }
}

function renderDeviceOptions(devices) {
  elements.deviceSelect.innerHTML = "";
  devices.forEach((deviceId) => {
    const option = document.createElement("option");
    option.value = deviceId;
    option.textContent = deviceId;
    elements.deviceSelect.appendChild(option);
  });
  elements.deviceSelect.value = state.deviceId;
}

function startPolling() {
  if (state.pollTimer) {
    clearInterval(state.pollTimer);
  }
  pollNow();
  state.pollTimer = setInterval(pollNow, 3000);
}

async function pollNow() {
  if (!state.deviceId) {
    return;
  }

  try {
    const summary = await apiGet(`/devices/${encodeURIComponent(state.deviceId)}/summary`);
    updateFromSummary(summary);
    setConnection("online", "Đang nhận dữ liệu");
    clearPollError();
  } catch (error) {
    setConnection("offline", "Mất dữ liệu telemetry");
    logPollError(error.message);
  }

  try {
    const recommendation = await apiGet(
      `/devices/${encodeURIComponent(state.deviceId)}/ml-recommendation/latest?user_id=${encodeURIComponent(state.userId)}`,
    );
    updateMlRecommendation(recommendation);
  } catch {
    updateMlRecommendation(null);
  }
}

function updateFromSummary(summary) {
  const latest = summary.latest || {};
  const twin = summary.device_twin || {};

  const temp = firstNumber(latest.temp_ma, latest.temp_raw);
  const hum = firstNumber(latest.hum_ma, latest.hum_raw);
  const actual = {
    mode: twin.mode_actual || latest.mode || state.mode,
    setpoint: firstNumber(twin.setpoint_actual, latest.setpoint_current),
    fanPwm: firstNumber(twin.fan_pwm_actual, latest.fan_pwm_actual, latest.fan_pwm_cmd),
    relay: firstNumber(twin.lamp_actual, latest.lamp_actual, latest.lamp_cmd),
  };
  const pending = reconcilePendingCommand(actual, newestTimestampMs(latest.ts, twin.ts));
  const display = applyPendingCommand(actual, pending);

  state.mode = display.mode || "auto";
  if (display.setpoint !== null) {
    state.setpoint = display.setpoint;
    elements.setpointInput.value = formatNumber(display.setpoint, 1);
  }
  if (display.fanPwm !== null) {
    state.fanPwm = Math.round(display.fanPwm);
    elements.fanPwmInput.value = String(state.fanPwm);
    elements.fanPwmValue.value = String(state.fanPwm);
  }
  if (display.relay !== null) {
    state.relay = Boolean(display.relay);
    elements.relayInput.checked = state.relay;
  }

  elements.tempValue.textContent = temp === null ? "--" : `${formatNumber(temp, 1)}°C`;
  elements.humValue.textContent = hum === null ? "--" : `${formatNumber(hum, 1)}%`;
  elements.setpointValue.textContent =
    display.setpoint === null ? "--" : `${formatNumber(display.setpoint, 1)}°C`;
  elements.modeValue.textContent = state.mode.toUpperCase();
  elements.modeValue.classList.toggle("pending-state", Boolean(pending));
  elements.tempSource.textContent = latest.temp_ma == null ? "Raw sensor" : "Moving average";
  elements.humSource.textContent = latest.hum_ma == null ? "Raw sensor" : "Moving average";
  elements.setpointSource.textContent = twin.setpoint_actual == null ? "Telemetry" : "Device twin";
  elements.lastSeenValue.textContent = pending
    ? "Chờ ESP32 xác nhận command"
    : latest.ts
      ? `Cập nhật ${formatTime(latest.ts)}`
      : "Chưa có telemetry";

  updateModeControls();

  if (temp !== null || hum !== null) {
    state.samples.push({
      ts: latest.ts || new Date().toISOString(),
      temp,
      hum,
    });
    if (state.samples.length > 80) {
      state.samples.shift();
    }
    drawChart();
  }
}

function updateModeControls() {
  document.querySelectorAll(".mode-button").forEach((button) => {
    button.classList.toggle("active", button.dataset.mode === state.mode);
  });

  const manualDisabled = state.mode !== "manual";
  elements.fanPwmInput.disabled = manualDisabled;
  elements.relayInput.disabled = manualDisabled;
  elements.manualApplyButton.disabled = false;
  elements.manualApplyButton.textContent = manualDisabled ? "Chuyển sang Manual" : "Áp dụng Manual";
}

function updateMlRecommendation(recommendation) {
  if (!recommendation) {
    elements.mlSetpointValue.textContent = "--";
    elements.mlTemp10Value.textContent = "--";
    elements.mlHum10Value.textContent = "--";
    elements.mlTemp20Value.textContent = "--";
    elements.mlHum20Value.textContent = "--";
    elements.mlMeta.textContent = "Chưa có recommendation";
    return;
  }

  elements.mlSetpointValue.textContent = formatUnit(recommendation.setpoint_dynamic, "°C");
  elements.mlTemp10Value.textContent = formatUnit(recommendation.pred_temp_plus_10m, "°C");
  elements.mlHum10Value.textContent = formatUnit(recommendation.pred_hum_plus_10m, "%");
  elements.mlTemp20Value.textContent = formatUnit(recommendation.pred_temp_plus_20m, "°C");
  elements.mlHum20Value.textContent = formatUnit(recommendation.pred_hum_plus_20m, "%");
  elements.mlMeta.textContent = [
    recommendation.model_version ? `Model ${recommendation.model_version}` : null,
    recommendation.user_id ? `User ${recommendation.user_id}` : null,
    recommendation.control_hint ? `Hint ${recommendation.control_hint}` : null,
    recommendation.ts ? `Cập nhật ${formatTime(recommendation.ts)}` : null,
  ]
    .filter(Boolean)
    .join(" · ");
}

async function sendCommand(payload) {
  saveSettings();
  const body = {
    ...payload,
    user_id: state.userId,
    source: "dashboard",
  };

  try {
    const response = await apiPost(`/devices/${encodeURIComponent(state.deviceId)}/command`, body);
    rememberPendingCommand(payload, response);
    const commandName = describeCommand(payload);
    const publishText = response.publish_skipped
      ? "đã lưu trong Backend"
      : response.publish_success
        ? "đã publish MQTT"
        : "đã lưu, MQTT chưa sẵn sàng";
    logEvent(`${commandName}: ${publishText}`, "ok");
    await pollNow();
  } catch (error) {
    logEvent(error.message, "error");
  }
}

function rememberPendingCommand(payload, response) {
  const pending = {
    sentAt: timestampMs(response && response.payload && response.payload.ts) || Date.now(),
    expiresAt: Date.now() + COMMAND_CONFIRM_WINDOW_MS,
    mode: payload.mode ?? null,
    setpoint: payload.setpoint ?? null,
    fanPwm: payload.fan_pwm ?? null,
    relay: payload.relay ?? null,
  };

  if (
    pending.mode === null &&
    pending.setpoint === null &&
    pending.fanPwm === null &&
    pending.relay === null
  ) {
    return;
  }

  state.pendingCommand = pending;
  const display = applyPendingCommand(
    {
      mode: state.mode,
      setpoint: state.setpoint,
      fanPwm: state.fanPwm,
      relay: state.relay ? 1 : 0,
    },
    pending,
  );
  state.mode = display.mode || state.mode;
  updateModeControls();
}

function reconcilePendingCommand(actual, actualTsMs) {
  const pending = state.pendingCommand;
  if (!pending) {
    return null;
  }

  if (pendingCommandConfirmed(pending, actual, actualTsMs)) {
    state.pendingCommand = null;
    return null;
  }

  if (Date.now() >= pending.expiresAt) {
    state.pendingCommand = null;
    logEvent("ESP32 chưa xác nhận command, dùng trạng thái telemetry hiện tại", "info");
    return null;
  }

  return pending;
}

function applyPendingCommand(actual, pending) {
  if (!pending) {
    return actual;
  }

  return {
    mode: pending.mode ?? actual.mode,
    setpoint: pending.setpoint ?? actual.setpoint,
    fanPwm: pending.fanPwm ?? actual.fanPwm,
    relay: pending.relay ?? actual.relay,
  };
}

function pendingCommandConfirmed(pending, actual, actualTsMs) {
  if (actualTsMs !== null && actualTsMs < pending.sentAt) {
    return false;
  }

  return (
    stringMatches(pending.mode, actual.mode) &&
    numberMatches(pending.setpoint, actual.setpoint, 0.05) &&
    numberMatches(pending.fanPwm, actual.fanPwm, 0) &&
    boolMatches(pending.relay, actual.relay)
  );
}

function stringMatches(expected, actual) {
  return expected === null || expected === actual;
}

function numberMatches(expected, actual, tolerance) {
  return expected === null || (actual !== null && Math.abs(Number(expected) - Number(actual)) <= tolerance);
}

function boolMatches(expected, actual) {
  return expected === null || (actual !== null && Boolean(expected) === Boolean(actual));
}

function describeCommand(payload) {
  if (payload.feedback) {
    return `Feedback ${feedbackLabel(payload.feedback)}`;
  }
  if (payload.mode && payload.fan_pwm !== undefined) {
    return `Manual fan ${payload.fan_pwm}, relay ${payload.relay ? "ON" : "OFF"}`;
  }
  if (payload.mode) {
    return `Chế độ ${payload.mode}`;
  }
  if (payload.setpoint !== undefined) {
    return `Setpoint ${payload.setpoint}°C`;
  }
  return "Command";
}

function feedbackLabel(value) {
  return {
    too_hot: "Quá nóng",
    comfortable: "Thoải mái",
    too_cold: "Quá lạnh",
  }[value] || value;
}

async function apiGet(path) {
  return api(path, { method: "GET" });
}

async function apiPost(path, body) {
  return api(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

async function api(path, options) {
  let response;
  try {
    response = await fetch(`${state.apiBase}${path}`, options);
  } catch {
    throw new Error(`Không gọi được Backend ${state.apiBase}. Kiểm tra server hoặc trường Backend API.`);
  }

  let data = null;
  const contentType = response.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    data = await response.json();
  }
  if (!response.ok) {
    const detail = data && data.detail ? data.detail : `HTTP ${response.status}`;
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return data;
}

function firstNumber(...values) {
  for (const value of values) {
    if (value === null || value === undefined || value === "") {
      continue;
    }
    const number = Number(value);
    if (Number.isFinite(number)) {
      return number;
    }
  }
  return null;
}

function formatNumber(value, digits = 1) {
  return Number(value).toFixed(digits);
}

function formatUnit(value, unit) {
  const number = firstNumber(value);
  return number === null ? "--" : `${formatNumber(number, 1)}${unit}`;
}

function formatTime(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleTimeString("vi-VN", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function timestampMs(value) {
  if (!value) {
    return null;
  }
  const timestamp = new Date(value).getTime();
  return Number.isNaN(timestamp) ? null : timestamp;
}

function newestTimestampMs(...values) {
  const timestamps = values.map(timestampMs).filter((value) => value !== null);
  return timestamps.length ? Math.max(...timestamps) : null;
}

function setConnection(status, message) {
  elements.connectionDot.className = `status-dot ${status}`;
  elements.connectionText.textContent = message;
}

function logPollError(message) {
  const now = Date.now();
  if (
    state.lastPollError.message === message &&
    now - state.lastPollError.at < POLL_ERROR_LOG_COOLDOWN_MS
  ) {
    return;
  }

  state.lastPollError = { message, at: now };
  logEvent(message, "error");
}

function clearPollError() {
  state.lastPollError = { message: "", at: 0 };
}

function logEvent(message, level = "info") {
  const item = document.createElement("li");
  const now = new Date().toLocaleTimeString("vi-VN", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
  const label = level === "error" ? "Lỗi" : level === "ok" ? "OK" : "Info";
  item.innerHTML = `<strong>${label}</strong> ${now} - ${escapeHtml(message)}`;
  elements.eventLog.prepend(item);
  while (elements.eventLog.children.length > 10) {
    elements.eventLog.lastElementChild.remove();
  }
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function drawChart() {
  const canvas = elements.sensorChart;
  const rect = canvas.getBoundingClientRect();
  if (rect.width === 0 || rect.height === 0) {
    return;
  }

  const dpr = window.devicePixelRatio || 1;
  const width = Math.floor(rect.width);
  const height = Math.floor(rect.height);
  if (canvas.width !== width * dpr || canvas.height !== height * dpr) {
    canvas.width = width * dpr;
    canvas.height = height * dpr;
  }

  const ctx = canvas.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, width, height);

  const padding = { top: 22, right: 22, bottom: 34, left: 42 };
  const chartWidth = width - padding.left - padding.right;
  const chartHeight = height - padding.top - padding.bottom;

  drawGrid(ctx, padding, chartWidth, chartHeight);
  if (state.samples.length < 2) {
    drawEmptyChart(ctx, width, height);
    return;
  }

  drawSeries(ctx, padding, chartWidth, chartHeight, "temp", "#e56f4f");
  drawSeries(ctx, padding, chartWidth, chartHeight, "hum", "#3b72d9");
  drawAxisLabels(ctx, padding, chartWidth, chartHeight);
}

function drawGrid(ctx, padding, chartWidth, chartHeight) {
  ctx.save();
  ctx.strokeStyle = "#dce3ea";
  ctx.lineWidth = 1;
  ctx.fillStyle = "#647084";
  ctx.font = "12px Inter, system-ui, sans-serif";

  for (let i = 0; i <= 4; i++) {
    const y = padding.top + (chartHeight / 4) * i;
    ctx.beginPath();
    ctx.moveTo(padding.left, y);
    ctx.lineTo(padding.left + chartWidth, y);
    ctx.stroke();
  }

  ctx.fillText("Cảm biến gần đây", padding.left, padding.top - 7);
  ctx.restore();
}

function drawEmptyChart(ctx, width, height) {
  ctx.save();
  ctx.fillStyle = "#647084";
  ctx.font = "14px Inter, system-ui, sans-serif";
  ctx.textAlign = "center";
  ctx.fillText("Đang chờ telemetry để vẽ biểu đồ", width / 2, height / 2);
  ctx.restore();
}

function drawSeries(ctx, padding, chartWidth, chartHeight, key, color) {
  const values = state.samples
    .map((sample) => sample[key])
    .filter((value) => Number.isFinite(value));
  if (values.length < 2) {
    return;
  }

  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const paddedMin = min - range * 0.18;
  const paddedMax = max + range * 0.18;
  const paddedRange = paddedMax - paddedMin || 1;

  ctx.save();
  ctx.strokeStyle = color;
  ctx.lineWidth = 3;
  ctx.lineJoin = "round";
  ctx.lineCap = "round";
  ctx.beginPath();

  let started = false;
  state.samples.forEach((sample, index) => {
    const value = sample[key];
    if (!Number.isFinite(value)) {
      return;
    }
    const x = padding.left + (chartWidth * index) / Math.max(state.samples.length - 1, 1);
    const y = padding.top + chartHeight - ((value - paddedMin) / paddedRange) * chartHeight;
    if (!started) {
      ctx.moveTo(x, y);
      started = true;
    } else {
      ctx.lineTo(x, y);
    }
  });

  ctx.stroke();
  ctx.restore();
}

function drawAxisLabels(ctx, padding, chartWidth, chartHeight) {
  const first = state.samples[0];
  const last = state.samples[state.samples.length - 1];

  ctx.save();
  ctx.fillStyle = "#647084";
  ctx.font = "12px Inter, system-ui, sans-serif";
  ctx.fillText(formatTime(first.ts), padding.left, padding.top + chartHeight + 24);
  ctx.textAlign = "right";
  ctx.fillText(formatTime(last.ts), padding.left + chartWidth, padding.top + chartHeight + 24);
  ctx.restore();
}

initialize();
