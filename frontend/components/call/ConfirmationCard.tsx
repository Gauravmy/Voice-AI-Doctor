import { CalendarCheck2, CalendarX2 } from "lucide-react";

import { cn, formatDate, formatTime } from "@/lib/format";
import type { ConfirmationCard as Card } from "@/types";

/** Shown only after the backend confirms the DB write (booking_confirmed event). */
export function ConfirmationCard({ card }: { card: Card }) {
  const booked = card.kind === "booked";
  return (
    <div role="status" className={cn("card-in rounded-xl border p-3.5",
      booked ? "border-emerald-200 bg-emerald-50/70" : "border-rose-200 bg-rose-50/70")}>
      <div className="flex items-center gap-2">
        {booked ? <CalendarCheck2 className="size-4 text-emerald-600" /> : <CalendarX2 className="size-4 text-rose-600" />}
        <p className={cn("text-sm font-semibold", booked ? "text-emerald-800" : "text-rose-800")}>
          {booked ? "Appointment confirmed" : "Appointment cancelled"}
        </p>
        <span className="ml-auto font-mono text-xs font-semibold text-slate-700">{card.appointment_id}</span>
      </div>
      <dl className="mt-2.5 grid grid-cols-2 gap-x-3 gap-y-1.5 text-xs">
        <dt className="text-slate-500">Doctor</dt>
        <dd className="text-right font-medium text-slate-800">{card.doctor_name}</dd>
        <dt className="text-slate-500">When</dt>
        <dd className="text-right font-medium text-slate-800">{formatDate(card.date)}, {formatTime(card.start_time)}</dd>
        <dt className="text-slate-500">Phone</dt>
        <dd className="text-right font-mono text-slate-800">{card.patient_phone}</dd>
      </dl>
    </div>
  );
}
