import { CalendarCheck, CalendarClock, ClipboardList, UserRound } from "lucide-react";
import type { ReactNode } from "react";

import { Skeleton } from "@/components/ui/Card";
import type { Stats } from "@/types";

function Stat({ label, value, hint, icon }: { label: string; value: ReactNode; hint: string; icon: ReactNode }) {
  return (
    <div className="rounded-2xl border border-slate-200/80 bg-white p-4 shadow-[0_1px_2px_rgba(15,23,42,0.04)]">
      <div className="flex items-center justify-between">
        <p className="text-xs font-medium text-slate-500">{label}</p>
        <span className="text-slate-400">{icon}</span>
      </div>
      <p className="mt-2 text-2xl font-semibold tabular-nums tracking-tight text-slate-900">{value}</p>
      <p className="mt-1 text-xs text-slate-500">{hint}</p>
    </div>
  );
}

export function StatCards({ stats }: { stats: Stats | null }) {
  if (!stats) {
    return (
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4" aria-busy="true">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-[108px] rounded-2xl" />
        ))}
      </div>
    );
  }
  return (
    <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
      <Stat label="Doctors" value={stats.total_doctors} hint={`${stats.total_specialties} specialties`}
        icon={<UserRound className="size-4" />} />
      <Stat label="Available slots" value={stats.available_slots} hint="Upcoming, unbooked"
        icon={<CalendarClock className="size-4" />} />
      <Stat label="Appointments" value={stats.total_appointments}
        hint={`${stats.active_appointments} active · ${stats.cancelled_appointments} cancelled`}
        icon={<ClipboardList className="size-4" />} />
      <Stat label="Today" value={stats.todays_appointments}
        hint={`${stats.voice_bookings} booked by voice in total`}
        icon={<CalendarCheck className="size-4" />} />
    </div>
  );
}
