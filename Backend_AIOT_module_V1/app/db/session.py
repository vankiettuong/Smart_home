from app.core.config import settings
from app.db.database import Database


db = Database(settings.db_path)
