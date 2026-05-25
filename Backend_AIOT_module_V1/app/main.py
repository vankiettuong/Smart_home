from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes.commands import bind_mqtt_bridge as bind_command_mqtt_bridge
from app.api.routes.commands import router as commands_router
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
bind_command_mqtt_bridge(mqtt_bridge)
resample_worker = ResampleWorker(db=db)

app = FastAPI(title="Smart Home Backend", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(health_router)
app.include_router(devices_router)
app.include_router(commands_router)
app.include_router(ingest_router)
app.include_router(datasets_router)
app.include_router(ml_router)

dashboard_dir = Path(__file__).resolve().parents[2] / "Dashboard_Web_V1"
if dashboard_dir.exists():
    app.mount("/dashboard", StaticFiles(directory=str(dashboard_dir), html=True), name="dashboard")


@app.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    return RedirectResponse(url="/dashboard/")


@app.on_event("startup")
def on_startup() -> None:
    mqtt_bridge.start()
    resample_worker.start()


@app.on_event("shutdown")
def on_shutdown() -> None:
    resample_worker.stop()
