"""End-to-end flows over the real /ws/call WebSocket (mock mode, no API keys),
plus a wiring check of the live Pipecat pipeline."""

import re

import pytest
from fastapi.testclient import TestClient

from app.services import appointment_service as appts
from app.services.validation import spoken_time

from .conftest import first_free_day_for


@pytest.fixture
def client():
    from app.main import app

    with TestClient(app) as c:
        yield c


class Call:
    def __init__(self, ws):
        self.ws = ws
        self.events = []

    def agent_reply(self) -> str:
        while True:
            e = self.ws.receive_json()
            self.events.append(e)
            if e["type"] == "transcript" and e["role"] == "agent":
                assert e.get("mock") is True  # mock output is always labelled
                return e["text"]

    def say(self, text: str) -> str:
        self.ws.send_json({"type": "user_text", "text": text})
        return self.agent_reply()


def _start(ws) -> Call:
    call = Call(ws)
    first = ws.receive_json()
    assert first == {"type": "call_state", "state": "connected", "mode": "mock",
                     "missing_keys": ["GOOGLE_API_KEY", "ELEVENLABS_API_KEY"]}
    assert "thank you for calling" in call.agent_reply().lower()
    return call


def test_scenario_1_booking_updates_dashboard(client, conn):
    day, slot = first_free_day_for(conn, "Cardiology")
    surname = slot["name"].split()[-1]
    with client.websocket_connect("/ws/dashboard") as dash, \
            client.websocket_connect("/ws/call") as ws:
        dash.receive_json()
        call = _start(ws)
        assert "preferred date" in call.say("Hello, I want to book an appointment with a cardiologist.")
        offer = call.say(day.isoformat())
        assert spoken_time(slot["start_time"]) in offer  # real slots from the DB
        assert "name" in call.say(f"{slot['start_time']} with Dr {surname}").lower()
        assert "phone number" in call.say("Asha Patel")
        readback = call.say("nine eight seven six five four three two one zero")
        assert "9 8 7 6 5, 4 3 2 1 0" in readback and "correct" in readback
        confirmation = call.say("yes, that's right")
        assert "confirmed" in confirmation
        appt_id = re.search(r"A P T - (\w(?: \w){5})", confirmation).group(0).replace(" ", "")
        assert any(e["type"] == "booking_confirmed" for e in call.events)

        event = dash.receive_json()  # dashboard was pushed the new booking
        assert event["type"] == "appointment.booked" and event["data"]["id"] == appt_id

    stored = appts.get_appointment(conn, appt_id)
    assert stored["status"] == "booked" and stored["patient_phone"] == "9876543210"
    assert stored["slot_id"] == slot["slot_id"] and stored["patient_name"] == "Asha Patel"


def test_scenario_2_availability_only_creates_nothing(client, conn):
    day, slot = first_free_day_for(conn, "Dermatology")
    before = conn.execute("SELECT COUNT(*) FROM appointments").fetchone()[0]
    with client.websocket_connect("/ws/call") as ws:
        call = _start(ws)
        reply = call.say(f"Is Dr Thompson available on {day.isoformat()}? Just checking availability.")
        assert "Dr. Sarah Thompson has" in reply
        assert "no problem" in call.say("no thanks").lower()
    assert conn.execute("SELECT COUNT(*) FROM appointments").fetchone()[0] == before


def test_scenario_3_cancellation_with_multiple_appointments(client, conn):
    with client.websocket_connect("/ws/call") as ws:
        call = _start(ws)
        assert "phone number" in call.say("I need to cancel my appointment")
        assert "9 8 7 6 5, 0 0 0 0 1" in call.say("98765 00001")
        listing = call.say("yes")
        assert "2 appointments" in listing and "Which one" in listing
        confirm = call.say("the one with Dr Thompson")
        assert "Shall I cancel it" in confirm
        assert "has been cancelled" in call.say("yes please")
    remaining = appts.find_active_by_phone(conn, "9876500001")
    assert len(remaining) == 1 and remaining[0]["doctor_id"] == "DOC-001"


def test_booking_then_cancellation_round_trip(client, conn):
    day, slot = first_free_day_for(conn, "Cardiology")
    with client.websocket_connect("/ws/call") as ws:
        call = _start(ws)
        call.say("book a cardiologist")
        call.say(day.isoformat())
        call.say(f"{slot['start_time']} with {slot['name']}")
        call.say("Ravi")
        call.say("9123456780")
        assert "confirmed" in call.say("yes")
    with client.websocket_connect("/ws/call") as ws:
        call = _start(ws)
        call.say("cancel my booking")
        call.say("9123456780")
        assert "Shall I cancel it" in call.say("yes")
        assert "has been cancelled" in call.say("yes")
    assert appts.find_active_by_phone(conn, "9123456780") == []


def test_wrong_number_correction_and_unknown_number(client, conn):
    with client.websocket_connect("/ws/call") as ws:
        call = _start(ws)
        call.say("cancel appointment")
        call.say("9555555555")
        assert "again" in call.say("no, that's wrong")
        call.say("9555555556")
        assert "couldn't find any upcoming appointments" in call.say("yes")


def test_live_pipeline_wiring_without_network(monkeypatch):
    """Builds the real Pipecat pipeline (fake keys, nothing started) and checks
    that STT -> LLM -> TTS are present and all three tools are registered."""
    import asyncio

    import aiohttp

    from app.config import get_settings
    from app.voice.pipeline import build_voice_call

    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
    monkeypatch.setenv("ELEVENLABS_API_KEY", "test-key")
    get_settings.cache_clear()

    class FakeWebSocket:
        headers = {"origin": "http://localhost:3000"}

    from pipecat.pipeline.worker import PipelineWorker
    from pipecat.services.elevenlabs.stt import ElevenLabsRealtimeSTTService
    from pipecat.services.elevenlabs.tts import ElevenLabsTTSService
    from pipecat.services.google.llm import GoogleLLMService

    import app.voice.pipeline as pipeline_module

    built = {}
    for name in ("_build_stt", "_build_llm", "_build_tts"):
        original = getattr(pipeline_module, name)

        def spy(*args, _orig=original, _name=name):
            built[_name] = _orig(*args)
            return built[_name]
        monkeypatch.setattr(pipeline_module, name, spy)

    async def build():
        async with aiohttp.ClientSession() as http:
            return build_voice_call(FakeWebSocket(), http, get_settings())

    worker = asyncio.run(build())
    assert isinstance(worker, PipelineWorker)
    assert isinstance(built["_build_stt"], ElevenLabsRealtimeSTTService)
    assert isinstance(built["_build_tts"], ElevenLabsTTSService)
    llm = built["_build_llm"]
    assert isinstance(llm, GoogleLLMService)
    # The three tools are registered with the LLM under their exact names.
    assert set(llm._functions) == {
        "check_doctor_availability", "book_appointment", "cancel_appointment"}
