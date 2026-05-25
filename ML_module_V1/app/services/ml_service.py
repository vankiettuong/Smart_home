import json
import threading
from collections import defaultdict, deque
from datetime import datetime
from typing import Any, Deque, Dict, List, Optional

import numpy as np
import pandas as pd
from fastapi import HTTPException
from pandas.api.types import is_numeric_dtype
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.multioutput import MultiOutputRegressor
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

from app.core.config import (
    CACHE_MAXLEN,
    DAY_START_HOUR,
    DEFAULT_SETPOINT,
    DEFAULT_USER_ID,
    DEVICE_IDS,
    FEATURE_UTC_OFFSET_HOURS,
    FORECAST_INTERVAL_SECONDS,
    FORECAST_LOOKBACK,
    HABIT_INTERVAL_SECONDS,
    HORIZON_1_MIN,
    HORIZON_2_MIN,
    LOG_RECOMMENDATIONS_TO_BACKEND,
    MAX_SETPOINT,
    MIN_SETPOINT,
    N_ESTIMATORS,
    NIGHT_START_HOUR,
    RANDOM_STATE,
    RECOMMEND_USER_IDS,
    SYNTHETIC_FORECAST_CSV,
    SYNTHETIC_HABIT_CSV,
    TRAINING_DATA_SOURCE,
)
from app.core.helpers import clamp, majority, safe_float
from app.core.time_utils import cyclic_hour_features, day_period, floor_time, parse_ts, utc_now
from app.models.bundles import ForecastBundle, SetpointBundle
from app.services.backend_client import BackendClient


def split_feature_columns(df: pd.DataFrame, feature_cols: List[str]) -> tuple[List[str], List[str]]:
    num_cols = [col for col in feature_cols if is_numeric_dtype(df[col])]
    cat_cols = [col for col in feature_cols if col not in num_cols]
    return num_cols, cat_cols


SYNTHETIC_DATA_SOURCES = {"synthetic", "simulation", "simulated", "csv"}


class MLService:
    def __init__(self, client: BackendClient) -> None:
        self.client = client
        self._lock = threading.Lock()
        self.raw_cache: Dict[str, Deque[Dict[str, Any]]] = defaultdict(lambda: deque(maxlen=CACHE_MAXLEN))
        self.forecast_models: Dict[str, ForecastBundle] = {}
        self.setpoint_models: Dict[str, SetpointBundle] = {}
        self.last_seen_ts: Dict[str, Optional[str]] = {}

    def train_all(self) -> Dict[str, Any]:
        device_ids = DEVICE_IDS or self._available_device_ids()
        result: Dict[str, Any] = {}
        for device_id in device_ids:
            result[device_id] = self.train_device(device_id)
        return result

    def _available_device_ids(self) -> List[str]:
        if self._uses_synthetic_training_data():
            device_ids: set[str] = set()
            for path in (SYNTHETIC_FORECAST_CSV, SYNTHETIC_HABIT_CSV):
                if not path.exists():
                    continue
                df = pd.read_csv(path, usecols=["device_id"])
                device_ids.update(str(x) for x in df["device_id"].dropna().unique())
            return sorted(device_ids)
        return self.client.get_devices()

    @staticmethod
    def _uses_synthetic_training_data() -> bool:
        return TRAINING_DATA_SOURCE in SYNTHETIC_DATA_SOURCES

    @staticmethod
    def _read_synthetic_csv(path) -> pd.DataFrame:
        if not path.exists():
            raise FileNotFoundError(f"Synthetic dataset not found: {path}")
        return pd.read_csv(path)

    def _forecast_training_dataset(self, device_id: str) -> pd.DataFrame:
        if self._uses_synthetic_training_data():
            df = self._read_synthetic_csv(SYNTHETIC_FORECAST_CSV)
            if "device_id" in df.columns:
                df = df[df["device_id"].astype(str) == str(device_id)]
            if "interval_seconds" in df.columns:
                df = df[pd.to_numeric(df["interval_seconds"], errors="coerce") == FORECAST_INTERVAL_SECONDS]
            return df.reset_index(drop=True)

        return self.client.get_forecast_dataset(
            device_id=device_id,
            interval_seconds=FORECAST_INTERVAL_SECONDS,
            lookback=FORECAST_LOOKBACK,
            horizon_1_min=HORIZON_1_MIN,
            horizon_2_min=HORIZON_2_MIN,
            limit=5000,
        )

    def _setpoint_training_dataset(self, device_id: str) -> pd.DataFrame:
        if self._uses_synthetic_training_data():
            df = self._read_synthetic_csv(SYNTHETIC_HABIT_CSV)
            if "device_id" in df.columns:
                df = df[df["device_id"].astype(str) == str(device_id)]
            return df.reset_index(drop=True)

        return self.client.get_habit_dataset(
            device_id=device_id,
            interval_seconds=HABIT_INTERVAL_SECONDS,
            window_minutes_before=10,
            window_minutes_after=5,
            limit=5000,
        )

    def _recommendation_user_ids(self, device_id: str) -> List[str]:
        if RECOMMEND_USER_IDS:
            return RECOMMEND_USER_IDS
        if not self._uses_synthetic_training_data():
            return []

        df = self._setpoint_training_dataset(device_id)
        if "user_id" not in df.columns:
            return []
        return sorted(str(x) for x in df["user_id"].dropna().unique())

    def train_device(self, device_id: str) -> Dict[str, Any]:
        report: Dict[str, Any] = {"device_id": device_id}
        report["forecast"] = self._safe_train(self._train_forecast, device_id)
        report["setpoint"] = self._safe_train(self._train_setpoint, device_id)
        return report

    @staticmethod
    def _safe_train(train_func, device_id: str) -> Dict[str, Any]:
        try:
            return train_func(device_id)
        except Exception as exc:
            return {
                "trained": False,
                "reason": str(exc),
                "error_type": exc.__class__.__name__,
            }

    def _train_forecast(self, device_id: str) -> Dict[str, Any]:
        df = self._forecast_training_dataset(device_id)
        if df.empty or len(df) < 40:
            return {"trained": False, "reason": "Not enough forecast samples"}

        target_cols = [
            f"target_temp_plus_{HORIZON_1_MIN}m",
            f"target_hum_plus_{HORIZON_1_MIN}m",
            f"target_temp_plus_{HORIZON_2_MIN}m",
            f"target_hum_plus_{HORIZON_2_MIN}m",
        ]
        missing_targets = [col for col in target_cols if col not in df.columns]
        if missing_targets:
            return {"trained": False, "reason": f"Missing target columns: {missing_targets}"}

        feature_cols = [
            c for c in df.columns
            if c not in {"device_id", "bucket_start", "interval_seconds", *target_cols}
        ]
        num_cols, cat_cols = split_feature_columns(df, feature_cols)

        X = df[feature_cols].copy()
        y = df[target_cols].apply(pd.to_numeric, errors="coerce")
        valid_targets = y.notna().all(axis=1)
        X = X.loc[valid_targets]
        y = y.loc[valid_targets]
        if len(X) < 40:
            return {"trained": False, "reason": "Not enough usable forecast samples"}

        split_idx = int(len(X) * 0.8)
        X_train, X_test = X.iloc[:split_idx], X.iloc[split_idx:]
        y_train, y_test = y.iloc[:split_idx], y.iloc[split_idx:]

        preprocessor = ColumnTransformer(
            transformers=[
                ("num", Pipeline([("imputer", SimpleImputer(strategy="median"))]), num_cols),
                (
                    "cat",
                    Pipeline(
                        [
                            ("imputer", SimpleImputer(strategy="most_frequent")),
                            ("onehot", OneHotEncoder(handle_unknown="ignore")),
                        ]
                    ),
                    cat_cols,
                ),
            ]
        )

        model = Pipeline(
            steps=[
                ("preprocessor", preprocessor),
                (
                    "regressor",
                    MultiOutputRegressor(
                        RandomForestRegressor(
                            n_estimators=N_ESTIMATORS,
                            random_state=RANDOM_STATE,
                            n_jobs=-1,
                            min_samples_leaf=2,
                        )
                    ),
                ),
            ]
        )
        model.fit(X_train, y_train)

        pred = model.predict(X_test)
        mae = float(mean_absolute_error(y_test, pred)) if len(X_test) > 0 else None
        r2 = float(r2_score(y_test, pred, multioutput="uniform_average")) if len(X_test) > 0 else None

        bundle = ForecastBundle(
            features=feature_cols,
            targets=target_cols,
            model=model,
            metrics={"mae": mae, "r2": r2, "samples": len(df)},
        )
        with self._lock:
            self.forecast_models[device_id] = bundle
        return {"trained": True, "source": TRAINING_DATA_SOURCE, **bundle.metrics}

    def _train_setpoint(self, device_id: str) -> Dict[str, Any]:
        df = self._setpoint_training_dataset(device_id)
        if df.empty or len(df) < 20:
            return {"trained": False, "reason": "Not enough habit samples"}

        df = df.copy()
        if "target_setpoint" in df.columns:
            df["target_setpoint"] = pd.to_numeric(df["target_setpoint"], errors="coerce")
        else:
            df["target_setpoint"] = df.apply(self._derive_target_setpoint, axis=1)
        df = df.dropna(subset=["target_setpoint"])
        if len(df) < 20:
            return {"trained": False, "reason": "Not enough usable setpoint targets"}

        feature_cols = [
            "temp_mean_before",
            "temp_min_before",
            "temp_max_before",
            "hum_mean_before",
            "fan_pwm_mean_before",
            "lamp_ratio_before",
            "setpoint_mean_before",
            "mode_majority_before",
            "user_id",
            "hour_sin",
            "hour_cos",
            "day_period",
            "event_type",
            "label",
        ]
        feature_cols = [c for c in feature_cols if c in df.columns]
        num_cols, cat_cols = split_feature_columns(df, feature_cols)

        X = df[feature_cols].copy()
        y = df["target_setpoint"].copy()

        split_idx = int(len(df) * 0.8)
        X_train, X_test = X.iloc[:split_idx], X.iloc[split_idx:]
        y_train, y_test = y.iloc[:split_idx], y.iloc[split_idx:]

        preprocessor = ColumnTransformer(
            transformers=[
                ("num", Pipeline([("imputer", SimpleImputer(strategy="median"))]), num_cols),
                (
                    "cat",
                    Pipeline(
                        [
                            ("imputer", SimpleImputer(strategy="most_frequent")),
                            ("onehot", OneHotEncoder(handle_unknown="ignore")),
                        ]
                    ),
                    cat_cols,
                ),
            ]
        )

        model = Pipeline(
            steps=[
                ("preprocessor", preprocessor),
                (
                    "regressor",
                    RandomForestRegressor(
                        n_estimators=N_ESTIMATORS,
                        random_state=RANDOM_STATE,
                        n_jobs=-1,
                        min_samples_leaf=2,
                    ),
                ),
            ]
        )
        model.fit(X_train, y_train)

        pred = model.predict(X_test)
        mae = float(mean_absolute_error(y_test, pred)) if len(X_test) > 0 else None
        r2 = float(r2_score(y_test, pred)) if len(X_test) > 0 else None

        bundle = SetpointBundle(
            features=feature_cols,
            model=model,
            metrics={"mae": mae, "r2": r2, "samples": len(df)},
        )
        with self._lock:
            self.setpoint_models[device_id] = bundle
        return {"trained": True, "source": TRAINING_DATA_SOURCE, **bundle.metrics}

    @staticmethod
    def _derive_target_setpoint(row: pd.Series) -> Optional[float]:
        if str(row.get("event_type", "")).lower() == "setpoint_change":
            try:
                return float(row.get("new_value"))
            except (TypeError, ValueError):
                pass

        base = safe_float(row.get("setpoint_mean_before"))
        if base is None:
            base = safe_float(row.get("temp_mean_before"))
        if base is None:
            return None

        user_feedback = row.get("user_feedback")
        label = str(row.get("label", ""))

        if user_feedback == 1 or label in {"too_hot", "prefer_cooler"}:
            return clamp(base - 0.5, MIN_SETPOINT, MAX_SETPOINT)
        if user_feedback == -1 or label in {"too_cold", "prefer_warmer"}:
            return clamp(base + 0.5, MIN_SETPOINT, MAX_SETPOINT)
        if user_feedback == 0 or label == "comfortable":
            return clamp(base, MIN_SETPOINT, MAX_SETPOINT)
        if label == "setpoint_adjustment":
            return clamp(base, MIN_SETPOINT, MAX_SETPOINT)
        return None

    def poll_latest_once(self) -> Dict[str, str]:
        device_ids = DEVICE_IDS or self.client.get_devices()
        result: Dict[str, str] = {}
        for device_id in device_ids:
            latest = self.client.get_latest_telemetry(device_id)
            if not latest:
                result[device_id] = "no_data"
                continue

            ts = latest.get("ts")
            if ts == self.last_seen_ts.get(device_id):
                result[device_id] = "unchanged"
                continue

            latest["parsed_ts"] = parse_ts(ts)
            self.raw_cache[device_id].append(latest)
            self.last_seen_ts[device_id] = ts
            result[device_id] = "cached"
        return result

    def recommend_cached_updates(self, poll_result: Dict[str, str]) -> Dict[str, str]:
        result: Dict[str, str] = {}
        for device_id, poll_status in poll_result.items():
            if poll_status != "cached":
                continue

            user_ids = self._recommendation_user_ids(device_id)
            if not user_ids:
                user_ids = [None]

            statuses = []
            for user_id in user_ids:
                try:
                    recommendation = self.recommend(device_id, user_id=user_id)
                except Exception as exc:
                    statuses.append(f"{user_id or DEFAULT_USER_ID}:error:{exc}")
                    continue

                if recommendation.get("log_warning"):
                    status = f"warning:{recommendation['log_warning']}"
                elif LOG_RECOMMENDATIONS_TO_BACKEND:
                    status = "posted"
                else:
                    status = "generated"
                statuses.append(f"{recommendation['user_id']}:{status}")

            result[device_id] = ", ".join(statuses)
        return result

    def _build_bucketed_history(self, device_id: str, interval_seconds: int) -> List[Dict[str, Any]]:
        cache = list(self.raw_cache.get(device_id, []))
        if not cache:
            return []

        buckets: Dict[datetime, List[Dict[str, Any]]] = defaultdict(list)
        for row in cache:
            dt = row["parsed_ts"]
            buckets[floor_time(dt, interval_seconds)].append(row)

        result: List[Dict[str, Any]] = []
        for bucket_start in sorted(buckets.keys()):
            items = buckets[bucket_start]
            temp_values = [safe_float(x.get("temp_ma")) for x in items if safe_float(x.get("temp_ma")) is not None]
            hum_values = [safe_float(x.get("hum_ma")) for x in items if safe_float(x.get("hum_ma")) is not None]
            fan_values = [safe_float(x.get("fan_pwm_actual")) for x in items if safe_float(x.get("fan_pwm_actual")) is not None]
            lamp_values = [safe_float(x.get("lamp_actual")) for x in items if safe_float(x.get("lamp_actual")) is not None]
            setpoint_values = [safe_float(x.get("setpoint_current")) for x in items if safe_float(x.get("setpoint_current")) is not None]
            mode_values = [str(x.get("mode", "auto")) for x in items]

            result.append(
                {
                    "bucket_start": bucket_start.isoformat(),
                    "temp_mean": np.mean(temp_values) if temp_values else None,
                    "hum_mean": np.mean(hum_values) if hum_values else None,
                    "fan_pwm_mean": np.mean(fan_values) if fan_values else None,
                    "lamp_on_ratio": np.mean(lamp_values) if lamp_values else None,
                    "mode_majority": majority(mode_values, default="auto"),
                    "setpoint_mean": np.mean(setpoint_values) if setpoint_values else None,
                }
            )
        return result

    def _current_forecast_features(self, device_id: str) -> Optional[pd.DataFrame]:
        with self._lock:
            bundle = self.forecast_models.get(device_id)
        if bundle is None:
            return None

        history = self._build_bucketed_history(device_id, FORECAST_INTERVAL_SECONDS)
        if len(history) < FORECAST_LOOKBACK:
            return self._forecast_dataset_features(device_id, bundle)

        recent = history[-FORECAST_LOOKBACK:]
        current_dt = parse_ts(recent[-1]["bucket_start"])
        hour_sin, hour_cos = cyclic_hour_features(current_dt, FEATURE_UTC_OFFSET_HOURS)

        row: Dict[str, Any] = {
            "temp_now": recent[-1]["temp_mean"],
            "hum_now": recent[-1]["hum_mean"],
            "fan_pwm_now": recent[-1]["fan_pwm_mean"],
            "lamp_on_ratio_now": recent[-1]["lamp_on_ratio"],
            "mode_now": recent[-1]["mode_majority"],
            "setpoint_now": recent[-1]["setpoint_mean"],
            "hour_sin": hour_sin,
            "hour_cos": hour_cos,
            "day_period": day_period(
                current_dt,
                FEATURE_UTC_OFFSET_HOURS,
                DAY_START_HOUR,
                NIGHT_START_HOUR,
            ),
        }

        for lag in range(FORECAST_LOOKBACK):
            source = recent[-1 - lag]
            row[f"temp_lag_{lag}"] = source["temp_mean"]
            row[f"hum_lag_{lag}"] = source["hum_mean"]
            row[f"fan_pwm_lag_{lag}"] = source["fan_pwm_mean"]
            row[f"lamp_ratio_lag_{lag}"] = source["lamp_on_ratio"]

        for feature in bundle.features:
            row.setdefault(feature, None)
        return pd.DataFrame([row])[bundle.features]

    def _latest_forecast_dataset_sample(self, device_id: str) -> Optional[Dict[str, Any]]:
        df = self._forecast_training_dataset(device_id)
        if df.empty:
            return None
        return df.iloc[-1].to_dict()

    def _forecast_dataset_features(self, device_id: str, bundle: ForecastBundle) -> Optional[pd.DataFrame]:
        sample = self._latest_forecast_dataset_sample(device_id)
        if sample is None:
            return None
        for feature in bundle.features:
            sample.setdefault(feature, None)
        return pd.DataFrame([sample])[bundle.features]

    def _current_setpoint_features(self, device_id: str, user_id: str) -> Optional[pd.DataFrame]:
        with self._lock:
            bundle = self.setpoint_models.get(device_id)
        if bundle is None:
            return None

        history = self._build_bucketed_history(device_id, HABIT_INTERVAL_SECONDS)
        if len(history) < 3:
            return self._setpoint_dataset_features(device_id, user_id, bundle)

        recent = history[-20:]
        temps = [x["temp_mean"] for x in recent if x["temp_mean"] is not None]
        hums = [x["hum_mean"] for x in recent if x["hum_mean"] is not None]
        fan = [x["fan_pwm_mean"] for x in recent if x["fan_pwm_mean"] is not None]
        lamp = [x["lamp_on_ratio"] for x in recent if x["lamp_on_ratio"] is not None]
        setpoints = [x["setpoint_mean"] for x in recent if x["setpoint_mean"] is not None]

        if not temps:
            return None

        current_dt = parse_ts(recent[-1]["bucket_start"])
        hour_sin, hour_cos = cyclic_hour_features(current_dt, FEATURE_UTC_OFFSET_HOURS)
        row: Dict[str, Any] = {
            "temp_mean_before": float(np.mean(temps)),
            "temp_min_before": float(np.min(temps)),
            "temp_max_before": float(np.max(temps)),
            "hum_mean_before": float(np.mean(hums)) if hums else None,
            "fan_pwm_mean_before": float(np.mean(fan)) if fan else None,
            "lamp_ratio_before": float(np.mean(lamp)) if lamp else None,
            "setpoint_mean_before": float(np.mean(setpoints)) if setpoints else DEFAULT_SETPOINT,
            "mode_majority_before": majority([x["mode_majority"] for x in recent]),
            "user_id": user_id,
            "hour_sin": hour_sin,
            "hour_cos": hour_cos,
            "day_period": day_period(
                current_dt,
                FEATURE_UTC_OFFSET_HOURS,
                DAY_START_HOUR,
                NIGHT_START_HOUR,
            ),
            "event_type": "ml_inference",
            "label": "comfortable",
        }
        for feature in bundle.features:
            row.setdefault(feature, None)
        return pd.DataFrame([row])[bundle.features]

    def _latest_habit_dataset_sample(self, device_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        df = self._setpoint_training_dataset(device_id)
        if df.empty:
            return None
        if "user_id" in df.columns:
            user_df = df[df["user_id"].astype(str) == str(user_id)]
            if not user_df.empty:
                df = user_df
        return df.iloc[-1].to_dict()

    def _setpoint_dataset_features(
        self,
        device_id: str,
        user_id: str,
        bundle: SetpointBundle,
    ) -> Optional[pd.DataFrame]:
        sample = self._latest_habit_dataset_sample(device_id, user_id)
        if sample is None:
            return None
        sample["user_id"] = user_id
        for feature in bundle.features:
            sample.setdefault(feature, None)
        return pd.DataFrame([sample])[bundle.features]

    def recommend(self, device_id: str, user_id: Optional[str] = None) -> Dict[str, Any]:
        latest_warning: Optional[str] = None
        try:
            latest = self.client.get_latest_telemetry(device_id)
        except Exception as exc:
            latest = None
            latest_warning = str(exc)

        fallback_sample: Optional[Dict[str, Any]] = None
        if latest is None:
            fallback_sample = self._latest_forecast_dataset_sample(device_id)
            if fallback_sample is None:
                raise HTTPException(status_code=404, detail="No telemetry available for device")
        resolved_user_id = user_id or (latest or {}).get("user_id") or DEFAULT_USER_ID

        with self._lock:
            forecast_bundle = self.forecast_models.get(device_id)
            setpoint_bundle = self.setpoint_models.get(device_id)

        forecast_result: Dict[str, Any] = {"available": False}
        if forecast_bundle is not None:
            x_forecast = self._current_forecast_features(device_id)
            if x_forecast is not None:
                pred = forecast_bundle.model.predict(x_forecast)[0]
                forecast_result = {
                    "available": True,
                    f"pred_temp_plus_{HORIZON_1_MIN}m": float(pred[0]),
                    f"pred_hum_plus_{HORIZON_1_MIN}m": float(pred[1]),
                    f"pred_temp_plus_{HORIZON_2_MIN}m": float(pred[2]),
                    f"pred_hum_plus_{HORIZON_2_MIN}m": float(pred[3]),
                }
            else:
                forecast_result = {"available": False, "reason": "Not enough live history for forecast features"}

        setpoint_result: Dict[str, Any] = {"available": False, "setpoint_dynamic": DEFAULT_SETPOINT}
        if setpoint_bundle is not None:
            x_setpoint = self._current_setpoint_features(device_id, resolved_user_id)
            if x_setpoint is not None:
                pred_setpoint = float(setpoint_bundle.model.predict(x_setpoint)[0])
                setpoint_result = {
                    "available": True,
                    "setpoint_dynamic": clamp(pred_setpoint, MIN_SETPOINT, MAX_SETPOINT),
                }
            else:
                setpoint_result = {
                    "available": False,
                    "reason": "Not enough live history for setpoint features",
                    "setpoint_dynamic": DEFAULT_SETPOINT,
                }

        final_setpoint = setpoint_result["setpoint_dynamic"]
        recommendation = {
            "device_id": device_id,
            "user_id": resolved_user_id,
            "ts": utc_now().isoformat(),
            "latest_temp": self._latest_temp(latest, fallback_sample),
            "latest_hum": self._latest_hum(latest, fallback_sample),
            "mode": (latest or {}).get("mode") or (fallback_sample or {}).get("mode_now"),
            "model_version": "rf_synthetic_v1" if self._uses_synthetic_training_data() else "rf_v1",
            "source_service": "ml_service_synthetic" if self._uses_synthetic_training_data() else "ml_service",
            "training_source": TRAINING_DATA_SOURCE,
            **forecast_result,
            **setpoint_result,
        }
        if latest_warning:
            recommendation["latest_warning"] = latest_warning

        pred_temp_10 = recommendation.get(f"pred_temp_plus_{HORIZON_1_MIN}m")
        if pred_temp_10 is not None:
            if pred_temp_10 > final_setpoint + 0.3:
                recommendation["control_hint"] = "cool_more"
            elif pred_temp_10 < final_setpoint - 0.3:
                recommendation["control_hint"] = "cool_less_or_heat_more"
            else:
                recommendation["control_hint"] = "hold"
        else:
            recommendation["control_hint"] = "hold"

        if LOG_RECOMMENDATIONS_TO_BACKEND:
            try:
                backend_response = self.client.post_ml_recommendation(recommendation)
                recommendation["backend_response"] = backend_response
            except Exception as exc:
                recommendation["log_warning"] = str(exc)

        return recommendation

    @staticmethod
    def _latest_temp(latest: Optional[Dict[str, Any]], fallback_sample: Optional[Dict[str, Any]]) -> Optional[float]:
        if latest is not None:
            return safe_float(latest.get("temp_ma") or latest.get("temp_raw"))
        if fallback_sample is not None:
            return safe_float(fallback_sample.get("temp_now"))
        return None

    @staticmethod
    def _latest_hum(latest: Optional[Dict[str, Any]], fallback_sample: Optional[Dict[str, Any]]) -> Optional[float]:
        if latest is not None:
            return safe_float(latest.get("hum_ma") or latest.get("hum_raw"))
        if fallback_sample is not None:
            return safe_float(fallback_sample.get("hum_now"))
        return None
