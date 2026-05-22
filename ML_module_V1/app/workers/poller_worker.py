import threading

from app.core.config import AUTO_RECOMMEND_ON_POLL, POLL_SECONDS
from app.services.ml_service import MLService


class PollerWorker:
    def __init__(self, service: MLService) -> None:
        self.service = service
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> None:
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        self.thread.join(timeout=3)

    def _run(self) -> None:
        while not self.stop_event.is_set():
            try:
                result = self.service.poll_latest_once()
                if result:
                    print(f"[POLL] {result}")
                if AUTO_RECOMMEND_ON_POLL:
                    recommendations = self.service.recommend_cached_updates(result)
                    if recommendations:
                        print(f"[RECOMMEND] {recommendations}")
            except Exception as exc:
                print(f"[POLL] Error: {exc}")
            self.stop_event.wait(POLL_SECONDS)
