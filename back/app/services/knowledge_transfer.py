from datetime import datetime, timezone

from sqlalchemy.dialects.postgresql import insert
from sqlmodel import Session, select

from app.models.knowledge import KnowledgeDocument, KnowledgePassage
from app.schemas.knowledge_transfer import PublicDocument, PublicKnowledgeBundle, PublicPassage


def import_public_knowledge(session: Session, bundle: PublicKnowledgeBundle) -> None:
    for document in bundle.documents:
        session.execute(insert(KnowledgeDocument).values(
            stable_id=document.stable_id,
            title=document.title,
            source_url=str(document.source_url),
            revision=document.revision,
            document_type=document.document_type,
            imported_at=document.imported_at or datetime.now(timezone.utc),
            is_public=True,
        ).on_conflict_do_nothing())
        existing = session.exec(select(KnowledgeDocument).where(
            KnowledgeDocument.stable_id == document.stable_id
        )).one_or_none()
        if existing is None or not existing.is_public:
            raise ValueError("Document identity conflicts with an existing reference")
        for passage in document.passages:
            session.execute(insert(KnowledgePassage).values(
                stable_id=passage.stable_id, document_id=existing.id,
                section=passage.section, page_number=passage.page_number,
                content=passage.content, topic_codes=passage.topic_codes,
            ).on_conflict_do_nothing())
            saved = session.exec(select(KnowledgePassage).where(
                KnowledgePassage.stable_id == passage.stable_id
            )).one_or_none()
            if saved is None or saved.document_id != existing.id:
                raise ValueError("Passage identity conflicts with an existing reference")
    session.flush()


def export_public_knowledge(session: Session) -> PublicKnowledgeBundle:
    documents = session.exec(select(KnowledgeDocument).where(
        KnowledgeDocument.is_public.is_(True)
    ).order_by(KnowledgeDocument.stable_id)).all()
    passages = session.exec(select(KnowledgePassage).join(
        KnowledgeDocument, KnowledgePassage.document_id == KnowledgeDocument.id
    ).where(KnowledgeDocument.is_public.is_(True)).order_by(KnowledgePassage.stable_id)).all()
    by_document: dict[int, list[PublicPassage]] = {}
    for passage in passages:
        by_document.setdefault(passage.document_id, []).append(PublicPassage(
            stable_id=passage.stable_id, section=passage.section,
            page_number=passage.page_number, content=passage.content,
            topic_codes=passage.topic_codes,
        ))
    return PublicKnowledgeBundle(documents=[
        PublicDocument(
            stable_id=document.stable_id, title=document.title,
            source_url=document.source_url, revision=document.revision,
            document_type=document.document_type, imported_at=document.imported_at,
            passages=by_document.get(document.id, []),
        )
        for document in documents
    ])
