import { useMemo, useState } from "react";
import { HudCalibrator, fromHex, newMeter, toHex } from "./HudCalibrator";
import type { AppState, GameProfile, HudConfig, MonitorInfo, ScreenCapture } from "../types";

interface Props {
  state: AppState;
  send: (data: Record<string, unknown>) => void;
  processes: string[];
  monitors: MonitorInfo[];
  screenCapture: ScreenCapture | null;
  hudProbe: { id: string | null; fraction: number | null } | null;
  error: string;
  clearError: () => void;
}

type Draft = {
  id?: string;
  name: string;
  processes: string;
  effect: string;
  trigger: "running" | "focused";
  enabled: boolean;
  useBrightness: boolean;
  brightness: number;
  useSpeed: boolean;
  speed: number;
  useColor1: boolean;
  color1: string;
  useColor2: boolean;
  color2: string;
  hud: HudConfig | null;
};

function emptyDraft(effect: string): Draft {
  return {
    name: "", processes: "", effect, trigger: "running", enabled: true,
    useBrightness: false, brightness: 1, useSpeed: false, speed: 1,
    useColor1: false, color1: "#00ffc8", useColor2: false, color2: "#ff0064", hud: null,
  };
}

function draftOf(p: GameProfile): Draft {
  return {
    id: p.id, name: p.name, processes: p.processes.join(", "), effect: p.effect,
    trigger: p.trigger, enabled: p.enabled,
    useBrightness: p.brightness !== null, brightness: p.brightness ?? 1,
    useSpeed: p.speed !== null, speed: p.speed ?? 1,
    useColor1: p.color1 !== null, color1: toHex(p.color1, "#00ffc8"),
    useColor2: p.color2 !== null, color2: toHex(p.color2, "#ff0064"),
    hud: p.hud,
  };
}

function Toggle(props: { on: boolean; onClick: () => void; label: string }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={props.on}
      aria-label={props.label}
      className={`wt-toggle ${props.on ? "wt-toggle-on" : ""}`}
      onClick={props.onClick}
    >
      <span className="wt-toggle-knob" />
    </button>
  );
}

export function GamesPage({ state, send, processes, monitors, screenCapture, hudProbe, error, clearError }: Props) {
  const info = state.gameProfiles;
  const effects = state.effects;
  const [draft, setDraft] = useState<Draft | null>(null);

  const effectName = useMemo(() => new Map(effects), [effects]);
  const patch = (p: Partial<Draft>) => setDraft((d) => (d ? { ...d, ...p } : d));

  const [localError, setLocalError] = useState("");

  const save = () => {
    if (!draft) return;
    clearError();
    const procs = draft.processes.split(/[,;\n]/).map((s) => s.trim()).filter(Boolean);
    if (!draft.name.trim() || procs.length === 0) {
      setLocalError("Indica um nome e pelo menos um executável (por exemplo cs2.exe).");
      return;
    }
    setLocalError("");
    send({
      action: "save_game_profile",
      profile: {
        id: draft.id,
        name: draft.name,
        processes: draft.processes.split(/[,;\n]/).map((s) => s.trim()).filter(Boolean),
        effect: draft.effect,
        trigger: draft.trigger,
        enabled: draft.enabled,
        brightness: draft.useBrightness ? draft.brightness : null,
        speed: draft.useSpeed ? draft.speed : null,
        color1: draft.useColor1 ? fromHex(draft.color1) : null,
        color2: draft.useColor2 ? fromHex(draft.color2) : null,
        hud: draft.effect === "hud_meters" ? draft.hud : null,
      },
    });
    setDraft(null);
  };

  const addProcess = (name: string) =>
    setDraft((d) => {
      if (!d) return d;
      const current = d.processes.split(/[,;\n]/).map((s) => s.trim()).filter(Boolean);
      if (current.includes(name)) return d;
      return { ...d, processes: [...current, name].join(", ") };
    });

  if (!info) {
    return <p className="text-sm text-gray-400">A carregar perfis de jogo…</p>;
  }

  return (
    <div className="wf-settings-grid">
      <div className="wf-settings-head">
        <h2 className="text-2xl font-semibold text-white">Perfis de Jogo</h2>
        <p className="text-sm text-gray-400">
          Muda o efeito do teclado sozinho quando um jogo abre e volta ao teu efeito quando fecha.
        </p>
      </div>

      <div className="wf-card">
        <div className="flex items-center justify-between gap-4">
          <div>
            <h3 className="text-sm font-medium text-gray-300">Trocar perfil automaticamente</h3>
            <p className="text-xs text-gray-500 mt-1">
              O WootFlow verifica a cada 2 segundos que programas estão abertos.
            </p>
          </div>
          <Toggle
            on={info.enabled}
            label="Trocar perfil automaticamente"
            onClick={() => send({ action: "set_game_profiles_enabled", enabled: !info.enabled })}
          />
        </div>
        {!info.supported && (
          <p className="text-xs text-amber-300 mt-3">A deteção de jogos só funciona no Windows.</p>
        )}
      </div>

      {info.profiles.map((p) => (
        <div key={p.id} className={`wf-card wf-game-card ${info.active === p.id ? "wf-game-active" : ""}`}>
          <div className="flex items-start justify-between gap-4">
            <div className="min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <h3 className="text-base font-semibold text-white">{p.name}</h3>
                {info.active === p.id && <span className="wf-game-badge">A ATIVAR AGORA</span>}
                {!p.enabled && <span className="text-xs text-gray-500">desativado</span>}
              </div>
              <p className="text-xs text-gray-400 mt-1">
                {effectName.get(p.effect) ?? p.effect} ·{" "}
                {p.trigger === "focused" ? "só em primeiro plano" : "enquanto estiver aberto"}
                {p.brightness !== null && ` · brilho ${Math.round(p.brightness * 100)}%`}
                {p.speed !== null && ` · velocidade ${p.speed.toFixed(1)}x`}
              </p>
              <div className="flex gap-1.5 flex-wrap mt-2">
                {p.processes.map((proc) => (
                  <span key={proc} className="wf-game-chip">{proc}</span>
                ))}
              </div>
            </div>
            <div className="flex items-center gap-2 shrink-0">
              <Toggle
                on={p.enabled}
                label={`Ativar ${p.name}`}
                onClick={() =>
                  send({ action: "save_game_profile", profile: { ...p, enabled: !p.enabled } })
                }
              />
              <button type="button" className="wt-btn" onClick={() => { clearError(); setDraft(draftOf(p)); }}>
                Editar
              </button>
              <button
                type="button"
                className="wt-btn"
                onClick={() => send({ action: "delete_game_profile", id: p.id })}
              >
                Apagar
              </button>
            </div>
          </div>
        </div>
      ))}

      {info.profiles.length === 0 && !draft && (
        <div className="wf-card">
          <p className="text-sm text-gray-400">
            Ainda não tens perfis. Cria um, escolhe o executável do jogo (por exemplo <code>cs2.exe</code>) e o efeito que
            queres quando ele estiver aberto.
          </p>
        </div>
      )}

      {!draft && (
        <div>
          <button
            type="button"
            className="wf-primary-btn"
            onClick={() => {
              clearError();
              setDraft(emptyDraft(state.effect in Object.fromEntries(effects) ? state.effect : effects[0]?.[0] ?? "breathing"));
            }}
          >
            + Novo perfil
          </button>
        </div>
      )}

      {draft && (
        <div className="wf-card wf-game-editor">
          <h3 className="text-sm font-medium text-gray-300 mb-3">{draft.id ? "Editar perfil" : "Novo perfil"}</h3>

          <label className="wf-game-field">
            <span>Nome</span>
            <input
              className="wf-field"
              value={draft.name}
              maxLength={60}
              placeholder="Counter-Strike 2"
              onChange={(e) => patch({ name: e.target.value })}
            />
          </label>

          <label className="wf-game-field">
            <span>Executáveis (separados por vírgula)</span>
            <input
              className="wf-field"
              value={draft.processes}
              placeholder="cs2.exe"
              onChange={(e) => patch({ processes: e.target.value })}
            />
          </label>
          <div className="flex items-center gap-2 flex-wrap mb-3">
            <button type="button" className="wt-btn" onClick={() => send({ action: "list_processes" })}>
              Escolher das janelas abertas
            </button>
            {processes.map((name) => (
              <button key={name} type="button" className="wf-game-chip wf-game-chip-btn" onClick={() => addProcess(name)}>
                + {name}
              </button>
            ))}
          </div>

          <div className="grid grid-cols-2 gap-3">
            <label className="wf-game-field">
              <span>Efeito</span>
              <select
                className="wf-field"
                value={draft.effect}
                onChange={(e) =>
                  patch({
                    effect: e.target.value,
                    hud: e.target.value === "hud_meters" ? draft.hud ?? { monitor: 0, meters: [newMeter(0)] } : draft.hud,
                  })
                }
              >
                {effects.map(([id, name]) => (
                  <option key={id} value={id}>{name}</option>
                ))}
              </select>
            </label>
            <label className="wf-game-field">
              <span>Quando aplicar</span>
              <select
                className="wf-field"
                value={draft.trigger}
                onChange={(e) => patch({ trigger: e.target.value as Draft["trigger"] })}
              >
                <option value="running">Enquanto o jogo estiver aberto</option>
                <option value="focused">Só com o jogo em primeiro plano</option>
              </select>
            </label>
          </div>

          {draft.effect === "hud_meters" && draft.hud && (
            <HudCalibrator
              hud={draft.hud}
              onChange={(hud) => patch({ hud })}
              monitors={monitors}
              capture={screenCapture}
              probe={hudProbe}
              send={send}
            />
          )}

          <div className="wf-game-overrides">
            <label className="wf-game-check">
              <input type="checkbox" checked={draft.useBrightness} onChange={(e) => patch({ useBrightness: e.target.checked })} />
              Brilho próprio
            </label>
            {draft.useBrightness && (
              <input type="range" min={0} max={1} step={0.05} value={draft.brightness}
                onChange={(e) => patch({ brightness: Number(e.target.value) })} />
            )}
            <label className="wf-game-check">
              <input type="checkbox" checked={draft.useSpeed} onChange={(e) => patch({ useSpeed: e.target.checked })} />
              Velocidade própria
            </label>
            {draft.useSpeed && (
              <input type="range" min={0.1} max={5} step={0.1} value={draft.speed}
                onChange={(e) => patch({ speed: Number(e.target.value) })} />
            )}
            <label className="wf-game-check">
              <input type="checkbox" checked={draft.useColor1} onChange={(e) => patch({ useColor1: e.target.checked })} />
              Cor 1
              {draft.useColor1 && (
                <input type="color" value={draft.color1} onChange={(e) => patch({ color1: e.target.value })} />
              )}
            </label>
            <label className="wf-game-check">
              <input type="checkbox" checked={draft.useColor2} onChange={(e) => patch({ useColor2: e.target.checked })} />
              Cor 2
              {draft.useColor2 && (
                <input type="color" value={draft.color2} onChange={(e) => patch({ color2: e.target.value })} />
              )}
            </label>
          </div>

          {(localError || error) && <p className="text-xs text-red-300 mt-3">{localError || error}</p>}

          <div className="flex gap-2 mt-4">
            <button type="button" className="wf-primary-btn" onClick={save}>Guardar</button>
            <button type="button" className="wt-btn" onClick={() => { clearError(); setLocalError(""); setDraft(null); }}>Cancelar</button>
          </div>
        </div>
      )}
      {!draft && error && <p className="text-xs text-red-300">{error}</p>}
    </div>
  );
}
