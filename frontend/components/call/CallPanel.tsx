"use client";

import { AlertTriangle, Mic, MicOff, Phone, PhoneOff, RotateCcw, SendHorizontal, Wifi, WifiOff } from "lucide-react";
import { useState } from "react";

import { ConfirmationCard } from "@/components/call/ConfirmationCard";
import { Transcript } from "@/components/call/Transcript";
import { Waveform } from "@/components/call/Waveform";
import { Badge } from "@/components/ui/Badge";
import { useVoiceCall } from "@/hooks/useVoiceCall";
import type { CallPhase } from "@/lib/callReducer";
import { cn, formatDuration } from "@/lib/format";

const PHASE_LABEL: Record<CallPhase, string> = {
  idle: "Ready to call",
  ringing: "Ringing…",
  connecting: "Connecting…",
  connected: "Connected",
  ended: "Call ended",
  error: "Call failed",
};

const AGENT_LABEL = {
  idle: "",
  listening: "Listening",
  speaking: "Speaking",
  thinking: "Thinking…",
} as const;

export function CallPanel({ mode, clinicName }: { mode: "live" | "mock" | null; clinicName: string }) {
  const { state, elapsed, levels, start, end, toggleMute, sendText, reset } = useVoiceCall(mode);
  const [draft, setDraft] = useState("");
  const inCall = state.phase === "ringing" || state.phase === "connecting" || state.phase === "connected";
  const connected = state.phase === "connected";
  const isMock = (state.mode ?? mode) === "mock";
  const speaking = state.agentState === "speaking";

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    sendText(draft);
    setDraft("");
  };

  return (
    <section aria-label="Voice call" className="overflow-hidden rounded-[28px] border border-slate-200 bg-white shadow-xl shadow-slate-900/[0.06]">
      {/* Phone header */}
      <div className="relative bg-gradient-to-b from-indigo-600 to-indigo-700 px-5 pb-6 pt-5 text-white">
        <div className="flex items-center justify-between text-[11px] text-indigo-100">
          <span className="flex items-center gap-1.5">
            {connected ? <Wifi className="size-3.5" /> : <WifiOff className="size-3.5 opacity-70" />}
            <span data-testid="connection-status">{connected ? "Connected" : inCall ? "Connecting" : "Offline"}</span>
          </span>
          <span className="flex items-center gap-1.5" data-testid="mic-status">
            {isMock ? "Text input (mock)" : state.muted ? <><MicOff className="size-3.5" />Muted</> :
              connected ? <><Mic className="size-3.5" />Mic on</> : "Mic off"}
          </span>
        </div>

        <div className="mt-5 flex flex-col items-center text-center">
          <div className="relative">
            {(state.phase === "ringing" || state.phase === "connecting") && (
              <>
                <span className="ring-pulse absolute inset-0 rounded-full bg-white/30" />
                <span className="ring-pulse absolute inset-0 rounded-full bg-white/20 [animation-delay:600ms]" />
              </>
            )}
            <span className={cn("relative grid size-16 place-items-center rounded-full bg-white/15 text-xl font-semibold ring-1 ring-white/30 transition",
              speaking && "ring-4 ring-white/50")}>M</span>
          </div>
          <p className="mt-3 text-base font-semibold">Maya · {clinicName}</p>
          <p className="text-xs text-indigo-100" data-testid="call-phase">
            {PHASE_LABEL[state.phase]}
            {connected && ` · ${formatDuration(elapsed)}`}
          </p>
          {connected && AGENT_LABEL[state.agentState] && (
            <span className="mt-2 rounded-full bg-white/15 px-2.5 py-0.5 text-[11px]">{AGENT_LABEL[state.agentState]}</span>
          )}
        </div>
        <div className="mt-3">
          <Waveform level={speaking ? levels.agent : levels.mic} active={connected && !isMock}
            color={speaking ? "#ffffff" : "#c7d2fe"} />
        </div>
      </div>

      {isMock && (
        <div className="flex items-start gap-2 border-b border-amber-200 bg-amber-50 px-4 py-2.5 text-[11px] leading-snug text-amber-900">
          <AlertTriangle className="mt-0.5 size-3.5 shrink-0" />
          <span><b>Development mock mode.</b> No Gemini or ElevenLabs calls are made: a rule-based receptionist replies in text using the same booking tools and database. Add API keys to enable real voice.</span>
        </div>
      )}

      {/* Transcript */}
      <div className="h-[300px] overflow-y-auto bg-slate-50/60 px-4 py-4">
        <Transcript entries={state.transcript} />
      </div>

      {state.confirmations.length > 0 && (
        <div className="space-y-2 border-t border-slate-100 px-4 py-3">
          {state.confirmations.map((c) => <ConfirmationCard key={c.kind + c.appointment_id} card={c} />)}
        </div>
      )}

      {state.error && (
        <p role="alert" className="flex items-start gap-2 border-t border-rose-100 bg-rose-50 px-4 py-2.5 text-xs text-rose-800">
          <AlertTriangle className="mt-0.5 size-3.5 shrink-0" />{state.error}
        </p>
      )}

      {isMock && connected && (
        <form onSubmit={submit} className="flex gap-2 border-t border-slate-100 px-4 py-3">
          <input value={draft} onChange={(e) => setDraft(e.target.value)} aria-label="Type what the caller says"
            placeholder="Type what the caller says…"
            className="h-9 min-w-0 flex-1 rounded-lg border border-slate-200 px-3 text-sm outline-none focus:border-indigo-400 focus:ring-2 focus:ring-indigo-100" />
          <button type="submit" aria-label="Send" className="grid size-9 place-items-center rounded-lg bg-indigo-600 text-white transition hover:bg-indigo-700">
            <SendHorizontal className="size-4" />
          </button>
        </form>
      )}

      {/* Controls */}
      <div className="flex items-center justify-center gap-4 border-t border-slate-100 px-5 py-4">
        {inCall ? (
          <>
            {!isMock && (
              <button onClick={toggleMute} disabled={!connected} aria-pressed={state.muted}
                aria-label={state.muted ? "Unmute microphone" : "Mute microphone"}
                className={cn("grid size-12 place-items-center rounded-full ring-1 transition disabled:opacity-40",
                  state.muted ? "bg-slate-900 text-white ring-slate-900" : "bg-white text-slate-700 ring-slate-200 hover:bg-slate-50")}>
                {state.muted ? <MicOff className="size-5" /> : <Mic className="size-5" />}
              </button>
            )}
            <button onClick={end} aria-label="End call"
              className="grid size-14 place-items-center rounded-full bg-rose-600 text-white shadow-lg shadow-rose-600/30 transition hover:bg-rose-700 active:scale-95">
              <PhoneOff className="size-6" />
            </button>
          </>
        ) : (
          <div className="flex items-center gap-3">
            <button onClick={start} disabled={!mode} aria-label="Start call"
              className="flex h-12 items-center gap-2 rounded-full bg-emerald-600 px-6 text-sm font-medium text-white shadow-lg shadow-emerald-600/30 transition hover:bg-emerald-700 active:scale-95 disabled:opacity-50">
              <Phone className="size-4" />
              {state.phase === "idle" ? "Start call" : "Call again"}
            </button>
            {(state.phase === "ended" || state.phase === "error") && (
              <button onClick={reset} aria-label="Clear call" className="grid size-10 place-items-center rounded-full text-slate-500 ring-1 ring-slate-200 hover:bg-slate-50">
                <RotateCcw className="size-4" />
              </button>
            )}
          </div>
        )}
      </div>
      <div className="flex justify-center border-t border-slate-100 bg-slate-50/60 px-4 py-2">
        <Badge tone={isMock ? "amber" : "indigo"}>
          {isMock ? "Mock agent · text only" : "Pipecat · ElevenLabs STT → Gemini → ElevenLabs TTS"}
        </Badge>
      </div>
    </section>
  );
}
