from datetime import datetime
from typing import Literal

from app.schemas.preflight import OutputModel


class NotificationResponse(OutputModel):
    id: int
    mission_id: int
    mission_name: str
    astronaut_id: int
    astronaut_name: str
    alert_id: int
    indicator: str
    severity: Literal['critical'] = 'critical'
    alert_status: Literal['open', 'acknowledged', 'resolved']
    title: str
    message: str
    created_at: datetime
    collected_at: datetime
    read_at: datetime | None
    verification_required: bool


class NotificationSummary(OutputModel):
    unread_count: int
    pending_count: int


class NotificationReadAllResponse(OutputModel):
    marked_count: int
