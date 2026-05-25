import unittest
from unittest.mock import patch

from app.core.config import DEFAULT_SETPOINT
from app.services.ml_service import MLService


class FakeBackendClient:
    def __init__(self) -> None:
        self.latest = {
            "device_id": "esp32-room-a",
            "ts": "2026-05-22T10:00:00+00:00",
            "temp_ma": 30.1,
            "hum_ma": 65.0,
            "mode": "auto",
        }
        self.recommendations = []

    def get_devices(self):
        return ["esp32-room-a"]

    def get_latest_telemetry(self, device_id):
        if device_id != "esp32-room-a":
            return None
        return dict(self.latest)

    def post_ml_recommendation(self, payload):
        self.recommendations.append(payload)
        return {"status": "stored"}


class PollRecommendationFlowTest(unittest.TestCase):
    def test_cached_telemetry_posts_recommendation(self):
        client = FakeBackendClient()
        service = MLService(client)

        with (
            patch("app.services.ml_service.DEVICE_IDS", ["esp32-room-a"]),
            patch("app.services.ml_service.LOG_RECOMMENDATIONS_TO_BACKEND", True),
        ):
            poll_result = service.poll_latest_once()
            recommendation_result = service.recommend_cached_updates(poll_result)

        self.assertEqual(poll_result, {"esp32-room-a": "cached"})
        self.assertEqual(recommendation_result, {"esp32-room-a": "user-a:posted, user-b:posted"})
        self.assertEqual(len(client.recommendations), 2)
        self.assertEqual({item["device_id"] for item in client.recommendations}, {"esp32-room-a"})
        self.assertEqual({item["user_id"] for item in client.recommendations}, {"user-a", "user-b"})
        self.assertEqual({item["setpoint_dynamic"] for item in client.recommendations}, {DEFAULT_SETPOINT})

    def test_unchanged_telemetry_does_not_post_again(self):
        client = FakeBackendClient()
        service = MLService(client)

        with (
            patch("app.services.ml_service.DEVICE_IDS", ["esp32-room-a"]),
            patch("app.services.ml_service.LOG_RECOMMENDATIONS_TO_BACKEND", True),
        ):
            first_poll = service.poll_latest_once()
            service.recommend_cached_updates(first_poll)
            second_poll = service.poll_latest_once()
            recommendation_result = service.recommend_cached_updates(second_poll)

        self.assertEqual(second_poll, {"esp32-room-a": "unchanged"})
        self.assertEqual(recommendation_result, {})
        self.assertEqual(len(client.recommendations), 2)


if __name__ == "__main__":
    unittest.main()
