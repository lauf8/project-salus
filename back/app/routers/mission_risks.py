from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlmodel import Session

from app.database import get_session
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.schemas.mission_risks import OccurrenceInput, ReplayInput, RiskActionInput, RiskPlanInput, SearchInput
from app.services.mission_rag import MissionRagService
from app.services.mission_risk_service import MissionRiskService
from app.services.nutrition_service import NutritionService


router = APIRouter(tags=['mission risks'])


def risk_service(session: Session = Depends(get_session), user: User = Depends(get_current_user)):
    return MissionRiskService(session, user)


Service = Annotated[MissionRiskService, Depends(risk_service)]


def document_writer(service):
    NutritionService(service.session, service.user)._food_catalog_writer()


@router.get('/risk-documents')
def documents(service: Service):
    return MissionRagService(service.session).documents()


@router.get('/risk-documents/ollama')
def ollama_status(service: Service):
    document_writer(service)
    try:
        return MissionRagService(service.session).rag.capabilities()
    except Exception:
        raise HTTPException(503, 'Ollama is unavailable or configured models are not installed')


@router.post('/risk-documents', status_code=201)
def import_document(service: Service, title: Annotated[str, Form(min_length=1, max_length=300)], revision: Annotated[str, Form(min_length=1, max_length=100)], file: Annotated[UploadFile, File()], source_url: Annotated[str, Form(max_length=2000)] = ''):
    document_writer(service)
    data = file.file.read(20 * 1024 * 1024 + 1)
    return MissionRagService(service.session).import_pdf(data, title, source_url, revision)


@router.post('/risk-documents/search')
def search_documents(payload: SearchInput, service: Service):
    try:
        return MissionRagService(service.session).search(payload.query, payload.document_id, payload.origin)
    except Exception:
        raise HTTPException(503, 'Document retrieval is unavailable; stock and calculated alerts are preserved')


@router.post('/risk-documents/{document_id}/process')
def process_document(document_id: int, service: Service):
    document_writer(service)
    return MissionRagService(service.session).process(document_id)


@router.get('/mission-risks/assigned')
def assigned_actions(service: Service):
    return service.assigned()


@router.get('/missions/{mission_id}/risks')
def mission_risks(mission_id: int, service: Service):
    return service.list_state(mission_id)


@router.get('/missions/{mission_id}/risks/health')
def health_risks(mission_id: int, service: Service):
    return service.health_risks(mission_id)


@router.post('/missions/{mission_id}/risks/evaluate')
def evaluate(mission_id: int, service: Service):
    return service.evaluate(mission_id)


@router.get('/missions/{mission_id}/risks/plans')
def risk_plans(mission_id: int, service: Service):
    return service.plans(mission_id)


@router.post('/missions/{mission_id}/risks/plans', status_code=201)
def save_plan(mission_id: int, payload: RiskPlanInput, service: Service):
    return service.save_plan(mission_id, payload)


@router.get('/missions/{mission_id}/risks/occurrences')
def occurrences(mission_id: int, service: Service):
    return service.occurrences(mission_id)


@router.post('/missions/{mission_id}/risks/occurrences', status_code=201)
def record_occurrence(mission_id: int, payload: OccurrenceInput, service: Service):
    return service.record_occurrence(mission_id, payload)


@router.post('/missions/{mission_id}/risks/occurrences/{occurrence_id}/confirm')
def confirm_occurrence(mission_id: int, occurrence_id: int, service: Service):
    return service.confirm_occurrence(mission_id, occurrence_id)


@router.post('/missions/{mission_id}/risks/{alert_id}/guidance')
def guidance(mission_id: int, alert_id: int, service: Service):
    return service.guidance(mission_id, alert_id)


@router.post('/missions/{mission_id}/risks/{alert_id}/actions')
def record_action(mission_id: int, alert_id: int, payload: RiskActionInput, service: Service):
    alert = service.action(mission_id, alert_id, payload)
    return service.alert_response(alert, astronaut=service.user.is_astronaut and not service.user.is_global_admin)


@router.get('/missions/{mission_id}/risks/{alert_id}/actions')
def actions(mission_id: int, alert_id: int, service: Service):
    return service.actions(mission_id, alert_id)


@router.post('/missions/{mission_id}/risks/replay')
def replay(mission_id: int, payload: ReplayInput, service: Service):
    return service.replay(mission_id, payload.start_at, payload.end_at)
