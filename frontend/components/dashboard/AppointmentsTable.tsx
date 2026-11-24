"use client";

import { CalendarDays, Mic } from "lucide-react";
import { useState } from "react";

import { Badge } from "@/components/ui/Badge";
import { Card, CardHeader, Skeleton } from "@/components/ui/Card";
import { cn, formatDate, formatTime, timeAgo } from "@/lib/format";
import type { Appointment } from "@/types";

const FILTERS = ["all", "booked", "cancelled"] as const;
type Filter = (typeof FILTERS)[number];

export function AppointmentsTable({
  appointments,
  loading,
  highlighted,
}: {
  appointments: Appointment[];
  loading: boolean;
  highlighted: Record<string, "booked" | "cancelled">;
}) {
  const [filter, setFilter] = useState<Filter>("all");
  const rows = appointments.filter((a) => filter === "all" || a.status === filter);

  return (
    <Card>
      <CardHeader
        title="Appointments"
        subtitle="Patient numbers are masked · updates appear instantly"
        icon={<CalendarDays className="size-4" />}
        action={
          <div role="tablist" aria-label="Filter appointments" className="flex rounded-lg bg-slate-100 p-0.5 text-xs">
            {FILTERS.map((f) => (
              <button key={f} role="tab" aria-selected={filter === f} onClick={() => setFilter(f)}
                className={cn("rounded-md px-2.5 py-1 capitalize transition",
                  filter === f ? "bg-white font-medium text-slate-900 shadow-sm" : "text-slate-500 hover:text-slate-700")}>
                {f}
              </button>
            ))}
          </div>
        }
      />
      <div className="max-h-[440px] overflow-auto">
        {loading && appointments.length === 0 ? (
          <div className="space-y-2 p-5">{Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} className="h-9" />)}</div>
        ) : (
          <table className="w-full min-w-[640px] text-left text-[13px]">
            <thead className="sticky top-0 z-10 bg-slate-50/95 text-[11px] uppercase tracking-wide text-slate-500 backdrop-blur">
              <tr>
                <th className="px-5 py-2.5 font-medium">Appointment</th>
                <th className="px-3 py-2.5 font-medium">Patient</th>
                <th className="px-3 py-2.5 font-medium">Doctor</th>
                <th className="px-3 py-2.5 font-medium">Date &amp; time</th>
                <th className="px-5 py-2.5 font-medium">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {rows.map((a) => {
                const flash = highlighted[a.id];
                return (
                  <tr key={a.id} data-testid={`appt-${a.id}`} data-highlight={flash ?? undefined}
                    className={cn("transition-colors duration-700",
                      flash === "booked" && "bg-emerald-50/80 row-flash-booked",
                      flash === "cancelled" && "bg-rose-50/80 row-flash-cancelled")}>
                    <td className="px-5 py-2.5">
                      <div className="flex items-center gap-1.5 font-mono text-[12px] font-medium text-slate-800">
                        {a.id}
                        {a.source === "voice" && <Mic className="size-3 text-indigo-500" aria-label="Booked by voice" />}
                      </div>
                      <div className="text-[11px] text-slate-400">updated {timeAgo(a.updated_at)}</div>
                    </td>
                    <td className="px-3 py-2.5">
                      <div className="font-mono text-[12px] tabular-nums text-slate-700">{a.patient_phone}</div>
                      <div className="text-[11px] text-slate-400">{a.patient_name || "—"}</div>
                    </td>
                    <td className="px-3 py-2.5">
                      <div className="text-slate-800">{a.doctor_name}</div>
                      <div className="text-[11px] text-slate-400">{a.specialty}</div>
                    </td>
                    <td className="px-3 py-2.5 tabular-nums text-slate-700">
                      {formatDate(a.date)}<span className="text-slate-400"> · </span>{formatTime(a.start_time)}
                    </td>
                    <td className="px-5 py-2.5">
                      {a.status === "booked" ? <Badge tone="green" dot>Booked</Badge> : <Badge tone="red" dot>Cancelled</Badge>}
                    </td>
                  </tr>
                );
              })}
              {rows.length === 0 && (
                <tr><td colSpan={5} className="px-5 py-10 text-center text-sm text-slate-400">No appointments.</td></tr>
              )}
            </tbody>
          </table>
        )}
      </div>
    </Card>
  );
}
