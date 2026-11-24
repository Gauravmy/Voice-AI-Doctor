# Pipeline Description

> **DRAFT — rewrite this in your own words before submitting.**
> The assignment asks for a short, honest description *written by you*. This draft gives you the facts to work from. Change the wording, add what you learned, and delete this note.

---

My voice assistant is a Pipecat pipeline that runs once per browser call. The browser captures microphone audio with an AudioWorklet, converts it to 16 kHz PCM, and streams it over a WebSocket to a FastAPI server. There, Pipecat's `FastAPIWebsocketTransport` turns it into audio frames.

The frames go to **ElevenLabs Scribe realtime speech-to-text**. Silero VAD, plus Pipecat's turn detection, decides when the caller has finished speaking. The finished turn is added to the conversation context and sent to **Google Gemini**. Gemini has a receptionist system prompt and three function tools: `check_doctor_availability`, `book_appointment` and `cancel_appointment`.

When Gemini calls a tool, my Python handler queries or updates a **SQLite** database and returns structured JSON. Gemini turns that JSON into a spoken reply. The reply is streamed to **ElevenLabs text-to-speech**, and the audio goes back over the same WebSocket and plays in the browser. If the caller talks over the agent, Pipecat interrupts the speech and the browser drops the queued audio.

The caller is identified only by the phone number they say. I didn't want to rely on the LLM to follow the confirmation rule, so the booking and cancellation tools enforce it themselves. The first call returns a digit-by-digit read-back that the agent must confirm. Only a second call with the same, confirmed number can change the database.

Double booking is blocked by an atomic transaction, and also by a unique index in the database, so two callers cannot book the same slot. After each successful commit, an event is pushed to the dashboard over a second WebSocket, so the appointments table updates immediately.

**Honest notes:**
- I tested the full pipeline structure and its error handling against the real provider endpoints using invalid keys, and I tested the complete booking and cancellation flows with automated tests and a keyless mock mode. <!-- add: what you observed when you ran it with your real keys -->
- AI assistance was used to build this project. I reviewed the code and can explain each part.
