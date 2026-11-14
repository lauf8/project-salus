from datetime import datetime

from sqlalchemy import Column, DateTime, JSON
from sqlmodel import Field, SQLModel

from app.models.preflight import utc_now


class AccessAuditEvent(SQLModel, table=True):
    __tablename__ = "access_audit_events"

    id: int | None = Field(default=None, primary_key=True)
    actor_user_id: int = Field(foreign_key="users.id", index=True)
    resource_type: str
    resource_id: int
    action: str
    changed_fields: list[str] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    created_at: datetime = Field(default_factory=utc_now, sa_column=Column(DateTime(timezone=True), nullable=False))
