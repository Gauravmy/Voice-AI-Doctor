"use client";

import { useEffect, useRef } from "react";

import type { TranscriptEntry } from "@/lib/callReducer";
import { cn } from "@/lib/format";

export function Transcript({ entries }: { entries: TranscriptEntry[] }) {
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => {
    end.current?.scrollIntoView?.({ behavior: "smooth", block: "end" });
  }, [entries]);

  if (entries.length === 0) {
    return <p className="py-6 text-center text-xs text-slate-400">The live transcript will appear here.</p>;
  }
  return (
    <ol className="space-y-2.5" aria-label="Live transcript" aria-live="polite">
      {entries.map((e) => (
        <li key={e.id} className={cn("flex msg-in", e.role === "user" ? "justify-end" : "justify-start")}>
          <div className={cn("max-w-[85%] rounded-2xl px-3 py-2 text-[13px] leading-relaxed",
            e.role === "user"
              ? "rounded-br-md bg-indigo-600 text-white"
              : "rounded-bl-md bg-slate-100 text-slate-800",
            !e.final && "opacity-70")}>
            <p className={cn("mb-0.5 text-[10px] font-medium uppercase tracking-wide",
              e.role === "user" ? "text-indigo-200" : "text-slate-400")}>
              {e.role === "user" ? "Caller" : "Maya · Agent"}
              {e.mock && " · mock"}
              {!e.final && " · …"}
              {e.interrupted && " · interrupted"}
            </p>
            {e.text}
          </div>
        </li>
      ))}
      <div ref={end} />
    </ol>
  );
}
