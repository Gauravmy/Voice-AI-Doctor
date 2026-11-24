import type { Activity, Appointment, Doctor, Health, Stats } from "@/types";

// Only the backend's public URL is configured here - never any API keys.
export const API_BASE = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/$/, "");

export const WS_BASE = API_BASE.replace(/^http/, "ws");

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public code = "error",
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
      cache: "no-store",
    });
  } catch {
    throw new ApiError("Cannot reach the backend. Is it running on " + API_BASE + "?", 0, "network");
  }
  if (!res.ok) {
    let message = `Request failed (${res.status})`;
    let code = "error";
    try {
      const body = await res.json();
      message = body?.error?.message ?? message;
      code = body?.error?.code ?? code;
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(message, res.status, code);
  }
  return (await res.json()) as T;
}

export const api = {
  health: () => request<Health>("/api/health"),
  stats: () => request<Stats>("/api/stats"),
  doctors: () => request<Doctor[]>("/api/doctors"),
  appointments: () => request<Appointment[]>("/api/appointments?limit=100"),
  activity: () => request<Activity>("/api/activity?days=7"),
};
