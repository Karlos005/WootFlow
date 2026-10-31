import type { Page } from "../types";

const NAV_ITEMS: { id: Page; label: string; icon: string }[] = [
  { id: "keyboard", label: "Teclado", icon: "⌨" },
  { id: "effects", label: "Efeitos", icon: "✦" },
  { id: "sound", label: "Som", icon: "♫" },
  { id: "perkey", label: "Per-Key", icon: "▦" },
  { id: "settings", label: "Definições", icon: "⚙" },
];

interface Props {
  page: Page;
  onPageChange: (p: Page) => void;
  connected: boolean;
  wsConnected: boolean;
}

export function Sidebar({ page, onPageChange, connected, wsConnected }: Props) {
  return (
    <aside className="w-[88px] border-r border-white/10 flex flex-col items-center py-4 gap-2 select-none wf-sidebar"
      style={{ WebkitAppRegion: "no-drag" } as React.CSSProperties}>

      {/* Logo */}
      <div className="mb-4 wf-logo-mark">WF</div>

      {/* Nav buttons */}
      {NAV_ITEMS.map((item) => (
        <button
          key={item.id}
          onClick={() => onPageChange(item.id)}
          className={`w-[68px] h-[62px] rounded-2xl flex flex-col items-center justify-center text-xs gap-1 transition-all duration-200 border
            ${page === item.id
              ? "bg-white/10 text-white border-white/20 shadow-lg shadow-black/30"
              : "text-gray-500 border-transparent hover:text-gray-200 hover:bg-white/5 hover:border-white/10"
            }`}
          title={item.label}
        >
          <span className="text-lg leading-none">{item.icon}</span>
          <span className="text-[10px] leading-none font-medium tracking-wide">{item.label}</span>
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
