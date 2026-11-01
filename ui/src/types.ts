export interface AppState {
  connected: boolean;
  mode: "effect" | "audio" | "perkey" | "off";
  effect: string;
  effects: [string, string][]; // [id, name]
  brightness: number;
  speed: number;
  color1: number[];
  color2: number[];
  effectParams?: {
    magneticInfluence?: number;
    liquidDeform?: number;
  };
  audioRunning: boolean;
  audioAvailable: boolean;
  _sensitivity?: number;
  _smoothing?: number;
  pynputAvailable: boolean;
  analog?: AnalogState;
  autoStartEnabled?: boolean;
  autoStartSupported?: boolean;
  autoStartError?: string;
  device?: DeviceInfo;
}

export interface DeviceInfo {
  model: string;
  layout: string;
  name?: string;
  form_factor?: string;
  rows?: number;
  cols?: number;
  key_count?: number;
  band_count?: number;
  measured?: boolean;
}

export interface AudioData {
  bands: number[];
  peaks: number[];
  volume: number;
}

export interface FrameData {
  colors: Record<string, number[]>; // "row-col" → [r, g, b]
  delta: boolean;
}

export type Page = "keyboard" | "effects" | "sound" | "perkey" | "settings";

export interface KeyTuning {
  actuation_mm: number;
  rapid_trigger: boolean;
  separate_sensitivity: boolean;
  sensitivity_mm: number;
  upstroke_mm: number;
  downstroke_mm: number;
}

export interface AnalogState {
  tachyon: boolean;
  default: KeyTuning;
  keys: Record<string, KeyTuning>; // "row-col" -> tuning
}

/** Patch sent to the backend; camelCase mirrors AnalogTuning.apply. */
export interface AnalogPatch {
  actuationMm?: number;
  rapidTrigger?: boolean;
  separateSensitivity?: boolean;
  sensitivityMm?: number;
  upstrokeMm?: number;
  downstrokeMm?: number;
}

export interface HSV {
  h: number; // 0-360
  s: number; // 0-1
  v: number; // 0-1
}

export interface RGB {
  r: number;
  g: number;
  b: number;
}

// Keyboard layout: ISO PT 60HE
export interface KeyDef {
  row: number; // SDK row (1-5)
  col: number; // SDK col
  visualRow?: number; // optional visual row override for preview-only placement
  x: number;   // visual x position (units)
  w: number;   // width (units)
  label: string;
}
