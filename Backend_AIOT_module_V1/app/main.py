from fastapi import FastAPI

from app.api.routes.datasets import router as datasets_router
from app.api.routes.devices import router as devices_router
from app.api.routes.health import router as health_router
from app.api.routes.ingest import router as ingest_router
from app.api.routes.ml import bind_mqtt_bridge, router as ml_router
from app.db.session import db
from app.services.mqtt_bridge import MQTTBridge
from app.workers.resample_worker import ResampleWorker

mqtt_bridge = MQTTBridge(db=db)
bind_mqtt_bridge(mqtt_bridge)
resample_worker = ResampleWorker(db=db)

app = FastAPI(title="Smart Home Backend", version="1.0.0")
app.include_router(health_router)
app.include_router(devices_router)
app.include_router(ingest_router)
app.include_router(datasets_router)
app.include_router(ml_router)


@app.on_event("startup")
def on_startup() -> None:
    mqtt_bridge.start()
    resample_worker.start()


@app.on_event("shutdown")
def on_shutdown() -> None:
    resample_worker.stop()
