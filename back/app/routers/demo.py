from fastapi import APIRouter, Depends, HTTPException

from app.dependencies.ai import get_assessment_service
from app.providers.ai import AiInvalidResponseError, AiTimeoutError, AiUnavailableError
from app.schemas.assessments import AssessmentExtraction, AssessmentExtractRequest
from app.services.assessment_service import AssessmentService

router = APIRouter(prefix="/demo/assessments", tags=["demo"])


@router.post("/extract", response_model=AssessmentExtraction)
async def extract_assessment(
    payload: AssessmentExtractRequest,
    service: AssessmentService = Depends(get_assessment_service),
) -> AssessmentExtraction:
    try:
        return await service.extract(payload.context, payload.confirmed_symptom_codes)
    except AiTimeoutError as exc:
        raise HTTPException(504, "AI provider timed out") from exc
    except AiUnavailableError as exc:
        raise HTTPException(503, "AI provider unavailable") from exc
    except AiInvalidResponseError as exc:
        raise HTTPException(502, "AI provider returned an invalid response") from exc
