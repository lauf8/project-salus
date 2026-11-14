import os
from datetime import datetime, timezone

import pytest
from sqlalchemy import inspect, text
from sqlmodel import Session, select

from app.database import engine
from app.models.knowledge import KnowledgeDocument, KnowledgePassage
from app.repositories.knowledge_repository import KnowledgeRepository
from scripts.seed_knowledge import seed_knowledge
from scripts.knowledge import SEED_PATH, load_bundle

pytestmark = pytest.mark.skipif(
    os.getenv("KNOWLEDGE_POSTGRES_TESTS") != "1",
    reason="Requires an isolated migrated PostgreSQL development database",
)


def test_seed_is_idempotent_and_retrieval_matches():
    with Session(engine) as session:
        seed_knowledge(session)
        before = [
            (row.id, row.source_url, row.revision, row.imported_at)
            for row in session.exec(select(KnowledgeDocument).order_by(KnowledgeDocument.id))
        ]
        passage_ids = list(session.exec(select(KnowledgePassage.id).order_by(KnowledgePassage.id)))
        seed_knowledge(session)
        session.expire_all()
        after = [
            (row.id, row.source_url, row.revision, row.imported_at)
            for row in session.exec(select(KnowledgeDocument).order_by(KnowledgeDocument.id))
        ]
        assert before == after
        bundle = load_bundle(SEED_PATH)
        assert len(after) == len(bundle.documents)
        assert passage_ids == list(session.exec(select(KnowledgePassage.id).order_by(KnowledgePassage.id)))
        assert len(passage_ids) == sum(len(document.passages) for document in bundle.documents)
        repository = KnowledgeRepository(session)
        headache = repository.find_by_symptom_codes(["headache"])
        vision = repository.find_by_symptom_codes(["blurred_vision"])
        assert len(headache) == len(vision) == 1
        assert "Carbon Dioxide" in headache[0].title
        assert headache[0].page_number == 5
        assert headache[0].revision == "Rev D, 2026-03-10"
        assert "SANS" in vision[0].title
        assert vision[0].page_number is None
        assert headache[0].source_id == f"nasa:{bundle.documents[0].passages[0].stable_id}"
        assert "Sleep" in repository.find_by_symptom_codes(["fatigue"])[0].title
        assert repository.find_by_symptom_codes([]) == []
        assert repository.find_by_symptom_codes(["fictional_unknown"]) == []
        assert len(repository.find_by_symptom_codes(["headache", "cabin_co2"])) == 1
        assert len(repository.find_by_symptom_codes(["headache", "blurred_vision"])) == 2


def test_postgres_schema():
    inspector = inspect(engine)
    indexes = inspector.get_indexes("knowledge_passages")
    gin = next(index for index in indexes if index["name"] == "ix_knowledge_passages_topic_codes")
    assert gin["dialect_options"]["postgresql_using"] == "gin"
    foreign_keys = inspector.get_foreign_keys("knowledge_passages")
    assert any(key["referred_table"] == "knowledge_documents" for key in foreign_keys)
    with engine.connect() as connection:
        assert connection.execute(text(
            "SELECT udt_name FROM information_schema.columns "
            "WHERE table_name='knowledge_passages' AND column_name='topic_codes'"
        )).scalar_one() == "_text"


def test_retrieval_is_limited_to_four():
    with Session(engine) as session:
        try:
            document = KnowledgeDocument(
                title="Fictional test", source_url="https://example.test/limit",
                revision="Fictional", imported_at=datetime.now(timezone.utc), is_public=True,
            )
            session.add(document)
            session.flush()
            for index in range(6):
                session.add(KnowledgePassage(
                    document_id=document.id, section=f"Fictional section {index}",
                    content="Fictional test content", topic_codes=["fictional_limit"],
                ))
            session.flush()
            assert len(KnowledgeRepository(session).find_by_symptom_codes(["fictional_limit"])) == 4
        finally:
            session.rollback()


def test_demo_route_sends_references_before_generation():
    import json
    from fastapi.testclient import TestClient
    from app.main import app

    class Provider:
        async def generate(self, instructions, context):
            payload = json.loads(context)
            assert payload["confirmed_symptom_codes"] == ["headache"]
            excerpts = payload["reference_excerpts"]
            assert len(excerpts) == 1
            assert "Carbon Dioxide" in excerpts[0]["title"]
            return json.dumps({
                "symptom": "Fictional headache", "activity_context": None,
                "source_ids": [excerpts[0]["source_id"]],
            })

    with TestClient(app) as client:
        app.state.ai_provider = Provider()
        response = client.post("/demo/assessments/extract", json={
            "context": "Fictional headache after training",
            "confirmed_symptom_codes": ["headache"],
        })
        assert response.status_code == 200
        assert response.json()["source_ids"][0].startswith("nasa:")


def test_import_preserves_local_edits_and_public_export_scope():
    from app.services.knowledge_transfer import export_public_knowledge, import_public_knowledge

    with Session(engine) as session:
        before = export_public_knowledge(session)
        document = session.exec(select(KnowledgeDocument).where(
            KnowledgeDocument.stable_id == before.documents[0].stable_id
        )).one()
        passage = session.exec(select(KnowledgePassage).where(
            KnowledgePassage.stable_id == before.documents[0].passages[0].stable_id
        )).one()
        document.title = "Fictional local title edit"
        document.source_url = "https://example.test/local-edit"
        passage.section = "Fictional local section edit"
        passage.content = "Fictional local content edit"
        passage.topic_codes = ["fictional_local_tag"]
        session.add(document)
        session.add(passage)
        private_document = KnowledgeDocument(
            title="Fictional private record", source_url="https://example.test/private",
            revision="Fictional", is_public=False,
        )
        session.add(private_document)
        session.flush()
        session.add(KnowledgePassage(
            document_id=private_document.id, section="Fictional private section",
            content="Fictional private content", topic_codes=["fictional_private"],
        ))
        session.flush()
        import_public_knowledge(session, load_bundle(SEED_PATH))
        session.expire_all()
        saved = session.get(KnowledgeDocument, document.id)
        saved_passage = session.get(KnowledgePassage, passage.id)
        assert saved.title == "Fictional local title edit"
        assert saved.source_url == "https://example.test/local-edit"
        assert saved_passage.section == "Fictional local section edit"
        assert saved_passage.content == "Fictional local content edit"
        assert saved_passage.topic_codes == ["fictional_local_tag"]
        exported = export_public_knowledge(session)
        assert len(exported.documents) == len(before.documents)
        assert "Fictional private" not in exported.model_dump_json()
        assert KnowledgeRepository(session).find_by_symptom_codes(["fictional_private"]) == []
        session.rollback()


def test_conflicting_import_is_atomic():
    from app.schemas.knowledge_transfer import PublicKnowledgeBundle
    from app.services.knowledge_transfer import export_public_knowledge, import_public_knowledge

    with Session(engine) as session:
        before = export_public_knowledge(session)
        payload = before.model_dump(mode="json")
        payload["documents"][0]["stable_id"] = "fictional-conflicting-document-id"
        with pytest.raises(ValueError):
            with session.begin_nested():
                import_public_knowledge(session, PublicKnowledgeBundle.model_validate(payload))
        assert export_public_knowledge(session) == before
