"""The three function-calling tools exposed to the LLM.

    check_doctor_availability   read-only
    book_appointment            writes, two-step confirmation
    cancel_appointment          writes, two-step confirmation

`ClinicTools` holds per-call state and is pure Python (no Pipecat imports), so it
is unit-tested directly and reused by the keyless mock agent. `register_tools()`
adapts it to Pipecat's function-calling API.

Server-enforced confirmation
----------------------------
The prompt tells the LLM to read the phone number back and wait for a "yes", but
an LLM can still skip steps. So the tools enforce it in code:

1. The first call with a phone number (or any call with phone_confirmed=false)
   returns status `confirmation_required` plus a digit-by-digit read-back.
2. Only a later call with phone_confirmed=true AND the *same* number, within the
   same call session, can book or cancel.
3. Cancellation needs one more step: `confirm_cancellation_required` describing
   the exact appointment, then confirm_cancellation=true for that appointment.

The phone number is the only identity: no caller ID, login or OTP exists.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
import datetime as dt
from typing import Any

from app.database import get_connection
from app.services import appointment_service, doctor_service
from app.services.errors import DomainError
from app.services.validation import (
    mask_phone, normalize_phone, parse_date, parse_time, phone_readback, spoken_date, spoken_time,
)

logger = logging.getLogger(__name__)

EventEmitter = Callable[[dict[str, Any]], Awaitable[None]]


# --------------------------------------------------------------------------
# JSON schemas (provider-neutral). Pipecat converts these to Gemini's format.
# --------------------------------------------------------------------------
TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "name": "check_doctor_availability",
        "description": (
            "Look up doctors and their free appointment slots on a date. Use whenever the "
            "caller asks about availability or before offering any time. Provide a doctor "
            "name/ID and/or a specialty. Never invent slots - only offer what this returns."
        ),
        "properties": {
            "date": {"type": "string",
                     "description": "Requested date in YYYY-MM-DD (resolve 'tomorrow' etc. first)."},
            "doctor_name": {"type": "string", "description": "Doctor name as spoken, e.g. 'Dr. Rao'."},
            "doctor_id": {"type": "string", "description": "Doctor ID such as DOC-001, if known."},
            "specialty": {"type": "string",
                          "description": "Specialty or type of doctor, e.g. 'cardiologist'."},
        },
        "required": ["date"],
    },
    {
        "name": "book_appointment",
        "description": (
            "Book a slot returned by check_doctor_availability. Two steps: first call with "
            "phone_confirmed=false to get the read-back of the caller's spoken phone number; "
            "read it back and ask them to confirm; only after they clearly say yes, call again "
            "with phone_confirmed=true. Only say an appointment is booked if status is 'booked'."
        ),
        "properties": {
            "doctor_id": {"type": "string", "description": "Doctor ID, e.g. DOC-001."},
            "slot_id": {"type": "integer", "description": "slot_id from the availability result."},
            "date": {"type": "string", "description": "YYYY-MM-DD (only if slot_id is unknown)."},
            "start_time": {"type": "string", "description": "HH:MM 24h (only if slot_id is unknown)."},
            "patient_phone": {"type": "string",
                              "description": "Phone number exactly as the caller spoke it, digits only."},
            "phone_confirmed": {"type": "boolean",
                                "description": "True only after the caller confirmed the read-back."},
            "patient_name": {"type": "string", "description": "Patient name, if given."},
            "reason": {"type": "string", "description": "Short reason for the visit, if given."},
        },
        "required": ["doctor_id", "patient_phone", "phone_confirmed"],
    },
    {
        "name": "cancel_appointment",
        "description": (
            "Cancel an appointment for the caller, identified ONLY by the phone number they "
            "speak. Step 1: call with phone_confirmed=false to get the read-back and confirm it. "
            "Step 2: call with phone_confirmed=true to list their appointments (ask which one if "
            "several). Step 3: describe it and ask for final confirmation, then call with "
            "confirm_cancellation=true and the appointment_id."
        ),
        "properties": {
            "patient_phone": {"type": "string", "description": "Phone number as spoken, digits only."},
            "phone_confirmed": {"type": "boolean",
                                "description": "True only after the caller confirmed the read-back."},
            "appointment_id": {"type": "string", "description": "Appointment ID, e.g. APT-7K3Q9M."},
            "confirm_cancellation": {
                "type": "boolean",
                "description": "True only after the caller explicitly confirmed cancelling it."},
        },
        "required": ["patient_phone", "phone_confirmed"],
    },
]


def _slot_view(slot: dict) -> dict:
    return {"slot_id": slot["slot_id"], "start_time": slot["start_time"],
            "spoken_time": spoken_time(slot["start_time"])}


def _appt_view(a: dict) -> dict:
    d = dt.date.fromisoformat(a["date"])
    return {
        "appointment_id": a["id"], "doctor_id": a["doctor_id"], "doctor_name": a["doctor_name"],
        "specialty": a["specialty"], "date": a["date"], "spoken_date": spoken_date(d),
        "start_time": a["start_time"], "spoken_time": spoken_time(a["start_time"]),
        "status": a["status"],
    }


class ClinicTools:
    """Tool implementations with per-call confirmation state."""

    def __init__(self, emit: EventEmitter | None = None) -> None:
        self._emit = emit
        self._phones_read_back: set[str] = set()       # numbers the agent was told to confirm
        self._cancellations_presented: set[tuple[str, str]] = set()  # (phone, appt id)

    async def _notify(self, event: dict[str, Any]) -> None:
        if self._emit:
            try:
                await self._emit(event)
            except Exception:  # UI notification must never break the call
                logger.exception("Failed to emit call event")

    # ------------------------------------------------------------------ check
    async def check_doctor_availability(
        self, date: str | None = None, doctor_name: str | None = None,
        doctor_id: str | None = None, specialty: str | None = None, **_: Any,
    ) -> dict[str, Any]:
        try:
            day = parse_date(date)
        except DomainError as e:
            return {"status": e.code, "message": e.message}

        def query() -> dict[str, Any]:
            with get_connection() as conn:
                doctors = doctor_service.find_doctors(
                    conn, doctor_id=doctor_id, doctor_name=doctor_name, specialty=specialty)
                if not doctors:
                    names = [s["name"] for s in doctor_service.list_specialties(conn)]
                    return {"status": "no_matching_doctor",
                            "message": "No doctor matches that name or specialty.",
                            "available_specialties": names}
                results = []
                for doc in doctors[:5]:
                    slots = doctor_service.available_slots(conn, doc["id"], day)
                    entry = {"doctor_id": doc["id"], "name": doc["name"],
                             "specialty": doc["specialty"],
                             "available_slots": [_slot_view(s) for s in slots]}
                    if not slots:
                        entry["next_available_dates"] = doctor_service.next_available_dates(
                            conn, doc["id"], after=day)
                    results.append(entry)
                any_free = any(r["available_slots"] for r in results)
                return {
                    "status": "available" if any_free else "no_availability",
                    "date": day.isoformat(), "spoken_date": spoken_date(day),
                    "doctors": results,
                    "note": "Offer only these slots. Use slot_id when booking.",
                }

        result = await asyncio.to_thread(query)
        await self._notify({"type": "tool_result", "tool": "check_doctor_availability",
                            "status": result["status"]})
        return result

    # ------------------------------------------------------------------- book
    async def book_appointment(
        self, doctor_id: str | None = None, patient_phone: str | None = None,
        phone_confirmed: bool = False, slot_id: int | float | None = None,
        date: str | None = None, start_time: str | None = None,
        patient_name: str | None = None, reason: str | None = None, **_: Any,
    ) -> dict[str, Any]:
        try:
            phone = normalize_phone(patient_phone)
        except DomainError as e:
            return {"status": e.code, "message": e.message + " Ask the caller to repeat it."}

        if not phone_confirmed or phone not in self._phones_read_back:
            self._phones_read_back.add(phone)
            return {
                "status": "confirmation_required",
                "phone_readback": phone_readback(phone),
                "message": ("Read this number back to the caller digit by digit, together with "
                            "the doctor, date and time, and ask them to confirm. Call again with "
                            "phone_confirmed=true only after they say yes."),
            }

        try:
            slot_day = parse_date(date) if (date and slot_id is None) else None
            start = parse_time(start_time) if (start_time and slot_id is None) else None
        except DomainError as e:
            return {"status": e.code, "message": e.message}

        def do_book() -> dict[str, Any]:
            with get_connection() as conn:
                try:
                    appt = appointment_service.book_appointment(
                        conn, doctor_id=doctor_id or "", patient_phone=phone,
                        slot_id=int(slot_id) if slot_id is not None else None,
                        slot_date=slot_day, start_time=start,
                        patient_name=patient_name or "", reason=reason or "", source="voice")
                except DomainError as e:
                    out: dict[str, Any] = {"status": e.code, "message": e.message}
                    if e.code in ("slot_unavailable", "slot_in_past", "slot_not_found") and doctor_id:
                        doc = doctor_service.get_doctor(conn, doctor_id)
                        if doc:
                            the_day = slot_day
                            if the_day is None and slot_id is not None:
                                row = conn.execute("SELECT slot_date FROM slots WHERE id = ?",
                                                   (int(slot_id),)).fetchone()
                                the_day = (dt.date.fromisoformat(row["slot_date"])
                                           if row else None)
                            if the_day:
                                out["alternative_slots"] = [
                                    _slot_view(s) for s in
                                    doctor_service.available_slots(conn, doc["id"], the_day)]
                    return out
                view = _appt_view(appt)
                return {"status": "booked", **view, "phone_readback": phone_readback(phone),
                        "message": "Booking saved in the clinic database. Read the confirmation "
                                   "(appointment ID, doctor, date, time) to the caller."}

        result = await asyncio.to_thread(do_book)
        if result["status"] == "booked":
            await self._notify({"type": "booking_confirmed", "appointment": {
                **{k: result[k] for k in ("appointment_id", "doctor_name", "specialty", "date",
                                          "start_time", "spoken_date", "spoken_time")},
                "patient_phone": mask_phone(phone)}})
        else:
            await self._notify({"type": "tool_result", "tool": "book_appointment",
                                "status": result["status"]})
        return result

    # ----------------------------------------------------------------- cancel
    async def cancel_appointment(
        self, patient_phone: str | None = None, phone_confirmed: bool = False,
        appointment_id: str | None = None, confirm_cancellation: bool = False, **_: Any,
    ) -> dict[str, Any]:
        try:
            phone = normalize_phone(patient_phone)
        except DomainError as e:
            return {"status": e.code, "message": e.message + " Ask the caller to repeat it."}

        if not phone_confirmed or phone not in self._phones_read_back:
            self._phones_read_back.add(phone)
            return {
                "status": "confirmation_required",
                "phone_readback": phone_readback(phone),
                "message": ("Read this number back digit by digit and ask the caller to confirm "
                            "it. Call again with phone_confirmed=true only after they say yes."),
            }

        def do_cancel() -> dict[str, Any]:
            with get_connection() as conn:
                active = appointment_service.find_active_by_phone(conn, phone)
                if not active:
                    return {"status": "no_appointments",
                            "message": "There are no upcoming appointments for this phone number."}
                views = [_appt_view(a) for a in active]
                target = None
                if appointment_id:
                    wanted = appointment_id.strip().upper().replace(" ", "")
                    if not wanted.startswith("APT-"):
                        wanted = "APT-" + wanted.removeprefix("APT")
                    target = next((v for v in views if v["appointment_id"] == wanted), None)
                    if target is None:
                        return {"status": "appointment_not_found",
                                "message": "That ID does not match this caller's appointments.",
                                "appointments": views}
                elif len(views) == 1:
                    target = views[0]
                else:
                    return {"status": "multiple_found", "appointments": views,
                            "message": "Read the appointments and ask which one to cancel."}

                key = (phone, target["appointment_id"])
                if not confirm_cancellation or key not in self._cancellations_presented:
                    self._cancellations_presented.add(key)
                    return {"status": "confirm_cancellation_required", "appointment": target,
                            "message": "Describe this appointment and ask the caller to confirm "
                                       "the cancellation. Then call with confirm_cancellation=true."}
                try:
                    appt = appointment_service.cancel_appointment(
                        conn, appointment_id=target["appointment_id"], patient_phone=phone,
                        source="voice")
                except DomainError as e:
                    return {"status": e.code, "message": e.message}
                return {"status": "cancelled", "appointment": _appt_view(appt),
                        "message": "Cancellation saved in the clinic database. Confirm it to the "
                                   "caller."}

        result = await asyncio.to_thread(do_cancel)
        if result["status"] == "cancelled":
            await self._notify({"type": "cancellation_confirmed",
                                "appointment": {**result["appointment"],
                                                "patient_phone": mask_phone(phone)}})
        else:
            await self._notify({"type": "tool_result", "tool": "cancel_appointment",
                                "status": result["status"]})
        return result

    async def call(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Dispatch by tool name (used by the Pipecat adapter and the mock agent)."""
        handler = {
            "check_doctor_availability": self.check_doctor_availability,
            "book_appointment": self.book_appointment,
            "cancel_appointment": self.cancel_appointment,
        }.get(name)
        if handler is None:
            return {"status": "unknown_tool", "message": f"No tool named {name}."}
        try:
            return await handler(**dict(arguments or {}))
        except Exception:  # never let a tool bug crash the call
            logger.exception("Tool %s failed", name)
            return {"status": "internal_error",
                    "message": "A system error occurred. Apologise and offer to try again."}


# --------------------------------------------------------------------------
# Pipecat adapter
# --------------------------------------------------------------------------
def build_tools_schema():
    from pipecat.adapters.llm.schemas.function_schema import FunctionSchema
    from pipecat.adapters.llm.schemas.tools_schema import ToolsSchema

    return ToolsSchema(standard_tools=[
        FunctionSchema(name=t["name"], description=t["description"],
                       properties=t["properties"], required=t["required"])
        for t in TOOL_DEFINITIONS
    ])


def register_tools(llm, tools: ClinicTools, *, timeout_secs: float) -> None:
    """Register each tool with the Pipecat LLM service under its exact name."""
    from pipecat.services.llm_service import FunctionCallParams

    def make_handler(tool_name: str):
        async def handler(params: FunctionCallParams) -> None:
            logger.info("LLM called %s", tool_name)
            await tools._notify({"type": "tool_call", "tool": tool_name})
            result = await tools.call(tool_name, dict(params.arguments))
            await params.result_callback(result)
        return handler

    for t in TOOL_DEFINITIONS:
        llm.register_function(t["name"], make_handler(t["name"]), timeout_secs=timeout_secs)
