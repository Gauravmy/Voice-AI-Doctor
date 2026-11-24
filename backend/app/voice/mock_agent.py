"""DEVELOPMENT MOCK MODE - a deterministic, rule-based receptionist.

Used only when Gemini/ElevenLabs keys are not configured (or VOICE_MODE=mock).
It is text-only: no speech recognition, no speech synthesis and no LLM. Every
message it sends carries `"mock": true` and the UI labels it as such.

Its purpose is to let the dashboard, the database and - importantly - the *same*
`ClinicTools` used by the real pipeline be exercised end to end without API keys.
It follows the same conversation rules as the real agent: one question at a time,
phone read-back and confirmation before booking/cancelling.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from app.services.errors import DomainError
from app.services.validation import normalize_phone, parse_date, parse_time, spoken_date
from app.voice.tools import ClinicTools

_YES = re.compile(r"\b(yes|yeah|yep|yup|correct|right|sure|confirm|confirmed|please do|go ahead|"
                  r"that's right|thats right|ok|okay|absolutely)\b")
_NO = re.compile(r"\b(no|nope|wrong|incorrect|not right|don't|dont|cancel that)\b")


@dataclass
class _State:
    intent: str | None = None            # book | check | cancel
    doctor_query: str | None = None
    specialty: str | None = None
    date: str | None = None
    availability: dict | None = None
    slot: dict | None = None             # {doctor_id, doctor_name, slot_id, spoken_time}
    patient_name: str | None = None
    phone: str | None = None
    awaiting: str | None = None
    appointments: list[dict] = field(default_factory=list)
    target: dict | None = None


def _say_list(items: list[str]) -> str:
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]


class MockReceptionist:
    def __init__(self, tools: ClinicTools, clinic_name: str):
        self.tools = tools
        self.clinic_name = clinic_name
        self.s = _State()

    def greeting(self) -> str:
        return (f"Hello, thank you for calling {self.clinic_name}. This is Maya, the "
                f"development mock receptionist. How can I help you today?")

    # ------------------------------------------------------------------ helpers
    def _detect_intent(self, text: str) -> str | None:
        if re.search(r"\bcancel", text):
            return "cancel"
        if re.search(r"\b(book|appointment|schedule|see a|see dr|consult)", text):
            return "book"
        if re.search(r"\b(available|availability|free slot|slots|check)\b", text):
            return "check"
        return None

    def _extract_doctor(self, text: str) -> None:
        m = re.search(r"\b(?:dr|doctor)\.?\s+([a-z]+(?:\s+[a-z]+)?)", text)
        if m and m.group(1) not in {"appointment", "for", "on", "tomorrow", "today"}:
            self.s.doctor_query = m.group(1)
        from app.database import get_connection
        from app.services.doctor_service import resolve_specialty
        with get_connection() as conn:
            spec = resolve_specialty(conn, text)
        if spec:
            self.s.specialty = spec

    def _try_date(self, text: str) -> str | None:
        try:
            return parse_date(text).isoformat()
        except DomainError:
            return None

    async def _check(self) -> str:
        result = await self.tools.check_doctor_availability(
            date=self.s.date, doctor_name=self.s.doctor_query, specialty=self.s.specialty)
        self.s.availability = result
        status = result["status"]
        if status == "no_matching_doctor":
            self.s.doctor_query = self.s.specialty = None
            self.s.awaiting = "doctor"
            return ("I couldn't find a doctor matching that. We have "
                    + _say_list(result["available_specialties"]) + ". Which would you like?")
        if status in ("past_date", "invalid_date"):
            self.s.date = None
            self.s.awaiting = "date"
            return result["message"] + " Which date would you prefer?"
        if status == "no_availability":
            self.s.date = None
            self.s.awaiting = "date"
            nexts = sorted({d for doc in result["doctors"] for d in doc.get("next_available_dates", [])})
            spoken = [spoken_date(date.fromisoformat(d)) for d in nexts[:3]]
            hint = f" The next available dates are {_say_list(spoken)}." if nexts else ""
            return f"I'm sorry, there are no free slots on {result['spoken_date']}.{hint} Which date works for you?"
        parts = []
        for doc in result["doctors"]:
            if doc["available_slots"]:
                times = [s["spoken_time"] for s in doc["available_slots"][:3]]
                parts.append(f"{doc['name']} has {_say_list(times)}")
        intro = f"On {result['spoken_date']}, " + "; ".join(parts) + "."
        if self.s.intent == "check":
            self.s.awaiting = "book_after_check"
            return intro + " Would you like to book one of these?"
        self.s.awaiting = "slot"
        return intro + " Which time would you like?"

    def _match_slot(self, text: str) -> dict | list[dict] | None:
        try:
            wanted = parse_time(text)
        except DomainError:
            return None
        matches = []
        for doc in (self.s.availability or {}).get("doctors", []):
            for slot in doc["available_slots"]:
                if slot["start_time"] == wanted:
                    matches.append({"doctor_id": doc["doctor_id"], "doctor_name": doc["name"],
                                    **slot})
        named = [m for m in matches if any(
            tok in text for tok in m["doctor_name"].lower().replace("dr.", "").split())]
        if len(named) == 1:
            return named[0]
        if len(matches) == 1:
            return matches[0]
        return matches or None

    # ------------------------------------------------------------------- main
    async def respond(self, raw: str) -> str:
        text = raw.strip().lower()
        if not text:
            return "Sorry, I didn't catch that. Could you repeat it?"
        s = self.s

        if s.awaiting is None or s.intent is None:
            intent = self._detect_intent(text)
            if intent is None:
                return ("I can help you book, check or cancel a doctor's appointment. "
                        "What would you like to do?")
            s.intent = intent
            if intent == "cancel":
                s.awaiting = "phone"
                return "I can help with that. Please tell me the phone number used for the booking."
            self._extract_doctor(text)
            s.date = self._try_date(text)
            if not (s.doctor_query or s.specialty):
                s.awaiting = "doctor"
                return "Certainly. Which doctor or specialty would you like to see?"
            if not s.date:
                s.awaiting = "date"
                return "Certainly. May I know your preferred date?"
            return await self._check()

        if s.awaiting == "doctor":
            self._extract_doctor(text)
            if not (s.doctor_query or s.specialty):
                return "Which specialty do you need, for example cardiology or dermatology?"
            if not s.date:
                s.awaiting = "date"
                return "Thank you. May I know your preferred date?"
            return await self._check()

        if s.awaiting == "date":
            s.date = self._try_date(text)
            if not s.date:
                return "Sorry, I didn't get the date. Could you say it like 'tomorrow' or '28 November'?"
            return await self._check()

        if s.awaiting == "book_after_check":
            if _YES.search(text):
                s.intent = "book"
                s.awaiting = "slot"
                return "Great. Which time would you like?"
            if _NO.search(text):
                s.awaiting = None
                s.intent = None
                return "No problem. Is there anything else I can help you with?"
            s.awaiting = "slot"
            s.intent = "book"

        if s.awaiting == "slot":
            match = self._match_slot(text)
            if match is None:
                return "Sorry, that time isn't available. Please choose one of the times I mentioned."
            if isinstance(match, list):
                return ("That time is available with " + _say_list([m["doctor_name"] for m in match])
                        + ". Which doctor would you prefer?")
            s.slot = match
            s.awaiting = "name"
            return f"{match['spoken_time']} with {match['doctor_name']}. May I have the patient's name?"

        if s.awaiting == "name":
            name = re.sub(r"^(my name is|this is|it's|it is|i am|i'm|name is)\s+", "", raw.strip(),
                          flags=re.I).strip(" .")
            s.patient_name = name.title()[:80]
            s.awaiting = "phone"
            return f"Thank you, {s.patient_name}. Please tell me your phone number."

        if s.awaiting == "phone":
            try:
                phone = normalize_phone(text)
            except DomainError as e:
                return e.message
            s.phone = phone
            if s.intent == "cancel":
                result = await self.tools.cancel_appointment(patient_phone=phone, phone_confirmed=False)
                s.awaiting = "confirm_phone"
                return f"I have {result['phone_readback']}. Is that correct?"
            result = await self.tools.book_appointment(
                doctor_id=s.slot["doctor_id"], slot_id=s.slot["slot_id"], patient_phone=phone,
                phone_confirmed=False)
            s.awaiting = "confirm_phone"
            return (f"I have {result['phone_readback']}, for {s.slot['doctor_name']} on "
                    f"{s.availability['spoken_date']} at {s.slot['spoken_time']}. Is that correct?")

        if s.awaiting == "confirm_phone":
            if _NO.search(text):
                s.awaiting = "phone"
                return "Sorry about that. Please say your phone number again."
            if not _YES.search(text):
                return "Please say yes if the number is correct, or no to change it."
            if s.intent == "cancel":
                return await self._cancel_step(None)
            result = await self.tools.book_appointment(
                doctor_id=s.slot["doctor_id"], slot_id=s.slot["slot_id"], patient_phone=s.phone,
                phone_confirmed=True, patient_name=s.patient_name or "")
            if result["status"] == "booked":
                spelled = " ".join(result["appointment_id"])
                self.s = _State()
                return (f"Your appointment is confirmed with {result['doctor_name']} on "
                        f"{result['spoken_date']} at {result['spoken_time']}. Your appointment ID "
                        f"is {spelled}. Is there anything else I can help with?")
            if result["status"] == "slot_unavailable":
                alts = [a["spoken_time"] for a in result.get("alternative_slots", [])[:3]]
                s.awaiting = "slot"
                await self._check()
                return ("I'm sorry, that slot was just taken. "
                        + (f"Available times are {_say_list(alts)}. Which would you like?" if alts
                           else "Would you like another date?"))
            self.s = _State()
            return f"I'm sorry, I couldn't book that: {result['message']}"

        if s.awaiting == "which_appointment":
            chosen = None
            for a in s.appointments:
                if a["appointment_id"].lower() in text.replace(" ", "") or any(
                        tok in text for tok in a["doctor_name"].lower().replace("dr.", "").split()):
                    chosen = a
                    break
            if chosen is None:
                m = re.search(r"\b(first|1|one|second|2|two|third|3|three)\b", text)
                idx = {"first": 0, "1": 0, "one": 0, "second": 1, "2": 1, "two": 1,
                       "third": 2, "3": 2, "three": 2}.get(m.group(1)) if m else None
                if idx is not None and idx < len(s.appointments):
                    chosen = s.appointments[idx]
            if chosen is None:
                return "Which appointment should I cancel? You can say the doctor's name."
            return await self._cancel_step(chosen["appointment_id"])

        if s.awaiting == "confirm_cancel":
            if _NO.search(text):
                self.s = _State()
                return "Okay, I have not cancelled anything. Anything else I can help with?"
            if not _YES.search(text):
                return "Should I cancel it? Please say yes or no."
            result = await self.tools.cancel_appointment(
                patient_phone=s.phone, phone_confirmed=True,
                appointment_id=s.target["appointment_id"], confirm_cancellation=True)
            self.s = _State()
            if result["status"] == "cancelled":
                a = result["appointment"]
                return (f"Your appointment with {a['doctor_name']} on {a['spoken_date']} at "
                        f"{a['spoken_time']} has been cancelled. Anything else?")
            return f"I'm sorry, I couldn't cancel it: {result['message']}"

        self.s = _State()
        return "Sorry, I lost track. Could you tell me again what you'd like to do?"

    async def _cancel_step(self, appointment_id: str | None) -> str:
        s = self.s
        result = await self.tools.cancel_appointment(
            patient_phone=s.phone, phone_confirmed=True, appointment_id=appointment_id)
        status = result["status"]
        if status == "no_appointments":
            self.s = _State()
            return "I couldn't find any upcoming appointments for that number. Anything else?"
        if status == "multiple_found":
            s.appointments = result["appointments"]
            s.awaiting = "which_appointment"
            descs = [f"{a['doctor_name']} on {a['spoken_date']} at {a['spoken_time']}"
                     for a in s.appointments]
            return f"I found {len(descs)} appointments: {_say_list(descs)}. Which one should I cancel?"
        if status == "confirm_cancellation_required":
            s.target = result["appointment"]
            s.awaiting = "confirm_cancel"
            a = s.target
            return (f"Your appointment with {a['doctor_name']} on {a['spoken_date']} at "
                    f"{a['spoken_time']}. Shall I cancel it?")
        self.s = _State()
        return f"Sorry, {result.get('message', 'something went wrong')}"


async def run_mock_call(websocket, clinic_name: str, missing_keys: list[str]) -> None:
    """Text-only mock call over the same WebSocket protocol as the live call."""
    import json

    from fastapi import WebSocketDisconnect

    async def send(msg: dict[str, Any]) -> None:
        await websocket.send_text(json.dumps(msg))

    tools = ClinicTools(emit=send)
    agent = MockReceptionist(tools, clinic_name)
    await send({"type": "call_state", "state": "connected", "mode": "mock",
                "missing_keys": missing_keys})
    await send({"type": "transcript", "role": "agent", "text": agent.greeting(),
                "final": True, "mock": True})
    try:
        while True:
            message = await websocket.receive()
            if message.get("type") == "websocket.disconnect":
                break
            data = message.get("text")
            if data is None:
                continue  # mock mode ignores microphone audio
            try:
                payload = json.loads(data)
            except json.JSONDecodeError:
                continue
            if payload.get("type") == "end_call":
                break
            if payload.get("type") != "user_text":
                continue
            text = str(payload.get("text", ""))[:500]
            await send({"type": "transcript", "role": "user", "text": text, "final": True})
            reply = await agent.respond(text)
            await send({"type": "transcript", "role": "agent", "text": reply, "final": True,
                        "mock": True})
    except WebSocketDisconnect:
        pass
