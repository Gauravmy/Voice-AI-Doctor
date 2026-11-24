import { Activity, Stethoscope } from "lucide-react";

import { Badge } from "@/components/ui/Badge";
import type { Health } from "@/types";

export function Header({ health, live }: { health: Health | null; live: boolean }) {
  return (
    <header className="sticky top-0 z-20 border-b border-slate-200/70 bg-white/85 backdrop-blur">
      <div className="mx-auto flex max-w-[1440px] items-center justify-between gap-4 px-4 py-3 sm:px-6">
        <div className="flex items-center gap-3">
          <span className="grid size-9 place-items-center rounded-xl bg-indigo-600 text-white shadow-sm shadow-indigo-600/30">
            <Stethoscope className="size-5" />
          </span>
          <div className="leading-tight">
            <p className="text-[15px] font-semibold tracking-tight text-slate-900">
              {health?.clinic_name ?? "Clinic"} <span className="font-normal text-slate-400">· Front desk</span>
            </p>
            <p className="text-xs text-slate-500">Voice AI appointment assistant</p>
          </div>
        </div>
        <div className="flex flex-wrap items-center justify-end gap-2">
          {health && (
            health.voice_mode === "live" ? (
              <Badge tone="indigo" dot>Live voice · Gemini + ElevenLabs</Badge>
            ) : (
              <Badge tone="amber" dot>Development mock mode</Badge>
            )
          )}
          <Badge tone={live ? "green" : "slate"} className="hidden sm:inline-flex">
            <Activity className="size-3" />
            {live ? "Realtime updates" : "Reconnecting…"}
          </Badge>
        </div>
      </div>
    </header>
  );
}
