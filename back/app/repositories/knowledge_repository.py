from sqlmodel import Session, select

from app.models.knowledge import KnowledgeDocument, KnowledgePassage
from app.schemas.knowledge import ReferenceExcerpt


class KnowledgeRepository:
    def __init__(self, session: Session):
        self.session = session

    def find_by_symptom_codes(self, confirmed_symptom_codes: list[str]) -> list[ReferenceExcerpt]:
        codes = sorted({code.strip() for code in confirmed_symptom_codes if code.strip()})
        if not codes:
            return []
        statement = (
            select(KnowledgePassage, KnowledgeDocument)
            .join(KnowledgeDocument, KnowledgePassage.document_id == KnowledgeDocument.id)
            .where(
                KnowledgeDocument.is_public.is_(True),
                KnowledgePassage.topic_codes.overlap(codes),
            )
            .order_by(KnowledgePassage.id)
            .limit(4)
        )
        return [
            ReferenceExcerpt(
                source_id=f"nasa:{passage.stable_id}",
                title=document.title,
                source_url=document.source_url,
                revision=document.revision,
                section=passage.section,
                page_number=passage.page_number,
                content=passage.content,
            )
            for passage, document in self.session.exec(statement).all()
        ]
