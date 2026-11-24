import type { ReactNode } from "react";

import { cn } from "@/lib/format";

const TONES = {
  green: "bg-emerald-50 text-emerald-700 ring-emerald-600/15",
  red: "bg-rose-50 text-rose-700 ring-rose-600/15",
  amber: "bg-amber-50 text-amber-800 ring-amber-600/20",
  indigo: "bg-indigo-50 text-indigo-700 ring-indigo-600/15",
  slate: "bg-slate-100 text-slate-600 ring-slate-500/15",
} as const;

export type Tone = keyof typeof TONES;

export function Badge({ tone = "slate", children, dot, className }: {
  tone?: Tone;
  children: ReactNode;
  dot?: boolean;
  className?: string;
}) {
  return (
    <span className={cn("inline-flex items-center gap-1.5 whitespace-nowrap rounded-full px-2 py-0.5 text-[11px] font-medium ring-1 ring-inset", TONES[tone], className)}>
      {dot && <span className="size-1.5 rounded-full bg-current opacity-80" />}
      {children}
    </span>
  );
}
