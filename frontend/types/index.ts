// Shapes returned by the FastAPI backend (see backend/app/api/routes.py).

export interface Health {
  status: "ok";
  voice_mode: "live" | "mock";
  configured_mode: "auto" | "live" | "mock";
  missing_keys: string[];
  providers: { llm: string; stt: string; tts: string };
  clinic_name: string;
  timezone: string;
}

export interface Stats {
  total_doctors: number;
  total_specialties: number;
  available_slots: number;
  total_appointments: number;
  active_appointments: number;
  cancelled_appointments: number;
  todays_appointments: number;
  voice_bookings: number;
  today: string;
}

export interface Doctor {
  id: string;
  name: string;
  specialty: string;
  years_experience: number;
  room: string;
  bio: string;
  available_dates: { date: string; available: number }[];
  available_slots: number;
  total_slots: number;
  next_available: string | null;
  next_slots: string[];
}

export type AppointmentStatus = "booked" | "cancelled";

export interface Appointment {
  id: string;
  status: AppointmentStatus;
  patient_name: string; // initials only
  patient_phone: string; // masked, e.g. ******0001
  reason: string;
  source: "voice" | "api" | "seed";
  created_at: string;
  updated_at: string;
  cancelled_at: string | null;
  slot_id: number;
  date: string;
  start_time: string;
  end_time: string;
  doctor_id: string;
  doctor_name: string;
  specialty: string;
}

export interface ActivityPoint {
  date: string;
  booked: number;
  cancelled: number;
}

export interface ActivityEvent {
  id: number;
  appointment_id: string;
  action: "booked" | "cancelled";
  source: string;
  created_at: string;
  doctor_name: string;
  date: string;
  start_time: string;
}

export interface Activity {
  series: ActivityPoint[];
  recent: ActivityEvent[];
}

// ---- Voice call protocol (backend/app/voice/serializer.py) ----

export interface ConfirmationCard {
  kind: "booked" | "cancelled";
  appointment_id: string;
  doctor_name: string;
  specialty?: string;
  date: string;
  start_time: string;
  spoken_date?: string;
  spoken_time?: string;
  patient_phone: string;
}

export type CallServerEvent =
  | { type: "call_state"; state: "connected"; mode: "live" | "mock"; missing_keys?: string[] }
  | { type: "transcript"; role: "user" | "agent"; text: string; final: boolean; mock?: boolean; interrupted?: boolean }
  | { type: "agent_text"; text: string }
  | { type: "agent_state"; state: "speaking" | "listening" }
  | { type: "user_state"; state: "speaking" | "silent" }
  | { type: "interrupt" }
  | { type: "tool_call"; tool: string }
  | { type: "tool_result"; tool: string; status: string }
  | { type: "booking_confirmed"; appointment: Omit<ConfirmationCard, "kind" | "appointment_id"> & { appointment_id: string } }
  | { type: "cancellation_confirmed"; appointment: Omit<ConfirmationCard, "kind" | "appointment_id"> & { appointment_id: string } }
  | { type: "error"; message: string; fatal?: boolean };

export interface DashboardEvent {
  type: "hello" | "appointment.booked" | "appointment.cancelled";
  data?: Appointment;
}
