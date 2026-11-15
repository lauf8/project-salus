from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlmodel import select

from app.models.medicines import ActiveIngredient, CrewMemberAllergy, Medicine, MedicineActiveIngredient
from app.models.user import User
from app.schemas.medicines import MedicineResponse, NamedResponse
from app.services.health_service import HealthService
from app.services.preflight_service import PreflightService, transactional


class MedicineService(PreflightService):
    def ingredients(self, ids):
        rows = self.session.exec(select(ActiveIngredient).where(ActiveIngredient.id.in_(ids)).order_by(ActiveIngredient.name, ActiveIngredient.id).with_for_update()).all() if ids else []
        if len(rows) != len(ids):
            raise HTTPException(422, 'One or more active ingredients do not exist')
        return rows

    def composition(self, medicine_id):
        return self.session.exec(select(ActiveIngredient).join(MedicineActiveIngredient, MedicineActiveIngredient.active_ingredient_id == ActiveIngredient.id).where(MedicineActiveIngredient.medicine_id == medicine_id).order_by(ActiveIngredient.name, ActiveIngredient.id)).all()

    def medicine_response(self, medicine):
        return MedicineResponse(id=medicine.id, name=medicine.name, main_indications=medicine.main_indications, active_ingredients=[NamedResponse.model_validate(row) for row in self.composition(medicine.id)])

    def list_catalog(self, model, search, page, per_page):
        statement = select(model)
        if search:
            statement = statement.where(model.name.icontains(search, autoescape=True))
        result = self._page(statement.order_by(model.name, model.id), page, per_page)
        if model is Medicine:
            result['data'] = [self.medicine_response(row) for row in result['data']]
        return result

    def get_medicine(self, medicine_id):
        return self.medicine_response(self._get(Medicine, medicine_id))

    def replace_composition(self, medicine_id, ids):
        self.ingredients(ids)
        for row in self.session.exec(select(MedicineActiveIngredient).where(MedicineActiveIngredient.medicine_id == medicine_id)).all():
            self.session.delete(row)
        self.session.flush()
        for ingredient_id in ids:
            self.session.add(MedicineActiveIngredient(medicine_id=medicine_id, active_ingredient_id=ingredient_id))
        self.session.flush()

    @transactional
    def save_medicine(self, payload, medicine_id=None):
        self._catalog_writer()
        medicine = self.session.exec(select(Medicine).where(Medicine.id == medicine_id).with_for_update()).first() if medicine_id else Medicine(name=payload.name)
        if medicine is None:
            raise HTTPException(404, 'Medication not found')
        if payload.name is not None:
            medicine.name = payload.name
        if 'main_indications' in payload.model_fields_set:
            medicine.main_indications = payload.main_indications or None
        self.session.add(medicine)
        self.session.flush()
        if payload.active_ingredient_ids is not None:
            self.replace_composition(medicine.id, payload.active_ingredient_ids)
        return self.medicine_response(medicine)

    @transactional
    def save_ingredient(self, payload, ingredient_id=None):
        self._catalog_writer()
        row = self._get(ActiveIngredient, ingredient_id) if ingredient_id else ActiveIngredient(name=payload.name)
        row.name = payload.name
        self.session.add(row)
        self.session.flush()
        return NamedResponse.model_validate(row)

    @transactional
    def delete_catalog(self, model, record_id):
        self._catalog_writer()
        row = self._get(model, record_id)
        if model is ActiveIngredient:
            for link in (MedicineActiveIngredient, CrewMemberAllergy):
                if self.session.exec(select(link).where(link.active_ingredient_id == record_id)).first():
                    raise HTTPException(409, 'This active ingredient is linked to medications or allergies and cannot be deleted')
        else:
            for link in self.session.exec(select(MedicineActiveIngredient).where(MedicineActiveIngredient.medicine_id == record_id)).all():
                self.session.delete(link)
            self.session.flush()
        self.session.delete(row)
        try:
            self.session.flush()
        except IntegrityError as exc:
            raise HTTPException(409, 'The record is in use and cannot be deleted') from exc

    def allergy_response(self, crew_member_id, can_edit):
        target = self._get(User, crew_member_id)
        ingredients = self.session.exec(select(ActiveIngredient).join(CrewMemberAllergy, CrewMemberAllergy.active_ingredient_id == ActiveIngredient.id).where(CrewMemberAllergy.crew_member_id == crew_member_id).order_by(ActiveIngredient.name, ActiveIngredient.id)).all()
        return {'crew_member_id': crew_member_id, 'allergy_screening_completed': target.allergy_screening_completed, 'active_ingredients': ingredients, 'can_edit': can_edit}

    def get_allergies(self, crew_member_id, mission_id):
        can_edit = HealthService(self.session, self.user).authorize(crew_member_id, mission_id)
        return self.allergy_response(crew_member_id, can_edit)

    @transactional
    def update_allergies(self, crew_member_id, mission_id, payload):
        if not HealthService(self.session, self.user).authorize(crew_member_id, mission_id):
            raise HTTPException(403, 'Only the mission flight surgeon can edit allergies')
        target = self.session.exec(select(User).where(User.id == crew_member_id).with_for_update()).one()
        self.ingredients(payload.active_ingredient_ids)
        for row in self.session.exec(select(CrewMemberAllergy).where(CrewMemberAllergy.crew_member_id == crew_member_id)).all():
            self.session.delete(row)
        self.session.flush()
        for ingredient_id in payload.active_ingredient_ids:
            self.session.add(CrewMemberAllergy(crew_member_id=crew_member_id, active_ingredient_id=ingredient_id))
        target.allergy_screening_completed = payload.allergy_screening_completed
        self.session.add(target)
        self.session.flush()
        return self.allergy_response(crew_member_id, True)
