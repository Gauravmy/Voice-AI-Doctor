# Architecture

## Components

```mermaid
flowchart TB
    subgraph FE["frontend/ (Next.js, client-rendered)"]
        D["Dashboard.tsx"] --> UDD["useDashboardData<br/>REST + /ws/dashboard"]
        D --> CP["CallPanel.tsx"] --> UVC["useVoiceCall<br/>/ws/call"]
        UVC --> AUD["lib/audio.ts<br/>MicCapture (AudioWorklet) · PcmPlayer"]
        UVC --> RED["lib/callReducer.ts<br/>pure call state machine"]
    end

    subgraph BE["backend/app (FastAPI)"]
        MAIN["main.py"] --> ROUTES["api/routes.py"]
        MAIN --> AGENT["voice/agent.py<br/>live or mock?"]
        AGENT --> PIPE["voice/pipeline.py<br/>Pipecat"]
        AGENT --> MOCK["voice/mock_agent.py"]
        PIPE --> TOOLS["voice/tools.py<br/>ClinicTools"]
        MOCK --> TOOLS
        ROUTES --> SVC
        TOOLS --> SVC["services/<br/>appointment_service · doctor_service<br/>validation · events"]
        SVC --> DBM["database.py + models/schema.sql"]
    end

    DBM --> DB[("SQLite")]
    UDD <--> MAIN
    UVC <--> MAIN
    PIPE <--> EXT["ElevenLabs STT/TTS<br/>Google Gemini"]
```

## Layering rules

| Layer | May call | Never |
|---|---|---|
| `api/routes.py` (HTTP) | services | SQL directly |
| `voice/tools.py` (LLM tools) | services | SQL directly, Pipecat internals (only via `register_tools`) |
| `services/*` | `database.py`, `events.bus` | FastAPI, Pipecat |
| `database.py` / `schema.sql` | — | business logic |

Because both the REST API and the voice tools go through `appointment_service`, they share one implementation of the booking rules.

## Call sequence (booking)

```mermaid
sequenceDiagram
    autonumber
    participant B as Browser
    participant P as Pipecat pipeline
    participant G as Gemini
    participant T as ClinicTools
    participant DB as SQLite
    participant D as Dashboard WS

    B->>P: PCM16 audio (16 kHz, 20 ms frames)
    P->>P: ElevenLabs STT + Silero VAD → user turn
    P->>G: context + tools
    G->>T: check_doctor_availability(date, specialty)
    T->>DB: SELECT free slots
    T-->>G: {status: available, doctors[].available_slots}
    G-->>P: "Dr. Rao has 9 AM, 10 AM ..."
    P-->>B: ElevenLabs TTS audio + agent_text events
    Note over B,G: caller picks a slot, gives name and phone
    G->>T: book_appointment(..., phone_confirmed=false)
    T-->>G: {status: confirmation_required, phone_readback}
    G-->>B: "I have 9 8 7 6 5, 4 3 2 1 0 ... is that correct?"
    B->>P: "Yes"
    G->>T: book_appointment(..., phone_confirmed=true)
    T->>DB: BEGIN IMMEDIATE · check slot · INSERT · COMMIT
    T-->>B: booking_confirmed event (confirmation card)
    T->>D: appointment.booked (via event bus)
    T-->>G: {status: booked, appointment_id}
    G-->>B: "Your appointment is confirmed, ID A P T ..."
```

## Wire protocol (`/ws/call`)

| Direction | Frame | Content |
|---|---|---|
| browser → server | binary | PCM16 LE mono 16 kHz microphone audio |
| browser → server | text | `{"type":"end_call"}` · mock mode: `{"type":"user_text","text":…}` |
| server → browser | binary | PCM16 LE mono 24 kHz agent speech |
| server → browser | text | `call_state`, `transcript`, `agent_text`, `agent_state`, `user_state`, `interrupt`, `tool_call`, `tool_result`, `booking_confirmed`, `cancellation_confirmed`, `error` |

## Concurrency and consistency

- Each call has its own pipeline and its own `ClinicTools` (per-call confirmation state). Calls do not share any state except the database.
- Tool handlers run their SQLite work with `asyncio.to_thread` so the audio pipeline is never blocked.
- `BEGIN IMMEDIATE` serialises writers. If two callers race for the same slot, one wins. The other gets `slot_unavailable` and alternative slots, and the partial unique index guarantees this even if the code were bypassed.
- The event bus publishes **after commit**, so the dashboard never shows an uncommitted booking.

## Failure handling

| Failure | Behaviour |
|---|---|
| Missing API keys | `auto` mode falls back to the labelled mock; `live` mode refuses the call with a clear error |
| Provider rejects key / quota | `on_pipeline_error` → named error to UI once; if the processor is unusable the call ends cleanly; server keeps running |
| Tool exception | Caught in `ClinicTools.call` → `internal_error` result; the agent apologises |
| Tool hangs | `register_function(..., timeout_secs=10)` |
| Caller silent too long | `idle_timeout_secs` (120 s) cancels the pipeline |
| Very long call | `session_timeout` (600 s) |
| Browser closes tab | `on_client_disconnected` → `worker.cancel()` |
| Disallowed `Origin` | WebSocket rejected (1008) |
