from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlmodel import select

from app.models.health import HealthObservation
from app.models.health_alerts import HealthAlertSettings
from app.models.mental_health import MentalHealthAuditEvent, MentalHealthCheckIn, PsychologyContactRequest, PsychologyFollowUp
from app.models.preflight import Mission, MissionMember, utc_now
from app.services.preflight_service import transactional


class MentalHealthService:
    def __init__(self, session, user):
        self.session = session
        self.user = user

    def scope(self, mission_id, member_id=None, psychologist=False):
        mission = self.session.get(Mission, mission_id)
        actor = self.session.exec(select(MissionMember).where(MissionMember.mission_id == mission_id, MissionMember.user_id == self.user.id)).first()
        if mission is None or actor is None:
            raise HTTPException(404, "Mission not found")
        if actor.role == "psychologist" and not self.user.is_psychologist:
            raise HTTPException(403, "A psychologist profile is required")
        if actor.role != "psychologist" and (psychologist or actor.role != "astronaut"):
            raise HTTPException(403, "Mental health access requires an authorized psychologist or the astronaut")
        target = self.session.get(MissionMember, member_id) if member_id else actor
        if target is None or target.mission_id != mission_id or target.role != "astronaut":
            raise HTTPException(404, "Astronaut not found")
        if actor.role == "astronaut" and actor.id != target.id:
            raise HTTPException(403, "Access is restricted to your own records")
        return mission, actor, target

    def clock(self, mission):
        settings = self.session.get(HealthAlertSettings, mission.id)
        zone = ZoneInfo(settings.timezone if settings else "UTC")
        return zone, datetime.now(zone).date()

    def audit(self, record, action):
        self.session.add(MentalHealthAuditEvent(mission_id=record.mission_id, actor_user_id=self.user.id, resource_type=record.__tablename__, resource_id=record.id, action=action))

    def scoped_record(self, model, record_id, target):
        record = self.session.get(model, record_id)
        if record is None or record.mission_id != target.mission_id or record.mission_member_id != target.id:
            raise HTTPException(404, "Record not found")
        return record

    def period(self, mission, start, end):
        zone, today = self.clock(mission)
        start = start or today - timedelta(days=27)
        end = end or today
        if start > end or (end - start).days > 366:
            raise HTTPException(422, "Select an ordered period of up to 367 days")
        return zone, today, start, end

    @transactional
    def overview(self, mission_id, member_id, start=None, end=None):
        return self._overview(mission_id, member_id, start, end)

    def _overview(self, mission_id, member_id, start=None, end=None):
        mission, actor, target = self.scope(mission_id, member_id)
        zone, today, start, end = self.period(mission, start, end)
        check_ins = self.session.exec(select(MentalHealthCheckIn).where(MentalHealthCheckIn.mission_member_id == target.id, MentalHealthCheckIn.check_in_date >= start, MentalHealthCheckIn.check_in_date <= end).order_by(MentalHealthCheckIn.check_in_date)).all()
        requests = self.session.exec(select(PsychologyContactRequest).where(PsychologyContactRequest.mission_member_id == target.id).order_by(PsychologyContactRequest.created_at.desc())).all()
        sessions = self.session.exec(select(PsychologyFollowUp).where(PsychologyFollowUp.mission_member_id == target.id).order_by(PsychologyFollowUp.session_at.desc())).all()
        sleep = self.session.exec(select(HealthObservation).where(HealthObservation.astronaut_id == target.user_id, HealthObservation.mission_id == mission_id, HealthObservation.indicator.in_(["sleep_duration", "sleep_quality"]), HealthObservation.collected_at >= datetime.combine(start, time.min, zone), HealthObservation.collected_at < datetime.combine(end + timedelta(days=1), time.min, zone)).order_by(HealthObservation.collected_at)).all()
        anchor = (mission.started_at or mission.planned_launch_at).replace(tzinfo=timezone.utc) if (mission.started_at or mission.planned_launch_at).tzinfo is None else (mission.started_at or mission.planned_launch_at)
        anchor = anchor.astimezone(zone).date()
        weeks = []
        week_start = anchor + timedelta(days=max(0, (start - anchor).days // 7) * 7)
        while week_start <= end:
            week_end = week_start + timedelta(days=6)
            matching = [s.id for s in sessions if s.review_period_start <= week_end and s.review_period_end >= week_start]
            weeks.append(dict(start=week_start, end=week_end, week_number=(week_start-anchor).days // 7 + 1, session_ids=matching))
            week_start += timedelta(days=7)
        self.audit(target, "read_mental_health")
        return dict(today=today, timezone=str(zone), check_ins=[c.model_dump() for c in check_ins], requests=[r.model_dump() for r in requests], sessions=[self.session_output(s, actor) for s in sessions], weeks=weeks, days=[dict(date=start+timedelta(days=n), check_in_id=next((c.id for c in check_ins if c.check_in_date == start+timedelta(days=n)), None)) for n in range((end-start).days+1)], sleep_observations=[dict(id=s.id, indicator=s.indicator, value=s.value, unit=s.unit, collected_at=s.collected_at) for s in sleep])

    def session_output(self, record, actor):
        if actor.role == "psychologist":
            return record.model_dump()
        return dict(id=record.id, session_at=record.session_at, review_period_start=record.review_period_start, review_period_end=record.review_period_end, agreed_actions=record.agreed_actions if record.share_agreed_actions else None, next_follow_up_on=record.next_follow_up_on if record.share_next_follow_up else None)

    @transactional
    def roster(self, mission_id):
        actor = self.session.exec(select(MissionMember).where(MissionMember.mission_id == mission_id, MissionMember.user_id == self.user.id, MissionMember.role == "psychologist")).first()
        if actor is None or not self.user.is_psychologist:
            raise HTTPException(403, "An assigned psychologist is required")
        targets = self.session.exec(select(MissionMember).where(MissionMember.mission_id == mission_id, MissionMember.role == "astronaut")).all()
        result = []
        for target in targets:
            overview = self._overview(mission_id, target.id)
            result.append(dict(member_id=target.id, user_id=target.user_id, pending_requests=[r for r in overview['requests'] if r['status'] == 'pending'], weeks=overview['weeks']))
        return result

    @transactional
    def save_check_in(self, mission_id, member_id, check_in_date, payload):
        mission, actor, target = self.scope(mission_id, member_id)
        if actor.id != target.id or actor.role != "astronaut":
            raise HTTPException(403, "Only the astronaut may write their daily check-in")
        _, today = self.clock(mission)
        if check_in_date > today:
            raise HTTPException(422, "A check-in cannot be dated in the future")
        self.session.exec(select(MissionMember).where(MissionMember.id == target.id).with_for_update()).one()
        record = self.session.exec(select(MentalHealthCheckIn).where(MentalHealthCheckIn.mission_member_id == target.id, MentalHealthCheckIn.check_in_date == check_in_date)).first()
        action = "update" if record else "create"
        if record is None:
            record = MentalHealthCheckIn(mission_id=mission_id, mission_member_id=target.id, check_in_date=check_in_date, updated_by_user_id=self.user.id, **payload.model_dump())
        else:
            record.sqlmodel_update(payload.model_dump())
        record.updated_at = utc_now()
        record.updated_by_user_id = self.user.id
        self.session.add(record)
        self.session.flush()
        self.audit(record, action)
        return record.model_dump()

    @transactional
    def request_contact(self, mission_id, member_id):
        _, actor, target = self.scope(mission_id, member_id)
        if actor.id != target.id or actor.role != "astronaut":
            raise HTTPException(403, "Only the astronaut may request contact")
        self.session.exec(select(MissionMember).where(MissionMember.id == target.id).with_for_update()).one()
        record = self.session.exec(select(PsychologyContactRequest).where(PsychologyContactRequest.mission_member_id == target.id, PsychologyContactRequest.status == "pending")).first()
        if record is None:
            record = PsychologyContactRequest(mission_id=mission_id, mission_member_id=target.id, author_user_id=self.user.id, updated_by_user_id=self.user.id)
            self.session.add(record)
            self.session.flush()
            self.audit(record, "create")
        return record.model_dump()

    @transactional
    def save_session(self, mission_id, member_id, payload, record_id=None):
        _, _, target = self.scope(mission_id, member_id, psychologist=True)
        record = self.scoped_record(PsychologyFollowUp, record_id, target) if record_id else None
        if record and record.psychologist_user_id != self.user.id:
            raise HTTPException(403, "Only the responsible psychologist may edit this session")
        if record and record.contact_request_id != payload.contact_request_id:
            raise HTTPException(409, "A session's request link cannot be changed")
        contact = None
        if payload.contact_request_id:
            contact = self.scoped_record(PsychologyContactRequest, payload.contact_request_id, target)
            self.session.refresh(contact, with_for_update=True)
            if contact.status != "pending" and (record is None or record.contact_request_id != contact.id):
                raise HTTPException(409, "This request has already been fulfilled")
        action = "update" if record else "create"
        if record:
            record.sqlmodel_update(payload.model_dump())
        else:
            record = PsychologyFollowUp(mission_id=mission_id, mission_member_id=target.id, psychologist_user_id=self.user.id, updated_by_user_id=self.user.id, **payload.model_dump())
        record.updated_at = utc_now()
        record.updated_by_user_id = self.user.id
        self.session.add(record)
        self.session.flush()
        if contact and contact.status == "pending":
            contact.status = "fulfilled"
            contact.updated_at = utc_now()
            contact.updated_by_user_id = self.user.id
            self.session.add(contact)
            self.audit(contact, "fulfill")
        self.audit(record, action)
        return record.model_dump()
