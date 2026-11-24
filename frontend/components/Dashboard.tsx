"use client";

import { AlertTriangle, RefreshCw } from "lucide-react";

import { CallPanel } from "@/components/call/CallPanel";
import { ActivityPanel } from "@/components/dashboard/ActivityPanel";
import { AppointmentsTable } from "@/components/dashboard/AppointmentsTable";
import { DoctorsPanel } from "@/components/dashboard/DoctorsPanel";
import { Header } from "@/components/dashboard/Header";
import { StatCards } from "@/components/dashboard/StatCards";
import { useDashboardData } from "@/hooks/useDashboardData";
import { formatDate } from "@/lib/format";

export function Dashboard() {
  const { data, loading, error, live, highlighted, refresh } = useDashboardData();

  return (
    <div className="min-h-screen bg-slate-50">
      <Header health={data.health} live={live} />
      <main className="mx-auto grid max-w-[1440px] gap-6 px-4 py-6 sm:px-6 xl:grid-cols-[minmax(0,1fr)_400px]">
        <div className="min-w-0 space-y-6">
          <div className="flex flex-wrap items-end justify-between gap-3">
            <div>
              <h1 className="text-xl font-semibold tracking-tight text-slate-900">Overview</h1>
              <p className="text-sm text-slate-500">
                {data.stats ? formatDate(data.stats.today, { year: true }) : "Loading…"} · {data.health?.timezone ?? ""}
              </p>
            </div>
            <button onClick={() => void refresh()}
              className="flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-600 transition hover:bg-slate-50">
              <RefreshCw className="size-3.5" /> Refresh
            </button>
          </div>

          {error && (
            <div role="alert" className="flex items-start gap-3 rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-800">
              <AlertTriangle className="mt-0.5 size-4 shrink-0" />
              <div>
                <p className="font-medium">Couldn&apos;t load dashboard data</p>
                <p className="text-rose-700">{error}</p>
              </div>
            </div>
          )}

          <StatCards stats={data.stats} />
          <ActivityPanel activity={data.activity} />
          <DoctorsPanel doctors={data.doctors} loading={loading} />
          <AppointmentsTable appointments={data.appointments} loading={loading} highlighted={highlighted} />
        </div>

        <aside className="order-first xl:order-none">
          <div className="xl:sticky xl:top-[84px]">
            <CallPanel mode={data.health?.voice_mode ?? null} clinicName={data.health?.clinic_name ?? "Clinic"} />
            <p className="mt-3 px-2 text-center text-[11px] leading-relaxed text-slate-400">
              Callers are identified only by the phone number they say during the call.
              It is read back and confirmed before any booking or cancellation.
            </p>
          </div>
        </aside>
      </main>
    </div>
  );
}
