# Frontend: Voice AI Appointment Dashboard

Next.js (App Router) + TypeScript + Tailwind CSS. See the [root README](../README.md) for the full project.

```powershell
npm install
copy .env.example .env.local   # NEXT_PUBLIC_API_URL=http://localhost:8000
npm run dev                    # http://localhost:3000
npm test                       # Vitest + Testing Library
npm run typecheck; npm run lint; npm run build
```

| Path | Purpose |
|---|---|
| `components/Dashboard.tsx` | Page layout: overview, activity, doctors, appointments, call panel |
| `components/call/*` | Phone-style call UI, transcript, waveform, confirmation card |
| `hooks/useVoiceCall.ts` | `/ws/call` connection: mic audio out, agent audio + events in |
| `hooks/useDashboardData.ts` | REST loading + `/ws/dashboard` live updates and row highlighting |
| `lib/callReducer.ts` | Pure call state machine (unit-tested) |
| `lib/audio.ts`, `public/worklets/mic-processor.js` | 16 kHz PCM16 capture and 24 kHz PCM16 playback with barge-in flush |
