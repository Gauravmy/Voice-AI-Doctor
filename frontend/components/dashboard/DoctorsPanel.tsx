"use client";

import { Search, UsersRound } from "lucide-react";
import { useMemo, useState } from "react";

import { Badge, type Tone } from "@/components/ui/Badge";
import { Card, CardHeader, Skeleton } from "@/components/ui/Card";
import { formatDate, formatTime } from "@/lib/format";
import type { Doctor } from "@/types";

export function availabilityOf(doc: Doctor): { label: string; tone: Tone } {
  if (doc.available_slots === 0) return { label: "Fully booked", tone: "red" };
  const ratio = doc.total_slots ? doc.available_slots / doc.total_slots : 0;
  if (ratio < 0.35) return { label: "Limited", tone: "amber" };
  return { label: "Available", tone: "green" };
}

function initials(name: string) {
  return name.replace(/^Dr\.?\s*/, "").split(" ").map((p) => p[0]).join("").slice(0, 2);
}

export function DoctorsPanel({ doctors, loading }: { doctors: Doctor[]; loading: boolean }) {
  const [query, setQuery] = useState("");
  const [specialty, setSpecialty] = useState("All");
  const specialties = useMemo(() => ["All", ...Array.from(new Set(doctors.map((d) => d.specialty))).sort()], [doctors]);
  const visible = doctors.filter(
    (d) =>
      (specialty === "All" || d.specialty === specialty) &&
      (d.name + d.specialty).toLowerCase().includes(query.toLowerCase()),
  );

  return (
    <Card>
      <CardHeader
        title="Doctors"
        subtitle="Live availability for the next two weeks"
        icon={<UsersRound className="size-4" />}
        action={
          <div className="flex items-center gap-2">
            <label className="relative hidden sm:block">
              <span className="sr-only">Search doctors</span>
              <Search className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-slate-400" />
              <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search"
                className="h-8 w-36 rounded-lg border border-slate-200 bg-white pl-8 pr-2 text-xs outline-none transition focus:border-indigo-400 focus:ring-2 focus:ring-indigo-100" />
            </label>
            <select aria-label="Filter by specialty" value={specialty} onChange={(e) => setSpecialty(e.target.value)}
              className="h-8 rounded-lg border border-slate-200 bg-white px-2 text-xs text-slate-700 outline-none focus:border-indigo-400 focus:ring-2 focus:ring-indigo-100">
              {specialties.map((s) => <option key={s}>{s}</option>)}
            </select>
          </div>
        }
      />
      {loading && doctors.length === 0 ? (
        <div className="space-y-3 p-5">{Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-14" />)}</div>
      ) : (
        <ul className="divide-y divide-slate-100" aria-label="Doctor list">
          {visible.map((doc) => {
            const status = availabilityOf(doc);
            return (
              <li key={doc.id} className="grid grid-cols-1 gap-3 px-5 py-3.5 transition-colors hover:bg-slate-50/70 md:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)_minmax(0,1.4fr)] md:items-center">
                <div className="flex min-w-0 items-center gap-3">
                  <span className="grid size-9 shrink-0 place-items-center rounded-full bg-gradient-to-br from-indigo-50 to-sky-50 text-xs font-semibold text-indigo-700 ring-1 ring-indigo-100">
                    {initials(doc.name)}
                  </span>
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium text-slate-900">{doc.name}</p>
                    <p className="truncate text-xs text-slate-500">{doc.specialty} · {doc.years_experience} yrs · {doc.room}</p>
                  </div>
                </div>
                <div className="flex items-center gap-3 md:block">
                  <Badge tone={status.tone} dot>{status.label}</Badge>
                  <p className="text-xs text-slate-500 md:mt-1">
                    <span className="font-medium tabular-nums text-slate-700">{doc.available_slots}</span> open slots ·{" "}
                    {doc.available_dates.length} days
                  </p>
                </div>
                <div className="min-w-0">
                  {doc.next_available ? (
                    <>
                      <p className="text-xs text-slate-500">Next: <span className="font-medium text-slate-700">{formatDate(doc.next_available)}</span></p>
                      <div className="mt-1.5 flex flex-wrap gap-1">
                        {doc.next_slots.map((t) => (
                          <span key={t} className="rounded-md bg-slate-50 px-1.5 py-0.5 text-[11px] tabular-nums text-slate-600 ring-1 ring-slate-200">
                            {formatTime(t)}
                          </span>
                        ))}
                      </div>
                    </>
                  ) : (
                    <p className="text-xs text-slate-400">No upcoming availability</p>
                  )}
                </div>
              </li>
            );
          })}
          {visible.length === 0 && <li className="px-5 py-8 text-center text-sm text-slate-400">No doctors match your filters.</li>}
        </ul>
      )}
    </Card>
  );
}
