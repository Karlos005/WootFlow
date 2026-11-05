import { useState, useMemo, useEffect, type CSSProperties } from "react";
import { useWebSocket } from "./hooks/useWebSocket";
import { Sidebar } from "./components/Sidebar";
import { EffectsPanel } from "./components/EffectsPanel";
import { SoundReactive } from "./components/SoundReactive";
import { PerKeyPanel } from "./components/PerKeyPanel";
import { Settings } from "./components/Settings";
import { WootilityPage } from "./components/WootilityPage";
import { WootilityKeyboard } from "./components/WootilityKeyboard";
import type { Page } from "./types";
import type { RGB } from "./types";

function hexToRgbTuple(hex: string): string {
  const clean = hex.replace("#", "");
  if (!/^[0-9a-fA-F]{6}$/.test(clean)) return "0 255 200";
  const r = parseInt(clean.slice(0, 2), 16);
  const g = parseInt(clean.slice(2, 4), 16);
  const b = parseInt(clean.slice(4, 6), 16);
  return `${r} ${g} ${b}`;
}

export default function App() {
  const { state, audio, frame, keyDepth, connected, diagnostics, send } = useWebSocket();
  const [page, setPage] = useState<Page>("effects");
  const [themeHex, setThemeHex] = useState<string>(() => localStorage.getItem("wootflow.theme") || "#00ffc8");

  useEffect(() => {
    localStorage.setItem("wootflow.theme", themeHex);
  }, [themeHex]);

  // Convert frame data to Map<string, RGB> for KeyboardPreview
  const keyColors = useMemo(() => {
    if (!frame?.colors) return undefined;
    const map = new Map<string, RGB>();
    for (const [key, val] of Object.entries(frame.colors)) {
      map.set(key, { r: val[0], g: val[1], b: val[2] });
    }
    return map;
  }, [frame]);

  if (!state) {
    const statusText: Record<string, string> = {
      idle: "A iniciar...",
      connecting: "A tentar ligar WebSocket...",
      connected: "WebSocket ligado, a aguardar estado inicial...",
      retrying: "Nova tentativa em curso...",
      error: "Erro de ligação WebSocket",
    };

    return (
      <div className="h-screen wf-shell flex items-center justify-center">
        <div className="text-center max-w-lg px-6 wf-glass-panel">
          <div className="w-8 h-8 border-2 border-accent-cyan border-t-transparent rounded-full animate-spin mx-auto mb-4" />
          <p className="text-gray-200 text-sm font-medium">A ligar ao servidor...</p>
          <p className="text-gray-400 text-xs mt-3">{statusText[diagnostics.status] ?? diagnostics.status}</p>
          <p className="text-gray-500 text-xs mt-1">Tentativa: {diagnostics.attempt || 1}</p>
          <p className="text-gray-500 text-xs mt-1 break-all">Endpoint: {diagnostics.endpoint}</p>
          <p className="text-gray-500 text-xs mt-1">
            Backend: {diagnostics.backendReachable ? "OK" : "Indisponivel"}
          </p>
          {!!diagnostics.lastError && (
            <p className="text-red-400 text-xs mt-2">Erro: {diagnostics.lastError}</p>
          )}

          <p className="text-gray-600 text-xs mt-4">
            Se ficar preso aqui: fecha outras apps que usem porta 9120 e reinicia o WootFlow.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div
      className="h-screen text-white flex overflow-hidden wf-shell"
      style={{
        "--theme-accent": themeHex,
        "--theme-accent-rgb": hexToRgbTuple(themeHex),
      } as CSSProperties}
    >
      {/* Titlebar drag region */}
      <div
        className="fixed top-0 left-0 right-0 h-9 z-50"
        style={{ WebkitAppRegion: "drag" } as CSSProperties}
      />

      {/* Sidebar */}
      <Sidebar
        page={page}
        onPageChange={setPage}
        connected={state.connected}
        wsConnected={connected}
      />

      {/* Main content */}
      <div className="flex-1 flex flex-col min-w-0 pt-9">
        {/* Top bar with keyboard preview (always visible, except perkey and settings) */}
        {page !== "perkey" && page !== "settings" && page !== "keyboard" && (
          <div className="px-5 pt-4 pb-2 shrink-0">
            <div className="wf-glass-panel wf-top-preview flex justify-center">
            <WootilityKeyboard view="rgb" keyColors={keyColors} maxWidth={760} />
            </div>
          </div>
        )}

        {/* Page content */}
        <div className={`flex-1 p-5 overflow-y-auto custom-scroll ${page === "settings" ? "wf-settings-page" : ""}`}>
          {page === "keyboard" && <WootilityPage state={state} send={send} keyColors={keyColors} keyDepth={keyDepth} />}
          {page === "effects" && <EffectsPanel state={state} send={send} />}
          {page === "sound" && <SoundReactive state={state} audio={audio} send={send} />}
          {page === "perkey" && <PerKeyPanel state={state} send={send} />}
          {page === "settings" && (
            <Settings
              connected={state.connected}
              device={state.device}
              mode={state.mode}
              autoStartEnabled={Boolean(state.autoStartEnabled)}
              autoStartSupported={Boolean(state.autoStartSupported)}
              autoStartError={state.autoStartError}
              sleepDimMin={state.sleepDimMin ?? null}
              sleepOffMin={state.sleepOffMin ?? null}
              debounce={Boolean(state.debounce)}
              send={send}
              themeHex={themeHex}
              onThemeChange={setThemeHex}
            />
          )}
        </div>
      </div>
    </div>
  );
}
