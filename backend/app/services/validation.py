"""Input normalisation and validation shared by the REST API, the voice tools and
the mock agent.

Phone numbers are the ONLY caller identity in this system. They arrive as text the
caller *spoke* (e.g. "98765 00001", "nine eight seven six five ...", "+91 98765-00001")
and are normalised to a plain digit string before any lookup.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta

from app.services.clock import today_local
from app.services.errors import ValidationError

PHONE_MIN_DIGITS = 10
PHONE_MAX_DIGITS = 13

_DIGIT_WORDS = {
    "zero": "0", "oh": "0", "o": "0", "one": "1", "two": "2", "three": "3", "four": "4",
    "five": "5", "six": "6", "seven": "7", "eight": "8", "nine": "9",
}
_MULTIPLIERS = {"double": 2, "triple": 3}


def normalize_phone(raw: str | None) -> str:
    """Return the digits of a spoken/typed phone number or raise ValidationError.

    Handles digits with spaces/dashes/brackets, a leading '+', digit words and
    "double"/"triple" (common when people read numbers aloud).
    """
    if raw is None or not str(raw).strip():
        raise ValidationError("invalid_phone", "A phone number is required.")
    text = str(raw).lower()
    tokens = re.findall(r"[a-z]+|\d+", text)
    digits: list[str] = []
    repeat = 1
    for tok in tokens:
        if tok in _MULTIPLIERS:
            repeat = _MULTIPLIERS[tok]
            continue
        if tok.isdigit():
            chunk = tok
        elif tok in _DIGIT_WORDS:
            chunk = _DIGIT_WORDS[tok]
        else:
            # Ignore filler words such as "my", "number", "is", "plus".
            repeat = 1
            continue
        if repeat > 1:
            chunk = chunk[0] * repeat + chunk[1:]
            repeat = 1
        digits.append(chunk)
    number = "".join(digits)
    if len(number) > 10 and number.startswith("91") and len(number) == 12:
        number = number[2:]  # strip India country code -> canonical 10-digit form
    if len(number) == 11 and number.startswith("0"):
        number = number[1:]  # strip trunk prefix
    if not (PHONE_MIN_DIGITS <= len(number) <= PHONE_MAX_DIGITS):
        raise ValidationError(
            "invalid_phone",
            f"That phone number has {len(number)} digits; please provide a 10-digit number.",
        )
    return number


def phone_readback(digits: str) -> str:
    """How the agent should read the number back: grouped, digit by digit."""
    if len(digits) == 10:
        groups = [digits[:5], digits[5:]]
    else:
        groups = [digits[i:i + 4] for i in range(0, len(digits), 4)]
    return ", ".join(" ".join(g) for g in groups)


def mask_phone(digits: str) -> str:
    """Dashboard-safe representation, e.g. ******0001."""
    if len(digits) <= 4:
        return "*" * len(digits)
    return "*" * (len(digits) - 4) + digits[-4:]


_WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
_MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august",
     "september", "october", "november", "december"], start=1)}
_MONTHS.update({k[:3]: v for k, v in list(_MONTHS.items())})


def parse_date(raw: str | None, *, today: date | None = None, allow_past: bool = False) -> date:
    """Parse ISO dates plus common spoken forms ("today", "tomorrow", "next friday",
    "25 november", "november 25th"). The LLM is instructed to send ISO dates; the
    extra forms make the tools forgiving and power the keyless mock agent."""
    if raw is None or not str(raw).strip():
        raise ValidationError("invalid_date", "A date is required.")
    today = today or today_local()
    text = str(raw).strip().lower()
    result: date | None = None

    iso = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", text)
    if iso:
        try:
            result = date.fromisoformat(iso.group(1))
        except ValueError as exc:
            raise ValidationError("invalid_date", f"'{raw}' is not a valid date.") from exc

    if result is None:
        if "day after tomorrow" in text:
            result = today + timedelta(days=2)
        elif "tomorrow" in text:
            result = today + timedelta(days=1)
        elif re.search(r"\btoday\b", text):
            result = today

    if result is None:
        for idx, name in enumerate(_WEEKDAYS):
            if re.search(rf"\b{name}\b", text):
                delta = (idx - today.weekday()) % 7
                if delta == 0 and "this" not in text:
                    delta = 7  # "Monday" said on a Monday means next Monday
                result = today + timedelta(days=delta)
                break

    if result is None:
        m = re.search(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(?:of\s+)?([a-z]+)\b", text)
        m2 = re.search(r"\b([a-z]+)\s+(\d{1,2})(?:st|nd|rd|th)?\b", text)
        day_month = None
        if m and m.group(2)[:3] in _MONTHS:
            day_month = (int(m.group(1)), _MONTHS[m.group(2)[:3]])
        elif m2 and m2.group(1)[:3] in _MONTHS:
            day_month = (int(m2.group(2)), _MONTHS[m2.group(1)[:3]])
        if day_month:
            d, mo = day_month
            try:
                result = date(today.year, mo, d)
                if result < today:
                    result = date(today.year + 1, mo, d)
            except ValueError as exc:
                raise ValidationError("invalid_date", f"'{raw}' is not a valid date.") from exc

    if result is None:
        for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y"):
            try:
                result = datetime.strptime(text, fmt).date()
                break
            except ValueError:
                continue

    if result is None:
        raise ValidationError(
            "invalid_date", f"I couldn't understand the date '{raw}'. Please use a calendar date."
        )
    if not allow_past and result < today:
        raise ValidationError("past_date", f"{result.isoformat()} is in the past.")
    return result


def parse_time(raw: str | None) -> str:
    """Normalise "10", "10 am", "2:30 pm", "14:30" -> "HH:MM" (24h)."""
    if raw is None or not str(raw).strip():
        raise ValidationError("invalid_time", "A time is required.")
    text = str(raw).strip().lower().replace(".", "")
    m = re.search(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm|a m|p m)?\b", text)
    if not m:
        raise ValidationError("invalid_time", f"I couldn't understand the time '{raw}'.")
    hour, minute = int(m.group(1)), int(m.group(2) or 0)
    meridiem = (m.group(3) or "").replace(" ", "")
    if meridiem == "pm" and hour < 12:
        hour += 12
    elif meridiem == "am" and hour == 12:
        hour = 0
    elif not meridiem and 1 <= hour <= 7:
        hour += 12  # "at 3" in a clinic context means 3 PM
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValidationError("invalid_time", f"'{raw}' is not a valid time.")
    return f"{hour:02d}:{minute:02d}"


def spoken_time(hhmm: str) -> str:
    """14:30 -> '2:30 PM' (for TTS-friendly responses)."""
    h, m = map(int, hhmm.split(":"))
    suffix = "AM" if h < 12 else "PM"
    h12 = h % 12 or 12
    return f"{h12}:{m:02d} {suffix}" if m else f"{h12} {suffix}"


def spoken_date(d: date) -> str:
    return f"{d.strftime('%A')}, {d.day} {d.strftime('%B %Y')}"
