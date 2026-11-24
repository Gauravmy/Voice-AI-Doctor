"""Clinic-local time helpers. Kept in one place so tests can reason about "today"."""

from __future__ import annotations

from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from app.config import get_settings


def clinic_tz() -> ZoneInfo:
    return ZoneInfo(get_settings().clinic_timezone)


def now_local() -> datetime:
    return datetime.now(clinic_tz())


def today_local() -> date:
    return now_local().date()


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
