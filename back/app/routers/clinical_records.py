from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session

from app.database import get_session
from app.dependencies.auth import get_current_user
from app.models.clinical_records import ClinicalAssessment, HealthOccurrence, MedicationUse
from app.models.user import User
from app.schemas.clinical_records import AssessmentCreate, AssessmentResponse, AssessmentReview, MedicationUseCreate, MedicationUseResponse, OccurrenceCreate, OccurrenceResolve, OccurrenceResponse
from app.schemas.preflight import Page
from app.services.clinical_record_service import ClinicalRecordService
from app.services.icd_catalog import icd_search


router = APIRouter(prefix='/health', tags=['clinical records'])


def get_service(session: Session = Depends(get_session), user: User = Depends(get_current_user)):
    return ClinicalRecordService(session, user)


Service = Annotated[ClinicalRecordService, Depends(get_service)]


@router.get('/icd10')
def list_icd_codes(service: Service, search: str = Query('', max_length=250), page: int = Query(1, ge=1), per_page: int = Query(50, ge=1, le=100)):
    return icd_search(search, page, per_page)


@router.get('/astronauts/{astronaut_id}/occurrences', response_model=Page[OccurrenceResponse])
def list_occurrences(astronaut_id: int, service: Service, mission_id: int | None = Query(None, gt=0), active: bool = False, page: int = Query(1, ge=1), per_page: int = Query(20, ge=1, le=100)):
    return service.list_records(HealthOccurrence, astronaut_id, mission_id, page, per_page, active)


@router.post('/astronauts/{astronaut_id}/occurrences', response_model=OccurrenceResponse, status_code=201)
def create_occurrence(astronaut_id: int, payload: OccurrenceCreate, service: Service):
    return service.create_occurrence(astronaut_id, payload)


@router.post('/astronauts/{astronaut_id}/occurrences/{occurrence_id}/recover', response_model=OccurrenceResponse)
def recover_occurrence(astronaut_id: int, occurrence_id: int, payload: OccurrenceResolve, service: Service, mission_id: int = Query(gt=0)):
    return service.resolve_occurrence(astronaut_id, mission_id, occurrence_id, payload)


@router.get('/astronauts/{astronaut_id}/medication-uses', response_model=Page[MedicationUseResponse])
def list_medication_uses(astronaut_id: int, service: Service, mission_id: int | None = Query(None, gt=0), page: int = Query(1, ge=1), per_page: int = Query(20, ge=1, le=100)):
    return service.list_records(MedicationUse, astronaut_id, mission_id, page, per_page)


@router.post('/astronauts/{astronaut_id}/medication-uses', response_model=MedicationUseResponse, status_code=201)
def create_medication_use(astronaut_id: int, payload: MedicationUseCreate, service: Service):
    return service.create_medication(astronaut_id, payload)


@router.get('/astronauts/{astronaut_id}/clinical-report')
def clinical_report(astronaut_id: int, service: Service, mission_id: int = Query(gt=0)):
    return service.report_snapshot(astronaut_id, mission_id)


@router.get('/astronauts/{astronaut_id}/assessments', response_model=Page[AssessmentResponse])
def list_assessments(astronaut_id: int, service: Service, mission_id: int | None = Query(None, gt=0), page: int = Query(1, ge=1), per_page: int = Query(20, ge=1, le=100)):
    return service.list_records(ClinicalAssessment, astronaut_id, mission_id, page, per_page)


@router.post('/astronauts/{astronaut_id}/assessments', response_model=AssessmentResponse, status_code=201)
def create_assessment(astronaut_id: int, payload: AssessmentCreate, service: Service):
    return service.create_assessment(astronaut_id, payload.mission_id)


@router.post('/astronauts/{astronaut_id}/assessments/{assessment_id}/review', response_model=AssessmentResponse)
def review_assessment(astronaut_id: int, assessment_id: int, payload: AssessmentReview, service: Service, mission_id: int = Query(gt=0)):
    return service.review_assessment(astronaut_id, mission_id, assessment_id, payload)
