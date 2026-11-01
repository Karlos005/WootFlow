import { LAYOUT } from "./KeyboardPreview";
import type { KeyTuning, RGB } from "../types";
import "../wootility.css";

export const keyId = (row: number, col: number) => `${row}-${col}`;

/** Cinzento do Wootility: escuro em repouso, claro com a tecla totalmente premida. */
export function depthShade(depth: number) {
  const v = Math.round(58 + Math.min(1, depth) * 172);
  return { bg: `rgb(${v} ${v + 2} ${v + 6})`, fg: v > 150 ? "#10131a" : "#e8edf8" };
}

interface Props {
  view: "live" | "rgb";
  keyColors?: Map<string, RGB>;
  keyDepth?: Record<string, number>;
  selected?: Set<string>;
  tuningOf?: (id: string) => KeyTuning;
  onKeyClick?: (id: string, additive: boolean) => void;
  maxWidth?: number;
}

export function WootilityKeyboard({ view, keyColors, keyDepth, selected, tuningOf, onKeyClick, maxWidth }: Props) {
  return (
    <div className="wt-board">
      <div className="wt-keyboard" style={maxWidth ? { width: `min(100%, ${maxWidth}px)` } : undefined}>
        <div className="wt-keys">
          {LAYOUT.map((k, i) => {
            const id = keyId(k.row, k.col);
            const row = (k.visualRow ?? k.row) - 1;
            const live = keyColors?.get(id);
            const hue = (360 + 320 - (k.x / 15) * 320) % 360;
            const rgbBg = live ? `rgb(${live.r} ${live.g} ${live.b})` : `hsl(${hue} 82% 42%)`;
            const shade = depthShade(keyDepth?.[id] ?? 0);
            const on = selected?.has(id) ?? false;
            const t = tuningOf?.(id);
            return (
              <button
                key={`${id}-${i}`}
                type="button"
                className={`wt-key ${on ? "wt-key-on" : ""}`}
                style={{
                  left: `calc(${(k.x / 15) * 100}% + 1.5px)`,
                  top: `calc(${(row / 5) * 100}% + 1.5px)`,
                  width: `calc(${(k.w / 15) * 100}% - 3px)`,
                  height: "calc(20% - 3px)",
                  background: view === "live" ? shade.bg : rgbBg,
                  color: view === "live" ? shade.fg : undefined,
                  textShadow: view === "live" ? "none" : undefined,
                  cursor: onKeyClick ? undefined : "default",
                }}
                title={
                  t
                    ? `${k.label || "Space"} · ${t.actuation_mm.toFixed(1)} mm${t.rapid_trigger ? " · RT" : ""}`
                    : k.label || "Space"
                }
                onClick={(e) => onKeyClick?.(id, e.ctrlKey || e.shiftKey || e.metaKey)}
              >
                {k.label}
                {on && <span className="wt-key-dot" />}
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}
