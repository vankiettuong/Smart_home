from app.main import app

# Run with:
# uvicorn run:app --host 0.0.0.0 --port 8000 --reload
# DB_PATH=smart_home_userpref_sim.db FEATURE_UTC_OFFSET_HOURS=7 ../.venv/bin/uvicorn run:app --host 0.0.0.0 --port 8000 --reload