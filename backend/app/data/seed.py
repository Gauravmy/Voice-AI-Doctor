"""Fictional seed data.

Every name, phone number and appointment here is made up. Availability is
generated relative to *today* (clinic timezone) so the demo always has
upcoming slots, and it is deterministic (fixed RNG seed) so tests are stable.

Demo phone numbers for cancellation testing:
    9876500001 -> two active appointments (tests "which one?" disambiguation)
    9876500002 -> one active appointment
    9876500003 -> one cancelled appointment only (tests "nothing to cancel")
"""

from __future__ import annotations

import random
import sqlite3
from datetime import timedelta

from app.config import get_settings
from app.services.clock import today_local, utc_now_iso

SPECIALTIES: list[tuple[str, str]] = [
    ("Cardiology", "Heart and blood vessel care"),
    ("Dermatology", "Skin, hair and nail conditions"),
    ("Pediatrics", "Care for infants, children and teens"),
    ("Orthopedics", "Bones, joints and muscles"),
    ("Neurology", "Brain, spine and nerves"),
    ("General Medicine", "Primary care and general check-ups"),
    ("ENT", "Ear, nose and throat"),
    ("Gynecology", "Women's reproductive health"),
]

# (id, name, specialty, years, room, working weekdays (Mon=0), session)
DOCTORS: list[tuple[str, str, str, int, str, tuple[int, ...], str]] = [
    ("DOC-001", "Dr. Ananya Rao", "Cardiology", 14, "Room 101", (0, 2, 4), "morning"),
    ("DOC-002", "Dr. Vikram Mehta", "Cardiology", 9, "Room 102", (1, 3, 5), "afternoon"),
    ("DOC-003", "Dr. Sarah Thompson", "Dermatology", 11, "Room 201", (0, 1, 3), "morning"),
    ("DOC-004", "Dr. Rohan Iyer", "Pediatrics", 8, "Room 203", (0, 1, 2, 3, 4), "afternoon"),
    ("DOC-005", "Dr. Meera Kapoor", "Orthopedics", 16, "Room 301", (1, 2, 4), "morning"),
    ("DOC-006", "Dr. Daniel Okafor", "Neurology", 12, "Room 302", (0, 3), "afternoon"),
    ("DOC-007", "Dr. Priya Nair", "General Medicine", 7, "Room 105", (0, 1, 2, 3, 4, 5), "morning"),
    ("DOC-008", "Dr. Arjun Desai", "ENT", 10, "Room 205", (1, 4), "afternoon"),
    ("DOC-009", "Dr. Kavita Sharma", "Gynecology", 13, "Room 401", (0, 2, 3, 5), "morning"),
]

SESSIONS = {
    "morning": ["09:00", "09:30", "10:00", "10:30", "11:00", "11:30"],
    "afternoon": ["14:00", "14:30", "15:00", "15:30", "16:00", "16:30"],
}

SEED_APPOINTMENTS = [
    # (phone, name, reason, doctor_id, nth upcoming working day, slot index, status)
    ("9876500001", "Rahul Verma", "Follow-up on blood pressure", "DOC-001", 1, 1, "booked"),
    ("9876500001", "Rahul Verma", "Skin rash", "DOC-003", 2, 2, "booked"),
    ("9876500002", "Neha Gupta", "Child vaccination", "DOC-004", 1, 0, "booked"),
    ("9876500003", "Aman Joshi", "Knee pain", "DOC-005", 1, 3, "cancelled"),
    ("9876500004", "Fatima Khan", "Annual check-up", "DOC-007", 0, 4, "booked"),
]


def _add_minutes(hhmm: str, minutes: int) -> str:
    h, m = map(int, hhmm.split(":"))
    total = h * 60 + m + minutes
    return f"{total // 60:02d}:{total % 60:02d}"


def ensure_slot_horizon(conn: sqlite3.Connection) -> int:
    """Create slots for every doctor's working days from today to the horizon.
    INSERT OR IGNORE + the UNIQUE(doctor, date, time) constraint make this
    safe to run on every start-up."""
    horizon = get_settings().booking_horizon_days
    today = today_local()
    added = 0
    doctors = conn.execute("SELECT id FROM doctors").fetchall()
    schedule = {d[0]: (d[5], d[6]) for d in DOCTORS}
    for row in doctors:
        weekdays, session = schedule.get(row["id"], ((0, 1, 2, 3, 4), "morning"))
        for offset in range(horizon + 1):
            day = today + timedelta(days=offset)
            if day.weekday() not in weekdays:
                continue
            for start in SESSIONS[session]:
                cur = conn.execute(
                    "INSERT OR IGNORE INTO slots (doctor_id, slot_date, start_time, end_time) "
                    "VALUES (?, ?, ?, ?)",
                    (row["id"], day.isoformat(), start, _add_minutes(start, 30)),
                )
                added += cur.rowcount
    return added


def seed_database(conn: sqlite3.Connection) -> None:
    rng = random.Random(42)
    conn.execute("BEGIN")
    try:
        for name, desc in SPECIALTIES:
            conn.execute(
                "INSERT INTO specialties (name, description) VALUES (?, ?)", (name, desc)
            )
        spec_ids = {
            r["name"]: r["id"] for r in conn.execute("SELECT id, name FROM specialties")
        }
        for doc_id, name, spec, years, room, _days, session in DOCTORS:
            conn.execute(
                "INSERT INTO doctors (id, name, specialty_id, years_experience, room, bio) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (doc_id, name, spec_ids[spec], years, room,
                 f"{spec} specialist, {years} years of experience, {session} clinic."),
            )
        ensure_slot_horizon(conn)

        now = utc_now_iso()
        today = today_local().isoformat()
        seq = 0

        def add_appt(slot_id: int, doctor_id: str, phone: str, name: str, reason: str,
                     status: str) -> None:
            nonlocal seq
            seq += 1
            appt_id = f"APT-SEED{seq:02d}"
            conn.execute(
                "INSERT INTO appointments (id, slot_id, doctor_id, patient_name, patient_phone,"
                " reason, status, source, created_at, updated_at, cancelled_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, 'seed', ?, ?, ?)",
                (appt_id, slot_id, doctor_id, name, phone, reason, status, now, now,
                 now if status == "cancelled" else None),
            )
            conn.execute(
                "INSERT INTO activity_log (appointment_id, action, source, created_at)"
                " VALUES (?, 'booked', 'seed', ?)", (appt_id, now),
            )
            if status == "cancelled":
                conn.execute(
                    "INSERT INTO activity_log (appointment_id, action, source, created_at)"
                    " VALUES (?, 'cancelled', 'seed', ?)", (appt_id, now),
                )

        # Named demo appointments (for the cancellation scenario).
        for phone, name, reason, doc_id, nth_day, slot_idx, status in SEED_APPOINTMENTS:
            dates = [
                r["slot_date"] for r in conn.execute(
                    "SELECT DISTINCT slot_date FROM slots WHERE doctor_id = ? AND slot_date > ?"
                    " ORDER BY slot_date", (doc_id, today),
                )
            ]
            if not dates:
                continue
            day = dates[min(nth_day, len(dates) - 1)]
            slot = conn.execute(
                "SELECT id FROM slots WHERE doctor_id = ? AND slot_date = ? ORDER BY start_time"
                " LIMIT 1 OFFSET ?", (doc_id, day, slot_idx),
            ).fetchone()
            if slot:
                add_appt(slot["id"], doc_id, phone, name, reason, status)

        # Background bookings so some slots are already taken (~20%).
        free_slots = conn.execute(
            "SELECT s.id, s.doctor_id FROM slots s WHERE s.slot_date > ? AND NOT EXISTS ("
            " SELECT 1 FROM appointments a WHERE a.slot_id = s.id AND a.status = 'booked')"
            " ORDER BY s.id", (today,),
        ).fetchall()
        for slot in free_slots:
            if rng.random() < 0.2:
                phone = "90000" + "".join(str(rng.randint(0, 9)) for _ in range(5))
                add_appt(slot["id"], slot["doctor_id"], phone, "Walk-in Patient",
                         "General consultation", "booked")
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise
