import { useEffect, useRef, useState } from "react";
import type { HudConfig, HudMeter, MonitorInfo, ScreenCapture } from "../types";

export const toHex = (c: number[] | null | undefined, fallback: string) =>
  c ? `#${c.map((v) => v.toString(16).padStart(2, "0")).join("")}` : fallback;

export const fromHex = (hex: string) => [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16));

const ROW_LABELS = [
  "Fila 1 — números",
  "Fila 2 — Q a P",
  "Fila 3 — A a Ç",
  "Fila 4 — Z a -",
  "Fila 5 — espaço",
];

const MAX_METERS = 6;

export function newMeter(index: number): HudMeter {
  return {
    id: `m${Date.now().toString(36)}${index}`,
    name: index === 0 ? "Vida" : `Medidor ${index + 1}`,
    region: [0.1, 0.9, 0.2, 0.03],
    color: [255, 255, 255],
    tolerance: 60,
    orientation: "horizontal",
    row: Math.min(5, index + 1),
    color_full: [0, 255, 60],
    color_empty: [255, 0, 0],
    low_threshold: 0.25,
    flash_on_drop: true,
  };
}

interface Props {
  hud: HudConfig;
  onChange: (hud: HudConfig) => void;
  monitors: MonitorInfo[];
  capture: ScreenCapture | null;
  probe: { id: string | null; fraction: number | null } | null;
  send: (data: Record<string, unknown>) => void;
}

type Tool = "region" | "color";

export function HudCalibrator({ hud, onChange, monitors, capture, probe, send }: Props) {
  const [active, setActive] = useState(0);
  const [tool, setTool] = useState<Tool>("region");
  const [waiting, setWaiting] = useState(false);
  const imgRef = useRef<HTMLImageElement>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const drag = useRef<{ x: number; y: number } | null>(null);

  const meter: HudMeter | undefined = hud.meters[active] ?? hud.meters[0];

  useEffect(() => {
    send({ action: "list_monitors" });
  }, [send]);

  useEffect(() => {
    if (capture) setWaiting(false);
  }, [capture]);

  const setMeter = (patch: Partial<HudMeter>) =>
    onChange({ ...hud, meters: hud.meters.map((m, i) => (i === active ? { ...m, ...patch } : m)) });

  const grab = (delay: number) => {
    setWaiting(true);
    send({ action: "capture_screen", monitor: hud.monitor, delay });
  };

  // Posição normalizada (0..1) de um evento sobre a captura.
  const norm = (e: React.PointerEvent) => {
    const r = imgRef.current!.getBoundingClientRect();
    return {
      x: Math.min(1, Math.max(0, (e.clientX - r.left) / r.width)),
      y: Math.min(1, Math.max(0, (e.clientY - r.top) / r.height)),
    };
  };

  const pickColor = (p: { x: number; y: number }) => {
    const img = imgRef.current;
    if (!img || !img.naturalWidth) return;
    const canvas = (canvasRef.current ??= document.createElement("canvas"));
    canvas.width = img.naturalWidth;
    canvas.height = img.naturalHeight;
    const ctx = canvas.getContext("2d", { willReadFrequently: true });
    if (!ctx) return;
    ctx.drawImage(img, 0, 0);
    const px = ctx.getImageData(
      Math.min(canvas.width - 1, Math.floor(p.x * canvas.width)),
      Math.min(canvas.height - 1, Math.floor(p.y * canvas.height)),
      1, 1,
    ).data;
    setMeter({ color: [px[0], px[1], px[2]] });
  };

  const onDown = (e: React.PointerEvent) => {
    if (!meter) return;
    const p = norm(e);
    if (tool === "color") {
      pickColor(p);
      return;
    }
    e.currentTarget.setPointerCapture(e.pointerId);
    drag.current = p;
  };

  const onMove = (e: React.PointerEvent) => {
    if (!drag.current || tool !== "region") return;
    const p = norm(e);
    const x = Math.min(drag.current.x, p.x);
    const y = Math.min(drag.current.y, p.y);
    setMeter({ region: [x, y, Math.max(0.005, Math.abs(p.x - drag.current.x)), Math.max(0.003, Math.abs(p.y - drag.current.y))] });
  };

  const onUp = () => {
    drag.current = null;
  };

  const measuring = probe && meter && probe.id === meter.id ? probe.fraction : null;

  return (
    <div className="wf-hud">
      <h4 className="text-sm font-medium text-gray-300 mb-1">Leitura do ecrã (HUD)</h4>
      <p className="text-xs text-gray-500 mb-3">
        Ao estilo das integrações do SignalRGB: escolhe a barra de vida (ou outra) no ecrã do jogo e o teclado mostra-a
        numa fila. Usa o jogo em janela sem bordas; em ecrã inteiro exclusivo a captura pode vir preta.
      </p>

      <div className="flex items-center gap-2 flex-wrap mb-3">
        <label className="text-xs text-gray-400 flex items-center gap-2">
          Monitor
          <select
            className="wf-field"
            value={hud.monitor}
            onChange={(e) => onChange({ ...hud, monitor: Number(e.target.value) })}
          >
            {(monitors.length ? monitors : [{ index: 0, width: 0, height: 0, primary: false }]).map((m) => (
              <option key={m.index} value={m.index}>
                {m.index + 1}{m.width ? ` — ${m.width}×${m.height}` : ""}{m.primary ? " (principal)" : ""}
              </option>
            ))}
          </select>
        </label>
        <button type="button" className="wt-btn" disabled={waiting} onClick={() => grab(0)}>Capturar agora</button>
        <button type="button" className="wt-btn" disabled={waiting} onClick={() => grab(5)}>
          {waiting ? "A capturar…" : "Capturar em 5 s"}
        </button>
      </div>
      <p className="text-xs text-gray-500 mb-3">
        «Capturar em 5 s» dá-te tempo para pôr o jogo à frente com a barra visível.
      </p>

      {capture?.error && <p className="text-xs text-red-300 mb-2">{capture.error}</p>}

      {capture?.image && (
        <div className="mb-3">
          <div className="flex gap-2 mb-2">
            <button type="button" className={`wt-btn ${tool === "region" ? "wf-hud-tool-on" : ""}`} onClick={() => setTool("region")}>
              1. Desenhar a região da barra
            </button>
            <button type="button" className={`wt-btn ${tool === "color" ? "wf-hud-tool-on" : ""}`} onClick={() => setTool("color")}>
              2. Escolher a cor da barra
            </button>
          </div>
          <div
            className="wf-hud-shot"
            onPointerDown={onDown}
            onPointerMove={onMove}
            onPointerUp={onUp}
            style={{ cursor: tool === "color" ? "crosshair" : "cell" }}
          >
            <img ref={imgRef} src={capture.image} alt="Captura do ecrã" draggable={false} />
            {hud.meters.map((m, i) => (
              <div
                key={m.id}
                className={`wf-hud-box ${i === active ? "on" : ""}`}
                style={{
                  left: `${m.region[0] * 100}%`, top: `${m.region[1] * 100}%`,
                  width: `${m.region[2] * 100}%`, height: `${m.region[3] * 100}%`,
                }}
              />
            ))}
          </div>
        </div>
      )}

      <div className="flex gap-2 flex-wrap mb-3">
        {hud.meters.map((m, i) => (
          <button
            key={m.id}
            type="button"
            className={`wt-btn ${i === active ? "wf-hud-tool-on" : ""}`}
            onClick={() => setActive(i)}
          >
            {m.name}
          </button>
        ))}
        {hud.meters.length < MAX_METERS && (
          <button
            type="button"
            className="wt-btn"
            onClick={() => {
              onChange({ ...hud, meters: [...hud.meters, newMeter(hud.meters.length)] });
              setActive(hud.meters.length);
            }}
          >
            + Medidor
          </button>
        )}
      </div>

      {meter && (
        <div className="wf-hud-meter">
          <div className="grid grid-cols-2 gap-3">
            <label className="wf-game-field">
              <span>Nome</span>
              <input className="wf-field" value={meter.name} maxLength={40} onChange={(e) => setMeter({ name: e.target.value })} />
            </label>
            <label className="wf-game-field">
              <span>Mostrar na</span>
              <select className="wf-field" value={meter.row} onChange={(e) => setMeter({ row: Number(e.target.value) })}>
                {ROW_LABELS.map((label, i) => (
                  <option key={label} value={i + 1}>{label}</option>
                ))}
              </select>
            </label>
            <label className="wf-game-field">
              <span>Direção da barra</span>
              <select
                className="wf-field"
                value={meter.orientation}
                onChange={(e) => setMeter({ orientation: e.target.value as HudMeter["orientation"] })}
              >
                <option value="horizontal">Horizontal</option>
                <option value="vertical">Vertical</option>
              </select>
            </label>
            <label className="wf-game-field">
              <span>Tolerância da cor ({meter.tolerance})</span>
              <input type="range" min={10} max={200} step={5} value={meter.tolerance}
                onChange={(e) => setMeter({ tolerance: Number(e.target.value) })} />
            </label>
          </div>

          <div className="flex items-center gap-4 flex-wrap mb-3 text-xs text-gray-300">
            <label className="flex items-center gap-2">
              Cor da barra no jogo
              <input type="color" value={toHex(meter.color, "#ffffff")} onChange={(e) => setMeter({ color: fromHex(e.target.value) })} />
            </label>
            <label className="flex items-center gap-2">
              Cheia
              <input type="color" value={toHex(meter.color_full, "#00ff3c")} onChange={(e) => setMeter({ color_full: fromHex(e.target.value) })} />
            </label>
            <label className="flex items-center gap-2">
              Vazia
              <input type="color" value={toHex(meter.color_empty, "#ff0000")} onChange={(e) => setMeter({ color_empty: fromHex(e.target.value) })} />
            </label>
            <label className="flex items-center gap-2">
              <input type="checkbox" checked={meter.flash_on_drop} onChange={(e) => setMeter({ flash_on_drop: e.target.checked })} />
              Piscar ao levar dano
            </label>
          </div>

          <div className="flex items-center gap-3 flex-wrap">
            <button
              type="button"
              className="wt-btn"
              onClick={() => send({ action: "hud_probe", monitor: hud.monitor, meter })}
            >
              Medir agora
            </button>
            {measuring !== null && (
              <span className="text-sm text-white">Leitura: {Math.round(measuring * 100)}%</span>
            )}
            {probe && probe.id === meter.id && probe.fraction === null && (
              <span className="text-xs text-red-300">Não foi possível ler este monitor.</span>
            )}
            {hud.meters.length > 1 && (
              <button
                type="button"
                className="wt-btn"
                onClick={() => {
                  onChange({ ...hud, meters: hud.meters.filter((_, i) => i !== active) });
                  setActive(0);
                }}
              >
                Remover medidor
              </button>
            )}
          </div>
          <p className="text-xs text-gray-500 mt-2">
            Dica: com a barra cheia a leitura deve dar perto de 100%, e com pouca vida deve descer. Se ler 0%,
            volta a escolher a cor ou sobe a tolerância.
          </p>
        </div>
      )}
    </div>
  );
}
