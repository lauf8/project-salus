from fastapi import HTTPException
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlmodel import select

from app.models.preflight import Mission
from app.models.spacecraft import Spacecraft, SpacecraftModule
from app.schemas.spacecraft import ModuleResponse, SpacecraftResponse
from app.services.preflight_service import PreflightService, transactional


class SpacecraftService(PreflightService):
    def get_spacecraft(self, spacecraft_id, lock=False):
        statement = select(Spacecraft).where(Spacecraft.id == spacecraft_id)
        if lock:
            statement = statement.with_for_update()
        row = self.session.exec(statement).first()
        if row is None:
            raise HTTPException(404, 'Spacecraft not found')
        return row

    def get_module(self, spacecraft_id, module_id, lock=False):
        statement = select(SpacecraftModule).where(SpacecraftModule.id == module_id, SpacecraftModule.spacecraft_id == spacecraft_id)
        if lock:
            statement = statement.with_for_update()
        row = self.session.exec(statement).first()
        if row is None:
            raise HTTPException(404, 'Module not found in this spacecraft')
        return row

    def list_spacecraft(self, search, page, per_page):
        statement = select(Spacecraft)
        if search:
            statement = statement.where(or_(*(column.icontains(search.strip(), autoescape=True) for column in (Spacecraft.name, Spacecraft.model, Spacecraft.manufacturer))))
        return self._page(statement.order_by(Spacecraft.name, Spacecraft.id), page, per_page)

    def list_modules(self, spacecraft_id, search, page, per_page):
        self.get_spacecraft(spacecraft_id)
        statement = select(SpacecraftModule).where(SpacecraftModule.spacecraft_id == spacecraft_id)
        if search:
            statement = statement.where(or_(SpacecraftModule.name.icontains(search.strip(), autoescape=True), SpacecraftModule.code.icontains(search.strip(), autoescape=True)))
        return self._page(statement.order_by(SpacecraftModule.name, SpacecraftModule.id), page, per_page)

    @transactional
    def save_spacecraft(self, payload, spacecraft_id=None):
        self._catalog_writer()
        values = payload.model_dump(mode='json', exclude_unset=True)
        row = self.get_spacecraft(spacecraft_id, lock=True) if spacecraft_id is not None else Spacecraft(**values)
        capacity = values.get('maximum_crew_capacity')
        if spacecraft_id is not None and capacity is not None:
            missions = self.session.exec(select(Mission).where(Mission.spacecraft_id == spacecraft_id, Mission.status != 'completed')).all()
            if any(max(mission.crew_size or 0, self._crew_count(mission.id)) > capacity for mission in missions):
                raise HTTPException(409, 'Maximum crew capacity cannot be lower than the crew of an open mission')
        for key, value in values.items():
            setattr(row, key, value)
        self.session.add(row)
        self.session.flush()
        return SpacecraftResponse.model_validate(row)

    @transactional
    def save_module(self, spacecraft_id, payload, module_id=None):
        self._catalog_writer()
        self.get_spacecraft(spacecraft_id, lock=True)
        values = payload.model_dump(mode='json', exclude_unset=True)
        row = self.get_module(spacecraft_id, module_id, lock=True) if module_id is not None else SpacecraftModule(spacecraft_id=spacecraft_id, **values)
        for key, value in values.items():
            setattr(row, key, value)
        self.session.add(row)
        try:
            self.session.flush()
        except IntegrityError as exc:
            raise HTTPException(409, 'A module with this code already exists in this spacecraft') from exc
        return ModuleResponse.model_validate(row)

    @transactional
    def delete_spacecraft(self, spacecraft_id):
        self._catalog_writer()
        row = self.get_spacecraft(spacecraft_id, lock=True)
        if self.session.exec(select(SpacecraftModule.id).where(SpacecraftModule.spacecraft_id == spacecraft_id).limit(1)).first() is not None:
            raise HTTPException(409, 'Delete all linked modules before deleting this spacecraft')
        if self.session.exec(select(Mission.id).where(Mission.spacecraft_id == spacecraft_id).limit(1)).first() is not None:
            raise HTTPException(409, 'This spacecraft has linked missions and cannot be deleted')
        self.session.delete(row)
        try:
            self.session.flush()
        except IntegrityError as exc:
            raise HTTPException(409, 'This spacecraft has linked modules and cannot be deleted') from exc

    @transactional
    def delete_module(self, spacecraft_id, module_id):
        self._catalog_writer()
        self.get_spacecraft(spacecraft_id, lock=True)
        self.session.delete(self.get_module(spacecraft_id, module_id, lock=True))
        self.session.flush()
