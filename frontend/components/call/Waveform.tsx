"use client";

import { useEffect, useRef } from "react";

/**
 * Animated voice waveform driven by real audio levels (mic RMS / agent output
 * analyser). Bars ease toward the target level so motion stays smooth.
 */
export function Waveform({ level, active, color = "#4f46e5", bars = 28 }: {
  level: number;
  active: boolean;
  color?: string;
  bars?: number;
}) {
  const refs = useRef<(HTMLSpanElement | null)[]>([]);
  const heights = useRef<number[]>(Array(bars).fill(0.08));
  const target = useRef(0);

  useEffect(() => {
    target.current = active ? Math.min(1, level * 6) : 0;
  }, [level, active]);

  useEffect(() => {
    let raf = 0;
    let t = 0;
    const tick = () => {
      t += 0.12;
      heights.current = heights.current.map((h, i) => {
        const shape = 0.55 + 0.45 * Math.sin(t + i * 0.55) * Math.cos(t * 0.7 + i * 0.3);
        const goal = 0.08 + target.current * shape;
        return h + (goal - h) * 0.25;
      });
      heights.current.forEach((h, i) => {
        const el = refs.current[i];
        if (el) el.style.transform = `scaleY(${h.toFixed(3)})`;
      });
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, []);

  return (
    <div className="flex h-12 items-center justify-center gap-[3px]" aria-hidden="true">
      {Array.from({ length: bars }).map((_, i) => (
        <span key={i} ref={(el) => { refs.current[i] = el; }}
          className="h-full w-[3px] origin-center rounded-full transition-colors"
          style={{ background: color, transform: "scaleY(0.08)", opacity: active ? 0.9 : 0.35 }} />
      ))}
    </div>
  );
}
