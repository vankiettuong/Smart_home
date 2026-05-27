import unittest
from unittest.mock import patch

from app.api.routes import ml
from app.schemas.ml_recommendation import MLRecommendationIn


class FakeDb:
    def __init__(self, active_user_id="user-a", mode="auto") -> None:
        self.active_user_id = active_user_id
        self.mode = mode
        self.saved = []

    def latest_control_event(self, device_id, event_type=None):
        if event_type == "mode_change":
            return {"device_id": device_id, "new_value": self.mode}
        return {"device_id": device_id, "user_id": self.active_user_id}

    def latest_user_control_event(self, device_id):
        return {"device_id": device_id, "user_id": self.active_user_id}

    def latest_device_twin(self, device_id):
        return {"device_id": device_id, "mode_actual": self.mode}

    def latest_telemetry(self, device_id):
        return {"device_id": device_id, "mode": self.mode, "user_id": self.active_user_id}

    def latest_user_telemetry(self, device_id):
        return {"device_id": device_id, "mode": self.mode, "user_id": self.active_user_id}

    def insert_ml_recommendation(self, item, published_topic=None, publish_success=False):
        self.saved.append(
            {
                "item": item,
                "published_topic": published_topic,
                "publish_success": publish_success,
            }
        )
        return len(self.saved)


class FakeMqttBridge:
    def __init__(self) -> None:
        self.published = []

    def publish_ml_setpoint(self, device_id, payload):
        self.published.append((device_id, payload))
        return True


class MlActiveUserPublishTest(unittest.TestCase):
    def test_inactive_user_recommendation_is_saved_but_not_published(self):
        fake_db = FakeDb(active_user_id="user-a")
        fake_bridge = FakeMqttBridge()
        item = MLRecommendationIn(
            device_id="esp32-room-a",
            user_id="user-b",
            setpoint_dynamic=27.2,
        )

        with patch.object(ml, "db", fake_db), patch.object(ml, "_mqtt_bridge", fake_bridge):
            response = ml.create_ml_recommendation(item)

        self.assertTrue(response["publish_skipped"])
        self.assertEqual(response["skip_reason"], "inactive_user")
        self.assertEqual(response["active_user_id"], "user-a")
        self.assertFalse(fake_db.saved[0]["publish_success"])
        self.assertEqual(fake_bridge.published, [])

    def test_active_user_recommendation_is_published(self):
        fake_db = FakeDb(active_user_id="user-a")
        fake_bridge = FakeMqttBridge()
        item = MLRecommendationIn(
            device_id="esp32-room-a",
            user_id="user-a",
            setpoint_dynamic=29.4,
        )

        with patch.object(ml, "db", fake_db), patch.object(ml, "_mqtt_bridge", fake_bridge):
            response = ml.create_ml_recommendation(item)

        self.assertFalse(response["publish_skipped"])
        self.assertIsNone(response["skip_reason"])
        self.assertTrue(response["publish_success"])
        self.assertTrue(fake_db.saved[0]["publish_success"])
        self.assertEqual(fake_bridge.published[0][1]["user_id"], "user-a")


if __name__ == "__main__":
    unittest.main()
