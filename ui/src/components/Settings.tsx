import type { DeviceInfo } from "../types";

interface Props {
  connected: boolean;
  device?: DeviceInfo;
  mode: string;
  autoStartEnabled: boolean;
  autoStartSupported: boolean;
  autoStartError?: string;
  send: (data: Record<string, unknown>) => void;
  themeHex: string;
  onThemeChange: (value: string) => void;
}

export function Settings({
  connected,
  device,
  mode,
  autoStartEnabled,
  autoStartSupported,
  autoStartError,
  send,
  themeHex,
  onThemeChange,
}: Props) {
  return (
    <div className="wf-settings-grid">
      <div className="wf-settings-head">
        <h2 className="text-2xl font-semibold text-white">Definições</h2>
        <p className="text-sm text-gray-400">Configuração da aplicação e personalização da interface.</p>
      </div>

      {/* Device info */}
      <div className="wf-card wf-card-hero">
        <h3 className="text-sm font-medium text-gray-300 mb-3">Dispositivo</h3>
        <div className="flex items-center gap-3 mb-3">
          <div className={`w-3 h-3 rounded-full ${connected ? "bg-green-500 animate-pulse" : "bg-red-500"}`} />
          <span className="text-base text-gray-200">
            {connected && device
              ? `${device.model} (${device.layout})`
              : connected
              ? "Teclado conectado"
              : "Nenhum teclado detectado"}
          </span>
        </div>
        {connected && device && (
          <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs text-gray-400 mb-3">
            {device.form_factor && (<><dt>Formato</dt><dd className="text-gray-200">{device.form_factor}</dd></>)}
            {device.key_count != null && (<><dt>Teclas com LED</dt><dd className="text-gray-200">{device.key_count}</dd></>)}
            {device.rows != null && (<><dt>Matriz RGB</dt><dd className="text-gray-200">{device.rows}×{device.cols}</dd></>)}
            {device.measured != null && (
              <><dt>Efeitos adaptados</dt>
              <dd className="text-gray-200">{device.measured ? "Layout medido" : "Grelha aproximada"}</dd></>
            )}
          </dl>
        )}
        <p className="text-xs text-gray-500 mb-4">
          Estado atualizado em tempo real. Se desligares o cabo USB, este painel reflete de imediato.
        </p>
        <button
          onClick={() => send({ action: "reconnect" })}
          className="wf-primary-btn"
        >
          ↻ Reconectar
        </button>
      </div>

      {/* LEDs */}
      <div className="wf-card">
        <h3 className="text-sm font-medium text-gray-300 mb-3">LEDs</h3>
        <div className="flex gap-2 flex-wrap">
          <button
            onClick={() => send({ action: "set_mode", mode: "off" })}
            className={`px-4 py-2 rounded-lg text-sm transition-all ${
              mode === "off"
                ? "bg-red-500/20 text-red-400 border border-red-500/30"
                : "bg-white/5 text-gray-300 border border-white/10 hover:bg-white/10"
            }`}
          >
            ⏻ Desligar LEDs
          </button>
          {mode === "off" && (
            <button
              onClick={() => send({ action: "set_mode", mode: "effect" })}
              className="px-4 py-2 rounded-lg text-sm bg-white/10 text-white border border-white/20 hover:bg-white/15 transition-all"
            >
              ✦ Ligar LEDs
            </button>
          )}
        </div>
      </div>

      {/* Theme */}
      <div className="wf-card">
        <h3 className="text-sm font-medium text-gray-300 mb-3">Tema da Interface</h3>
        <div className="flex items-center gap-4 flex-wrap">
          <label className="flex items-center gap-3">
            <span className="text-xs text-gray-400 uppercase tracking-wider">Cor Base</span>
            <input
              type="color"
              value={themeHex}
              onChange={(e) => onThemeChange(e.target.value)}
              className="w-12 h-9 bg-transparent border border-white/20 rounded-md p-1 cursor-pointer"
            />
          </label>
          <input
            value={themeHex}
            onChange={(e) => onThemeChange(e.target.value)}
            className="wf-field w-28"
            maxLength={7}
          />
          <button
            onClick={() => onThemeChange("#00ffc8")}
            className="px-3 py-1.5 rounded-md text-xs bg-white/5 text-gray-300 border border-white/10 hover:bg-white/10"
          >
            Reset tema
          </button>
        </div>
      </div>

      {/* Auto start */}
      <div className="wf-card">
        <h3 className="text-sm font-medium text-gray-300 mb-3">Arranque Automático</h3>
        <div className="flex items-center justify-between gap-4">
          <div>
            <p className="text-sm text-gray-200">Iniciar WootFlow com o Windows</p>
            <p className="text-xs text-gray-500">
              Quando ativo, a app inicia minimizada na tray para continuar os efeitos.
            </p>
          </div>
          <button
            type="button"
            disabled={!autoStartSupported}
            onClick={() => send({ action: "set_auto_start", enabled: !autoStartEnabled })}
            className={`px-4 py-2 rounded-lg text-sm border transition-all ${
              autoStartEnabled
                ? "bg-emerald-500/20 text-emerald-300 border-emerald-500/30"
                : "bg-white/5 text-gray-300 border-white/10 hover:bg-white/10"
            } ${!autoStartSupported ? "opacity-40 cursor-not-allowed" : ""}`}
          >
            {autoStartEnabled ? "Ativo" : "Desativado"}
          </button>
        </div>
        {!autoStartSupported && (
          <p className="text-xs text-amber-300 mt-3">Disponível apenas em Windows.</p>
        )}
        {autoStartError && (
          <p className="text-xs text-red-300 mt-3">Falha ao atualizar auto arranque: {autoStartError}</p>
        )}
      </div>

      {/* About */}
      <div className="wf-card">
        <h3 className="text-sm font-medium text-gray-300 mb-3">Sobre</h3>
        <div className="space-y-1 text-sm text-gray-500">
          <p>WootFlow Control v3.3.0</p>
          <p>Layout: ISO PT 60HE</p>
          <p>Backend: Python + FastAPI + WebSocket</p>
          <p>Frontend: React + Tailwind + pywebview</p>
        </div>
      </div>

      {/* Tech stack */}
      <div className="wf-card">
        <h3 className="text-sm font-medium text-gray-300 mb-3">Stack</h3>
        <div className="grid grid-cols-2 gap-2 text-xs text-gray-500">
          <span>● WootFlow SDK Bridge</span>
          <span>● PyAudioWPATCH (WASAPI)</span>
          <span>● pynput (input hooks)</span>
          <span>● FastAPI + uvicorn</span>
          <span>● React 19</span>
          <span>● Tailwind CSS 3</span>
          <span>● pywebview</span>
          <span>● Vite</span>
        </div>
      </div>
    </div>
  );
}
