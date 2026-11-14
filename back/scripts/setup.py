import time
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlmodel import Session

from app.database import engine
from app.services.knowledge_transfer import import_public_knowledge
from scripts.knowledge import SEED_PATH, load_bundle


ROOT = Path(__file__).resolve().parent.parent


def setup_database() -> None:
    bundle = load_bundle(SEED_PATH)
    deadline = time.monotonic() + 60
    while True:
        try:
            connection = engine.connect()
            break
        except OperationalError:
            if time.monotonic() >= deadline:
                raise
            time.sleep(1)
    with connection:
        connection.execute(text("SELECT pg_advisory_lock(742306101)"))
        try:
            config = Config(str(ROOT / "alembic.ini"))
            config.set_main_option("script_location", str(ROOT / "alembic"))
            command.upgrade(config, "head")
            with Session(engine) as session, session.begin():
                import_public_knowledge(session, bundle)
        finally:
            connection.execute(text("SELECT pg_advisory_unlock(742306101)"))
    print("Database migrations and initial public knowledge are ready")


if __name__ == "__main__":
    setup_database()
