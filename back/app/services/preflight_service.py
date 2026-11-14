from datetime import datetime, timedelta, timezone
from functools import wraps

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import func, update
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.models.preflight import (
    AstronautExam, ExamDefinition, ExamResult, ExamResultReview, ExamType, Mission,
    MissionExamRequirement, MissionMember,
)
from app.models.nutrition import MealLog
from app.models.user import User
from app.models.spacecraft import Spacecraft
from app.services.exam_fields import snapshot, validate_result
from app.schemas.preflight import (
    AcceptedExamResponse, ChecklistResponse, MissionCreate, ResultResponse, ReviewResponse,
)


ALL_ROLES = {"astronaut", "flight_surgeon", "mission_admin"}


def transactional(method):
    @wraps(method)
    def wrapped(self, *args, **kwargs):
        try:
            result = method(self, *args, **kwargs)
            self.session.commit()
            return result
        except IntegrityError as exc:
            self.session.rollback()
            raise HTTPException(409, "A operação conflita com registros existentes ou com um histórico protegido") from exc
        except Exception:
            self.session.rollback()
            raise
    return wrapped


class PreflightService:
    def __init__(self, session: Session, user: User):
        self.session = session
        self.user = user

    def _require_physician(self):
        if not self.user.is_physician:
            raise HTTPException(403, "Somente médicos podem alterar exames")

    def _get(self, model, record_id):
        record = self.session.get(model, record_id)
        if record is None:
            raise HTTPException(404, "Record not found")
        return record

    def _access(self, mission_id, roles=ALL_ROLES, lock=False):
        statement = select(Mission).where(Mission.id == mission_id)
        if lock:
            statement = statement.with_for_update()
        mission = self.session.exec(statement).first()
        member = self.session.exec(select(MissionMember).where(
            MissionMember.mission_id == mission_id, MissionMember.user_id == self.user.id,
        )).first()
        if mission is None or member is None:
            raise HTTPException(404, "Mission not found")
        if member.role not in roles:
            raise HTTPException(403, "This mission role cannot perform this operation")
        return mission, member

    def _scoped(self, model, record_id, mission_id):
        record = self._get(model, record_id)
        if record.mission_id != mission_id:
            raise HTTPException(404, "Record not found in this mission")
        return record

    def _catalog_writer(self):
        self._require_physician()
        member = self.session.exec(select(MissionMember).where(
            MissionMember.user_id == self.user.id, MissionMember.role.in_(["mission_admin", "flight_surgeon"]),
        )).first()
        if member is None:
            raise HTTPException(403, "A physician assigned as mission administrator or flight surgeon is required")

    def _clinical_access(self, mission_id, exam, write=False):
        roles = {"flight_surgeon"} if write else {"astronaut", "flight_surgeon"}
        mission, actor = self._access(mission_id, roles, lock=write)
        if actor.role == "flight_surgeon":
            self._require_physician()
        if exam.mission_id != mission_id:
            raise HTTPException(404, "Exam not found in this mission")
        if actor.role == "astronaut" and exam.mission_member_id != actor.id:
            raise HTTPException(403, "Astronauts may only access their own preflight records")
        return mission, actor

    def _page(self, statement, page, per_page):
        total = self.session.exec(select(func.count()).select_from(statement.order_by(None).subquery())).one()
        return {
            "data": self.session.exec(statement.offset((page - 1) * per_page).limit(per_page)).all(),
            "pagination": {
                "page": page, "per_page": per_page, "total": total,
                "total_pages": (total + per_page - 1) // per_page,
                "has_next": page * per_page < total, "has_previous": page > 1,
            },
        }

    def _latest_result(self, exam_id):
        return self.session.exec(select(ExamResult).where(
            ExamResult.astronaut_exam_id == exam_id,
        ).order_by(ExamResult.performed_at.desc(), ExamResult.recorded_at.desc(), ExamResult.id.desc())).first()

    def _latest_review(self, result_id):
        return self.session.exec(select(ExamResultReview).where(
            ExamResultReview.exam_result_id == result_id,
        ).order_by(ExamResultReview.reviewed_at.desc(), ExamResultReview.id.desc())).first()

    def _state(self, exam):
        result = self._latest_result(exam.id)
        if result is None:
            return "scheduled" if exam.scheduled_at else "pending"
        review = self._latest_review(result.id)
        if review is None:
            return "awaiting_review"
        return "completed" if review.decision == "accepted" else "repeat_requested"

    def _due(self, mission, requirement):
        try:
            return mission.planned_launch_at - timedelta(days=requirement.due_days_before_launch)
        except OverflowError as exc:
            raise HTTPException(422, "The requirement produces an out-of-range deadline") from exc

    def _recalculate_open(self, mission, exams):
        for exam in exams:
            self._require_physician()
            if self._state(exam) != "completed":
                requirement = self._get(MissionExamRequirement, exam.requirement_id)
                exam.due_at = self._due(mission, requirement)
                self.session.add(exam)

    def _generate(self, mission):
        members = self.session.exec(select(MissionMember).where(
            MissionMember.mission_id == mission.id, MissionMember.role == "astronaut",
        )).all()
        requirements = self.session.exec(select(MissionExamRequirement).where(
            MissionExamRequirement.mission_id == mission.id,
        )).all()
        existing = set(self.session.exec(select(
            AstronautExam.mission_member_id, AstronautExam.requirement_id,
        ).where(AstronautExam.mission_id == mission.id)).all())
        for member in members:
            for requirement in requirements:
                if (member.id, requirement.id) not in existing:
                    self._require_physician()
                    self.session.add(AstronautExam(
                        mission_id=mission.id, mission_member_id=member.id,
                        requirement_id=requirement.id, due_at=self._due(mission, requirement),
                        definition_snapshot=self._definition_snapshot(requirement.exam_definition_id),
                    ))
        self.session.flush()

    def _checklist_row(self, exam):
        requirement = self._get(MissionExamRequirement, exam.requirement_id)
        state = self._state(exam)
        return ChecklistResponse(
            **exam.model_dump(), exam_type_id=requirement.exam_type_id,
            exam_definition_id=requirement.exam_definition_id,
            exam_name=(exam.definition_snapshot or {}).get("name"),
            is_required=requirement.is_required, state=state,
            is_overdue=exam.due_at < datetime.now(timezone.utc) and state != "completed",
        )

    def _remove_empty_exams(self, exams):
        for exam in exams:
            self._require_physician()
            if self._latest_result(exam.id) is not None:
                raise HTTPException(409, "Exams with results must retain their membership and requirement")
            self.session.delete(exam)
        self.session.flush()

    def _validate_performed_at(self, mission, performed_at):
        if performed_at > datetime.now(timezone.utc):
            raise HTTPException(422, "A performed exam cannot have a future timestamp")
        if mission.started_at and performed_at > mission.started_at:
            raise HTTPException(422, "Preflight exams must be performed before the mission starts")

    def _crew_count(self, mission_id):
        return self.session.exec(select(func.count()).select_from(MissionMember).where(
            MissionMember.mission_id == mission_id, MissionMember.role == "astronaut",
        )).one()

    def _validate_crew(self, spacecraft_id, crew_size, assigned_count):
        if crew_size is not None and assigned_count > crew_size:
            raise HTTPException(409, "The planned crew size has been reached. Increase it before adding another astronaut.")
        if spacecraft_id is not None:
            spacecraft = self.session.exec(select(Spacecraft).where(Spacecraft.id == spacecraft_id).with_for_update()).first()
            if spacecraft is None:
                raise HTTPException(404, "Spacecraft not found")
            capacity = spacecraft.maximum_crew_capacity
            if capacity is not None and max(crew_size or 0, assigned_count) > capacity:
                raise HTTPException(409, "The crew exceeds the spacecraft maximum crew capacity.")

    def _validate_astronaut(self, user_id):
        user = self._get(User, user_id)
        if not user.is_astronaut:
            raise HTTPException(422, "Only users with an astronaut profile can join the flight crew")
        return user

    def _reserve_spacecraft(self, spacecraft_id):
        if spacecraft_id is None:
            return
        result = self.session.execute(update(Spacecraft).where(
            Spacecraft.id == spacecraft_id, Spacecraft.status == "available",
        ).values(status="in_use"))
        if result.rowcount != 1:
            if self.session.get(Spacecraft, spacecraft_id) is None:
                raise HTTPException(404, "Spacecraft not found")
            raise HTTPException(409, "Spacecraft is no longer available. Select another spacecraft.")

    def _release_spacecraft(self, spacecraft_id):
        if spacecraft_id is not None:
            self.session.execute(update(Spacecraft).where(
                Spacecraft.id == spacecraft_id,
            ).values(status="available"))

    @transactional
    def create_mission(self, payload):
        self._validate_crew(payload.spacecraft_id, payload.crew_size, len(payload.astronaut_ids))
        for user_id in payload.astronaut_ids:
            self._validate_astronaut(user_id)
            if user_id == self.user.id:
                raise HTTPException(409, "The mission administrator already has a mission membership")
        self._reserve_spacecraft(payload.spacecraft_id)
        mission = Mission(**payload.model_dump(exclude={"astronaut_ids"}))
        mission.status = "completed" if mission.ended_at else "in_progress" if mission.started_at else "planned"
        if mission.status == "completed":
            self._release_spacecraft(mission.spacecraft_id)
        self.session.add(mission)
        self.session.flush()
        self.session.add(MissionMember(
            mission_id=mission.id, user_id=self.user.id, role="mission_admin",
        ))
        for user_id in payload.astronaut_ids:
            self.session.add(MissionMember(mission_id=mission.id, user_id=user_id, role="astronaut"))
        self.session.flush()
        return mission

    def list_missions(self, page, per_page):
        return self._page(select(Mission).join(MissionMember).where(
            MissionMember.user_id == self.user.id,
        ).order_by(Mission.id), page, per_page)

    def get_mission(self, mission_id):
        return self._access(mission_id)[0]

    @transactional
    def update_mission(self, mission_id, payload):
        mission, _ = self._access(mission_id, {"mission_admin"}, lock=True)
        values = payload.model_dump(exclude_unset=True)
        current_values = {key: getattr(mission, key) for key in MissionCreate.model_fields if key != "astronaut_ids"}
        for key, value in current_values.items():
            if isinstance(value, datetime) and value.tzinfo is None:
                current_values[key] = value.replace(tzinfo=timezone.utc)
        try:
            MissionCreate.model_validate({
                **current_values,
                **{key: value for key, value in values.items() if key in MissionCreate.model_fields},
            })
        except ValidationError as exc:
            raise HTTPException(422, "Invalid mission dates") from exc
        old_spacecraft_id = mission.spacecraft_id
        old_open = mission.status != "completed"
        new_spacecraft_id = values.get("spacecraft_id", old_spacecraft_id)
        new_status = values.get("status", mission.status)
        if "ended_at" in values and "status" not in values:
            if values["ended_at"] is not None:
                new_status = "completed"
            elif mission.status == "completed" and mission.ended_at is not None:
                new_status = "in_progress" if values.get("started_at", mission.started_at) else "planned"
        elif "started_at" in values and new_status != "completed" and "status" not in values:
            new_status = "in_progress" if values["started_at"] else "planned"
        if new_status != "completed" and values.get("ended_at", mission.ended_at) is not None:
            values["ended_at"] = None
        new_open = new_status != "completed"
        if "crew_size" in values or "spacecraft_id" in values or (not old_open and new_open):
            self._validate_crew(new_spacecraft_id, values.get("crew_size", mission.crew_size), self._crew_count(mission_id))
        if new_spacecraft_id is not None:
            if new_open and (not old_open or new_spacecraft_id != old_spacecraft_id):
                self._reserve_spacecraft(new_spacecraft_id)
            else:
                self._get(Spacecraft, new_spacecraft_id)
        if old_open and (not new_open or new_spacecraft_id != old_spacecraft_id):
            self._release_spacecraft(old_spacecraft_id)
        values["status"] = new_status
        for key, value in values.items():
            setattr(mission, key, value)
        self.session.add(mission)
        self.session.flush()
        if "planned_launch_at" in values:
            self._recalculate_open(mission, self.session.exec(select(AstronautExam).where(
                AstronautExam.mission_id == mission_id,
            )).all())
        return mission

    @transactional
    def delete_mission(self, mission_id):
        mission, actor = self._access(mission_id, {"mission_admin"}, lock=True)
        members = self.session.exec(select(MissionMember).where(MissionMember.mission_id == mission_id)).all()
        requirements = self.session.exec(select(MissionExamRequirement).where(
            MissionExamRequirement.mission_id == mission_id,
        )).all()
        if len(members) != 1 or actor.id != members[0].id or requirements:
            raise HTTPException(409, "Remove mission configuration before deleting an empty mission")
        if mission.status != "completed":
            self._release_spacecraft(mission.spacecraft_id)
        self.session.delete(actor)
        self.session.flush()
        self.session.delete(mission)

    def list_members(self, mission_id, page, per_page):
        self._access(mission_id)
        return self._page(select(MissionMember).where(
            MissionMember.mission_id == mission_id,
        ).order_by(MissionMember.id), page, per_page)

    def get_member(self, mission_id, member_id):
        self._access(mission_id)
        return self._scoped(MissionMember, member_id, mission_id)

    @transactional
    def create_member(self, mission_id, payload):
        mission, _ = self._access(mission_id, {"mission_admin"}, lock=True)
        self._get(User, payload.user_id)
        existing = self.session.exec(select(MissionMember).where(
            MissionMember.mission_id == mission_id, MissionMember.user_id == payload.user_id,
        )).first()
        if existing:
            if existing.role != payload.role:
                raise HTTPException(409, "User already has another mission role; update the membership")
            self._generate(mission)
            return existing
        if payload.role == "astronaut":
            self._validate_astronaut(payload.user_id)
            self._validate_crew(mission.spacecraft_id, mission.crew_size, self._crew_count(mission_id) + 1)
        member = MissionMember(mission_id=mission_id, **payload.model_dump())
        self.session.add(member)
        self.session.flush()
        self._generate(mission)
        return member

    def _protect_last_admin(self, member, next_role):
        if member.role == "mission_admin" and next_role != "mission_admin":
            others = self.session.exec(select(MissionMember).where(
                MissionMember.mission_id == member.mission_id,
                MissionMember.role == "mission_admin", MissionMember.id != member.id,
            )).first()
            if others is None:
                raise HTTPException(409, "A mission must retain at least one administrator")

    @transactional
    def update_member(self, mission_id, member_id, payload):
        mission, _ = self._access(mission_id, {"mission_admin"}, lock=True)
        member = self._scoped(MissionMember, member_id, mission_id)
        if payload.role == "astronaut" and member.role != "astronaut":
            self._validate_astronaut(member.user_id)
            self._validate_crew(mission.spacecraft_id, mission.crew_size, self._crew_count(mission_id) + 1)
        self._protect_last_admin(member, payload.role)
        if member.role != payload.role:
            if self.session.exec(select(MealLog.id).where(MealLog.mission_member_id == member.id).limit(1)).first() is not None:
                raise HTTPException(409, "A crew membership with meal history cannot change role")
            if self.session.exec(select(ExamResultReview).where(
                ExamResultReview.reviewer_member_id == member.id,
            )).first():
                raise HTTPException(409, "A clinical reviewer's historical membership cannot change role")
            self._remove_empty_exams(self.session.exec(select(AstronautExam).where(
                AstronautExam.mission_member_id == member.id,
            )).all())
        member.role = payload.role
        self.session.add(member)
        self.session.flush()
        self._generate(mission)
        return member

    @transactional
    def delete_member(self, mission_id, member_id):
        self._access(mission_id, {"mission_admin"}, lock=True)
        member = self._scoped(MissionMember, member_id, mission_id)
        self._protect_last_admin(member, None)
        if self.session.exec(select(MealLog.id).where(MealLog.mission_member_id == member.id).limit(1)).first() is not None:
            raise HTTPException(409, "A crew membership with meal history cannot be deleted")
        self._remove_empty_exams(self.session.exec(select(AstronautExam).where(
            AstronautExam.mission_member_id == member.id,
        )).all())
        self.session.delete(member)

    def list_exam_types(self, page, per_page):
        return self._page(select(ExamType).order_by(ExamType.id), page, per_page)

    def get_exam_type(self, exam_type_id):
        return self._get(ExamType, exam_type_id)

    @transactional
    def create_exam_type(self, payload):
        self._catalog_writer()
        exam_type = ExamType(**payload.model_dump())
        self.session.add(exam_type)
        self.session.flush()
        return exam_type

    @transactional
    def update_exam_type(self, exam_type_id, payload):
        self._catalog_writer()
        exam_type = self._get(ExamType, exam_type_id)
        values = payload.model_dump(exclude_unset=True)
        if "code" in values and values["code"] != exam_type.code:
            if self.session.exec(select(MissionExamRequirement).where(
                MissionExamRequirement.exam_type_id == exam_type.id,
            )).first():
                raise HTTPException(409, "An exam type code in use is immutable")
        for key, value in values.items():
            setattr(exam_type, key, value)
        self.session.add(exam_type)
        self.session.flush()
        return exam_type

    @transactional
    def delete_exam_type(self, exam_type_id):
        self._catalog_writer()
        self.session.delete(self._get(ExamType, exam_type_id))

    def _definition_snapshot(self, definition_id):
        return snapshot(self._get(ExamDefinition, definition_id)) if definition_id else None

    def _validate_definition(self, definition_id, type_id):
        exam_type = self._get(ExamType, type_id)
        if not exam_type.is_active:
            raise HTTPException(409, "O tipo de exame está inativo")
        if definition_id:
            definition = self._get(ExamDefinition, definition_id)
            if definition.exam_type_id != type_id:
                raise HTTPException(422, "O exame não pertence ao tipo informado")
            if not definition.is_active:
                raise HTTPException(409, "O exame está inativo")

    def list_exams(self, page, per_page, search=None, exam_type_id=None, is_active=None):
        statement = select(ExamDefinition)
        if search:
            statement = statement.where(ExamDefinition.name.ilike("%" + search.replace("%", "\\%").replace("_", "\\_") + "%"))
        if exam_type_id is not None:
            statement = statement.where(ExamDefinition.exam_type_id == exam_type_id)
        if is_active is not None:
            statement = statement.where(ExamDefinition.is_active == is_active)
        return self._page(statement.order_by(ExamDefinition.name, ExamDefinition.id), page, per_page)

    def get_exam(self, exam_id):
        return self._get(ExamDefinition, exam_id)

    @transactional
    def create_exam(self, payload):
        self._catalog_writer()
        self._validate_definition(None, payload.exam_type_id)
        exam = ExamDefinition(**payload.model_dump(mode="json"))
        self.session.add(exam)
        self.session.flush()
        return exam

    @transactional
    def update_exam(self, exam_id, payload):
        self._catalog_writer()
        exam = self.session.exec(select(ExamDefinition).where(ExamDefinition.id == exam_id).with_for_update()).first()
        if exam is None:
            raise HTTPException(404, "Exame não encontrado")
        if exam.revision != payload.expected_revision:
            raise HTTPException(409, "Este exame foi alterado. Atualize a página antes de salvar")
        linked = self.session.exec(select(MissionExamRequirement).where(MissionExamRequirement.exam_definition_id == exam_id)).first()
        if linked and (payload.exam_type_id != exam.exam_type_id or payload.code != exam.code):
            raise HTTPException(409, "O código e o tipo de um exame em uso não podem ser alterados")
        self._get(ExamType, payload.exam_type_id)
        for key, value in payload.model_dump(mode="json", exclude={"expected_revision"}).items():
            setattr(exam, key, value)
        exam.revision += 1
        self.session.add(exam)
        self.session.flush()
        return exam

    @transactional
    def delete_exam(self, exam_id):
        self._catalog_writer()
        exam = self._get(ExamDefinition, exam_id)
        if self.session.exec(select(MissionExamRequirement).where(MissionExamRequirement.exam_definition_id == exam_id)).first():
            raise HTTPException(409, "Este exame está vinculado a uma missão. Inative-o para preservar o histórico")
        self.session.delete(exam)

    def list_requirements(self, mission_id, page, per_page):
        self._access(mission_id)
        return self._page(select(MissionExamRequirement).where(
            MissionExamRequirement.mission_id == mission_id,
        ).order_by(MissionExamRequirement.id), page, per_page)

    def get_requirement(self, mission_id, requirement_id):
        self._access(mission_id)
        return self._scoped(MissionExamRequirement, requirement_id, mission_id)

    @transactional
    def create_requirement(self, mission_id, payload):
        self._require_physician()
        mission, _ = self._access(mission_id, {"mission_admin", "flight_surgeon"}, lock=True)
        self._validate_definition(payload.exam_definition_id, payload.exam_type_id)
        existing = self.session.exec(select(MissionExamRequirement).where(
            MissionExamRequirement.mission_id == mission_id,
            MissionExamRequirement.exam_type_id == payload.exam_type_id,
            MissionExamRequirement.exam_definition_id == payload.exam_definition_id,
        )).first()
        if existing:
            if any(getattr(existing, key) != value for key, value in payload.model_dump().items()):
                raise HTTPException(409, "Requirement already exists; update it explicitly")
            self._generate(mission)
            return existing
        requirement = MissionExamRequirement(mission_id=mission_id, **payload.model_dump())
        self.session.add(requirement)
        self.session.flush()
        self._generate(mission)
        return requirement

    @transactional
    def update_requirement(self, mission_id, requirement_id, payload):
        self._require_physician()
        mission, _ = self._access(mission_id, {"mission_admin", "flight_surgeon"}, lock=True)
        requirement = self._scoped(MissionExamRequirement, requirement_id, mission_id)
        exams = self.session.exec(select(AstronautExam).where(
            AstronautExam.requirement_id == requirement.id,
        )).all()
        values = payload.model_dump(exclude_unset=True)
        changed_definition = any(key in values and values[key] != getattr(requirement, key) for key in ("exam_type_id", "exam_definition_id"))
        if changed_definition:
            self._validate_definition(values.get("exam_definition_id", requirement.exam_definition_id), values.get("exam_type_id", requirement.exam_type_id))
            if any(self._latest_result(exam.id) is not None for exam in exams):
                raise HTTPException(409, "Um requisito com resultados não pode trocar de exame")
            for exam in exams:
                exam.definition_snapshot = self._definition_snapshot(values.get("exam_definition_id", requirement.exam_definition_id))
                self.session.add(exam)
        for key, value in values.items():
            setattr(requirement, key, value)
        self.session.add(requirement)
        self.session.flush()
        self._generate(mission)
        self._recalculate_open(mission, exams)
        return requirement

    @transactional
    def delete_requirement(self, mission_id, requirement_id):
        self._require_physician()
        self._access(mission_id, {"mission_admin", "flight_surgeon"}, lock=True)
        requirement = self._scoped(MissionExamRequirement, requirement_id, mission_id)
        self._remove_empty_exams(self.session.exec(select(AstronautExam).where(
            AstronautExam.requirement_id == requirement.id,
        )).all())
        self.session.delete(requirement)

    def checklist(self, mission_id, member_id, page, per_page):
        _, actor = self._access(mission_id)
        member = self._scoped(MissionMember, member_id, mission_id)
        if member.role != "astronaut":
            raise HTTPException(422, "A checklist requires an astronaut membership")
        if actor.role == "astronaut" and actor.id != member_id:
            raise HTTPException(403, "Astronauts may only access their own checklist")
        result = self._page(select(AstronautExam).where(
            AstronautExam.mission_id == mission_id, AstronautExam.mission_member_id == member_id,
        ).order_by(AstronautExam.id), page, per_page)
        result["data"] = [self._checklist_row(exam) for exam in result["data"]]
        return result

    def get_astronaut_exam(self, mission_id, exam_id):
        _, actor = self._access(mission_id)
        exam = self._scoped(AstronautExam, exam_id, mission_id)
        if actor.role == "astronaut" and exam.mission_member_id != actor.id:
            raise HTTPException(403, "Astronauts may only access their own checklist")
        return self._checklist_row(exam)

    @transactional
    def schedule(self, mission_id, exam_id, payload):
        self._require_physician()
        self._access(mission_id, {"mission_admin", "flight_surgeon"}, lock=True)
        exam = self._scoped(AstronautExam, exam_id, mission_id)
        if self._state(exam) == "completed":
            raise HTTPException(409, "A completed exam cannot be rescheduled")
        exam.scheduled_at = payload.scheduled_at
        self.session.add(exam)
        self.session.flush()
        return self._checklist_row(exam)

    def list_results(self, mission_id, exam_id, page, per_page):
        self._access(mission_id)
        exam = self._scoped(AstronautExam, exam_id, mission_id)
        self._clinical_access(mission_id, exam)
        return self._page(select(ExamResult).where(ExamResult.astronaut_exam_id == exam_id).order_by(
            ExamResult.performed_at.desc(), ExamResult.recorded_at.desc(), ExamResult.id.desc(),
        ), page, per_page)

    def _result_access(self, mission_id, result_id, write=False):
        self._access(mission_id, {"flight_surgeon"} if write else {"astronaut", "flight_surgeon"}, lock=write)
        result = self._get(ExamResult, result_id)
        exam = self._scoped(AstronautExam, result.astronaut_exam_id, mission_id)
        mission, actor = self._clinical_access(mission_id, exam, write=write)
        return result, exam, mission, actor

    def get_result(self, mission_id, result_id):
        return self._result_access(mission_id, result_id)[0]

    @transactional
    def create_result(self, mission_id, exam_id, payload):
        self._require_physician()
        self._access(mission_id, {"flight_surgeon"}, lock=True)
        exam = self._scoped(AstronautExam, exam_id, mission_id)
        mission, _ = self._clinical_access(mission_id, exam, write=True)
        self._validate_performed_at(mission, payload.performed_at)
        validate_result(exam.definition_snapshot, payload.structured_values, payload.reference_ranges, payload.collected_at, payload.performed_at)
        result = ExamResult(
            astronaut_exam_id=exam.id, recorded_by_user_id=self.user.id, exam_snapshot=exam.definition_snapshot, **payload.model_dump(),
        )
        self.session.add(result)
        self.session.flush()
        self._recalculate_open(mission, [exam])
        return result

    @transactional
    def update_result(self, mission_id, result_id, payload):
        self._require_physician()
        result, exam, mission, _ = self._result_access(mission_id, result_id, write=True)
        if self._latest_review(result.id) is not None:
            raise HTTPException(409, "Reviewed results are immutable; record a new realization")
        values = payload.model_dump(exclude_unset=True)
        self._validate_performed_at(mission, values.get("performed_at", result.performed_at))
        validate_result(result.exam_snapshot, values.get("structured_values", result.structured_values), values.get("reference_ranges", result.reference_ranges), values.get("collected_at", result.collected_at), values.get("performed_at", result.performed_at))
        for key, value in values.items():
            setattr(result, key, value)
        self.session.add(result)
        self.session.flush()
        self._recalculate_open(mission, [exam])
        return result

    def list_reviews(self, mission_id, result_id, page, per_page):
        self._result_access(mission_id, result_id)
        return self._page(select(ExamResultReview).where(
            ExamResultReview.exam_result_id == result_id,
        ).order_by(ExamResultReview.reviewed_at.desc(), ExamResultReview.id.desc()), page, per_page)

    @transactional
    def create_review(self, mission_id, result_id, payload):
        self._require_physician()
        result, exam, mission, actor = self._result_access(mission_id, result_id, write=True)
        review = ExamResultReview(
            exam_result_id=result.id, reviewer_member_id=actor.id, **payload.model_dump(),
        )
        self.session.add(review)
        self.session.flush()
        self._recalculate_open(mission, [exam])
        return review

    def latest_accepted(self, mission_id, member_id, exam_type_id, exam_id=None):
        self._access(mission_id, {"astronaut", "flight_surgeon"})
        member = self._scoped(MissionMember, member_id, mission_id)
        if member.role != "astronaut":
            raise HTTPException(422, "A preflight record requires an astronaut membership")
        statement = select(AstronautExam).join(MissionExamRequirement, AstronautExam.requirement_id == MissionExamRequirement.id).where(
            AstronautExam.mission_id == mission_id, AstronautExam.mission_member_id == member_id,
            MissionExamRequirement.exam_type_id == exam_type_id,
        )
        if exam_id is not None:
            statement = statement.where(AstronautExam.id == exam_id)
        matches = self.session.exec(statement).all()
        if len(matches) > 1:
            raise HTTPException(409, "Informe o exame para consultar o resultado aceito deste tipo")
        exam = matches[0] if matches else None
        if exam is None:
            raise HTTPException(404, "Astronaut exam not found")
        self._clinical_access(mission_id, exam)
        results = self.session.exec(select(ExamResult).where(
            ExamResult.astronaut_exam_id == exam.id,
        ).order_by(ExamResult.performed_at.desc(), ExamResult.recorded_at.desc(), ExamResult.id.desc())).all()
        latest = results[0] if results else None
        accepted = None
        for result in results:
            review = self._latest_review(result.id)
            if review and review.decision == "accepted":
                accepted = result
                break
        latest_review = self._latest_review(latest.id) if latest else None
        state = self._state(exam)
        return AcceptedExamResponse(
            latest_accepted_result=ResultResponse.model_validate(accepted) if accepted else None,
            latest_result=ResultResponse.model_validate(latest) if latest else None,
            latest_review=ReviewResponse.model_validate(latest_review) if latest_review else None,
            latest_result_state=state,
            newer_result_requires_review=bool(latest and (accepted is None or latest.id != accepted.id)),
        )
