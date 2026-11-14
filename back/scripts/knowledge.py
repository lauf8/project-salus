import argparse
from pathlib import Path

from sqlmodel import Session

from app.database import engine
from app.schemas.knowledge_transfer import PublicKnowledgeBundle
from app.services.knowledge_transfer import export_public_knowledge, import_public_knowledge


SEED_PATH = Path(__file__).resolve().parent.parent / "knowledge_seed.json"


def load_bundle(path: Path) -> PublicKnowledgeBundle:
    return PublicKnowledgeBundle.model_validate_json(path.read_text(encoding="utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Import or export public reference knowledge")
    parser.add_argument("action", choices=["import", "export"])
    parser.add_argument("path", type=Path)
    args = parser.parse_args()
    with Session(engine) as session:
        if args.action == "import":
            with session.begin():
                import_public_knowledge(session, load_bundle(args.path))
        else:
            bundle = export_public_knowledge(session)
            args.path.write_text(bundle.model_dump_json(indent=2) + "\n", encoding="utf-8")
    print(f"Public knowledge {args.action} completed: {args.path}")


if __name__ == "__main__":
    main()
