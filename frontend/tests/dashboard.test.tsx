import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { Dashboard } from "@/components/Dashboard";
import { availabilityOf } from "@/components/dashboard/DoctorsPanel";

import { appointment, doctors, FakeWebSocket, installFakes } from "./fixtures";

beforeEach(() => {
  installFakes();
});
afterEach(() => vi.unstubAllGlobals());

describe("Dashboard", () => {
  it("loads overview stats, doctors and appointments", async () => {
    render(<Dashboard />);
    expect(await screen.findByText("292")).toBeInTheDocument(); // available slots
    expect(screen.getByText("Available slots")).toBeInTheDocument();
    const list = screen.getByRole("list", { name: "Doctor list" });
    expect(within(list).getByText("Dr. Ananya Rao")).toBeInTheDocument();
    expect(within(list).getByText("Fully booked")).toBeInTheDocument(); // Dr. Okafor: 0 slots
    expect(within(list).getByText("10:30 AM")).toBeInTheDocument(); // next available slot chip
    expect(screen.getByText("APT-SEED01")).toBeInTheDocument();
    expect(screen.getByText("******0001")).toBeInTheDocument(); // masked phone
    expect(screen.getAllByText("Development mock mode").length).toBeGreaterThan(0);
  });

  it("shows an error state when the backend is unreachable", async () => {
    installFakes({ "/api/stats": new TypeError("network down") });
    render(<Dashboard />);
    expect(await screen.findByText("Couldn't load dashboard data")).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("Cannot reach the backend");
  });

  it("shows the backend's error message for HTTP errors", async () => {
    installFakes({ "/api/doctors": { __status: 500, error: { code: "internal_error", message: "An unexpected error occurred." } } });
    render(<Dashboard />);
    expect(await screen.findByRole("alert")).toHaveTextContent("An unexpected error occurred.");
  });

  it("filters doctors by specialty", async () => {
    render(<Dashboard />);
    await screen.findByText("292");
    await userEvent.selectOptions(screen.getByLabelText("Filter by specialty"), "Neurology");
    const list = screen.getByRole("list", { name: "Doctor list" });
    expect(within(list).queryByText("Dr. Ananya Rao")).not.toBeInTheDocument();
    expect(within(list).getByText("Dr. Daniel Okafor")).toBeInTheDocument();
  });

  it("refetches and highlights a row when a booking is pushed", async () => {
    const { routes, fetchMock } = installFakes();
    render(<Dashboard />);
    await screen.findByText("APT-SEED01");
    const ws = FakeWebSocket.last("/ws/dashboard");
    act(() => ws.open());

    const booked = appointment({ id: "APT-NEW234", source: "voice", patient_phone: "******3210" });
    routes["/api/appointments"] = [booked, appointment()];
    const callsBefore = fetchMock.mock.calls.length;
    act(() => ws.receive({ type: "appointment.booked", data: booked }));

    const row = await screen.findByTestId("appt-APT-NEW234");
    expect(row).toHaveAttribute("data-highlight", "booked");
    expect(within(row).getByText("Booked")).toBeInTheDocument();
    expect(fetchMock.mock.calls.length).toBeGreaterThan(callsBefore);
  });

  it("shows a cancellation update", async () => {
    const { routes } = installFakes();
    render(<Dashboard />);
    await screen.findByText("APT-SEED01");
    const ws = FakeWebSocket.last("/ws/dashboard");
    const cancelled = appointment({ status: "cancelled", cancelled_at: "2026-11-24T09:00:00+00:00" });
    routes["/api/appointments"] = [cancelled];
    act(() => ws.receive({ type: "appointment.cancelled", data: cancelled }));
    await waitFor(() => {
      const row = screen.getByTestId("appt-APT-SEED01");
      expect(row).toHaveAttribute("data-highlight", "cancelled");
      expect(within(row).getByText("Cancelled")).toBeInTheDocument();
    });
    await userEvent.click(screen.getByRole("tab", { name: "booked" }));
    expect(screen.queryByTestId("appt-APT-SEED01")).not.toBeInTheDocument();
  });
});

describe("availability indicator", () => {
  it("classifies doctors", () => {
    expect(availabilityOf(doctors[0]).label).toBe("Available");
    expect(availabilityOf(doctors[1]).label).toBe("Fully booked");
    expect(availabilityOf({ ...doctors[0], available_slots: 5, total_slots: 36 }).label).toBe("Limited");
  });
});
