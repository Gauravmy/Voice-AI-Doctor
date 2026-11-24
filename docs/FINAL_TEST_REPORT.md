# Final Test Report

Date: 2026-11-24 · Machine: Windows 11, Python 3.11.9, Node 22.19.0 · Pipecat 1.17.0, Next.js 16.4.6

Every result below comes from commands that were actually run. Nothing is extrapolated.

## Summary

| Suite | Command | Result |
|---|---|---|
| Backend (pytest) | `cd backend; .venv\Scripts\python -m pytest -q` | **83 passed** (≈11–16 s) |
| Frontend (Vitest) | `cd frontend; npm test` | **20 passed** (3 files) |
| Frontend typecheck | `npm run typecheck` | clean |
| Frontend lint | `npm run lint` | clean (0 problems) |
| Frontend production build | `npm run build` | succeeded |
| Manual UI run (mock mode) | browser, `localhost:3000` + `:8000` | Scenario 1 completed; dashboard updated live |
| Live pipeline probe (invalid keys) | custom WebSocket client streaming silence | pipeline ran and every provider was reached; failure handled cleanly (details below) |
| Live pipeline with **real** keys | — | **Not run.** No API keys were available in this environment |

## Backend tests (83)

| File | Tests | What it covers |
|---|---|---|
| `test_validation.py` | 33 | Spoken phone formats (digits, words, "double/triple", +91, leading 0), invalid phones, read-back and masking, date parsing (ISO, today/tomorrow, weekdays, "28 November", dd/mm/yyyy), past/invalid dates, time parsing |
| `test_services.py` | 19 | Seed realism (≥8 doctors, booked slots), idempotent init, doctor search by alias/name/id, availability excludes booked slots, booking **persists** (checked from a new connection), booking by date+time, **double-booking prevention** (service and raw DB index), status CHECK constraint, invalid requests (phone/doctor/slot), slot must belong to doctor, past slots rejected, cancel frees the slot and allows rebooking, **wrong phone cannot cancel**, double cancel rejected, multiple appointments per phone, masking |
| `test_tools.py` | 15 | Exact tool names; availability by specialty, by name, errors, next-available suggestions; availability creates no appointment; **booking refused until the phone was read back** (even when `phone_confirmed=true` is sent first); a different number restarts the read-back; invalid phone; slot conflict returns alternatives; confirmation event (masked phone); cancellation with **multiple appointments**, single appointment, wrong phone, another caller's appointment ID; unknown tool and internal errors never raise |
| `test_api.py` | 10 | Health (mode + missing keys), stats/doctors/specialties/activity, availability endpoint (404/422), masked appointments, book → 409 duplicate → 404 wrong-phone cancel → cancel, invalid request bodies (422 + error codes), **dashboard WebSocket receives the booking event** |
| `test_integration.py` | 6 | Over the real `/ws/call` socket: **Scenario 1** booking (real DB slots offered, read-back, confirmation, DB row, dashboard push), **Scenario 2** availability only (no rows created), **Scenario 3** cancellation with two appointments, booking → cancellation round-trip, wrong-number correction + unknown number, **live Pipecat pipeline wiring** (built with fake keys: ElevenLabs STT, Gemini, ElevenLabs TTS present; exactly the 3 tools registered) |

### Integration: "the spoken phone number is used for identification"
- `test_booking_requires_phone_readback_first`: the stored `patient_phone` equals the spoken number.
- `test_cancel_cannot_target_someone_elses_appointment`: a confirmed caller cannot cancel an appointment that belongs to another number.
- No code path reads caller ID, cookies, browser identity or login. The phone number in the tool arguments is the only identity input.

## Frontend tests (20)

- `callReducer.test.ts` (8): phase transitions (idle → ringing → connecting → connected → ended), late events ignored, interim → final user transcript, streamed agent words then final, barge-in marks interrupted, booking + cancellation cards, speaking/tool/mute state, non-fatal vs fatal errors.
- `dashboard.test.tsx` (7): **dashboard loading** (stats, **doctor listing**, **available slot** chips, masked phones, mock badge), **API error states** (network and HTTP 500), specialty filter, **booking update** (WebSocket push → refetch → highlighted row), **cancellation update**, availability indicator rules.
- `callPanel.test.tsx` (5): **start/end call states** (socket closed, `end_call` sent), **transcript rendering** + typed input in mock mode, confirmation card only after the backend confirms, fatal error display, microphone permission denied.

## Manual verification in the browser (mock mode)

Both servers were run (`uvicorn` :8000, `next dev` :3000) and the call was placed through the UI:

1. "Hello, I want to book an appointment with a cardiologist." → *"Certainly. May I know your preferred date?"*
2. "tomorrow" → *"On Wednesday, 25 November 2026, Dr. Ananya Rao has 9 AM, 10 AM and 10:30 AM…"* (real free slots)
3. "10:30 am please" → name → "nine eight seven six five four three two one zero" → *"I have 9 8 7 6 5, 4 3 2 1 0, for Dr. Ananya Rao on … at 10:30 AM. Is that correct?"*
4. "yes, that's correct" → *"Your appointment is confirmed … ID A P T - U 6 6 E 7 L"*

Result: the confirmation card appeared, and the new row `APT-U66E7L` (voice icon, `******3210`) appeared at the top of the Appointments table, highlighted, without a page reload. Ending the call showed "Call ended / Offline". The mobile viewport (375 px) has no page-level horizontal overflow.

## Live pipeline probe (real Pipecat, invalid keys)

Server started with `VOICE_MODE=live` and fake keys. A WebSocket client sent 16 kHz silence, as the browser would. Observed:

- The pipeline started. The transport accepted the client and the agent sent `call_state: connected`.
- **ElevenLabs STT** connected and rejected the key: "You must be authenticated to use this endpoint."
- **ElevenLabs TTS** connected and was closed with "1008 Invalid API key".
- **Gemini** answered `400 API key not valid`, and Pipecat marked the LLM service unusable.
- The browser received named errors ("The speech-to-text (ElevenLabs) service reported an error; retrying.", then a fatal "The language model (Gemini) service stopped working … The call has been ended."). The call closed normally (code 1000), and **the server kept serving requests** (`/api/health` → 200).
- A connection from a disallowed `Origin` was rejected with close code 1008.

This shows the pipeline wiring and the failure handling work against the real provider endpoints. **It does not show** speech quality, latency or Gemini's conversation behaviour. Those need real keys (see "Still to verify").

## Bugs found by testing and fixed

1. Specialty matching used substring search, so "appoint**ment**" matched **ENT**. Fixed with word-boundary regexes (`doctor_service.resolve_specialty`).
2. An ISO date in the middle of a sentence was not recognised. `parse_date` now searches for it.
3. Seeding was slow (one commit per slot insert). It now runs in a single transaction, and the test suite dropped from 141 s to 11 s.
4. Errors repeated generically and the call kept running with a dead LLM. Errors are now reported once per service, with the service named, and the call ends cleanly when a service becomes unusable.
5. `WorkerRunner.run(worker)` is deprecated in Pipecat 1.17. Replaced with `add_workers()` + `run()`.

## Still to verify (requires your API keys)

- [ ] Put real keys in `backend/.env`, restart, and confirm `/api/health` shows `voice_mode: live`.
- [ ] Run Scenarios 1–3 by voice (see `DEMO_SCRIPT.md`). Check that Gemini follows the read-back flow and reads the appointment ID.
- [ ] If your Gemini key has no access to the default model, set `GEMINI_MODEL` to one that it does.
- [ ] If realtime STT is not available on your ElevenLabs plan, set `ELEVENLABS_STT_MODE=batch`.
