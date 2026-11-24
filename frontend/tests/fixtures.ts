import { vi } from "vitest";

import type { Activity, Appointment, Doctor, Health, Stats } from "@/types";

export const health: Health = {
  status: "ok",
  voice_mode: "mock",
  configured_mode: "auto",
  missing_keys: ["GOOGLE_API_KEY", "ELEVENLABS_API_KEY"],
  providers: { llm: "Google Gemini", stt: "ElevenLabs STT", tts: "ElevenLabs TTS" },
  clinic_name: "Brightwell Family Clinic",
  timezone: "Asia/Kolkata",
};

export const stats: Stats = {
  total_doctors: 9, total_specialties: 8, available_slots: 292, total_appointments: 87,
  active_appointments: 86, cancelled_appointments: 1, todays_appointments: 2, voice_bookings: 3,
  today: "2026-11-24",
};

export const doctors: Doctor[] = [
  {
    id: "DOC-001", name: "Dr. Ananya Rao", specialty: "Cardiology", years_experience: 14, room: "Room 101",
    bio: "", available_dates: [{ date: "2026-11-25", available: 3 }], available_slots: 29, total_slots: 36,
    next_available: "2026-11-25", next_slots: ["09:00", "10:30"],
  },
  {
    id: "DOC-006", name: "Dr. Daniel Okafor", specialty: "Neurology", years_experience: 12, room: "Room 302",
    bio: "", available_dates: [], available_slots: 0, total_slots: 24, next_available: null, next_slots: [],
  },
];

export const appointment = (over: Partial<Appointment> = {}): Appointment => ({
  id: "APT-SEED01", status: "booked", patient_name: "R. V.", patient_phone: "******0001", reason: "",
  source: "seed", created_at: "2026-11-24T08:00:00+00:00", updated_at: "2026-11-24T08:00:00+00:00",
  cancelled_at: null, slot_id: 1, date: "2026-11-25", start_time: "09:30", end_time: "10:00",
  doctor_id: "DOC-001", doctor_name: "Dr. Ananya Rao", specialty: "Cardiology", ...over,
});

export const activity: Activity = {
  series: Array.from({ length: 7 }, (_, i) => ({ date: `2026-11-${18 + i}`, booked: i % 3, cancelled: i === 6 ? 1 : 0 })),
  recent: [],
};

/** Minimal controllable WebSocket used in place of the browser's. */
export class FakeWebSocket {
  static instances: FakeWebSocket[] = [];
  static OPEN = 1;
  static CLOSED = 3;
  readyState = 0;
  binaryType = "blob";
  sent: unknown[] = [];
  onopen: (() => void) | null = null;
  onmessage: ((e: { data: unknown }) => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  constructor(public url: string) {
    FakeWebSocket.instances.push(this);
  }
  send(data: unknown) {
    this.sent.push(data);
  }
  close() {
    this.readyState = FakeWebSocket.CLOSED;
    this.onclose?.();
  }
  open() {
    this.readyState = FakeWebSocket.OPEN;
    this.onopen?.();
  }
  receive(msg: object) {
    this.onmessage?.({ data: JSON.stringify(msg) });
  }
  static last(path: string) {
    return [...FakeWebSocket.instances].reverse().find((w) => w.url.endsWith(path))!;
  }
}

export function installFakes(overrides: Partial<Record<string, unknown>> = {}) {
  FakeWebSocket.instances = [];
  vi.stubGlobal("WebSocket", FakeWebSocket);
  const routes: Record<string, unknown> = {
    "/api/health": health,
    "/api/stats": stats,
    "/api/doctors": doctors,
    "/api/appointments": [appointment()],
    "/api/activity": activity,
    ...overrides,
  };
  const fetchMock = vi.fn(async (url: string) => {
    const path = new URL(url).pathname;
    const body = routes[path];
    if (body instanceof Error) throw body;
    if (body && typeof body === "object" && "__status" in body) {
      const { __status, ...rest } = body as { __status: number };
      return new Response(JSON.stringify(rest), { status: __status });
    }
    return new Response(JSON.stringify(body), { status: 200 });
  });
  vi.stubGlobal("fetch", fetchMock);
  return { fetchMock, routes };
}
