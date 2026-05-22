from app.core.config import BACKEND_BASE_URL
from app.services.backend_client import BackendClient
from app.services.ml_service import MLService

backend_client = BackendClient(BACKEND_BASE_URL)
ml_service = MLService(backend_client)
