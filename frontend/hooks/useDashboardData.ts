"use client";

/**
 * Loads dashboard data from the REST API and keeps it live: the backend pushes
 * appointment.booked / appointment.cancelled over /ws/dashboard, and we refetch
 * and briefly highlight the changed row.
 */
import { useCallback, useEffect, useRef, useState } from "react";

import { api, ApiError, WS_BASE } from "@/lib/api";
import type { Activity, Appointment, DashboardEvent, Doctor, Health, Stats } from "@/types";

export interface DashboardData {
  health: Health | null;
  stats: Stats | null;
  doctors: Doctor[];
  appointments: Appointment[];
  activity: Activity | null;
}

const EMPTY: DashboardData = { health: null, stats: null, doctors: [], appointments: [], activity: null };
const HIGHLIGHT_MS = 6000;

export function useDashboardData() {
  const [data, setData] = useState<DashboardData>(EMPTY);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [live, setLive] = useState(false);
  const [highlighted, setHighlighted] = useState<Record<string, "booked" | "cancelled">>({});
  const timers = useRef<number[]>([]);

  const refresh = useCallback(async () => {
    try {
      const [health, stats, doctors, appointments, activity] = await Promise.all([
        api.health(), api.stats(), api.doctors(), api.appointments(), api.activity(),
      ]);
      setData({ health, stats, doctors, appointments, activity });
      setError(null);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to load dashboard data.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- initial data load
    void refresh();
  }, [refresh]);

  useEffect(() => {
    let socket: WebSocket | null = null;
    let retry: number | undefined;
    let closed = false;

    const connect = () => {
      socket = new WebSocket(`${WS_BASE}/ws/dashboard`);
      socket.onopen = () => setLive(true);
      socket.onmessage = (msg) => {
        let event: DashboardEvent;
        try {
          event = JSON.parse(msg.data as string);
        } catch {
          return;
        }
        if (event.type === "hello" || !event.data) return;
        const id = event.data.id;
        const kind = event.type === "appointment.booked" ? "booked" : "cancelled";
        setHighlighted((h) => ({ ...h, [id]: kind }));
        timers.current.push(
          window.setTimeout(() => setHighlighted((h) => {
            const next = { ...h };
            delete next[id];
            return next;
          }), HIGHLIGHT_MS),
        );
        void refresh();
      };
      socket.onclose = () => {
        setLive(false);
        if (!closed) retry = window.setTimeout(connect, 3000); // auto-reconnect
      };
    };
    connect();
    const pending = timers.current;
    return () => {
      closed = true;
      window.clearTimeout(retry);
      pending.forEach((t) => window.clearTimeout(t));
      socket?.close();
    };
  }, [refresh]);

  return { data, loading, error, live, highlighted, refresh };
}
