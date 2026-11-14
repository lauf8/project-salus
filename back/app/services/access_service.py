from fastapi import HTTPException
from sqlmodel import select

from app.core.roles import ROLE_PROFILES
from app.models.access import AccessAuditEvent
from app.models.preflight import MissionMember
from app.models.user import User
from app.schemas.users import UserResponse
from app.services.preflight_service import PreflightService, transactional


class AccessService(PreflightService):
    def require_global_admin(self):
        if not self.user.is_global_admin:
            raise HTTPException(403, "A global administrator is required")

    @transactional
    def update_profiles(self, user_id, payload):
        self.require_global_admin()
        administrators = self.session.exec(select(User).where(User.is_global_admin == True).order_by(User.id).with_for_update()).all()
        target = self._get(User, user_id)
        if target.is_global_admin and (not payload.is_global_admin or not payload.is_active):
            if not any(user.id != target.id and user.is_active for user in administrators):
                raise HTTPException(409, "The last active global administrator cannot be removed or disabled")
        memberships = self.session.exec(select(MissionMember).where(MissionMember.user_id == target.id)).all()
        for member in memberships:
            required = ROLE_PROFILES.get(member.role)
            if required and not getattr(payload, required):
                raise HTTPException(409, "Remove or reassign the mission membership before removing its required profile")
            if member.role == "flight_surgeon" and target.is_physician and not payload.is_physician:
                raise HTTPException(409, "Reassign clinical mission responsibilities before removing the physician profile")
        changed = [name for name, value in payload.model_dump().items() if getattr(target, name) != value]
        target.sqlmodel_update(payload.model_dump())
        self.session.add(target)
        self.session.add(AccessAuditEvent(actor_user_id=self.user.id, resource_type="users", resource_id=target.id, action="update_profiles", changed_fields=changed))
        self.session.flush()
        return UserResponse.model_validate(target)

    def audit_history(self, page, per_page):
        self.require_global_admin()
        return self._page(select(AccessAuditEvent).order_by(AccessAuditEvent.id.desc()), page, per_page)
