"""REST endpoints consumed by the dashboard (and usable for manual testing).

Patient phone numbers are always masked in responses; the full number is only
ever used server-side to match the caller's spoken number."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Query

from app.config import get_settings
from app.database import get_connection
from app.schemas.api import BookAppointmentRequest, CancelAppointmentRequest
from app.services import appointment_service, doctor_service
from app.services.errors import NotFoundError
from app.services.validation import parse_date, parse_time

router = APIRouter(prefix="/api")


@router.get("/health")
def health() -> dict:
    s = get_settings()
    return {
        "status": "ok",
        "voice_mode": s.effective_voice_mode,
        "configured_mode": s.voice_mode,
        "missing_keys": s.missing_live_keys,
        "providers": {
            "llm": f"Google Gemini ({s.gemini_model or 'pipecat default'})",
            "stt": f"ElevenLabs STT ({s.elevenlabs_stt_mode})",
            "tts": f"ElevenLabs TTS ({s.elevenlabs_tts_model})",
        },
        "clinic_name": s.clinic_name,
        "timezone": s.clinic_timezone,
    }


@router.get("/stats")
def stats() -> dict:
    with get_connection() as conn:
        return appointment_service.dashboard_stats(conn)


@router.get("/activity")
def activity(days: int = Query(default=7, ge=1, le=31)) -> dict:
    with get_connection() as conn:
        return appointment_service.booking_activity(conn, days)


@router.get("/specialties")
def specialties() -> list[dict]:
    with get_connection() as conn:
        return doctor_service.list_specialties(conn)


@router.get("/doctors")
def doctors() -> list[dict]:
    with get_connection() as conn:
        return doctor_service.doctor_summaries(conn)


@router.get("/doctors/{doctor_id}/availability")
def doctor_availability(doctor_id: str, date_: str = Query(alias="date")) -> dict:
    day: date = parse_date(date_)
    with get_connection() as conn:
        doc = doctor_service.get_doctor(conn, doctor_id)
        if doc is None:
            raise NotFoundError("doctor_not_found", f"No doctor with id '{doctor_id}'.")
        return {
            "doctor": doc,
            "date": day.isoformat(),
            "slots": doctor_service.available_slots(conn, doc["id"], day),
        }


@router.get("/appointments")
def appointments(
    status: str | None = Query(default=None, pattern="^(booked|cancelled)$"),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[dict]:
    with get_connection() as conn:
        rows = appointment_service.list_appointments(conn, status=status, limit=limit)
        return [appointment_service.public_view(r) for r in rows]


@router.post("/appointments", status_code=201)
def create_appointment(body: BookAppointmentRequest) -> dict:
    slot_date = parse_date(body.date) if body.date else None
    start = parse_time(body.start_time) if body.start_time else None
    with get_connection() as conn:
        appt = appointment_service.book_appointment(
            conn, doctor_id=body.doctor_id, slot_id=body.slot_id, slot_date=slot_date,
            start_time=start, patient_phone=body.patient_phone, patient_name=body.patient_name,
            reason=body.reason, source="api",
        )
        return appointment_service.public_view(appt)


@router.post("/appointments/{appointment_id}/cancel")
def cancel(appointment_id: str, body: CancelAppointmentRequest) -> dict:
    with get_connection() as conn:
        appt = appointment_service.cancel_appointment(
            conn, appointment_id=appointment_id, patient_phone=body.patient_phone, source="api"
        )
        return appointment_service.public_view(appt)
