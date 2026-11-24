# Implementation Checklist & Requirement Map

Legend: ✅ done and verified by tests or a manual run · 🔑 needs your API keys to verify · 📝 needs your action

## Phases

| Phase | Status |
|---|---|
| 1 Workspace inspection & architecture | ✅ (empty workspace; Python 3.11.9, Node 22.19, Git; ports 3000/8000 free; Pipecat 1.17 APIs read from installed source) |
| 2 Backend, SQLite, availability | ✅ |
| 3 Booking & cancellation tools | ✅ |
| 4 Pipecat voice pipeline | ✅ built + run against real endpoints with invalid keys · 🔑 real conversation |
| 5 Gemini & ElevenLabs integration | ✅ wired, auth path exercised · 🔑 real conversation |
| 6 Frontend dashboard | ✅ |
| 7 Real-time browser voice connection | ✅ protocol, mic worklet, player · 🔑 audio round-trip with real TTS |
| 8 End-to-end testing | ✅ 83 backend + 20 frontend tests, manual UI run |
| 9 UI polish & bonus | ✅ |
| 10 Docs & demo prep | ✅ · 📝 rewrite PIPELINE_DESCRIPTION in your words, record video |

## Requirement → file map

| Requirement | Implementation | Tests |
|---|---|---|
| Pipecat pipeline STT → LLM → TTS | `backend/app/voice/pipeline.py` | `test_integration.py::test_live_pipeline_wiring_without_network` |
| ElevenLabs STT / TTS | `_build_stt`, `_build_tts` in `pipeline.py` | same |
| Gemini LLM | `_build_llm` in `pipeline.py`, `prompts.py` | same |
| 3 exact tool names registered | `voice/tools.py` (`TOOL_DEFINITIONS`, `register_tools`) | `test_tools.py::test_exact_tool_names`, wiring test |
| check_doctor_availability | `ClinicTools.check_doctor_availability` | `test_tools.py` (5 tests) |
| book_appointment + read-back + confirmation | `ClinicTools.book_appointment` | `test_tools.py`, `test_integration.py` scenario 1 |
| cancel_appointment + multi-appointment | `ClinicTools.cancel_appointment` | `test_tools.py`, scenario 3 |
| Phone-only identity | `services/validation.normalize_phone`, tools | `test_cancel_cannot_target_someone_elses_appointment` |
| No double booking | `schema.sql` partial unique index, `appointment_service.book_appointment` | `test_services.py` (2 tests), `test_api.py` 409 |
| Persistent SQLite + seed (≥8 doctors, booked slots, demo appts) | `database.py`, `data/seed.py` | `test_seed_data_is_realistic`, `test_init_db_is_idempotent` |
| Valid status & transitions, timestamps | `schema.sql` CHECKs, `cancel_appointment` | `test_status_check_constraint`, `test_cancel_twice_is_rejected` |
| Dashboard: overview / doctors / appointments / call | `frontend/components/**` | `dashboard.test.tsx`, `callPanel.test.tsx` |
| Masked phone numbers | `appointment_service.public_view` | `test_public_view_masks_patient_details`, `test_appointments_are_masked` |
| Live dashboard updates | `services/events.py`, `/ws/dashboard`, `useDashboardData` | `test_dashboard_websocket_receives_booking_event`, frontend update tests |
| Call UI states, timer, mute, transcript, waveform, card | `components/call/*`, `lib/callReducer.ts`, `hooks/useVoiceCall.ts` | `callReducer.test.ts`, `callPanel.test.tsx` |
| Silero VAD | `LLMUserAggregatorParams(vad_analyzer=SileroVADAnalyzer(...))` | wiring test (model loads) |
| Env config, no hardcoded keys, `.env.example` | `config.py`, `backend/.env.example`, `frontend/.env.example`, `.gitignore` | `test_health_reports_mock_mode` |
| Mock mode, clearly labelled | `voice/mock_agent.py`, UI banner/badges | `test_integration.py` (asserts `mock: true`) |
| Error handling (timeouts, invalid input, API failure) | `main.py` handlers, `register_function(timeout_secs)`, `on_pipeline_error` | `test_invalid_booking_requests`, live probe in test report |

## Your remaining steps

1. 📝 Add your keys to `backend/.env` (copy from `.env.example`) and run the three scenarios by voice.
2. 📝 Rewrite `docs/PIPELINE_DESCRIPTION.md` in your own words.
3. 📝 Record the video (≤ 3 min) following `docs/DEMO_SCRIPT.md`.
4. 📝 Decide on repository visibility, then create the GitHub repo and push. Nothing has been committed or pushed yet.
5. 📝 Submit through the Google Form named in the assignment email.
