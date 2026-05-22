import threading

from app.core.config import settings
from app.db.database import Database


class ResampleWorker:
    def __init__(self, db: Database) -> None:
        self.db = db
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=3)

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                result = self.db.resample_all_devices(settings.resample_intervals)
                if result:
                    print(f"[RESAMPLE] Updated: {result}")
            except Exception as exc:
                print(f"[RESAMPLE] Error: {exc}")
            self._stop.wait(settings.resample_loop_period_seconds)
