# Demo Script (≤ 3 minutes)

The assignment video needs **one complete booking flow**. The plan below fits in about 2:30. Scenarios 2 and 3 are optional extras.

## Before recording

1. `backend/.env` has real `GOOGLE_API_KEY` and `ELEVENLABS_API_KEY`.
2. Reset the data so the screen is clean: `cd backend; .venv\Scripts\python -m app.data.reset`
3. Start the backend (`uvicorn app.main:app --port 8000`) and the frontend (`npm run dev`).
4. Open http://localhost:3000 in Chrome. Check that the header badge says **Live voice · Gemini + ElevenLabs**. Use headphones to avoid echo.
5. Check which cardiology dates have slots (Doctors panel → "Next:"), so you can name a date that works.

## Recording plan

| Time | Show / say |
|---|---|
| 0:00–0:15 | Dashboard tour: stats, doctors with availability, appointments with masked numbers. "The voice agent runs on Pipecat with ElevenLabs and Gemini." |
| 0:15–0:20 | Click **Start call**. Show the ringing → connected states. Maya greets you. |
| 0:20 | **You:** "Hello, I want to book an appointment with a cardiologist." |
| | **Maya:** "Certainly. May I know your preferred date?" |
| | **You:** "Tomorrow." *(or the date you checked)* |
| | **Maya:** reads real free slots, e.g. "Dr. Ananya Rao has 9 AM, 10 AM and 10:30 AM…" |
| | **You:** "10:30, please." |
| | **Maya:** asks for the patient's name. **You:** "Asha Patel." |
| | **Maya:** asks for your phone number. **You:** "Nine eight seven six five, four three two one zero." |
| | **Maya:** "I have 9 8 7 6 5, 4 3 2 1 0, for Dr. Rao on … at 10:30 AM. Is that correct?" |
| | **You:** "Yes." |
| | **Maya:** "Your appointment is confirmed… your appointment ID is A P T …" |
| ~1:45 | Point at the **confirmation card** and the new **highlighted row** in Appointments (voice icon, masked number). Point out that the slot count dropped. |
| ~2:00 | End the call (timer, end state). Optional: show interrupting Maya mid-sentence (barge-in). |
| ~2:15–2:45 | Explain in a sentence or two that the phone number is the only identity, that the read-back is enforced in code, and that the database blocks double booking. |

## Optional: Scenario 2 (availability only)
**You:** "Is Dr. Thompson available on Thursday?" → Maya lists slots. **You:** "No thanks, just checking." → nothing is added to Appointments.

## Optional: Scenario 3 (cancellation with two appointments)
**You:** "I'd like to cancel my appointment." → "Nine eight seven six five, zero zero zero zero one." → Maya reads it back → "Yes" → Maya lists **two** appointments (Dr. Rao and Dr. Thompson) and asks which one → "The one with Dr. Thompson" → "Shall I cancel it?" → "Yes" → the row turns **Cancelled** (red highlight).

## If something goes wrong on camera
- The agent doesn't hear you: check that the mic badge shows "Mic on" and the waveform moves.
- A red error names a service (for example "language model (Gemini) … stopped working"). Check that key, its quota, and `GEMINI_MODEL`.
- No keys at all: the app runs in **mock mode** (text only, clearly labelled). This does not count as the voice demo.
