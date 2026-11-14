from sqlmodel import Session

from app.database import engine
from app.services.knowledge_transfer import import_public_knowledge
from scripts.knowledge import SEED_PATH, load_bundle


def seed_knowledge(session: Session) -> None:
    import_public_knowledge(session, load_bundle(SEED_PATH))
    session.commit()


def main() -> None:
    with Session(engine) as session:
        seed_knowledge(session)
    print("NASA reference seed completed")


if __name__ == "__main__":
    main()
