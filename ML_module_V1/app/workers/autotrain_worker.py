import json
import threading

from app.core.config import BACKGROUND_AUTOTRAIN_SECONDS
from app.services.ml_service import MLService


class AutoTrainWorker:
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
                report = self.service.train_all()
                print(f"[TRAIN] {json.dumps(report, ensure_ascii=False)}")
            except Exception as exc:
                print(f"[TRAIN] Error: {exc}")
            self.stop_event.wait(BACKGROUND_AUTOTRAIN_SECONDS)
