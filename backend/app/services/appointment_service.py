"""Booking and cancellation - the only code that writes appointments.

Both the REST API and the voice tools call these functions, so the rules
(validation, double-booking prevention, state transitions) live in one place.
"""

from __future__ import annotations

import logging
import secrets
import sqlite3
from datetime import date, timedelta

from app.services import doctor_service
from app.services.clock import now_local, today_local, utc_now_iso
from app.services.errors import NotFoundError, SlotUnavailableError, ValidationError
from app.services.events import bus
from app.services.validation import mask_phone, normalize_phone
from app.database import transaction

logger = logging.getLogger(__name__)

# No 0/O or 1/I: IDs are read aloud over the phone.
_ID_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"

_APPT_SELECT = (
    "SELECT a.id, a.status, a.patient_name, a.patient_phone, a.reason, a.source, "
    "a.created_at, a.updated_at, a.cancelled_at, a.slot_id, "
    "s.slot_date AS date, s.start_time, s.end_time, "
    "d.id AS doctor_id, d.name AS doctor_name, sp.name AS specialty "
    "FROM appointments a JOIN slots s ON s.id = a.slot_id "
    "JOIN doctors d ON d.id = a.doctor_id JOIN specialties sp ON sp.id = d.specialty_id"
)


def _new_appointment_id() -> str:
    return "APT-" + "".join(secrets.choice(_ID_ALPHABET) for _ in range(6))


def public_view(appt: dict) -> dict:
    """Appointment as shown on the dashboard: phone masked, name reduced to initials."""
    out = dict(appt)
    out["patient_phone"] = mask_phone(appt["patient_phone"])
    name = (appt.get("patient_name") or "").strip()
    out["patient_name"] = " ".join(p[0] + "." for p in name.split()) if name else ""
    return out


def get_appointment(conn: sqlite3.Connection, appointment_id: str) -> dict | None:
    row = conn.execute(
        _APPT_SELECT + " WHERE a.id = ?", (appointment_id.strip().upper(),)
    ).fetchone()
    return dict(row) if row else None


def list_appointments(
    conn: sqlite3.Connection, *, status: str | None = None, limit: int = 200
) -> list[dict]:
    sql = _APPT_SELECT
    args: list = []
    if status:
        sql += " WHERE a.status = ?"
        args.append(status)
    sql += " ORDER BY a.updated_at DESC, a.id DESC LIMIT ?"
    args.append(limit)
    return [dict(r) for r in conn.execute(sql, args)]


def find_active_by_phone(conn: sqlite3.Connection, phone_digits: str) -> list[dict]:
    """Upcoming booked appointments for the caller-provided phone number."""
    today = today_local().isoformat()
    rows = conn.execute(
        _APPT_SELECT + " WHERE a.patient_phone = ? AND a.status = 'booked' AND s.slot_date >= ?"
        " ORDER BY s.slot_date, s.start_time",
        (phone_digits, today),
    )
    return [dict(r) for r in rows]


def _resolve_slot(
    conn: sqlite3.Connection, doctor_id: str, slot_id: int | None,
    slot_date: date | None, start_time: str | None,
) -> sqlite3.Row:
    if slot_id is not None:
        slot = conn.execute(
            "SELECT * FROM slots WHERE id = ? AND doctor_id = ?", (slot_id, doctor_id)
        ).fetchone()
    elif slot_date and start_time:
        slot = conn.execute(
            "SELECT * FROM slots WHERE doctor_id = ? AND slot_date = ? AND start_time = ?",
            (doctor_id, slot_date.isoformat(), start_time),
        ).fetchone()
    else:
        raise ValidationError("invalid_slot", "Provide a slot_id, or a date and start time.")
    if slot is None:
        raise NotFoundError("slot_not_found", "That doctor has no slot at the requested time.")
    return slot


def book_appointment(
    conn: sqlite3.Connection,
    *,
    doctor_id: str,
    patient_phone: str,
    slot_id: int | None = None,
    slot_date: date | None = None,
    start_time: str | None = None,
    patient_name: str = "",
    reason: str = "",
    source: str = "api",
) -> dict:
    """Atomically book a slot. Raises a DomainError on any rule violation.

    Double booking is prevented twice: an explicit availability check inside a
    BEGIN IMMEDIATE transaction, and the partial UNIQUE index on
    appointments(slot_id) WHERE status='booked' as the final guard.
    """
    phone = normalize_phone(patient_phone)
    doctor = doctor_service.get_doctor(conn, doctor_id or "")
    if doctor is None:
        raise NotFoundError("doctor_not_found", f"No doctor with id '{doctor_id}'.")

    with transaction(conn):
        slot = _resolve_slot(conn, doctor["id"], slot_id, slot_date, start_time)
        slot_day = date.fromisoformat(slot["slot_date"])
        today = today_local()
        if slot_day < today or (
            slot_day == today and slot["start_time"] <= now_local().strftime("%H:%M")
        ):
            raise ValidationError("slot_in_past", "That time slot has already passed.")
        taken = conn.execute(
            "SELECT 1 FROM appointments WHERE slot_id = ? AND status = 'booked'", (slot["id"],)
        ).fetchone()
        if taken:
            raise SlotUnavailableError("slot_unavailable", "Sorry, that slot was just booked.")

        now = utc_now_iso()
        for _ in range(5):  # retry on the (astronomically unlikely) ID collision
            appt_id = _new_appointment_id()
            try:
                conn.execute(
                    "INSERT INTO appointments (id, slot_id, doctor_id, patient_name, patient_phone,"
                    " reason, status, source, created_at, updated_at)"
                    " VALUES (?, ?, ?, ?, ?, ?, 'booked', ?, ?, ?)",
                    (appt_id, slot["id"], doctor["id"], patient_name.strip()[:80], phone,
                     reason.strip()[:200], source, now, now),
                )
                break
            except sqlite3.IntegrityError as exc:
                if "ux_appointments_active_slot" in str(exc) or "slot_id" in str(exc):
                    raise SlotUnavailableError(
                        "slot_unavailable", "Sorry, that slot was just booked."
                    ) from exc
                if "appointments.id" in str(exc):
                    continue
                raise
        else:  # pragma: no cover
            raise RuntimeError("Could not allocate a unique appointment id")
        conn.execute(
            "INSERT INTO activity_log (appointment_id, action, source, created_at)"
            " VALUES (?, 'booked', ?, ?)", (appt_id, source, now),
        )

    appt = get_appointment(conn, appt_id)
    assert appt is not None
    logger.info("Appointment %s booked (doctor=%s slot=%s phone=%s)",
                appt_id, doctor["id"], slot["id"], mask_phone(phone))
    bus.publish("appointment.booked", public_view(appt))
    return appt


def cancel_appointment(
    conn: sqlite3.Connection, *, appointment_id: str, patient_phone: str, source: str = "api"
) -> dict:
    """Cancel an appointment. The caller's phone must match the appointment's
    phone - this is the only identity check in the system."""
    phone = normalize_phone(patient_phone)
    with transaction(conn):
        appt = get_appointment(conn, appointment_id or "")
        # Same error for "doesn't exist" and "belongs to another phone": we never
        # reveal that an appointment exists to someone with the wrong number.
        if appt is None or appt["patient_phone"] != phone:
            raise NotFoundError(
                "appointment_not_found",
                "No active appointment with that ID was found for this phone number.",
            )
        if appt["status"] == "cancelled":
            raise ValidationError("already_cancelled", "That appointment is already cancelled.")
        now = utc_now_iso()
        cur = conn.execute(
            "UPDATE appointments SET status = 'cancelled', cancelled_at = ?, updated_at = ?"
            " WHERE id = ? AND status = 'booked'", (now, now, appt["id"]),
        )
        if cur.rowcount != 1:  # pragma: no cover - guarded by the checks above
            raise ValidationError("already_cancelled", "That appointment is already cancelled.")
        conn.execute(
            "INSERT INTO activity_log (appointment_id, action, source, created_at)"
            " VALUES (?, 'cancelled', ?, ?)", (appt["id"], source, now),
        )
    updated = get_appointment(conn, appt["id"])
    assert updated is not None
    logger.info("Appointment %s cancelled (phone=%s)", appt["id"], mask_phone(phone))
    bus.publish("appointment.cancelled", public_view(updated))
    return updated


def dashboard_stats(conn: sqlite3.Connection) -> dict:
    today = today_local()
    now_hhmm = now_local().strftime("%H:%M")
    q = lambda sql, *a: conn.execute(sql, a).fetchone()[0]  # noqa: E731
    available = q(
        "SELECT COUNT(*) FROM slots s WHERE (s.slot_date > ? OR (s.slot_date = ? AND "
        "s.start_time > ?)) AND NOT EXISTS (SELECT 1 FROM appointments a WHERE a.slot_id = s.id"
        " AND a.status = 'booked')", today.isoformat(), today.isoformat(), now_hhmm,
    )
    return {
        "total_doctors": q("SELECT COUNT(*) FROM doctors"),
        "total_specialties": q("SELECT COUNT(*) FROM specialties"),
        "available_slots": available,
        "total_appointments": q("SELECT COUNT(*) FROM appointments"),
        "active_appointments": q("SELECT COUNT(*) FROM appointments WHERE status = 'booked'"),
        "cancelled_appointments": q(
            "SELECT COUNT(*) FROM appointments WHERE status = 'cancelled'"),
        "todays_appointments": q(
            "SELECT COUNT(*) FROM appointments a JOIN slots s ON s.id = a.slot_id "
            "WHERE s.slot_date = ? AND a.status = 'booked'", today.isoformat()),
        "voice_bookings": q(
            "SELECT COUNT(*) FROM activity_log WHERE action = 'booked' AND source = 'voice'"),
        "today": today.isoformat(),
    }


def booking_activity(conn: sqlite3.Connection, days: int = 7) -> dict:
    """Daily booked/cancelled counts (by local activity date) + recent events."""
    today = today_local()
    series = []
    rows = conn.execute(
        "SELECT action, created_at FROM activity_log WHERE source != 'seed'"
    ).fetchall()
    from datetime import datetime
    from app.services.clock import clinic_tz
    buckets: dict[str, dict[str, int]] = {}
    for r in rows:
        local_day = datetime.fromisoformat(r["created_at"]).astimezone(clinic_tz()).date()
        b = buckets.setdefault(local_day.isoformat(), {"booked": 0, "cancelled": 0})
        b[r["action"]] += 1
    for i in range(days - 1, -1, -1):
        d = (today - timedelta(days=i)).isoformat()
        series.append({"date": d, **buckets.get(d, {"booked": 0, "cancelled": 0})})
    recent = conn.execute(
        "SELECT l.id, l.appointment_id, l.action, l.source, l.created_at, d.name AS doctor_name,"
        " s.slot_date AS date, s.start_time FROM activity_log l"
        " JOIN appointments a ON a.id = l.appointment_id JOIN slots s ON s.id = a.slot_id"
        " JOIN doctors d ON d.id = a.doctor_id WHERE l.source != 'seed'"
        " ORDER BY l.id DESC LIMIT 12"
    ).fetchall()
    return {"series": series, "recent": [dict(r) for r in recent]}
