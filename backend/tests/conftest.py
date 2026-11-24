"""Each test gets its own freshly seeded SQLite file, and mock voice mode."""

from __future__ import annotations

from datetime import date

import pytest

from app.config import get_settings


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "test_clinic.db"))
    monkeypatch.setenv("VOICE_MODE", "mock")
    monkeypatch.setenv("GOOGLE_API_KEY", "")
    monkeypatch.setenv("ELEVENLABS_API_KEY", "")
    get_settings.cache_clear()
    from app.database import init_db

    init_db()
    yield tmp_path / "test_clinic.db"
    get_settings.cache_clear()


@pytest.fixture
def conn():
    from app.database import get_connection

    with get_connection() as c:
        yield c


@pytest.fixture
def free_slot(conn):
    """A free slot strictly after today (so time-of-day never matters)."""
    from app.services.clock import today_local

    row = conn.execute(
        "SELECT s.id, s.doctor_id, s.slot_date, s.start_time FROM slots s "
        "WHERE s.slot_date > ? AND NOT EXISTS (SELECT 1 FROM appointments a "
        "WHERE a.slot_id = s.id AND a.status = 'booked') ORDER BY s.slot_date, s.start_time "
        "LIMIT 1", (today_local().isoformat(),),
    ).fetchone()
    return dict(row)


def first_free_day_for(conn, specialty: str) -> tuple[date, dict]:
    """First future date on which a doctor of `specialty` has a free slot."""
    from app.services.clock import today_local

    row = conn.execute(
        "SELECT s.id AS slot_id, s.slot_date, s.start_time, d.id AS doctor_id, d.name "
        "FROM slots s JOIN doctors d ON d.id = s.doctor_id "
        "JOIN specialties sp ON sp.id = d.specialty_id WHERE sp.name = ? AND s.slot_date > ? "
        "AND NOT EXISTS (SELECT 1 FROM appointments a WHERE a.slot_id = s.id "
        "AND a.status = 'booked') ORDER BY s.slot_date, s.start_time LIMIT 1",
        (specialty, today_local().isoformat()),
    ).fetchone()
    return date.fromisoformat(row["slot_date"]), dict(row)
