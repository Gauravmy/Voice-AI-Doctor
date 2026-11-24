/**
 * Pure state machine for a call. Kept free of browser APIs so it is unit-tested.
 *
 *   idle -> ringing (requesting mic / opening socket) -> connecting (socket open,
 *   waiting for the backend's call_state) -> connected -> ended
 *   any state -> error
 */
import type { CallServerEvent, ConfirmationCard } from "@/types";

export type CallPhase = "idle" | "ringing" | "connecting" | "connected" | "ended" | "error";

export interface TranscriptEntry {
  id: number;
  role: "user" | "agent";
  text: string;
  final: boolean;
  interrupted?: boolean;
  mock?: boolean;
}

export interface CallState {
  phase: CallPhase;
  mode: "live" | "mock" | null;
  agentState: "idle" | "speaking" | "listening" | "thinking";
  userSpeaking: boolean;
  muted: boolean;
  transcript: TranscriptEntry[];
  confirmations: ConfirmationCard[];
  lastTool: string | null;
  error: string | null;
  startedAt: number | null;
  endedAt: number | null;
  nextId: number;
}

export const initialCallState: CallState = {
  phase: "idle",
  mode: null,
  agentState: "idle",
  userSpeaking: false,
  muted: false,
  transcript: [],
  confirmations: [],
  lastTool: null,
  error: null,
  startedAt: null,
  endedAt: null,
  nextId: 1,
};

export type CallAction =
  | { type: "dial" }
  | { type: "socket_open" }
  | { type: "server"; event: CallServerEvent; now: number }
  | { type: "toggle_mute" }
  | { type: "hangup"; now: number }
  | { type: "failed"; message: string; now: number }
  | { type: "reset" };

/** Index of the last non-final entry for a role, or -1. */
function pendingIndex(list: TranscriptEntry[], role: "user" | "agent"): number {
  for (let i = list.length - 1; i >= 0; i--) {
    if (list[i].role === role) return list[i].final ? -1 : i;
  }
  return -1;
}

function upsert(state: CallState, role: "user" | "agent", text: string, final: boolean,
                extra: Partial<TranscriptEntry> = {}, append = false): CallState {
  const list = [...state.transcript];
  const idx = pendingIndex(list, role);
  if (idx >= 0) {
    const prev = list[idx];
    const merged = append ? `${prev.text} ${text}`.replace(/\s+/g, " ").trim() : text;
    list[idx] = { ...prev, text: merged, final, ...extra };
    return { ...state, transcript: list };
  }
  list.push({ id: state.nextId, role, text: text.trim(), final, ...extra });
  return { ...state, transcript: list, nextId: state.nextId + 1 };
}

function applyServerEvent(state: CallState, event: CallServerEvent, now: number): CallState {
  switch (event.type) {
    case "call_state":
      return { ...state, phase: "connected", mode: event.mode, startedAt: now, agentState: "listening" };
    case "transcript":
      if (event.role === "agent") {
        return { ...upsert(state, "agent", event.text, event.final,
          { mock: event.mock, interrupted: event.interrupted }), agentState: event.mock ? "listening" : state.agentState };
      }
      return upsert(state, "user", event.text, event.final);
    case "agent_text":
      return upsert(state, "agent", event.text, false, {}, true);
    case "agent_state":
      return { ...state, agentState: event.state };
    case "user_state":
      return { ...state, userSpeaking: event.state === "speaking",
        agentState: event.state === "silent" ? "thinking" : state.agentState };
    case "interrupt": {
      const idx = pendingIndex(state.transcript, "agent");
      if (idx < 0) return state;
      const list = [...state.transcript];
      list[idx] = { ...list[idx], final: true, interrupted: true };
      return { ...state, transcript: list };
    }
    case "tool_call":
      return { ...state, lastTool: event.tool, agentState: "thinking" };
    case "tool_result":
      return state;
    case "booking_confirmed":
    case "cancellation_confirmed": {
      const card: ConfirmationCard = {
        kind: event.type === "booking_confirmed" ? "booked" : "cancelled",
        ...event.appointment,
      };
      return { ...state, confirmations: [card, ...state.confirmations] };
    }
    case "error":
      return event.fatal
        ? { ...state, phase: "error", error: event.message, endedAt: now }
        : { ...state, error: event.message };
    default:
      return state;
  }
}

export function callReducer(state: CallState, action: CallAction): CallState {
  switch (action.type) {
    case "dial":
      return { ...initialCallState, phase: "ringing" };
    case "socket_open":
      return state.phase === "ringing" ? { ...state, phase: "connecting" } : state;
    case "server":
      if (state.phase === "ended" || state.phase === "idle") return state;
      return applyServerEvent(state, action.event, action.now);
    case "toggle_mute":
      return { ...state, muted: !state.muted };
    case "hangup":
      if (state.phase === "error") return state;
      return { ...state, phase: "ended", agentState: "idle", userSpeaking: false, endedAt: action.now };
    case "failed":
      return { ...state, phase: "error", error: action.message, agentState: "idle", endedAt: action.now };
    case "reset":
      return initialCallState;
    default:
      return state;
  }
}
