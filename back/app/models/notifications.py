from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Index, Text, UniqueConstraint
from sqlmodel import Field, SQLModel


class HealthNotification(SQLModel, table=True):
    __tablename__ = 'health_notifications'
    __table_args__ = (
        UniqueConstraint('recipient_user_id', 'mission_id', 'alert_id', name='uq_health_notification_recipient_mission_alert'),
        Index('ix_health_notification_inbox', 'recipient_user_id', 'read_at', 'created_at', 'id'),
    )

    id: int | None = Field(default=None, primary_key=True)
    recipient_user_id: int = Field(foreign_key='users.id')
    mission_id: int = Field(foreign_key='missions.id')
    alert_id: int = Field(foreign_key='health_alerts.id')
    observation_id: int = Field(foreign_key='health_observations.id')
    title: str
    message: str = Field(sa_type=Text)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), sa_column=Column(DateTime(timezone=True), nullable=False))
    read_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))
