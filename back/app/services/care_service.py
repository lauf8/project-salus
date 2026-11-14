from datetime import datetime, timezone

from fastapi import HTTPException
from sqlmodel import select

from app.models.access import AccessAuditEvent
from app.models.care import NursingRecord, NutritionPlan
from app.models.health import HealthObservation
from app.models.medicines import ActiveIngredient, CrewMemberAllergy
from app.models.preflight import MissionMember, utc_now
from app.services.preflight_service import PreflightService, transactional


class CareService(PreflightService):
    def scope(self, mission_id, member_id, kind, write=False):
        professional = "nutritionist" if kind == "nutrition" else "nurse"
        _, actor = self._access(mission_id, {professional} if write else {professional, "flight_surgeon", "astronaut"}, lock=write)
        target = self._scoped(MissionMember, member_id, mission_id)
        if target.role != "astronaut":
            raise HTTPException(404, "Astronaut not found")
        if actor.role == "astronaut" and actor.id != target.id:
            raise HTTPException(403, "Only your own care records are accessible")
        if actor.role == "flight_surgeon":
            self._require_physician()
        if actor.role == professional and not getattr(self.user, "is_" + professional):
            raise HTTPException(403, "The assigned professional profile is required")
        return target

    def audit_care(self, record, action):
        self.session.add(AccessAuditEvent(actor_user_id=self.user.id, resource_type=record.__tablename__, resource_id=record.id, action=action, changed_fields=[]))

    @transactional
    def history(self, mission_id, member_id, kind):
        self.scope(mission_id, member_id, kind)
        model = NutritionPlan if kind == "nutrition" else NursingRecord
        records = self.session.exec(select(model).where(model.mission_id == mission_id, model.mission_member_id == member_id).order_by(model.created_at.desc(), model.id.desc())).all()
        self.session.add(AccessAuditEvent(actor_user_id=self.user.id, resource_type=model.__tablename__, resource_id=member_id, action="read_care_history", changed_fields=[]))
        return [record.model_dump() for record in records]

    @transactional
    def save(self, mission_id, member_id, kind, payload, record_id=None):
        self.scope(mission_id, member_id, kind, write=True)
        model = NutritionPlan if kind == "nutrition" else NursingRecord
        record = self._scoped(model, record_id, mission_id) if record_id else None
        if record and record.mission_member_id != member_id:
            raise HTTPException(404, "Record not found for this astronaut")
        if record and record.author_user_id != self.user.id:
            raise HTTPException(403, "Only the author may correct this record")
        if kind == "nursing" and payload.observed_at > datetime.now(timezone.utc):
            raise HTTPException(422, "Care cannot be recorded in the future")
        action = "update_care_record" if record else "create_care_record"
        if record:
            record.sqlmodel_update(payload.model_dump())
        else:
            record = model(mission_id=mission_id, mission_member_id=member_id, author_user_id=self.user.id, updated_by_user_id=self.user.id, **payload.model_dump())
        record.updated_by_user_id = self.user.id
        record.updated_at = utc_now()
        self.session.add(record)
        self.session.flush()
        self.audit_care(record, action)
        return record.model_dump()

    @transactional
    def nutrition_context(self, mission_id, member_id):
        target = self.scope(mission_id, member_id, "nutrition")
        ingredients = self.session.exec(select(ActiveIngredient).join(CrewMemberAllergy, CrewMemberAllergy.active_ingredient_id == ActiveIngredient.id).where(CrewMemberAllergy.crew_member_id == target.user_id).order_by(ActiveIngredient.name)).all()
        glucose = self.session.exec(select(HealthObservation).where(HealthObservation.mission_id == mission_id, HealthObservation.astronaut_id == target.user_id, HealthObservation.indicator == "blood_glucose").order_by(HealthObservation.collected_at.desc()).limit(1)).first()
        self.session.add(AccessAuditEvent(actor_user_id=self.user.id, resource_type="nutrition_context", resource_id=target.id, action="read_nutrition_context", changed_fields=[]))
        return {"allergies": [{"id": row.id, "name": row.name} for row in ingredients], "latest_blood_glucose": {"value": glucose.value, "unit": glucose.unit, "collected_at": glucose.collected_at, "glucose_context": glucose.glucose_context} if glucose else None}
