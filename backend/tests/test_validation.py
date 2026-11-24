from datetime import date

import pytest

from app.services.errors import ValidationError
from app.services.validation import (
    mask_phone, normalize_phone, parse_date, parse_time, phone_readback, spoken_time,
)

TODAY = date(2026, 11, 24)  # a Tuesday


@pytest.mark.parametrize("spoken,expected", [
    ("9876500001", "9876500001"),
    ("98765 00001", "9876500001"),
    ("(987) 650-0001", "9876500001"),
    ("+91 98765 00001", "9876500001"),
    ("09876500001", "9876500001"),
    ("nine eight seven six five zero zero zero zero one", "9876500001"),
    ("my number is nine eight seven six five double zero double zero one", "9876500001"),
    ("98765 oh oh oh oh 1", "9876500001"),
])
def test_normalize_phone_accepts_spoken_forms(spoken, expected):
    assert normalize_phone(spoken) == expected


@pytest.mark.parametrize("bad", ["", None, "12345", "call me maybe", "1" * 20])
def test_normalize_phone_rejects_invalid(bad):
    with pytest.raises(ValidationError) as exc:
        normalize_phone(bad)
    assert exc.value.code == "invalid_phone"


def test_readback_and_mask():
    assert phone_readback("9876500001") == "9 8 7 6 5, 0 0 0 0 1"
    assert mask_phone("9876500001") == "******0001"


@pytest.mark.parametrize("raw,expected", [
    ("2026-11-26", date(2026, 11, 26)),
    ("today", TODAY),
    ("tomorrow", date(2026, 11, 25)),
    ("day after tomorrow", date(2026, 11, 26)),
    ("friday", date(2026, 11, 27)),
    ("next tuesday", date(2026, 12, 1)),
    ("28 november", date(2026, 11, 28)),
    ("November 28th", date(2026, 11, 28)),
    ("5th of january", date(2027, 1, 5)),
    ("30/11/2026", date(2026, 11, 30)),
])
def test_parse_date(raw, expected):
    assert parse_date(raw, today=TODAY) == expected


def test_parse_date_rejects_past_and_garbage():
    with pytest.raises(ValidationError) as exc:
        parse_date("2026-11-01", today=TODAY)
    assert exc.value.code == "past_date"
    with pytest.raises(ValidationError) as exc:
        parse_date("whenever", today=TODAY)
    assert exc.value.code == "invalid_date"
    with pytest.raises(ValidationError):
        parse_date("2026-02-30", today=TODAY)


@pytest.mark.parametrize("raw,expected", [
    ("10", "10:00"), ("10 am", "10:00"), ("10:30 AM", "10:30"), ("2:30 pm", "14:30"),
    ("14:30", "14:30"), ("3", "15:00"), ("12 pm", "12:00"),
])
def test_parse_time(raw, expected):
    assert parse_time(raw) == expected


def test_spoken_time():
    assert spoken_time("14:30") == "2:30 PM"
    assert spoken_time("09:00") == "9 AM"
