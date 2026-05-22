from fastapi import FastAPI

from app.api.routes.cache import router as cache_router
from app.api.routes.health import router as health_router
from app.api.routes.recommendations import router as recommendations_router
from app.api.routes.training import router as training_router
from app.dependencies import ml_service
from app.workers.autotrain_worker import AutoTrainWorker
from app.workers.poller_worker import PollerWorker

app = FastAPI(title="Smart Home Random Forest ML Service", version="1.0.0")

app.include_router(health_router)
app.include_router(training_router)
app.include_router(recommendations_router)
app.include_router(cache_router)

poller = PollerWorker(ml_service)
autotrain = AutoTrainWorker(ml_service)


@app.on_event("startup")
def startup() -> None:
    try:
        ml_service.train_all()
    except Exception as exc:
        print(f"[STARTUP] Initial train failed: {exc}")
    poller.start()
    autotrain.start()


@app.on_event("shutdown")
def shutdown() -> None:
    poller.stop()
    autotrain.stop()
