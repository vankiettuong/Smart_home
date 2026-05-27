from app.main import app

#run with uvicorn run:app --host 0.0.0.0 --port 8100 --reload
#BACKEND_BASE_URL=http://localhost:8000 DEVICE_IDS=esp32-room-a FEATURE_UTC_OFFSET_HOURS=7 TRAINING_DATA_SOURCE=synthetic ../.venv/bin/uvicorn run:app --host 0.0.0.0 --port 8100 --reload