"""Pydantic request/response models for the REST API."""

from __future__ import annotations

from pydantic import BaseModel, Field


class BookAppointmentRequest(BaseModel):
    doctor_id: str = Field(min_length=3, max_length=20, examples=["DOC-001"])
    slot_id: int | None = Field(default=None, ge=1)
    date: str | None = Field(default=None, examples=["2026-11-25"])
    start_time: str | None = Field(default=None, examples=["10:30"])
    patient_phone: str = Field(min_length=1, max_length=40, examples=["98765 00001"])
    patient_name: str = Field(default="", max_length=80)
    reason: str = Field(default="", max_length=200)


class CancelAppointmentRequest(BaseModel):
    patient_phone: str = Field(min_length=1, max_length=40)


class ErrorBody(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorBody
