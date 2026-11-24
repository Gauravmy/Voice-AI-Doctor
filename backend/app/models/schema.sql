-- SQLite schema for the clinic. Executed idempotently on every start-up.
-- Integrity rules live in the database itself, not only in Python code.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS specialties (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL UNIQUE,
    description TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS doctors (
    id               TEXT PRIMARY KEY,                -- e.g. DOC-001
    name             TEXT NOT NULL,
    specialty_id     INTEGER NOT NULL REFERENCES specialties(id),
    years_experience INTEGER NOT NULL DEFAULT 0,
    room             TEXT NOT NULL DEFAULT '',
    bio              TEXT NOT NULL DEFAULT ''
);

-- One row per bookable time slot. A slot is "available" when it has no
-- appointment in status 'booked'.
CREATE TABLE IF NOT EXISTS slots (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    doctor_id  TEXT NOT NULL REFERENCES doctors(id),
    slot_date  TEXT NOT NULL,                         -- YYYY-MM-DD
    start_time TEXT NOT NULL,                         -- HH:MM (24h)
    end_time   TEXT NOT NULL,                         -- HH:MM (24h)
    UNIQUE (doctor_id, slot_date, start_time)
);

CREATE TABLE IF NOT EXISTS appointments (
    id            TEXT PRIMARY KEY,                   -- e.g. APT-7K3Q9M
    slot_id       INTEGER NOT NULL REFERENCES slots(id),
    doctor_id     TEXT NOT NULL REFERENCES doctors(id),
    patient_name  TEXT NOT NULL DEFAULT '',
    patient_phone TEXT NOT NULL,                      -- digits only, as spoken by caller
    reason        TEXT NOT NULL DEFAULT '',
    status        TEXT NOT NULL DEFAULT 'booked'
                  CHECK (status IN ('booked', 'cancelled')),
    source        TEXT NOT NULL DEFAULT 'voice'
                  CHECK (source IN ('voice', 'api', 'seed')),
    created_at    TEXT NOT NULL,                      -- ISO-8601 UTC
    updated_at    TEXT NOT NULL,
    cancelled_at  TEXT,
    CHECK ((status = 'cancelled') = (cancelled_at IS NOT NULL))
);

-- The double-booking guard: at most ONE active ('booked') appointment per slot.
-- Cancelled appointments do not block the slot, so it can be re-booked.
CREATE UNIQUE INDEX IF NOT EXISTS ux_appointments_active_slot
    ON appointments (slot_id) WHERE status = 'booked';

CREATE INDEX IF NOT EXISTS ix_appointments_phone ON appointments (patient_phone);
CREATE INDEX IF NOT EXISTS ix_slots_doctor_date ON slots (doctor_id, slot_date);

-- Audit trail of booking / cancellation activity (drives the activity feed).
CREATE TABLE IF NOT EXISTS activity_log (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    appointment_id TEXT NOT NULL REFERENCES appointments(id),
    action         TEXT NOT NULL CHECK (action IN ('booked', 'cancelled')),
    source         TEXT NOT NULL,
    created_at     TEXT NOT NULL
);
