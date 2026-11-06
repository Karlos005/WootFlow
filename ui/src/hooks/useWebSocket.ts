import { useEffect, useRef, useState, useCallback } from "react";
import type { AppState, AudioData, FrameData, MonitorInfo, ScreenCapture } from "../types";

type WsStatus = "idle" | "connecting" | "connected" | "retrying" | "error";

export interface WsDiagnostics {
  status: WsStatus;
  attempt: number;
  endpoint: string;
  lastError: string;
  backendReachable: boolean;
}

function getWsCandidates(): string[] {
  const candidates = new Set<string>();

  if (typeof window !== "undefined") {
    const scheme = window.location.protocol === "https:" ? "wss" : "ws";
    if (window.location.host) {
      candidates.add(`${scheme}://${window.location.host}/ws`);
    }
  }

  candidates.add("ws://127.0.0.1:9120/ws");
  candidates.add("ws://localhost:9120/ws");
  return Array.from(candidates);
}

const RECONNECT_DELAY = 1500;  // Reduced from 2000ms for faster reconnect
const CONNECT_TIMEOUT = 8000;  // Increased from 5000ms to allow slower connections

export function useWebSocket() {
  const wsRef = useRef<WebSocket | null>(null);
  const [state, setState] = useState<AppState | null>(null);
  const [audio, setAudio] = useState<AudioData | null>(null);
  const [frame, setFrame] = useState<FrameData | null>(null);
  const [keyDepth, setKeyDepth] = useState<Record<string, number>>({});
  const [processes, setProcesses] = useState<string[]>([]);
  const [profileError, setProfileError] = useState<string>("");
  const [monitors, setMonitors] = useState<MonitorInfo[]>([]);
  const [screenCapture, setScreenCapture] = useState<ScreenCapture | null>(null);
  const [hudProbe, setHudProbe] = useState<{ id: string | null; fraction: number | null } | null>(null);
  const frameRef = useRef<Record<string, number[]>>({});
  const [connected, setConnected] = useState(false);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const connectTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const healthTimer = useRef<ReturnType<typeof setInterval> | undefined>(undefined);
  const endpointIndex = useRef(0);
  const wsCandidates = useRef<string[]>(getWsCandidates());
  const attemptCount = useRef(0);
  const [diagnostics, setDiagnostics] = useState<WsDiagnostics>({
    status: "idle",
    attempt: 0,
    endpoint: wsCandidates.current[0] ?? "ws://127.0.0.1:9120/ws",
    lastError: "",
    backendReachable: false,
  });

  const setDiag = useCallback((patch: Partial<WsDiagnostics>) => {
    setDiagnostics((prev) => ({ ...prev, ...patch }));
  }, []);

  const checkBackendHealth = useCallback(async () => {
    try {
      const res = await fetch("/health", { method: "GET", cache: "no-store" });
      if (!res.ok) {
        setDiag({ backendReachable: false });
        return;
      }
      const payload = await res.json();
      const ok = Boolean(payload?.ok) && payload?.service === "WootFlow";
      setDiag({ backendReachable: ok });
    } catch {
      setDiag({ backendReachable: false });
    }
  }, [setDiag]);

  const connect = useCallback(() => {
    if (
      wsRef.current?.readyState === WebSocket.OPEN ||
      wsRef.current?.readyState === WebSocket.CONNECTING
    ) {
      return;
    }

    const urls = wsCandidates.current;
    const wsUrl = urls[endpointIndex.current % urls.length];
    attemptCount.current += 1;
    setDiag({
      status: "connecting",
      attempt: attemptCount.current,
      endpoint: wsUrl,
    });

    console.log(`[WS] Attempt #${attemptCount.current}: Connecting to ${wsUrl}...`);

    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    clearTimeout(connectTimer.current);
    connectTimer.current = setTimeout(() => {
      if (ws.readyState === WebSocket.CONNECTING) {
        console.warn(`[WS] Connection timeout (${CONNECT_TIMEOUT}ms) for ${wsUrl}, trying next endpoint...`);
        setDiag({
          status: "retrying",
          lastError: `Timeout ao conectar (${CONNECT_TIMEOUT}ms)`,
        });
        ws.close();
      }
    }, CONNECT_TIMEOUT);

    ws.onopen = () => {
      clearTimeout(connectTimer.current);
      console.log(`[WS] ✓ Connected to ${wsUrl}`);
      setDiag({
        status: "connected",
        lastError: "",
        backendReachable: true,
      });
      setConnected(true);
      attemptCount.current = 0;  // Reset counter on success
    };

    ws.onmessage = (ev) => {
      try {
        const msg = JSON.parse(ev.data);
        if (msg.type === "state") {
          setState(msg as AppState);
        } else if (msg.type === "analog_live") {
          setKeyDepth(msg.keys ?? {});
        } else if (msg.type === "processes") {
          setProcesses(Array.isArray(msg.names) ? msg.names : []);
        } else if (msg.type === "monitors") {
          setMonitors(Array.isArray(msg.items) ? msg.items : []);
        } else if (msg.type === "screen_capture") {
          setScreenCapture(msg as ScreenCapture);
        } else if (msg.type === "hud_probe") {
          setHudProbe({ id: msg.id ?? null, fraction: msg.fraction ?? null });
        } else if (msg.type === "game_profile_error") {
          setProfileError(String(msg.message ?? "Erro ao guardar o perfil"));
        } else if (msg.type === "audio") {
          setAudio(msg as AudioData);
        } else if (msg.type === "frame") {
          const fd = msg as FrameData;
          if (fd.delta) {
            // Merge delta into accumulated frame
            const merged = { ...frameRef.current };
            for (const [k, v] of Object.entries(fd.colors)) {
              if (v[0] === 0 && v[1] === 0 && v[2] === 0) {
                delete merged[k];
              } else {
                merged[k] = v;
              }
            }
            frameRef.current = merged;
          } else {
            // Full frame — replace
            frameRef.current = { ...fd.colors };
          }
          setFrame({ colors: frameRef.current, delta: false });
        }
      } catch (err) {
        console.warn(`[WS] Failed to parse message:`, err);
      }
    };

    ws.onclose = () => {
      clearTimeout(connectTimer.current);
      console.log(`[WS] Disconnected from ${wsUrl}, will retry...`);
      setDiag({ status: "retrying" });
      setConnected(false);
      // Clear stale frame so the preview doesn't show stale colors after reconnect
      frameRef.current = {};
      setFrame(null);
      endpointIndex.current = (endpointIndex.current + 1) % wsCandidates.current.length;
      clearTimeout(reconnectTimer.current);
      reconnectTimer.current = setTimeout(connect, RECONNECT_DELAY);
    };

    ws.onerror = (ev) => {
      console.error(`[WS] Error connecting to ${wsUrl}:`, ev);
      setDiag({
        status: "error",
        lastError: "Falha na ligação WebSocket",
      });
      ws.close();
    };
  }, [setDiag]);

  useEffect(() => {
    checkBackendHealth();
    clearInterval(healthTimer.current);
    healthTimer.current = setInterval(checkBackendHealth, 2000);

    connect();

    return () => {
      clearInterval(healthTimer.current);
      clearTimeout(connectTimer.current);
      clearTimeout(reconnectTimer.current);
      wsRef.current?.close();
    };
  }, [checkBackendHealth, connect]);

  const send = useCallback((data: Record<string, unknown>) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(data));
    }
  }, []);

  return {
    state, audio, frame, keyDepth, processes, profileError, setProfileError,
    monitors, screenCapture, setScreenCapture, hudProbe, connected, diagnostics, send,
  };
}
