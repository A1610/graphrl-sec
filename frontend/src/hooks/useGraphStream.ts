/**
 * useGraphStream — WebSocket hook that subscribes to /ws/graph-stats.
 *
 * The server pushes a fresh GraphStatsResponse every 5 seconds.
 * The hook automatically reconnects with exponential back-off on disconnect.
 *
 * Returns:
 *   - `stats`       — latest received stats, or null before first message
 *   - `connected`   — true when the WebSocket is in OPEN state
 *   - `error`       — last error message, or null
 */

import { useCallback, useEffect, useRef, useState } from "react";

import type { GraphStatsResponse } from "@/types/api";

const WS_URL = "ws://localhost:8000/ws/graph-stats";
const INITIAL_BACKOFF_MS = 1_000;
const MAX_BACKOFF_MS = 30_000;

interface GraphStreamState {
  stats: GraphStatsResponse | null;
  connected: boolean;
  error: string | null;
}

export function useGraphStream(): GraphStreamState {
  const [state, setState] = useState<GraphStreamState>({
    stats: null,
    connected: false,
    error: null,
  });

  const wsRef = useRef<WebSocket | null>(null);
  const backoffRef = useRef<number>(INITIAL_BACKOFF_MS);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const unmountedRef = useRef<boolean>(false);

  const connect = useCallback(() => {
    if (unmountedRef.current) return;

    const ws = new WebSocket(WS_URL);
    wsRef.current = ws;

    ws.onopen = () => {
      if (unmountedRef.current) return;
      backoffRef.current = INITIAL_BACKOFF_MS;
      setState((prev) => ({ ...prev, connected: true, error: null }));
    };

    ws.onmessage = (event: MessageEvent<string>) => {
      if (unmountedRef.current) return;
      try {
        const payload = JSON.parse(event.data) as
          | (GraphStatsResponse & { error: string | null })
          | { error: string };

        if ("error" in payload && payload.error != null) {
          setState((prev) => ({ ...prev, error: payload.error as string }));
          return;
        }
        setState({
          stats: payload as GraphStatsResponse,
          connected: true,
          error: null,
        });
      } catch {
        setState((prev) => ({
          ...prev,
          error: "Failed to parse WebSocket message",
        }));
      }
    };

    ws.onerror = () => {
      if (unmountedRef.current) return;
      setState((prev) => ({
        ...prev,
        connected: false,
        error: "WebSocket connection error",
      }));
    };

    ws.onclose = () => {
      if (unmountedRef.current) return;
      setState((prev) => ({ ...prev, connected: false }));

      // Exponential back-off reconnect
      const delay = Math.min(backoffRef.current * 2, MAX_BACKOFF_MS);
      backoffRef.current = delay;
      reconnectTimerRef.current = setTimeout(connect, delay);
    };
  }, []);

  useEffect(() => {
    unmountedRef.current = false;
    connect();

    return () => {
      unmountedRef.current = true;
      if (reconnectTimerRef.current != null) {
        clearTimeout(reconnectTimerRef.current);
      }
      if (wsRef.current != null) {
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, [connect]);

  return state;
}
