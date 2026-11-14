import os
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.database import engine, get_session
from app.main import app
from app.models.preflight import AstronautExam, ExamResult, MissionExamRequirement, MissionMember
from app.models.user import User
from app.services.preflight_service import PreflightService
from tests.public_identity import public_headers


pytestmark = pytest.mark.skipif(
    os.getenv("PREFLIGHT_POSTGRES_TESTS") != "1",
    reason="Requires an isolated migrated PostgreSQL database",
)


def as_time(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


@pytest.fixture
def api():
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    people = {}
    for name in ("admin", "doctor", "astronaut", "outsider", "second_astronaut"):
        user = User(name=f"Fictional {name}", email=f"{name}@fictional.test", hashed_password="fictional", is_physician=name in {"admin", "doctor", "outsider"}, is_astronaut=name in {"astronaut", "second_astronaut"})
        session.add(user)
        session.flush()
        people[name] = user.id
    session.commit()

    def get_test_session():
        yield session

    app.dependency_overrides[get_session] = get_test_session
    with TestClient(app) as client:
        def call(actor, method, path, payload=None, expected=200):
            headers = public_headers(session, people[actor]) if actor else {}
            response = client.request(method, f"/v1{path}", json=payload, headers=headers)
            assert response.status_code == expected, response.text
            return response.json() if response.content else None
        yield call, session, people, client
    app.dependency_overrides.clear()
    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def case(api):
    call, session, people, client = api
    launch = datetime.now(timezone.utc) + timedelta(days=90)
    mission = call("admin", "POST", "/missions", {
        "name": "Fictional mission", "planned_launch_at": launch.isoformat(),
    }, 201)
    mid = mission["id"]
    exam_type = call("admin", "POST", "/exam-types", {
        "code": "visual_assessment", "name": "Fictional visual assessment",
    }, 201)
    req_payload = {"exam_type_id": exam_type["id"], "due_days_before_launch": 30}
    requirement = call("admin", "POST", f"/missions/{mid}/exam-requirements", req_payload, 201)
    astronaut = call("admin", "POST", f"/missions/{mid}/members", {
        "user_id": people["astronaut"], "role": "astronaut",
    }, 201)
    doctor = call("admin", "POST", f"/missions/{mid}/members", {
        "user_id": people["doctor"], "role": "flight_surgeon",
    }, 201)
    checklist = call("astronaut", "GET", f"/missions/{mid}/astronauts/{astronaut['id']}/exams")
    return dict(
        call=call, session=session, people=people, client=client, mid=mid, launch=launch,
        exam_type=exam_type, req_payload=req_payload, requirement=requirement,
        astronaut=astronaut, doctor=doctor, exam=checklist["data"][0],
        base=f"/missions/{mid}",
    )


def create_result(case, days_ago=10):
    return case["call"]("doctor", "POST", f"{case['base']}/astronaut-exams/{case['exam']['id']}/results", {
        "performed_at": (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat(),
        "summary": "Fictional visual examination",
    }, 201)


def review(case, result, decision):
    return case["call"]("doctor", "POST", f"{case['base']}/exam-results/{result['id']}/reviews", {
        "decision": decision, "notes": "Fictional review notes",
    }, 201)


def status(case):
    return case["call"]("astronaut", "GET", f"{case['base']}/astronaut-exams/{case['exam']['id']}")


def accepted(case):
    return case["call"]("astronaut", "GET", (
        f"{case['base']}/astronauts/{case['astronaut']['id']}/exam-types/{case['exam_type']['id']}/latest-accepted"
    ))


def test_repeat_and_accept_workflow_preserves_history(case):
    call, base = case["call"], case["base"]
    assert status(case)["state"] == "pending"
    assert not status(case)["is_overdue"]
    scheduled = (datetime.now(timezone.utc) + timedelta(days=5)).isoformat()
    call("admin", "PATCH", f"{base}/astronaut-exams/{case['exam']['id']}", {"scheduled_at": scheduled})
    assert status(case)["state"] == "scheduled"
    first = create_result(case)
    assert first["recorded_by_user_id"] == case["people"]["doctor"]
    assert status(case)["state"] == "awaiting_review"
    call("doctor", "PATCH", f"{base}/exam-results/{first['id']}", {"summary": "Fictional corrected summary"})
    first_review = review(case, first, "repeat_requested")
    assert first_review["reviewer_member_id"] == case["doctor"]["id"]
    assert status(case)["state"] == "repeat_requested"
    call("doctor", "PATCH", f"{base}/exam-results/{first['id']}", {"summary": "Not allowed"}, 409)
    second = create_result(case, days_ago=5)
    assert status(case)["state"] == "awaiting_review"
    review(case, second, "accepted")
    assert status(case)["state"] == "completed"
    assert not status(case)["is_overdue"]
    result = accepted(case)
    assert result["latest_accepted_result"]["id"] == second["id"]
    assert not result["newer_result_requires_review"]
    history = call("astronaut", "GET", f"{base}/astronaut-exams/{case['exam']['id']}/results")
    assert history["pagination"]["total"] == 2
    assert {row["id"] for row in history["data"]} == {first["id"], second["id"]}
    assert call("astronaut", "GET", f"{base}/exam-results/{first['id']}/reviews")["pagination"]["total"] == 1
    assert "summary" not in status(case)
    call("doctor", "DELETE", f"{base}/exam-results/{second['id']}", expected=405)
    call("doctor", "DELETE", f"{base}/exam-results/{second['id']}/reviews", expected=405)
    call("admin", "DELETE", f"{base}/members/{case['astronaut']['id']}", expected=409)
    call("admin", "DELETE", f"{base}/members/{case['doctor']['id']}", expected=409)
    call("admin", "DELETE", f"{base}/exam-requirements/{case['requirement']['id']}", expected=409)
    call("admin", "DELETE", f"/exam-types/{case['exam_type']['id']}", expected=409)


def test_checklist_generation_is_idempotent_and_handles_both_orders(case):
    call, base = case["call"], case["base"]
    member_payload = {"user_id": case["people"]["astronaut"], "role": "astronaut"}
    repeated_member = call("admin", "POST", f"{base}/members", member_payload, 201)
    assert repeated_member["id"] == case["astronaut"]["id"]
    repeated_req = call("admin", "POST", f"{base}/exam-requirements", case["req_payload"], 201)
    assert repeated_req["id"] == case["requirement"]["id"]
    another_type = call("admin", "POST", "/exam-types", {"code": "ecg", "name": "Fictional ECG"}, 201)
    call("admin", "POST", f"{base}/exam-requirements", {
        "exam_type_id": another_type["id"], "due_days_before_launch": 10,
    }, 201)
    checklist = call("astronaut", "GET", f"{base}/astronauts/{case['astronaut']['id']}/exams")
    assert checklist["pagination"]["total"] == 2
    rows = checklist["data"]
    assert len({(row["mission_member_id"], row["requirement_id"]) for row in rows}) == 2
    call("admin", "PATCH", f"{base}/members/{case['astronaut']['id']}", {"role": "astronaut"})
    assert call("astronaut", "GET", f"{base}/astronauts/{case['astronaut']['id']}/exams")["pagination"]["total"] == 2


def test_deadlines_recalculate_open_items_only(case):
    call, base = case["call"], case["base"]
    old_due = as_time(case["exam"]["due_at"])
    assert old_due == case["launch"] - timedelta(days=30)
    later_launch = case["launch"] + timedelta(days=20)
    call("admin", "PATCH", base, {"planned_launch_at": later_launch.isoformat()})
    assert as_time(status(case)["due_at"]) == later_launch - timedelta(days=30)
    result = create_result(case)
    review(case, result, "accepted")
    completed_due = status(case)["due_at"]
    call("admin", "PATCH", base, {"planned_launch_at": (later_launch + timedelta(days=10)).isoformat()})
    assert status(case)["due_at"] == completed_due
    review(case, result, "repeat_requested")
    assert as_time(status(case)["due_at"]) == later_launch + timedelta(days=10) - timedelta(days=30)
    call("admin", "PATCH", f"{base}/exam-requirements/{case['requirement']['id']}", {"due_days_before_launch": 15})
    assert as_time(status(case)["due_at"]) == later_launch + timedelta(days=10) - timedelta(days=15)
    call("admin", "PATCH", base, {"planned_launch_at": (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()})
    assert status(case)["is_overdue"]
    history = call("doctor", "GET", f"{base}/exam-results/{result['id']}")
    assert history["performed_at"] == result["performed_at"]
    assert history["recorded_at"] == result["recorded_at"]


def test_latest_accepted_uses_latest_review_and_flags_newer_pending_result(case):
    first = create_result(case, 10)
    review(case, first, "accepted")
    second = create_result(case, 5)
    result = accepted(case)
    assert result["latest_accepted_result"]["id"] == first["id"]
    assert result["latest_result"]["id"] == second["id"]
    assert result["latest_result_state"] == "awaiting_review"
    assert result["newer_result_requires_review"]
    review(case, second, "accepted")
    assert accepted(case)["latest_accepted_result"]["id"] == second["id"]
    review(case, second, "repeat_requested")
    result = accepted(case)
    assert result["latest_accepted_result"]["id"] == first["id"]
    assert result["latest_result_state"] == "repeat_requested"
    assert result["newer_result_requires_review"]
    review(case, first, "repeat_requested")
    assert accepted(case)["latest_accepted_result"] is None
    assert case["call"]("doctor", "GET", f"{case['base']}/exam-results/{second['id']}/reviews")["pagination"]["total"] == 2


def test_backdated_result_does_not_replace_latest_realization(case):
    latest = create_result(case, 5)
    review(case, latest, "accepted")
    create_result(case, 15)
    assert accepted(case)["latest_result"]["id"] == latest["id"]
    assert status(case)["state"] == "completed"


def test_clinical_authorization_and_mission_isolation(case):
    call, base = case["call"], case["base"]
    first = create_result(case)
    clinical_path = f"{base}/exam-results/{first['id']}"
    call("admin", "GET", clinical_path, expected=403)
    call("admin", "GET", f"{clinical_path}/reviews", expected=403)
    call("outsider", "GET", clinical_path, expected=404)
    call("outsider", "GET", base, expected=404)
    other = call("admin", "POST", f"{base}/members", {
        "user_id": case["people"]["second_astronaut"], "role": "astronaut",
    }, 201)
    call("second_astronaut", "GET", clinical_path, expected=403)
    call("second_astronaut", "GET", f"{base}/astronauts/{case['astronaut']['id']}/exams", expected=403)
    call("second_astronaut", "GET", f"{base}/astronauts/{other['id']}/exams")
    call("astronaut", "POST", f"{base}/astronaut-exams/{case['exam']['id']}/results", {
        "performed_at": first["performed_at"], "summary": "Fictional",
    }, 403)
    call("astronaut", "POST", f"{clinical_path}/reviews", {"decision": "accepted"}, 403)
    call("admin", "POST", f"{clinical_path}/reviews", {"decision": "accepted"}, 403)
    call("doctor", "PATCH", base, {"name": "Not allowed"}, 403)
    call("doctor", "POST", "/exam-types", {"code": "physician_catalog", "name": "Fictional"}, 201)
    other_mission = call("outsider", "POST", "/missions", {
        "name": "Another fictional mission", "planned_launch_at": case["launch"].isoformat(),
    }, 201)
    call("outsider", "POST", f"/missions/{other_mission['id']}/members", {
        "user_id": case["people"]["astronaut"], "role": "flight_surgeon",
    }, 201)
    call("astronaut", "POST", f"{clinical_path}/reviews", {"decision": "accepted"}, 403)
    call("doctor", "GET", f"/missions/{other_mission['id']}/exam-results/{first['id']}", expected=404)
    missions = call("doctor", "GET", "/missions")
    assert [row["id"] for row in missions["data"]] == [case["mid"]]
    call("doctor", "POST", f"{clinical_path}/reviews", {
        "decision": "accepted", "reviewer_member_id": case["astronaut"]["id"],
    }, 422)
    # Sem cabeçalhos, a API usa um administrador global (USER_ACCESS.md), não exige token.
    call(None, "GET", "/missions", expected=200)


def test_configuration_crud_and_pagination(case):
    call, base = case["call"], case["base"]
    assert call("admin", "GET", f"{base}/members?page=1&per_page=1")["pagination"]["has_next"]
    call("admin", "GET", f"{base}/members?per_page=101", expected=422)
    call("admin", "GET", f"{base}/exam-requirements/{case['requirement']['id']}")
    call("admin", "GET", f"{base}/members/{case['astronaut']['id']}")
    call("admin", "GET", f"/exam-types/{case['exam_type']['id']}")
    call("admin", "PATCH", f"/exam-types/{case['exam_type']['id']}", {"is_active": False})
    assert not call("astronaut", "GET", f"/exam-types/{case['exam_type']['id']}")["is_active"]
    call("admin", "PATCH", f"/exam-types/{case['exam_type']['id']}", {"code": "changed"}, 409)
    admin_members = call("admin", "GET", f"{base}/members")["data"]
    admin_id = next(member["id"] for member in admin_members if member["role"] == "mission_admin")
    call("admin", "DELETE", f"{base}/members/{admin_id}", expected=409)
    # O perfil de astronauta é validado antes da proteção do último administrador.
    call("admin", "PATCH", f"{base}/members/{admin_id}", {"role": "astronaut"}, 422)
    call("admin", "PATCH", base, {"ended_at": "2025-01-01T00:00:00Z"}, 422)
    call("admin", "PATCH", base, {"planned_launch_at": None}, 422)
    call("admin", "POST", f"{base}/exam-requirements", {
        "exam_type_id": case["exam_type"]["id"], "due_days_before_launch": -1,
    }, 422)
    call("admin", "POST", f"{base}/exam-requirements", {
        "exam_type_id": case["exam_type"]["id"], "due_days_before_launch": 12,
    }, 409)
    call("admin", "DELETE", f"{base}/exam-requirements/{case['requirement']['id']}", expected=204)
    assert call("astronaut", "GET", f"{base}/astronauts/{case['astronaut']['id']}/exams")["data"] == []
    call("admin", "POST", f"{base}/exam-requirements", case["req_payload"], 409)
    call("admin", "DELETE", f"/exam-types/{case['exam_type']['id']}", expected=204)
    call("admin", "DELETE", f"{base}/members/{case['astronaut']['id']}", expected=204)
    call("admin", "DELETE", f"{base}/members/{case['doctor']['id']}", expected=204)
    call("admin", "DELETE", base, expected=204)
    call("admin", "GET", base, expected=404)


def test_composite_foreign_keys_reject_cross_mission_links(case):
    call, session = case["call"], case["session"]
    another = call("outsider", "POST", "/missions", {
        "name": "Fictional other mission", "planned_launch_at": case["launch"].isoformat(),
    }, 201)
    other_id = another["id"]
    member = call("outsider", "POST", f"/missions/{other_id}/members", {
        "user_id": case["people"]["second_astronaut"], "role": "astronaut",
    }, 201)
    requirement = call("outsider", "POST", f"/missions/{other_id}/exam-requirements", case["req_payload"], 201)
    for member_id, requirement_id in (
        (member["id"], case["requirement"]["id"]),
        (case["astronaut"]["id"], requirement["id"]),
    ):
        with pytest.raises(IntegrityError):
            with session.begin_nested():
                session.add(AstronautExam(
                    mission_id=case["mid"], mission_member_id=member_id,
                    requirement_id=requirement_id, due_at=case["launch"],
                ))
                session.flush()
    with pytest.raises(IntegrityError):
        with session.begin_nested():
            session.add(MissionExamRequirement(
                mission_id=case["mid"], exam_type_id=case["exam_type"]["id"],
                due_days_before_launch=-1,
            ))
            session.flush()
    assert all(column["type"].timezone for column in inspect(engine).get_columns("exam_results") if column["name"].endswith("_at"))


def test_generation_failure_rolls_back_membership(case, monkeypatch):
    def fail(self, mission):
        raise RuntimeError("Fictional generation failure")

    monkeypatch.setattr(PreflightService, "_generate", fail)
    with pytest.raises(RuntimeError, match="Fictional generation failure"):
        case["call"]("admin", "POST", f"{case['base']}/members", {
            "user_id": case["people"]["second_astronaut"], "role": "astronaut",
        }, 201)
    session = case["session"]
    assert session.exec(select(MissionMember).where(
        MissionMember.mission_id == case["mid"],
        MissionMember.user_id == case["people"]["second_astronaut"],
    )).first() is None


def test_invalid_timestamps_and_deadlines_do_not_write_results(case):
    call, base = case["call"], case["base"]
    result_path = f"{base}/astronaut-exams/{case['exam']['id']}/results"
    call("doctor", "POST", result_path, {
        "performed_at": "2026-01-01T00:00:00", "summary": "Fictional naive timestamp",
    }, 422)
    call("doctor", "POST", result_path, {
        "performed_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
        "summary": "Fictional future timestamp",
    }, 422)
    started = datetime.now(timezone.utc) - timedelta(days=20)
    call("admin", "PATCH", base, {"started_at": started.isoformat()})
    call("doctor", "POST", result_path, {
        "performed_at": (started + timedelta(days=1)).isoformat(), "summary": "Fictional in-mission exam",
    }, 422)
    call("doctor", "POST", result_path, {
        "performed_at": (started - timedelta(days=1)).isoformat(),
        "summary": "Fictional exam", "recorded_by_user_id": case["people"]["astronaut"],
    }, 422)
    assert call("doctor", "GET", result_path)["pagination"]["total"] == 0
    req_path = f"{base}/exam-requirements/{case['requirement']['id']}"
    call("admin", "PATCH", req_path, {"due_days_before_launch": 2147483648}, 422)
    call("admin", "PATCH", req_path, {"due_days_before_launch": 2147483647}, 422)
    assert call("admin", "GET", req_path)["due_days_before_launch"] == 30


@pytest.mark.parametrize('mission_role', ['astronaut', 'flight_surgeon', 'mission_admin'])
def test_astronaut_only_cannot_mutate_exams_even_with_elevated_mission_role(case, mission_role):
    call, session, base = case['call'], case['session'], case['base']
    result = create_result(case)
    member = session.get(MissionMember, case['astronaut']['id'])
    member.role = mission_role
    session.add(member)
    session.commit()
    paths = [
        ('POST', '/exam-types', {'code': 'forbidden', 'name': 'Forbidden'}),
        ('PATCH', f"/exam-types/{case['exam_type']['id']}", {'name': 'Forbidden'}),
        ('DELETE', f"/exam-types/{case['exam_type']['id']}", None),
        ('POST', f'{base}/exam-requirements', case['req_payload']),
        ('PATCH', f"{base}/exam-requirements/{case['requirement']['id']}", {'due_days_before_launch': 1}),
        ('DELETE', f"{base}/exam-requirements/{case['requirement']['id']}", None),
        ('PATCH', f"{base}/astronaut-exams/{case['exam']['id']}", {'scheduled_at': None}),
        ('POST', f"{base}/astronaut-exams/{case['exam']['id']}/results", {
            'performed_at': (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(), 'summary': 'Forbidden',
        }),
        ('PATCH', f"{base}/exam-results/{result['id']}", {'summary': 'Forbidden'}),
        ('POST', f"{base}/exam-results/{result['id']}/reviews", {'decision': 'accepted'}),
    ]
    for method, path, payload in paths:
        call('astronaut', method, path, payload, 403)
    assert session.get(ExamResult, result['id']).summary == 'Fictional visual examination'
    if mission_role == 'astronaut':
        assert call('astronaut', 'GET', f"{base}/astronaut-exams/{case['exam']['id']}/results")['data'][0]['id'] == result['id']


def test_physician_astronaut_profile_can_manage_exams_with_mission_authorization(case):
    call, session, base = case['call'], case['session'], case['base']
    doctor = session.get(User, case['people']['doctor'])
    doctor.is_astronaut = True
    session.add(doctor)
    session.commit()
    call('doctor', 'PATCH', f"{base}/astronaut-exams/{case['exam']['id']}", {'scheduled_at': None})
    call('doctor', 'PATCH', f"{base}/exam-requirements/{case['requirement']['id']}", {'due_days_before_launch': 12})
    temporary_type = call('doctor', 'POST', '/exam-types', {'code': 'doctor_catalog', 'name': 'Fictional catalog'}, 201)
    call('doctor', 'PATCH', f"/exam-types/{temporary_type['id']}", {'name': 'Fictional updated catalog'})
    temporary_req = call('doctor', 'POST', f'{base}/exam-requirements', {'exam_type_id': temporary_type['id'], 'due_days_before_launch': 2}, 201)
    call('doctor', 'DELETE', f"{base}/exam-requirements/{temporary_req['id']}", expected=204)
    call('doctor', 'DELETE', f"/exam-types/{temporary_type['id']}", expected=204)
    result = create_result(case)
    call('doctor', 'PATCH', f"{base}/exam-results/{result['id']}", {'summary': 'Fictional correction'})
    review(case, result, 'accepted')
    assert status(case)['state'] == 'completed'
