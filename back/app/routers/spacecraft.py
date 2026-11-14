from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from sqlmodel import Session

from app.database import get_session
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.schemas.preflight import Page
from app.schemas.spacecraft import ModuleCreate, ModulePatch, ModuleResponse, SpacecraftCreate, SpacecraftPatch, SpacecraftResponse
from app.services.spacecraft_service import SpacecraftService


router = APIRouter(prefix='/spacecraft', tags=['spacecraft'])


def get_spacecraft_service(session: Session = Depends(get_session), user: User = Depends(get_current_user)):
    return SpacecraftService(session, user)


Service = Annotated[SpacecraftService, Depends(get_spacecraft_service)]


@router.get('', response_model=Page[SpacecraftResponse])
def list_spacecraft(service: Service, search: str | None = None, page: int = Query(1, ge=1), per_page: int = Query(20, ge=1, le=100)):
    return service.list_spacecraft(search, page, per_page)


@router.post('', response_model=SpacecraftResponse, status_code=201)
def create_spacecraft(payload: SpacecraftCreate, service: Service):
    return service.save_spacecraft(payload)


@router.get('/{spacecraft_id}', response_model=SpacecraftResponse)
def get_spacecraft(spacecraft_id: int, service: Service):
    return service.get_spacecraft(spacecraft_id)


@router.patch('/{spacecraft_id}', response_model=SpacecraftResponse)
def update_spacecraft(spacecraft_id: int, payload: SpacecraftPatch, service: Service):
    return service.save_spacecraft(payload, spacecraft_id)


@router.delete('/{spacecraft_id}', status_code=204)
def delete_spacecraft(spacecraft_id: int, service: Service):
    service.delete_spacecraft(spacecraft_id)
    return Response(status_code=204)


@router.get('/{spacecraft_id}/modules', response_model=Page[ModuleResponse])
def list_modules(spacecraft_id: int, service: Service, search: str | None = None, page: int = Query(1, ge=1), per_page: int = Query(20, ge=1, le=100)):
    return service.list_modules(spacecraft_id, search, page, per_page)


@router.post('/{spacecraft_id}/modules', response_model=ModuleResponse, status_code=201)
def create_module(spacecraft_id: int, payload: ModuleCreate, service: Service):
    return service.save_module(spacecraft_id, payload)


@router.get('/{spacecraft_id}/modules/{module_id}', response_model=ModuleResponse)
def get_module(spacecraft_id: int, module_id: int, service: Service):
    return service.get_module(spacecraft_id, module_id)


@router.patch('/{spacecraft_id}/modules/{module_id}', response_model=ModuleResponse)
def update_module(spacecraft_id: int, module_id: int, payload: ModulePatch, service: Service):
    return service.save_module(spacecraft_id, payload, module_id)


@router.delete('/{spacecraft_id}/modules/{module_id}', status_code=204)
def delete_module(spacecraft_id: int, module_id: int, service: Service):
    service.delete_module(spacecraft_id, module_id)
    return Response(status_code=204)
