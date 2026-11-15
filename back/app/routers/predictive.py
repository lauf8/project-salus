from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session

from app.database import get_session
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.schemas.predictive import RecommendationFeedbackInput, RecommendationOutcomeInput
from app.services.predictive_service import PredictiveService


router = APIRouter(tags=['predictive intelligence'])


def predictive_service(session: Session = Depends(get_session), user: User = Depends(get_current_user)):
    return PredictiveService(session, user)


Service = Annotated[PredictiveService, Depends(predictive_service)]


@router.get('/predictions/dashboard')
def dashboard(service: Service):
    return service.dashboard()


@router.get('/predictions/astronauts/{astronaut_id}')
def astronaut_predictions(astronaut_id: int, service: Service, mission_id: int | None = Query(default=None, gt=0)):
    return service.astronaut_view(astronaut_id, mission_id)


@router.post('/predictions/astronauts/{astronaut_id}/analyze')
def analyze_astronaut(astronaut_id: int, service: Service, mission_id: int | None = Query(default=None, gt=0)):
    run = service.analyze_astronaut(astronaut_id, mission_id)
    return service.astronaut_view(astronaut_id, run.mission_id)


@router.get('/predictions/missions/{mission_id}')
def mission_predictions(mission_id: int, service: Service):
    return service.mission_view(mission_id)


@router.post('/predictions/missions/{mission_id}/analyze')
def analyze_mission(mission_id: int, service: Service):
    service.analyze_mission(mission_id)
    return service.mission_view(mission_id)


@router.get('/predictions/spacecraft/{spacecraft_id}')
def spacecraft_predictions(spacecraft_id: int, service: Service):
    return service.spacecraft_view(spacecraft_id)


@router.get('/recommendations')
def recommendations(service: Service, status: Literal['pending', 'accepted', 'rejected', 'executed', 'superseded'] | None = None, mission_id: int | None = Query(default=None, gt=0), limit: int = Query(default=100, ge=1, le=200)):
    return service.list_recommendations(status, mission_id, limit)


@router.get('/recommendations/{recommendation_id}')
def recommendation(recommendation_id: int, service: Service):
    return service.recommendation(recommendation_id)


@router.post('/recommendations/{recommendation_id}/feedback')
def recommendation_feedback(recommendation_id: int, payload: RecommendationFeedbackInput, service: Service):
    return service.feedback(recommendation_id, payload)


@router.post('/recommendations/{recommendation_id}/outcomes', status_code=201)
def recommendation_outcome(recommendation_id: int, payload: RecommendationOutcomeInput, service: Service):
    return service.outcome(recommendation_id, payload)


@router.post('/recommendations/{recommendation_id}/evidence')
def recommendation_evidence(recommendation_id: int, service: Service):
    return service.refresh_evidence(recommendation_id)


@router.get('/prediction-models')
def prediction_models(service: Service):
    return service.models()


@router.get('/prediction-models/{model_id}/metrics')
def prediction_model_metrics(model_id: int, service: Service):
    return service.model_metrics(model_id)


@router.post('/prediction-models/{model_id}/approve')
def approve_model(model_id: int, service: Service):
    return service.transition_model(model_id, 'approved')


@router.post('/prediction-models/{model_id}/activate')
def activate_model(model_id: int, service: Service):
    return service.transition_model(model_id, 'active')


@router.post('/prediction-models/{model_id}/retire')
def retire_model(model_id: int, service: Service):
    return service.transition_model(model_id, 'retired')
