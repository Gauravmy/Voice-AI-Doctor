import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CallPanel } from "@/components/call/CallPanel";

import { FakeWebSocket, installFakes } from "./fixtures";

beforeEach(() => {
  installFakes();
});
afterEach(() => vi.unstubAllGlobals());

const phase = () => screen.getByTestId("call-phase").textContent;

async function connectMockCall() {
  render(<CallPanel mode="mock" clinicName="Brightwell Family Clinic" />);
  await userEvent.click(screen.getByRole("button", { name: "Start call" }));
  const ws = FakeWebSocket.last("/ws/call");
  expect(phase()).toContain("Ringing");
  act(() => ws.open());
  expect(phase()).toContain("Connecting");
  act(() => ws.receive({ type: "call_state", state: "connected", mode: "mock", missing_keys: [] }));
  return ws;
}

describe("CallPanel", () => {
  it("starts and ends a call", async () => {
    const ws = await connectMockCall();
    expect(phase()).toContain("Connected");
    expect(screen.getByTestId("connection-status")).toHaveTextContent("Connected");
    await userEvent.click(screen.getByRole("button", { name: "End call" }));
    expect(phase()).toContain("Call ended");
    expect(ws.readyState).toBe(FakeWebSocket.CLOSED);
    expect(ws.sent).toContain(JSON.stringify({ type: "end_call" }));
    expect(screen.getByRole("button", { name: "Start call" })).toHaveTextContent("Call again");
  });

  it("renders the live transcript and sends typed caller text in mock mode", async () => {
    const ws = await connectMockCall();
    act(() => ws.receive({ type: "transcript", role: "agent", text: "How can I help you today?", final: true, mock: true }));
    expect(screen.getByText("How can I help you today?")).toBeInTheDocument();
    expect(screen.getByText(/Development mock mode\./)).toBeInTheDocument();

    await userEvent.type(screen.getByLabelText("Type what the caller says"), "Book a cardiologist{Enter}");
    expect(ws.sent).toContain(JSON.stringify({ type: "user_text", text: "Book a cardiologist" }));
    act(() => ws.receive({ type: "transcript", role: "user", text: "Book a cardiologist", final: true }));
    expect(screen.getByText("Book a cardiologist")).toBeInTheDocument();
  });

  it("shows a booking confirmation card only when the backend confirms", async () => {
    const ws = await connectMockCall();
    expect(screen.queryByText("Appointment confirmed")).not.toBeInTheDocument();
    act(() => ws.receive({
      type: "booking_confirmed",
      appointment: { appointment_id: "APT-U66E7L", doctor_name: "Dr. Ananya Rao", date: "2026-11-25",
        start_time: "10:30", patient_phone: "******3210" },
    }));
    const card = screen.getByRole("status");
    expect(card).toHaveTextContent("Appointment confirmed");
    expect(card).toHaveTextContent("APT-U66E7L");
    expect(card).toHaveTextContent("10:30 AM");
    expect(card).toHaveTextContent("******3210");
  });

  it("shows fatal server errors", async () => {
    const ws = await connectMockCall();
    act(() => ws.receive({ type: "error", message: "The voice service failed to start.", fatal: true }));
    expect(phase()).toContain("Call failed");
    expect(screen.getByRole("alert")).toHaveTextContent("The voice service failed to start.");
  });

  it("reports a denied microphone in live mode", async () => {
    class FakeAudioContext {
      audioWorklet = { addModule: vi.fn() };
      createAnalyser() { return { connect: vi.fn(), fftSize: 0 }; }
      close() { return Promise.resolve(); }
      state = "running";
    }
    vi.stubGlobal("AudioContext", FakeAudioContext);
    Object.defineProperty(navigator, "mediaDevices", {
      configurable: true,
      value: { getUserMedia: vi.fn().mockRejectedValue(new DOMException("denied", "NotAllowedError")) },
    });
    render(<CallPanel mode="live" clinicName="Clinic" />);
    await userEvent.click(screen.getByRole("button", { name: "Start call" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Microphone permission was denied");
    expect(phase()).toContain("Call failed");
  });
});
