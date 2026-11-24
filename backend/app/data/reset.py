"""Reset the demo database: `python -m app.data.reset` (run from backend/)."""

import logging

from app.config import get_settings
from app.database import reset_db

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    reset_db()
    print(f"Database reset and re-seeded at {get_settings().database_path}")
