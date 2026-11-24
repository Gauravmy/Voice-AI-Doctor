"""REST API and dashboard WebSocket."""

import pytest
from fastapi.testclient import TestClient

from .conftest import first_free_day_for


@pytest.fixture
def client():
    from app.main import app

    with TestClient(app) as c:
        yield c


def test_health_reports_mock_mode(client):
    body = client.get("/api/health").json()
    assert body["status"] == "ok" and body["voice_mode"] == "mock"
    assert set(body["missing_keys"]) == {"GOOGLE_API_KEY", "ELEVENLABS_API_KEY"}
    assert "Gemini" in body["providers"]["llm"]


def test_dashboard_data_endpoints(client):
    stats = client.get("/api/stats").json()
    assert stats["total_doctors"] >= 8
    doctors = client.get("/api/doctors").json()
    assert len(doctors) == stats["total_doctors"]
    d = doctors[0]
    assert {"id", "name", "specialty", "available_slots", "available_dates", "next_available"} <= d.keys()
    assert len(client.get("/api/specialties").json()) >= 6
    activity = client.get("/api/activity").json()
    assert len(activity["series"]) == 7


def test_doctor_availability_endpoint(client, conn):
    day, slot = first_free_day_for(conn, "Cardiology")
    r = client.get(f"/api/doctors/{slot['doctor_id']}/availability", params={"date": day.isoformat()})
    assert r.status_code == 200
    assert slot["slot_id"] in {s["slot_id"] for s in r.json()["slots"]}
    assert client.get("/api/doctors/DOC-404/availability", params={"date": day.isoformat()}
                      ).status_code == 404
    bad = client.get("/api/doctors/DOC-001/availability", params={"date": "not-a-date"})
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "invalid_date"


def test_appointments_are_masked(client):
    rows = client.get("/api/appointments").json()
    assert rows and all(r["patient_phone"].startswith("******") for r in rows)


def test_book_conflict_and_cancel_via_api(client, conn):
    _, slot = first_free_day_for(conn, "Cardiology")
    body = {"doctor_id": slot["doctor_id"], "slot_id": slot["slot_id"],
            "patient_phone": "98765 43210", "patient_name": "Api Test"}
    r = client.post("/api/appointments", json=body)
    assert r.status_code == 201
    appt_id = r.json()["id"]

    dup = client.post("/api/appointments", json={**body, "patient_phone": "9123456780"})
    assert dup.status_code == 409 and dup.json()["error"]["code"] == "slot_unavailable"

    wrong = client.post(f"/api/appointments/{appt_id}/cancel", json={"patient_phone": "9999999999"})
    assert wrong.status_code == 404

    ok = client.post(f"/api/appointments/{appt_id}/cancel", json={"patient_phone": "9876543210"})
    assert ok.status_code == 200 and ok.json()["status"] == "cancelled"


@pytest.mark.parametrize("payload,code", [
    ({"doctor_id": "DOC-001", "slot_id": 1, "patient_phone": "12"}, "invalid_phone"),
    ({"doctor_id": "DOC-001", "patient_phone": "9876543210"}, "invalid_slot"),
    ({"doctor_id": "DOC-001", "slot_id": -5, "patient_phone": "9876543210"}, "invalid_request"),
    ({"slot_id": 1, "patient_phone": "9876543210"}, "invalid_request"),
])
def test_invalid_booking_requests(client, payload, code):
    r = client.post("/api/appointments", json=payload)
    assert r.status_code == 422
    assert r.json()["error"]["code"] == code


def test_dashboard_websocket_receives_booking_event(client, conn):
    _, slot = first_free_day_for(conn, "Dermatology")
    with client.websocket_connect("/ws/dashboard") as ws:
        assert ws.receive_json()["type"] == "hello"
        client.post("/api/appointments", json={
            "doctor_id": slot["doctor_id"], "slot_id": slot["slot_id"],
            "patient_phone": "9876543210"})
        event = ws.receive_json()
        assert event["type"] == "appointment.booked"
        assert event["data"]["patient_phone"] == "******3210"
