"""Doctor lookup and slot availability (read-only queries)."""

from __future__ import annotations

import re
import sqlite3
from datetime import date

from app.services.clock import now_local, today_local

# A slot is available when no 'booked' appointment references it.
_AVAILABLE = (
    "NOT EXISTS (SELECT 1 FROM appointments a WHERE a.slot_id = s.id AND a.status = 'booked')"
)

_DOCTOR_SELECT = (
    "SELECT d.id, d.name, d.years_experience, d.room, d.bio, sp.name AS specialty "
    "FROM doctors d JOIN specialties sp ON sp.id = d.specialty_id"
)

# Spoken synonyms -> canonical specialty names.
SPECIALTY_ALIASES = {
    "cardiologist": "Cardiology", "heart": "Cardiology", "cardio": "Cardiology",
    "dermatologist": "Dermatology", "skin": "Dermatology",
    "pediatrician": "Pediatrics", "paediatrician": "Pediatrics", "child": "Pediatrics",
    "children": "Pediatrics", "kids": "Pediatrics", "paediatrics": "Pediatrics",
    "orthopedic": "Orthopedics", "orthopaedic": "Orthopedics", "ortho": "Orthopedics",
    "bone": "Orthopedics", "orthopedist": "Orthopedics",
    "neurologist": "Neurology", "neuro": "Neurology", "brain": "Neurology",
    "general physician": "General Medicine", "general practitioner": "General Medicine",
    "gp": "General Medicine", "physician": "General Medicine", "general": "General Medicine",
    "family doctor": "General Medicine",
    "ent": "ENT", "ear": "ENT", "nose": "ENT", "throat": "ENT", "otolaryngologist": "ENT",
    "gynecologist": "Gynecology", "gynaecologist": "Gynecology", "gynaecology": "Gynecology",
    "gyno": "Gynecology", "obgyn": "Gynecology",
}


def resolve_specialty(conn: sqlite3.Connection, raw: str | None) -> str | None:
    if not raw:
        return None
    text = raw.strip().lower()
    names = [r["name"] for r in conn.execute("SELECT name FROM specialties")]
    for name in names:
        # Word-boundary match: a plain substring test would find "ent" in "appointment".
        if re.search(rf"\b{re.escape(name.lower())}\b", text):
            return name
    for alias in sorted(SPECIALTY_ALIASES, key=len, reverse=True):
        if re.search(rf"\b{re.escape(alias)}\b", text):
            return SPECIALTY_ALIASES[alias]
    return None


def list_specialties(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        "SELECT sp.id, sp.name, sp.description, COUNT(d.id) AS doctor_count "
        "FROM specialties sp LEFT JOIN doctors d ON d.specialty_id = sp.id "
        "GROUP BY sp.id ORDER BY sp.name"
    )
    return [dict(r) for r in rows]


def get_doctor(conn: sqlite3.Connection, doctor_id: str) -> dict | None:
    row = conn.execute(_DOCTOR_SELECT + " WHERE d.id = ?", (doctor_id.strip().upper(),)).fetchone()
    return dict(row) if row else None


def _name_tokens(name: str) -> list[str]:
    return [t for t in re.findall(r"[a-z]+", name.lower()) if t not in {"dr", "doctor"}]


def find_doctors(
    conn: sqlite3.Connection,
    *,
    doctor_id: str | None = None,
    doctor_name: str | None = None,
    specialty: str | None = None,
) -> list[dict]:
    """Match doctors by exact id, by any part of the name ("Dr Rao", "Ananya"),
    and/or by specialty. Returns [] when nothing matches."""
    if doctor_id:
        doc = get_doctor(conn, doctor_id)
        return [doc] if doc else []

    docs = [dict(r) for r in conn.execute(_DOCTOR_SELECT + " ORDER BY d.id")]
    if specialty:
        canonical = resolve_specialty(conn, specialty)
        if canonical is None:
            return []
        docs = [d for d in docs if d["specialty"] == canonical]
    if doctor_name:
        wanted = _name_tokens(doctor_name)
        if wanted:
            docs = [d for d in docs if any(t in _name_tokens(d["name"]) for t in wanted)]
    return docs


def _exclude_past_clause(day: date) -> tuple[str, tuple]:
    """Slots earlier today are not bookable."""
    if day == today_local():
        return " AND s.start_time > ?", (now_local().strftime("%H:%M"),)
    return "", ()


def available_slots(conn: sqlite3.Connection, doctor_id: str, day: date) -> list[dict]:
    extra, args = _exclude_past_clause(day)
    rows = conn.execute(
        f"SELECT s.id AS slot_id, s.slot_date AS date, s.start_time, s.end_time FROM slots s "
        f"WHERE s.doctor_id = ? AND s.slot_date = ? AND {_AVAILABLE}{extra} "
        f"ORDER BY s.start_time",
        (doctor_id, day.isoformat(), *args),
    )
    return [dict(r) for r in rows]


def slot_counts_for_day(conn: sqlite3.Connection, doctor_id: str, day: date) -> tuple[int, int]:
    """(total slots, available slots) for a doctor on a day."""
    total = conn.execute(
        "SELECT COUNT(*) FROM slots WHERE doctor_id = ? AND slot_date = ?",
        (doctor_id, day.isoformat()),
    ).fetchone()[0]
    return total, len(available_slots(conn, doctor_id, day))


def next_available_dates(
    conn: sqlite3.Connection, doctor_id: str, after: date | None = None, limit: int = 3
) -> list[str]:
    start = after or today_local()
    today = today_local()
    now_hhmm = now_local().strftime("%H:%M")
    rows = conn.execute(
        f"SELECT DISTINCT s.slot_date FROM slots s WHERE s.doctor_id = ? AND s.slot_date >= ? "
        f"AND {_AVAILABLE} AND (s.slot_date > ? OR s.start_time > ?) "
        f"ORDER BY s.slot_date LIMIT ?",
        (doctor_id, start.isoformat(), today.isoformat(), now_hhmm, limit),
    )
    return [r["slot_date"] for r in rows]


def doctor_summaries(conn: sqlite3.Connection) -> list[dict]:
    """Dashboard listing: each doctor with upcoming availability."""
    today = today_local()
    now_hhmm = now_local().strftime("%H:%M")
    result = []
    for doc in find_doctors(conn):
        rows = conn.execute(
            f"SELECT s.slot_date, COUNT(*) AS free FROM slots s WHERE s.doctor_id = ? "
            f"AND s.slot_date >= ? AND {_AVAILABLE} AND (s.slot_date > ? OR s.start_time > ?) "
            f"GROUP BY s.slot_date ORDER BY s.slot_date",
            (doc["id"], today.isoformat(), today.isoformat(), now_hhmm),
        ).fetchall()
        total_upcoming = conn.execute(
            "SELECT COUNT(*) FROM slots WHERE doctor_id = ? AND slot_date >= ?",
            (doc["id"], today.isoformat()),
        ).fetchone()[0]
        available = sum(r["free"] for r in rows)
        doc.update(
            available_dates=[{"date": r["slot_date"], "available": r["free"]} for r in rows],
            available_slots=available,
            total_slots=total_upcoming,
            next_available=rows[0]["slot_date"] if rows else None,
            next_slots=[
                s["start_time"] for s in available_slots(
                    conn, doc["id"], date.fromisoformat(rows[0]["slot_date"])
                )
            ][:4] if rows else [],
        )
        result.append(doc)
    return result
