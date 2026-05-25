import json
from typing import Any, Dict, List, Optional

import pandas as pd
import requests


DATASET_TIMEOUT_SECONDS = 120


class BackendClient:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()

    def get_devices(self) -> List[str]:
        resp = self.session.get(f"{self.base_url}/devices", timeout=10)
        resp.raise_for_status()
        return resp.json().get("devices", [])

    def get_latest_telemetry(self, device_id: str) -> Optional[Dict[str, Any]]:
        resp = self.session.get(f"{self.base_url}/devices/{device_id}/telemetry/latest", timeout=10)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()

    def get_forecast_dataset(
        self,
        device_id: str,
        interval_seconds: int,
        lookback: int,
        horizon_1_min: int,
        horizon_2_min: int,
        limit: int = 5000,
    ) -> pd.DataFrame:
        resp = self.session.get(
            f"{self.base_url}/devices/{device_id}/dataset/forecast",
            params={
                "interval_seconds": interval_seconds,
                "lookback": lookback,
                "horizon_1_min": horizon_1_min,
                "horizon_2_min": horizon_2_min,
                "limit": limit,
            },
            timeout=DATASET_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        rows = resp.json().get("rows", [])
        return pd.DataFrame(rows)

    def get_habit_dataset(
        self,
        device_id: str,
        interval_seconds: int,
        window_minutes_before: int = 10,
        window_minutes_after: int = 5,
        limit: int = 5000,
    ) -> pd.DataFrame:
        resp = self.session.get(
            f"{self.base_url}/devices/{device_id}/dataset/habit",
            params={
                "interval_seconds": interval_seconds,
                "window_minutes_before": window_minutes_before,
                "window_minutes_after": window_minutes_after,
                "limit": limit,
            },
            timeout=DATASET_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        rows = resp.json().get("rows", [])
        return pd.DataFrame(rows)

    def post_ml_recommendation(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        resp = self.session.post(
            f"{self.base_url}/ml/recommendations",
            json=payload,
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()
