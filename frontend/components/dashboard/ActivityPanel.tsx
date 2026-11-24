import { TrendingUp } from "lucide-react";

import { Card, CardHeader, Skeleton } from "@/components/ui/Card";
import { formatDate, formatTime, timeAgo } from "@/lib/format";
import type { Activity } from "@/types";

/** Booking activity: 7-day bars (booked vs cancelled) + the latest events. */
export function ActivityPanel({ activity }: { activity: Activity | null }) {
  const max = Math.max(1, ...(activity?.series ?? []).map((p) => p.booked + p.cancelled));
  return (
    <Card>
      <CardHeader title="Booking activity" subtitle="Bookings and cancellations, last 7 days"
        icon={<TrendingUp className="size-4" />} />
      <div className="grid gap-5 p-5 md:grid-cols-[1.2fr_1fr]">
        {!activity ? (
          <Skeleton className="h-40" />
        ) : (
          <div>
            <div className="flex h-36 items-end gap-2" role="img" aria-label="Bookings per day chart">
              {activity.series.map((p) => (
                <div key={p.date} className="flex h-full flex-1 flex-col items-center justify-end gap-1">
                  <span className="text-[10px] tabular-nums text-slate-400">{p.booked + p.cancelled || ""}</span>
                  <div className="flex w-full max-w-8 flex-col-reverse overflow-hidden rounded-md bg-slate-50" style={{ height: "100%" }}>
                    <div className="bg-indigo-500 transition-all duration-500" style={{ height: `${(p.booked / max) * 100}%` }}
                      title={`${p.booked} booked`} />
                    <div className="bg-rose-300 transition-all duration-500" style={{ height: `${(p.cancelled / max) * 100}%` }}
                      title={`${p.cancelled} cancelled`} />
                  </div>
                  <span className="text-[10px] text-slate-500">{formatDate(p.date).split(",")[0]}</span>
                </div>
              ))}
            </div>
            <div className="mt-3 flex gap-4 text-[11px] text-slate-500">
              <span className="flex items-center gap-1.5"><span className="size-2 rounded-sm bg-indigo-500" />Booked</span>
              <span className="flex items-center gap-1.5"><span className="size-2 rounded-sm bg-rose-300" />Cancelled</span>
            </div>
          </div>
        )}
        <div>
          <p className="mb-2 text-xs font-medium text-slate-500">Recent events</p>
          {!activity ? (
            <Skeleton className="h-32" />
          ) : activity.recent.length === 0 ? (
            <p className="text-sm text-slate-400">No activity yet.</p>
          ) : (
            <ul className="space-y-2">
              {activity.recent.slice(0, 5).map((e) => (
                <li key={e.id} className="flex items-start gap-2.5 text-[13px]">
                  <span className={`mt-1.5 size-1.5 shrink-0 rounded-full ${e.action === "booked" ? "bg-indigo-500" : "bg-rose-400"}`} />
                  <span className="min-w-0 flex-1 text-slate-600">
                    <span className="font-medium text-slate-800">{e.appointment_id}</span>{" "}
                    {e.action} · {e.doctor_name}, {formatDate(e.date)} {formatTime(e.start_time)}
                    {e.source === "voice" && <span className="ml-1 text-indigo-600">· voice</span>}
                  </span>
                  <span className="shrink-0 text-[11px] text-slate-400">{timeAgo(e.created_at)}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </Card>
  );
}
