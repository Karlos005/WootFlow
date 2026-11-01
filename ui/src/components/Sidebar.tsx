import type { Page } from "../types";

const ICONS: Record<Page, string> = {
  keyboard: "M3 7h18v10H3z M7 11h.01 M11 11h.01 M15 11h.01 M7 14h10",
  effects: "M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z M19 15l.8 2.2L22 18l-2.2.8L19 21l-.8-2.2L16 18l2.2-.8z",
  sound: "M9 18V6l10-2v12 M9 18a3 3 0 11-6 0 3 3 0 016 0z M19 16a3 3 0 11-6 0 3 3 0 016 0z",
  perkey: "M4 4h7v7H4z M13 4h7v7h-7z M4 13h7v7H4z M13 13h7v7h-7z",
  settings: "M12 15a3 3 0 100-6 3 3 0 000 6z M19.4 15a1.7 1.7 0 00.3 1.8l.1.1a2 2 0 11-2.8 2.8l-.1-.1a1.7 1.7 0 00-1.8-.3 1.7 1.7 0 00-1 1.5V21a2 2 0 11-4 0v-.1a1.7 1.7 0 00-1.1-1.5 1.7 1.7 0 00-1.8.3l-.1.1a2 2 0 11-2.8-2.8l.1-.1a1.7 1.7 0 00.3-1.8 1.7 1.7 0 00-1.5-1H3a2 2 0 110-4h.1a1.7 1.7 0 001.5-1.1 1.7 1.7 0 00-.3-1.8l-.1-.1a2 2 0 112.8-2.8l.1.1a1.7 1.7 0 001.8.3H9a1.7 1.7 0 001-1.5V3a2 2 0 114 0v.1a1.7 1.7 0 001 1.5 1.7 1.7 0 001.8-.3l.1-.1a2 2 0 112.8 2.8l-.1.1a1.7 1.7 0 00-.3 1.8V9a1.7 1.7 0 001.5 1H21a2 2 0 110 4h-.1a1.7 1.7 0 00-1.5 1z",
};

const NAV_ITEMS: { id: Page; label: string }[] = [
  { id: "keyboard", label: "Teclado" },
  { id: "effects", label: "Efeitos" },
  { id: "sound", label: "Som" },
  { id: "perkey", label: "Per-Key" },
  { id: "settings", label: "Definições" },
];

interface Props {
  page: Page;
  onPageChange: (p: Page) => void;
  connected: boolean;
  wsConnected: boolean;
}

export function Sidebar({ page, onPageChange, connected, wsConnected }: Props) {
  return (
    <aside className="w-[92px] border-r border-white/10 flex flex-col items-center py-4 gap-2 select-none wf-sidebar"
      style={{ WebkitAppRegion: "no-drag" } as React.CSSProperties}>

      {/* Logo */}
      <div className="mb-4 wf-logo-mark">WF</div>

      {/* Nav buttons */}
      {NAV_ITEMS.map((item) => (
        <button
          key={item.id}
          onClick={() => onPageChange(item.id)}
          className={`wf-nav ${page === item.id ? "on" : ""}`}
          title={item.label}
        >
          <svg viewBox="0 0 24 24" aria-hidden><path d={ICONS[item.id]} /></svg>
          <span>{item.label}</span>
        </button>
      ))}

      <div className="flex-1" />

      {/* Status */}
      <div className="flex flex-col items-center gap-2 mb-2 wf-status-pills">
        <div className="flex flex-col items-center gap-1">
          <div className={`w-2.5 h-2.5 rounded-full ${connected ? "bg-green-500 animate-pulse" : "bg-red-500"}`}
            title={connected ? "Teclado conectado" : "Teclado desconectado"} />
          <span className="text-[8px] text-gray-500 leading-none">KB</span>
        </div>
        <div className="flex flex-col items-center gap-1">
          <div className={`w-2.5 h-2.5 rounded-full ${wsConnected ? "bg-accent-cyan animate-pulse" : "bg-gray-600"}`}
            title={wsConnected ? "Servidor online" : "Servidor offline"} />
          <span className="text-[8px] text-gray-500 leading-none">WS</span>
        </div>
      </div>
    </aside>
  );
}
