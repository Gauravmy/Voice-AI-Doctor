"""Database + service-layer rules: seeding, availability, booking, cancellation."""

import sqlite3
from datetime import date

import pytest

from app.database import get_connection, init_db
from app.services import appointment_service as appts
from app.services import doctor_service
from app.services.errors import NotFoundError, SlotUnavailableError, ValidationError


def test_seed_data_is_realistic(conn):
    stats = appts.dashboard_stats(conn)
    assert stats["total_doctors"] >= 8
    assert stats["total_specialties"] >= 6
    assert stats["available_slots"] > 50
    booked = conn.execute("SELECT COUNT(*) FROM appointments WHERE status='booked'").fetchone()[0]
    assert booked > 5  # some slots already taken
    dates = conn.execute("SELECT COUNT(DISTINCT slot_date) FROM slots").fetchone()[0]
    assert dates >= 7


def test_init_db_is_idempotent(conn, isolated_db):
    before = [conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
              for t in ("doctors", "slots", "appointments")]
    init_db()
    init_db()
    after = [conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
             for t in ("doctors", "slots", "appointments")]
    assert before == after


def test_find_doctors_by_specialty_alias_and_name(conn):
    cardio = doctor_service.find_doctors(conn, specialty="I need a cardiologist")
    assert {d["specialty"] for d in cardio} == {"Cardiology"} and len(cardio) == 2
    assert doctor_service.find_doctors(conn, doctor_name="Dr. Rao")[0]["id"] == "DOC-001"
    assert doctor_service.find_doctors(conn, doctor_id="doc-003")[0]["name"] == "Dr. Sarah Thompson"
    assert doctor_service.find_doctors(conn, specialty="astrology") == []


def test_availability_excludes_booked_slots(conn):
    taken = conn.execute(
        "SELECT a.slot_id, s.doctor_id, s.slot_date FROM appointments a JOIN slots s "
        "ON s.id = a.slot_id WHERE a.status='booked' LIMIT 1").fetchone()
    free = doctor_service.available_slots(conn, taken["doctor_id"],
                                          date.fromisoformat(taken["slot_date"]))
    assert taken["slot_id"] not in {s["slot_id"] for s in free}


def test_book_appointment_persists(conn, free_slot, isolated_db):
    appt = appts.book_appointment(conn, doctor_id=free_slot["doctor_id"],
                                  slot_id=free_slot["id"], patient_phone="98765 43210",
                                  patient_name="Test Patient", source="voice")
    assert appt["status"] == "booked" and appt["id"].startswith("APT-")
    assert appt["patient_phone"] == "9876543210"
    # Persistence: visible through a brand-new connection.
    with get_connection() as other:
        row = other.execute("SELECT * FROM appointments WHERE id = ?", (appt["id"],)).fetchone()
        assert row["status"] == "booked" and row["slot_id"] == free_slot["id"]
        log = other.execute("SELECT action FROM activity_log WHERE appointment_id=?",
                            (appt["id"],)).fetchall()
        assert [r["action"] for r in log] == ["booked"]


def test_book_by_date_and_time(conn, free_slot):
    appt = appts.book_appointment(
        conn, doctor_id=free_slot["doctor_id"], slot_date=date.fromisoformat(free_slot["slot_date"]),
        start_time=free_slot["start_time"], patient_phone="9876543210")
    assert appt["slot_id"] == free_slot["id"]


def test_double_booking_is_prevented(conn, free_slot):
    appts.book_appointment(conn, doctor_id=free_slot["doctor_id"], slot_id=free_slot["id"],
                           patient_phone="9876543210")
    with pytest.raises(SlotUnavailableError):
        appts.book_appointment(conn, doctor_id=free_slot["doctor_id"], slot_id=free_slot["id"],
                               patient_phone="9123456780")


def test_database_index_blocks_double_booking_even_without_service_checks(conn, free_slot):
    now = "2026-01-01T00:00:00+00:00"
    sql = ("INSERT INTO appointments (id, slot_id, doctor_id, patient_phone, status, created_at,"
           " updated_at) VALUES (?, ?, ?, '9876543210', 'booked', ?, ?)")
    conn.execute(sql, ("APT-RAW001", free_slot["id"], free_slot["doctor_id"], now, now))
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(sql, ("APT-RAW002", free_slot["id"], free_slot["doctor_id"], now, now))


def test_status_check_constraint(conn, free_slot):
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO appointments (id, slot_id, doctor_id, patient_phone, status, created_at,"
            " updated_at) VALUES ('APT-BAD001', ?, ?, '9876543210', 'pending', 'x', 'x')",
            (free_slot["id"], free_slot["doctor_id"]))


@pytest.mark.parametrize("kwargs,error,code", [
    ({"patient_phone": "123"}, ValidationError, "invalid_phone"),
    ({"doctor_id": "DOC-999"}, NotFoundError, "doctor_not_found"),
    ({"slot_id": 999999}, NotFoundError, "slot_not_found"),
])
def test_invalid_booking_requests(conn, free_slot, kwargs, error, code):
    args = {"doctor_id": free_slot["doctor_id"], "slot_id": free_slot["id"],
            "patient_phone": "9876543210", **kwargs}
    with pytest.raises(error) as exc:
        appts.book_appointment(conn, **args)
    assert exc.value.code == code


def test_slot_must_belong_to_doctor(conn, free_slot):
    other_doctor = "DOC-002" if free_slot["doctor_id"] != "DOC-002" else "DOC-003"
    with pytest.raises(NotFoundError):
        appts.book_appointment(conn, doctor_id=other_doctor, slot_id=free_slot["id"],
                               patient_phone="9876543210")


def test_past_slot_cannot_be_booked(conn):
    conn.execute("INSERT INTO slots (doctor_id, slot_date, start_time, end_time) "
                 "VALUES ('DOC-001', '2020-01-06', '09:00', '09:30')")
    slot_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    with pytest.raises(ValidationError) as exc:
        appts.book_appointment(conn, doctor_id="DOC-001", slot_id=slot_id,
                               patient_phone="9876543210")
    assert exc.value.code == "slot_in_past"


def test_cancel_frees_slot_and_allows_rebooking(conn, free_slot):
    appt = appts.book_appointment(conn, doctor_id=free_slot["doctor_id"], slot_id=free_slot["id"],
                                  patient_phone="9876543210")
    cancelled = appts.cancel_appointment(conn, appointment_id=appt["id"],
                                         patient_phone="98765 43210")
    assert cancelled["status"] == "cancelled" and cancelled["cancelled_at"]
    day = date.fromisoformat(free_slot["slot_date"])
    assert free_slot["id"] in {s["slot_id"] for s in
                               doctor_service.available_slots(conn, free_slot["doctor_id"], day)}
    again = appts.book_appointment(conn, doctor_id=free_slot["doctor_id"],
                                   slot_id=free_slot["id"], patient_phone="9111111111")
    assert again["status"] == "booked"


def test_cancel_with_wrong_phone_is_rejected(conn):
    seeded = appts.find_active_by_phone(conn, "9876500002")[0]
    with pytest.raises(NotFoundError):
        appts.cancel_appointment(conn, appointment_id=seeded["id"], patient_phone="9999999999")
    assert appts.get_appointment(conn, seeded["id"])["status"] == "booked"


def test_cancel_twice_is_rejected(conn):
    seeded = appts.find_active_by_phone(conn, "9876500002")[0]
    appts.cancel_appointment(conn, appointment_id=seeded["id"], patient_phone="9876500002")
    with pytest.raises(ValidationError) as exc:
        appts.cancel_appointment(conn, appointment_id=seeded["id"], patient_phone="9876500002")
    assert exc.value.code == "already_cancelled"


def test_multiple_appointments_for_one_phone(conn):
    assert len(appts.find_active_by_phone(conn, "9876500001")) == 2
    assert len(appts.find_active_by_phone(conn, "9876500003")) == 0  # only a cancelled one


def test_public_view_masks_patient_details(conn):
    appt = appts.find_active_by_phone(conn, "9876500002")[0]
    view = appts.public_view(appt)
    assert view["patient_phone"] == "******0002"
    assert view["patient_name"] == "N. G."
