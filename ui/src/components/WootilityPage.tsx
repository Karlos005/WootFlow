import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { LAYOUT } from "./KeyboardPreview";
import { WootilityKeyboard, keyId } from "./WootilityKeyboard";
import type { AnalogPatch, AppState, KeyTuning, RGB } from "../types";
import "../wootility.css";

const MAX_MM = 4.0;
const MIN_MM = 0.1;
const DEFAULTS: KeyTuning = {
  actuation_mm: 1.5,
  rapid_trigger: false,
  separate_sensitivity: false,
  sensitivity_mm: 0.4,
  upstroke_mm: 0.4,
  downstroke_mm: 0.4,
};

interface Props {
  state: AppState;
  send: (data: Record<string, unknown>) => void;
  keyColors?: Map<string, RGB>;
  keyDepth?: Record<string, number>;
}

export function WootilityPage({ state, send, keyColors, keyDepth }: Props) {
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [view, setView] = useState<"live" | "rgb">("live");

  // Só lê o teclado enquanto o desenho ao vivo está visível.
  useEffect(() => {
    if (view !== "live") return;
    send({ action: "analog_live", enabled: true });
    return () => send({ action: "analog_live", enabled: false });
  }, [view, send]);

  const analog = state.analog;

  const tuningOf = useCallback(
    (id: string): KeyTuning => analog?.keys[id] ?? analog?.default ?? DEFAULTS,
    [analog],
  );

  const commit = useCallback(
    (patch: AnalogPatch) => {
      if (selected.size === 0) return;
      send({ action: "set_analog", keys: [...selected], patch });
    },
    [selected, send],
  );

  const toggleKey = (id: string, additive: boolean) =>
    setSelected((prev) => {
      const next = new Set(additive ? prev : []);
      const wasOnlySelection = prev.size === 1 && prev.has(id);
      if (additive ? prev.has(id) : wasOnlySelection) next.delete(id);
      else next.add(id);
      return next;
    });

  const allIds = useMemo(() => LAYOUT.map((k) => keyId(k.row, k.col)), []);
  const first = selected.size ? tuningOf([...selected][0]) : null;
  const mixed = useMemo(() => {
    if (selected.size < 2) return false;
    const [head, ...rest] = [...selected].map((id) => JSON.stringify(tuningOf(id)));
    return rest.some((v) => v !== head);
  }, [selected, tuningOf]);

  return (
    <div className="wt-page wf-page-entrance">
      <header className="wt-profile">
        <div className="wt-profile-badge">WF</div>
        <div className="wt-profile-name">Perfil de Escrita</div>
        <span className="wt-chip">{state.device?.model ?? "Wooting"}{state.device?.form_factor ? ` · ${state.device.form_factor}` : ""}</span>
        <div className="flex-1" />
        <div className="wt-seg" role="group" aria-label="Aspeto das teclas">
          <button type="button" className={view === "live" ? "on" : ""} onClick={() => setView("live")}>Ao vivo</button>
          <button type="button" className={view === "rgb" ? "on" : ""} onClick={() => setView("rgb")}>RGB</button>
        </div>
        <span
          className="wt-chip wt-chip-soft"
          title="Os valores são guardados no WootFlow; ainda não são gravados no firmware do teclado."
        >
          Modo software
        </span>
      </header>

      <WootilityKeyboard
        view={view}
        keyColors={keyColors}
        keyDepth={keyDepth}
        selected={selected}
        tuningOf={tuningOf}
        onKeyClick={toggleKey}
      />

      {selected.size === 0 && (
        <p className="wt-hint">
          Para ajustar o ponto de atuação e o Rapid Trigger, por favor selecione algumas teclas primeiro
        </p>
      )}

      <div className="wt-section-head">
        <h2>Definições rápidas</h2>
        <div className="flex-1" />
        <button type="button" className="wt-btn" onClick={() => setSelected(new Set(allIds))}>
          Selecionar todas as teclas
        </button>
        <button type="button" className="wt-btn" disabled={selected.size === 0} onClick={() => setSelected(new Set())}>
          Descartar seleção
        </button>
      </div>

      <div className={`wt-cards ${first ? "" : "wt-cards-idle"}`}>
        <ActuationCard
          value={first?.actuation_mm ?? DEFAULTS.actuation_mm}
          disabled={!first}
          mixed={mixed}
          onCommit={(mm) => commit({ actuationMm: mm })}
        />
        <RapidTriggerCard tuning={first ?? DEFAULTS} disabled={!first} onCommit={commit} />
        <TachyonCard
          on={Boolean(analog?.tachyon)}
          onToggle={() => send({ action: "set_analog", keys: [], tachyon: !analog?.tachyon })}
        />
      </div>
    </div>
  );
}

/* ── Cards ── */

function ActuationCard(props: { value: number; disabled: boolean; mixed: boolean; onCommit: (mm: number) => void }) {
  const [draft, setDraft] = useState(props.value);
  const dragging = useRef(false);
  useEffect(() => {
    if (!dragging.current) setDraft(props.value);
  }, [props.value]);

  return (
    <section className="wt-card">
      <h3>Ponto de Atuação</h3>
      <p>Defina o ponto para ativar uma premida de tecla para todas as teclas selecionadas.</p>
      <div className="wt-actuation">
        <SwitchGlyph travel={draft} />
        <VerticalSlider
          value={draft}
          min={MIN_MM}
          max={MAX_MM}
          disabled={props.disabled}
          onChange={(v) => {
            dragging.current = true;
            setDraft(v);
          }}
          onCommit={(v) => {
            dragging.current = false;
            props.onCommit(v);
          }}
        />
        <div className="wt-readout">
          <span>{props.mixed ? "—" : draft.toFixed(1)}</span> mm
        </div>
      </div>
    </section>
  );
}

function RapidTriggerCard(props: { tuning: KeyTuning; disabled: boolean; onCommit: (patch: AnalogPatch) => void }) {
  const { tuning: t, disabled } = props;
  return (
    <section className="wt-card">
      <div className="wt-card-title">
        <h3>Rapid Trigger</h3>
        <Toggle
          on={t.rapid_trigger}
          disabled={disabled}
          onClick={() => props.onCommit({ rapidTrigger: !t.rapid_trigger })}
        />
      </div>
      <p>
        Quando ativo, uma tecla rapidamente ativa e reinicia baseado no pressionamento intencionado ou largada de tecla.
      </p>
      <div className="wt-subrow">
        <span>Sensibilidade de upstroke e downstroke separadas</span>
        <Toggle
          on={t.separate_sensitivity}
          disabled={disabled || !t.rapid_trigger}
          onClick={() => props.onCommit({ separateSensitivity: !t.separate_sensitivity })}
        />
      </div>
      <div className={t.rapid_trigger && !disabled ? "" : "wt-dim"}>
        {t.separate_sensitivity ? (
          <>
            <HSlider label="Upstroke" value={t.upstroke_mm} onCommit={(v) => props.onCommit({ upstrokeMm: v })} />
            <HSlider label="Downstroke" value={t.downstroke_mm} onCommit={(v) => props.onCommit({ downstrokeMm: v })} />
          </>
        ) : (
          <HSlider
            label="Sensibilidade"
            value={t.sensitivity_mm}
            onCommit={(v) => props.onCommit({ sensitivityMm: v })}
          />
        )}
      </div>
    </section>
  );
}

function TachyonCard(props: { on: boolean; onToggle: () => void }) {
  return (
    <section className="wt-card">
      <div className="wt-card-title">
        <h3>Modo Tachyon</h3>
        <Toggle on={props.on} onClick={props.onToggle} />
      </div>
      <p>
        O modo Tachyon otimiza o teclado para velocidade da entrada. Quando ativo, cada tecla pressionada responde o mais
        rápido possível.
      </p>
      <div className="wt-label">Velocidade atual</div>
      <div className="wt-big">{props.on ? "~1 ms" : "~2 ms"}</div>
      <div className="wt-note">
        Esta característica limita o brilho do RGB. A definição fica guardada no WootFlow; a escrita no firmware ainda não
        está disponível.
      </div>
    </section>
  );
}

/* ── Controls ── */

function Toggle(props: { on: boolean; disabled?: boolean; onClick: () => void }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={props.on}
      disabled={props.disabled}
      className={`wt-toggle ${props.on ? "wt-toggle-on" : ""}`}
      onClick={props.onClick}
    >
      <span className="wt-toggle-knob" />
    </button>
  );
}

/** Horizontal slider that edits locally and commits once on release. */
function HSlider(props: { label: string; value: number; onCommit: (v: number) => void }) {
  const [draft, setDraft] = useState(props.value);
  const dragging = useRef(false);
  useEffect(() => {
    if (!dragging.current) setDraft(props.value);
  }, [props.value]);
  const release = () => {
    dragging.current = false;
    props.onCommit(draft);
  };
  return (
    <div className="wt-hslider">
      <div className="wt-label">{props.label}</div>
      <input
        type="range"
        min={MIN_MM}
        max={MAX_MM}
        step={0.1}
        value={draft}
        onChange={(e) => {
          dragging.current = true;
          setDraft(Number(e.target.value));
        }}
        onPointerUp={release}
        onKeyUp={release}
      />
      <div className="wt-readout wt-readout-sm">
        <span>{draft.toFixed(2)}</span> mm
      </div>
    </div>
  );
}

function VerticalSlider(props: {
  value: number;
  min: number;
  max: number;
  disabled: boolean;
  onChange: (v: number) => void;
  onCommit: (v: number) => void;
}) {
  const track = useRef<HTMLDivElement>(null);
  const latest = useRef(props.value);
  latest.current = props.value;

  const valueAt = (clientY: number) => {
    const r = track.current!.getBoundingClientRect();
    const ratio = Math.min(1, Math.max(0, (clientY - r.top) / r.height));
    const v = Math.round((props.min + ratio * (props.max - props.min)) * 10) / 10;
    latest.current = v;
    return v;
  };

  const onDown = (e: React.PointerEvent) => {
    if (props.disabled) return;
    e.currentTarget.setPointerCapture(e.pointerId);
    props.onChange(valueAt(e.clientY));
  };
  const onMove = (e: React.PointerEvent) => {
    if (e.buttons && !props.disabled) props.onChange(valueAt(e.clientY));
  };
  const onUp = () => {
    if (!props.disabled) props.onCommit(latest.current);
  };

  const pct = ((props.value - props.min) / (props.max - props.min)) * 100;
  return (
    <div
      ref={track}
      className={`wt-vslider ${props.disabled ? "wt-dim" : ""}`}
      onPointerDown={onDown}
      onPointerMove={onMove}
      onPointerUp={onUp}
      role="slider"
      aria-valuemin={props.min}
      aria-valuemax={props.max}
      aria-valuenow={props.value}
      aria-label="Ponto de atuação em milímetros"
    >
      <div className="wt-vtrack" />
      <div className="wt-vthumb" style={{ top: `${pct}%` }} />
    </div>
  );
}

/** Stylised switch; the dashed line marks the selected actuation depth. */
function SwitchGlyph({ travel }: { travel: number }) {
  const lineY = 58 + (travel / MAX_MM) * 56;
  return (
    <svg className="wt-switch" viewBox="0 0 120 140" aria-hidden>
      <rect x="22" y="58" width="76" height="70" rx="10" fill="#2b3340" stroke="#47536a" />
      <rect x="40" y="14" width="40" height="52" rx="6" fill="#3fbf95" opacity="0.85" />
      <line x1="10" x2="110" y1={lineY} y2={lineY} stroke="#00ffc8" strokeDasharray="4 3" />
    </svg>
  );
}
