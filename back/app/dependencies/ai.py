from fastapi import Depends, Request

from sqlmodel import Session

from app.database import get_session
from app.repositories.knowledge_repository import KnowledgeRepository
from app.providers.ai import AiProvider
from app.services.assessment_service import AssessmentService


def get_ai_provider(request: Request) -> AiProvider:
    return request.app.state.ai_provider


def get_assessment_service(
    request: Request,
    provider: AiProvider = Depends(get_ai_provider),
    session: Session = Depends(get_session),
) -> AssessmentService:
    return AssessmentService(
        provider, request.app.state.agent_instructions, KnowledgeRepository(session)
    )
