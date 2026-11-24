"use client";

/**
 * Connects the browser to the backend voice pipeline over /ws/call.
 * Binary frames carry audio both ways; text frames carry JSON events.
 */
import { useCallback, useEffect, useReducer, useRef, useState } from "react";

import { WS_BASE } from "@/lib/api";
import { MicCapture, PcmPlayer } from "@/lib/audio";
import { callReducer, initialCallState } from "@/lib/callReducer";
import type { CallServerEvent } from "@/types";

export function useVoiceCall(expectedMode: "live" | "mock" | null) {
  const [state, dispatch] = useReducer(callReducer, initialCallState);
  const [elapsed, setElapsed] = useState(0);
  const [levels, setLevels] = useState({ mic: 0, agent: 0 });

  const ws = useRef<WebSocket | null>(null);
  const ctx = useRef<AudioContext | null>(null);
  const mic = useRef<MicCapture | null>(null);
  const player = useRef<PcmPlayer | null>(null);
  const micLevel = useRef(0);
  const hungUp = useRef(false);

  const teardown = useCallback(() => {
    mic.current?.stop();
    mic.current = null;
    player.current?.flush();
    player.current = null;
    if (ctx.current && ctx.current.state !== "closed") void ctx.current.close();
    ctx.current = null;
    const socket = ws.current;
    ws.current = null;
    if (socket && socket.readyState <= WebSocket.OPEN) {
      try {
        if (socket.readyState === WebSocket.OPEN) socket.send(JSON.stringify({ type: "end_call" }));
      } catch {
        /* socket already closing */
      }
      socket.close(1000, "caller hung up");
    }
  }, []);

  const start = useCallback(async () => {
    hungUp.current = false;
    dispatch({ type: "dial" });
    setElapsed(0);
    try {
      const live = expectedMode !== "mock";
      if (live) {
        if (!navigator.mediaDevices?.getUserMedia) {
          throw new Error("This browser cannot access a microphone (use Chrome/Edge on localhost).");
        }
        ctx.current = new AudioContext();
        player.current = new PcmPlayer(ctx.current);
        mic.current = new MicCapture(
          ctx.current,
          (pcm) => {
            if (ws.current?.readyState === WebSocket.OPEN) ws.current.send(pcm);
          },
          (lvl) => (micLevel.current = lvl),
        );
        await mic.current.start(); // triggers the browser permission prompt
      }

      const socket = new WebSocket(`${WS_BASE}/ws/call`);
      socket.binaryType = "arraybuffer";
      ws.current = socket;

      socket.onopen = () => dispatch({ type: "socket_open" });
      socket.onmessage = (msg) => {
        if (msg.data instanceof ArrayBuffer) {
          player.current?.play(msg.data);
          return;
        }
        let event: CallServerEvent;
        try {
          event = JSON.parse(msg.data as string);
        } catch {
          return;
        }
        if (event.type === "interrupt") player.current?.flush();
        dispatch({ type: "server", event, now: Date.now() });
      };
      socket.onerror = () => {
        if (!hungUp.current) {
          dispatch({ type: "failed", message: "Lost connection to the voice server.", now: Date.now() });
        }
      };
      socket.onclose = () => {
        if (!hungUp.current) dispatch({ type: "hangup", now: Date.now() });
        teardown();
      };
    } catch (err) {
      const message =
        err instanceof DOMException && err.name === "NotAllowedError"
          ? "Microphone permission was denied. Allow it in the browser and try again."
          : err instanceof Error
            ? err.message
            : "Could not start the call.";
      dispatch({ type: "failed", message, now: Date.now() });
      teardown();
    }
  }, [expectedMode, teardown]);

  const end = useCallback(() => {
    hungUp.current = true;
    dispatch({ type: "hangup", now: Date.now() });
    teardown();
  }, [teardown]);

  const toggleMute = useCallback(() => {
    if (mic.current) mic.current.muted = !mic.current.muted;
    dispatch({ type: "toggle_mute" });
  }, []);

  const sendText = useCallback((text: string) => {
    const trimmed = text.trim();
    if (!trimmed || ws.current?.readyState !== WebSocket.OPEN) return;
    ws.current.send(JSON.stringify({ type: "user_text", text: trimmed }));
  }, []);

  // Call timer.
  useEffect(() => {
    if (state.phase !== "connected" || !state.startedAt) return;
    const id = window.setInterval(
      () => setElapsed(Math.floor((Date.now() - (state.startedAt ?? Date.now())) / 1000)),
      500,
    );
    return () => window.clearInterval(id);
  }, [state.phase, state.startedAt]);

  // Waveform levels (sampled ~12 times a second to keep renders cheap).
  useEffect(() => {
    if (state.phase !== "connected") return;
    const id = window.setInterval(() => {
      setLevels({ mic: micLevel.current, agent: player.current?.level() ?? 0 });
    }, 80);
    return () => window.clearInterval(id);
  }, [state.phase]);

  // Hang up if the component unmounts mid-call.
  useEffect(() => () => teardown(), [teardown]);

  return { state, elapsed, levels, start, end, toggleMute, sendText, reset: () => dispatch({ type: "reset" }) };
}
