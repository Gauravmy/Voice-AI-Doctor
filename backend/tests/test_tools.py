"""The three LLM tools, including server-enforced phone confirmation."""

from app.services import appointment_service as appts
from app.voice.tools import TOOL_DEFINITIONS, ClinicTools

from .conftest import first_free_day_for


def test_exact_tool_names():
    assert [t["name"] for t in TOOL_DEFINITIONS] == [
        "check_doctor_availability", "book_appointment", "cancel_appointment"]


async def test_check_availability_by_specialty(conn):
    day, _ = first_free_day_for(conn, "Cardiology")
    result = await ClinicTools().check_doctor_availability(date=day.isoformat(),
                                                           specialty="cardiologist")
    assert result["status"] == "available"
    assert all(d["specialty"] == "Cardiology" for d in result["doctors"])
    assert any(d["available_slots"] for d in result["doctors"])
    slot = next(s for d in result["doctors"] for s in d["available_slots"])
    assert {"slot_id", "start_time", "spoken_time"} <= slot.keys()


async def test_check_availability_creates_no_appointment(conn):
    before = conn.execute("SELECT COUNT(*) FROM appointments").fetchone()[0]
    day, _ = first_free_day_for(conn, "Dermatology")
    await ClinicTools().check_doctor_availability(date=day.isoformat(), doctor_name="Thompson")
    assert conn.execute("SELECT COUNT(*) FROM appointments").fetchone()[0] == before


async def test_check_availability_errors(conn):
    tools = ClinicTools()
    assert (await tools.check_doctor_availability(date="2001-01-01", specialty="ENT"))[
        "status"] == "past_date"
    assert (await tools.check_doctor_availability(date="someday", specialty="ENT"))[
        "status"] == "invalid_date"
    r = await tools.check_doctor_availability(date="tomorrow", specialty="astrology")
    assert r["status"] == "no_matching_doctor" and "Cardiology" in r["available_specialties"]


async def test_day_off_suggests_next_dates(conn):
    # Dr. Okafor works Mon/Thu only - find a date he does not work.
    from datetime import timedelta

    from app.services.clock import today_local
    day = today_local() + timedelta(days=1)
    while day.weekday() in (0, 3):
        day += timedelta(days=1)
    r = await ClinicTools().check_doctor_availability(date=day.isoformat(), doctor_id="DOC-006")
    assert r["status"] == "no_availability"
    assert r["doctors"][0]["next_available_dates"]


async def test_booking_requires_phone_readback_first(conn):
    day, slot = first_free_day_for(conn, "Cardiology")
    tools = ClinicTools()
    count = conn.execute("SELECT COUNT(*) FROM appointments").fetchone()[0]

    # The LLM tries to skip the read-back by claiming confirmation up-front.
    r = await tools.book_appointment(doctor_id=slot["doctor_id"], slot_id=slot["slot_id"],
                                     patient_phone="98765 43210", phone_confirmed=True)
    assert r["status"] == "confirmation_required"
    assert r["phone_readback"] == "9 8 7 6 5, 4 3 2 1 0"
    assert conn.execute("SELECT COUNT(*) FROM appointments").fetchone()[0] == count

    # After the read-back was produced, an explicit confirmation books it.
    r = await tools.book_appointment(doctor_id=slot["doctor_id"], slot_id=slot["slot_id"],
                                     patient_phone="9876543210", phone_confirmed=True,
                                     patient_name="Asha")
    assert r["status"] == "booked"
    stored = appts.get_appointment(conn, r["appointment_id"])
    assert stored["patient_phone"] == "9876543210"  # the spoken number is the identity
    assert stored["source"] == "voice"


async def test_confirming_a_different_number_restarts_readback(conn):
    _, slot = first_free_day_for(conn, "Cardiology")
    tools = ClinicTools()
    await tools.book_appointment(doctor_id=slot["doctor_id"], slot_id=slot["slot_id"],
                                 patient_phone="9876543210", phone_confirmed=False)
    r = await tools.book_appointment(doctor_id=slot["doctor_id"], slot_id=slot["slot_id"],
                                     patient_phone="9876543211", phone_confirmed=True)
    assert r["status"] == "confirmation_required"


async def test_invalid_phone_is_reported(conn):
    _, slot = first_free_day_for(conn, "Cardiology")
    r = await ClinicTools().book_appointment(doctor_id=slot["doctor_id"],
                                             slot_id=slot["slot_id"], patient_phone="12345",
                                             phone_confirmed=False)
    assert r["status"] == "invalid_phone"


async def test_slot_conflict_offers_alternatives(conn):
    _, slot = first_free_day_for(conn, "Cardiology")
    appts.book_appointment(conn, doctor_id=slot["doctor_id"], slot_id=slot["slot_id"],
                           patient_phone="9000000001")
    tools = ClinicTools()
    await tools.book_appointment(doctor_id=slot["doctor_id"], slot_id=slot["slot_id"],
                                 patient_phone="9876543210", phone_confirmed=False)
    r = await tools.book_appointment(doctor_id=slot["doctor_id"], slot_id=float(slot["slot_id"]),
                                     patient_phone="9876543210", phone_confirmed=True)
    assert r["status"] == "slot_unavailable"
    assert slot["slot_id"] not in {s["slot_id"] for s in r["alternative_slots"]}


async def test_booking_emits_confirmation_event(conn):
    _, slot = first_free_day_for(conn, "Cardiology")
    events = []

    async def emit(e):
        events.append(e)

    tools = ClinicTools(emit=emit)
    await tools.book_appointment(doctor_id=slot["doctor_id"], slot_id=slot["slot_id"],
                                 patient_phone="9876543210", phone_confirmed=False)
    await tools.book_appointment(doctor_id=slot["doctor_id"], slot_id=slot["slot_id"],
                                 patient_phone="9876543210", phone_confirmed=True)
    card = next(e for e in events if e["type"] == "booking_confirmed")["appointment"]
    assert card["patient_phone"] == "******3210"


async def test_cancel_flow_multiple_appointments(conn):
    tools = ClinicTools()
    r = await tools.cancel_appointment(patient_phone="98765 00001", phone_confirmed=False)
    assert r["status"] == "confirmation_required"
    r = await tools.cancel_appointment(patient_phone="9876500001", phone_confirmed=True)
    assert r["status"] == "multiple_found" and len(r["appointments"]) == 2
    target = r["appointments"][1]["appointment_id"]

    # Asking to cancel without presenting it first is refused.
    r = await tools.cancel_appointment(patient_phone="9876500001", phone_confirmed=True,
                                       appointment_id=target, confirm_cancellation=True)
    assert r["status"] == "confirm_cancellation_required"
    assert appts.get_appointment(conn, target)["status"] == "booked"

    r = await tools.cancel_appointment(patient_phone="9876500001", phone_confirmed=True,
                                       appointment_id=target, confirm_cancellation=True)
    assert r["status"] == "cancelled"
    assert appts.get_appointment(conn, target)["status"] == "cancelled"
    assert len(appts.find_active_by_phone(conn, "9876500001")) == 1


async def test_cancel_single_appointment(conn):
    tools = ClinicTools()
    await tools.cancel_appointment(patient_phone="9876500002", phone_confirmed=False)
    r = await tools.cancel_appointment(patient_phone="9876500002", phone_confirmed=True)
    assert r["status"] == "confirm_cancellation_required"
    appt_id = r["appointment"]["appointment_id"]
    r = await tools.cancel_appointment(patient_phone="9876500002", phone_confirmed=True,
                                       appointment_id=appt_id, confirm_cancellation=True)
    assert r["status"] == "cancelled"


async def test_cancel_wrong_phone_finds_nothing(conn):
    tools = ClinicTools()
    await tools.cancel_appointment(patient_phone="9555555555", phone_confirmed=False)
    r = await tools.cancel_appointment(patient_phone="9555555555", phone_confirmed=True)
    assert r["status"] == "no_appointments"


async def test_cancel_cannot_target_someone_elses_appointment(conn):
    other = appts.find_active_by_phone(conn, "9876500002")[0]["id"]
    tools = ClinicTools()
    await tools.cancel_appointment(patient_phone="9876500001", phone_confirmed=False)
    r = await tools.cancel_appointment(patient_phone="9876500001", phone_confirmed=True,
                                       appointment_id=other, confirm_cancellation=True)
    assert r["status"] == "appointment_not_found"
    assert appts.get_appointment(conn, other)["status"] == "booked"


async def test_unknown_tool_and_internal_errors_do_not_raise(conn, monkeypatch):
    tools = ClinicTools()
    assert (await tools.call("delete_everything", {}))["status"] == "unknown_tool"

    async def boom(**_):
        raise RuntimeError("db exploded")

    monkeypatch.setattr(tools, "check_doctor_availability", boom)
    assert (await tools.call("check_doctor_availability", {"date": "tomorrow"}))[
        "status"] == "internal_error"
