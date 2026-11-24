import { describe, expect, it } from "vitest";

import { callReducer, initialCallState, type CallAction, type CallState } from "@/lib/callReducer";
import type { CallServerEvent } from "@/types";

const run = (actions: CallAction[], start: CallState = initialCallState) => actions.reduce(callReducer, start);
const server = (event: CallServerEvent): CallAction => ({ type: "server", event, now: 1000 });

describe("call state machine", () => {
  it("goes idle -> ringing -> connecting -> connected -> ended", () => {
    let s = run([{ type: "dial" }]);
    expect(s.phase).toBe("ringing");
    s = run([{ type: "socket_open" }], s);
    expect(s.phase).toBe("connecting");
    s = run([server({ type: "call_state", state: "connected", mode: "live" })], s);
    expect(s).toMatchObject({ phase: "connected", mode: "live", startedAt: 1000 });
    s = run([{ type: "hangup", now: 5000 }], s);
    expect(s).toMatchObject({ phase: "ended", endedAt: 5000 });
  });

  it("ignores server events after the call ended", () => {
    const s = run([{ type: "dial" }, { type: "hangup", now: 1 }, server({ type: "agent_text", text: "late" })]);
    expect(s.transcript).toHaveLength(0);
  });

  it("replaces an interim user transcript with the final one", () => {
    const s = run([
      { type: "dial" },
      server({ type: "transcript", role: "user", text: "I want to", final: false }),
      server({ type: "transcript", role: "user", text: "I want to book", final: false }),
      server({ type: "transcript", role: "user", text: "I want to book a cardiologist", final: true }),
    ]);
    expect(s.transcript).toEqual([
      expect.objectContaining({ role: "user", text: "I want to book a cardiologist", final: true }),
    ]);
  });

  it("streams agent words and then finalises the turn", () => {
    const s = run([
      { type: "dial" },
      server({ type: "agent_text", text: "Certainly." }),
      server({ type: "agent_text", text: "May I know" }),
      server({ type: "transcript", role: "agent", text: "Certainly. May I know your preferred date?", final: true }),
      server({ type: "transcript", role: "user", text: "Tomorrow", final: true }),
      server({ type: "agent_text", text: "Let me check." }),
    ]);
    expect(s.transcript.map((t) => [t.role, t.text, t.final])).toEqual([
      ["agent", "Certainly. May I know your preferred date?", true],
      ["user", "Tomorrow", true],
      ["agent", "Let me check.", false],
    ]);
  });

  it("marks the agent turn as interrupted on barge-in", () => {
    const s = run([{ type: "dial" }, server({ type: "agent_text", text: "Dr Rao has" }), server({ type: "interrupt" })]);
    expect(s.transcript[0]).toMatchObject({ final: true, interrupted: true });
  });

  it("adds booking and cancellation confirmation cards", () => {
    const appt = {
      appointment_id: "APT-ABC234", doctor_name: "Dr. Ananya Rao", date: "2026-11-25",
      start_time: "10:30", patient_phone: "******3210",
    };
    const s = run([
      { type: "dial" },
      server({ type: "booking_confirmed", appointment: appt }),
      server({ type: "cancellation_confirmed", appointment: appt }),
    ]);
    expect(s.confirmations.map((c) => c.kind)).toEqual(["cancelled", "booked"]);
  });

  it("tracks speaking state, tool calls and mute", () => {
    let s = run([{ type: "dial" }, server({ type: "user_state", state: "speaking" })]);
    expect(s.userSpeaking).toBe(true);
    s = run([server({ type: "user_state", state: "silent" }), server({ type: "tool_call", tool: "book_appointment" })], s);
    expect(s).toMatchObject({ userSpeaking: false, agentState: "thinking", lastTool: "book_appointment" });
    s = run([{ type: "toggle_mute" }], s);
    expect(s.muted).toBe(true);
  });

  it("surfaces non-fatal errors and fails on fatal ones", () => {
    let s = run([{ type: "dial" }, server({ type: "error", message: "TTS hiccup" })]);
    expect(s).toMatchObject({ phase: "ringing", error: "TTS hiccup" });
    s = run([server({ type: "error", message: "keys missing", fatal: true })], s);
    expect(s.phase).toBe("error");
    // A hangup after a failure keeps the error visible.
    expect(run([{ type: "hangup", now: 2 }], s).phase).toBe("error");
  });
});
