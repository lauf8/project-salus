from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response

from app.dependencies.preflight import get_preflight_service
from app.schemas.preflight import (
    AcceptedExamResponse, ChecklistResponse, ExamTypeCreate, ExamTypePatch, ExamTypeResponse,
    MemberCreate, MemberPatch, MemberResponse, MissionCreate, MissionPatch, MissionResponse,
    Page, RequirementCreate, RequirementPatch, RequirementResponse, ResultCreate,
    ResultPatch, ResultResponse, ReviewCreate, ReviewResponse, SchedulePatch,
)
from app.schemas.exams import ExamCreate, ExamUpdate, ExamResponse
from app.services.preflight_service import PreflightService


router = APIRouter(tags=["preflight"])
Service = Annotated[PreflightService, Depends(get_preflight_service)]
PageNumber = Annotated[int, Query(ge=1)]
PageSize = Annotated[int, Query(ge=1, le=100)]


@router.post("/missions", response_model=MissionResponse, status_code=201)
def create_mission(payload: MissionCreate, service: Service):
    return service.create_mission(payload)


@router.get("/missions", response_model=Page[MissionResponse])
def list_missions(service: Service, page: PageNumber = 1, per_page: PageSize = 10):
    return service.list_missions(page, per_page)


@router.get("/missions/{mission_id}", response_model=MissionResponse)
def get_mission(mission_id: int, service: Service):
    return service.get_mission(mission_id)


@router.patch("/missions/{mission_id}", response_model=MissionResponse)
def update_mission(mission_id: int, payload: MissionPatch, service: Service):
    return service.update_mission(mission_id, payload)


@router.delete("/missions/{mission_id}", status_code=204)
def delete_mission(mission_id: int, service: Service):
    service.delete_mission(mission_id)
    return Response(status_code=204)


@router.post("/missions/{mission_id}/members", response_model=MemberResponse, status_code=201)
def create_member(mission_id: int, payload: MemberCreate, service: Service):
    return service.create_member(mission_id, payload)


@router.get("/missions/{mission_id}/members", response_model=Page[MemberResponse])
def list_members(mission_id: int, service: Service, page: PageNumber = 1, per_page: PageSize = 10):
    return service.list_members(mission_id, page, per_page)


@router.get("/missions/{mission_id}/members/{member_id}", response_model=MemberResponse)
def get_member(mission_id: int, member_id: int, service: Service):
    return service.get_member(mission_id, member_id)


@router.patch("/missions/{mission_id}/members/{member_id}", response_model=MemberResponse)
def update_member(mission_id: int, member_id: int, payload: MemberPatch, service: Service):
    return service.update_member(mission_id, member_id, payload)


@router.delete("/missions/{mission_id}/members/{member_id}", status_code=204)
def delete_member(mission_id: int, member_id: int, service: Service):
    service.delete_member(mission_id, member_id)
    return Response(status_code=204)


@router.get("/exams", response_model=Page[ExamResponse])
def list_exams(service: Service, page: PageNumber = 1, per_page: PageSize = 10, search: str | None = Query(default=None, max_length=200), exam_type_id: int | None = Query(default=None, gt=0), is_active: bool | None = None):
    return service.list_exams(page, per_page, search, exam_type_id, is_active)


@router.post("/exams", response_model=ExamResponse, status_code=201)
def create_exam(payload: ExamCreate, service: Service):
    return service.create_exam(payload)


@router.get("/exams/{exam_id}", response_model=ExamResponse)
def get_exam(exam_id: int, service: Service):
    return service.get_exam(exam_id)


@router.patch("/exams/{exam_id}", response_model=ExamResponse)
def update_exam(exam_id: int, payload: ExamUpdate, service: Service):
    return service.update_exam(exam_id, payload)


@router.delete("/exams/{exam_id}", status_code=204)
def delete_exam(exam_id: int, service: Service):
    service.delete_exam(exam_id)
    return Response(status_code=204)


@router.post("/exam-types", response_model=ExamTypeResponse, status_code=201)
def create_exam_type(payload: ExamTypeCreate, service: Service):
    return service.create_exam_type(payload)


@router.get("/exam-types", response_model=Page[ExamTypeResponse])
def list_exam_types(service: Service, page: PageNumber = 1, per_page: PageSize = 10):
    return service.list_exam_types(page, per_page)


@router.get("/exam-types/{exam_type_id}", response_model=ExamTypeResponse)
def get_exam_type(exam_type_id: int, service: Service):
    return service.get_exam_type(exam_type_id)


@router.patch("/exam-types/{exam_type_id}", response_model=ExamTypeResponse)
def update_exam_type(exam_type_id: int, payload: ExamTypePatch, service: Service):
    return service.update_exam_type(exam_type_id, payload)


@router.delete("/exam-types/{exam_type_id}", status_code=204)
def delete_exam_type(exam_type_id: int, service: Service):
    service.delete_exam_type(exam_type_id)
    return Response(status_code=204)


@router.post("/missions/{mission_id}/exam-requirements", response_model=RequirementResponse, status_code=201)
def create_requirement(mission_id: int, payload: RequirementCreate, service: Service):
    return service.create_requirement(mission_id, payload)


@router.get("/missions/{mission_id}/exam-requirements", response_model=Page[RequirementResponse])
def list_requirements(mission_id: int, service: Service, page: PageNumber = 1, per_page: PageSize = 10):
    return service.list_requirements(mission_id, page, per_page)


@router.get("/missions/{mission_id}/exam-requirements/{requirement_id}", response_model=RequirementResponse)
def get_requirement(mission_id: int, requirement_id: int, service: Service):
    return service.get_requirement(mission_id, requirement_id)


@router.patch("/missions/{mission_id}/exam-requirements/{requirement_id}", response_model=RequirementResponse)
def update_requirement(mission_id: int, requirement_id: int, payload: RequirementPatch, service: Service):
    return service.update_requirement(mission_id, requirement_id, payload)


@router.delete("/missions/{mission_id}/exam-requirements/{requirement_id}", status_code=204)
def delete_requirement(mission_id: int, requirement_id: int, service: Service):
    service.delete_requirement(mission_id, requirement_id)
    return Response(status_code=204)


@router.get("/missions/{mission_id}/astronauts/{member_id}/exams", response_model=Page[ChecklistResponse])
def get_checklist(mission_id: int, member_id: int, service: Service, page: PageNumber = 1, per_page: PageSize = 10):
    return service.checklist(mission_id, member_id, page, per_page)


@router.get("/missions/{mission_id}/astronaut-exams/{exam_id}", response_model=ChecklistResponse)
def get_astronaut_exam(mission_id: int, exam_id: int, service: Service):
    return service.get_astronaut_exam(mission_id, exam_id)


@router.patch("/missions/{mission_id}/astronaut-exams/{exam_id}", response_model=ChecklistResponse)
def update_schedule(mission_id: int, exam_id: int, payload: SchedulePatch, service: Service):
    return service.schedule(mission_id, exam_id, payload)


@router.post("/missions/{mission_id}/astronaut-exams/{exam_id}/results", response_model=ResultResponse, status_code=201)
def create_result(mission_id: int, exam_id: int, payload: ResultCreate, service: Service):
    return service.create_result(mission_id, exam_id, payload)


@router.get("/missions/{mission_id}/astronaut-exams/{exam_id}/results", response_model=Page[ResultResponse])
def list_results(mission_id: int, exam_id: int, service: Service, page: PageNumber = 1, per_page: PageSize = 10):
    return service.list_results(mission_id, exam_id, page, per_page)


@router.get("/missions/{mission_id}/exam-results/{result_id}", response_model=ResultResponse)
def get_result(mission_id: int, result_id: int, service: Service):
    return service.get_result(mission_id, result_id)


@router.patch("/missions/{mission_id}/exam-results/{result_id}", response_model=ResultResponse)
def update_result(mission_id: int, result_id: int, payload: ResultPatch, service: Service):
    return service.update_result(mission_id, result_id, payload)


@router.post("/missions/{mission_id}/exam-results/{result_id}/reviews", response_model=ReviewResponse, status_code=201)
def create_review(mission_id: int, result_id: int, payload: ReviewCreate, service: Service):
    return service.create_review(mission_id, result_id, payload)


@router.get("/missions/{mission_id}/exam-results/{result_id}/reviews", response_model=Page[ReviewResponse])
def list_reviews(mission_id: int, result_id: int, service: Service, page: PageNumber = 1, per_page: PageSize = 10):
    return service.list_reviews(mission_id, result_id, page, per_page)


@router.get("/missions/{mission_id}/astronauts/{member_id}/exam-types/{exam_type_id}/latest-accepted", response_model=AcceptedExamResponse)
def latest_accepted(mission_id: int, member_id: int, exam_type_id: int, service: Service, exam_id: int | None = Query(default=None, gt=0)):
    return service.latest_accepted(mission_id, member_id, exam_type_id, exam_id)


@router.get("/missions/{mission_id}/operations")
def mission_operations(mission_id: int, service: Service):
    return service.operations(mission_id)
