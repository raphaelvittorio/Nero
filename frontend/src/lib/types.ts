// Bentuk data dari API Flask (app.py)

export type ProjectStatus = "antri" | "proses" | "siap" | "gagal";
export type RenderStatus = "antri" | "proses" | "selesai" | "gagal" | null;
export type Language = "id" | "en" | "auto" | "ms" | "jv";

export interface Clip {
  id: string;
  start: number;
  end: number;
  title: string;
  score?: number;
  reason?: string;
  caption?: string;
  hashtags?: string[];
  text?: string;
  selected: boolean;
  render_status: RenderStatus;
  render_progress?: number;
  file: string | null;
  error?: string;
  rendered_at?: number;
}

export interface Project {
  id: string;
  title: string;
  url?: string;
  status: ProjectStatus;
  stage?: string;
  progress?: number;
  error?: string;
  warning?: string;
  source?: string | null;
  source_removed?: boolean;
  duration?: number;
  size_mb?: number;
  used_ai?: boolean;
  n_clips?: number;
  clips?: Clip[];
}

export interface AppState {
  projects: Project[];
  queue: number;
}

export interface Style {
  layout: "auto" | "face" | "split" | "blur" | "center";
  captions: boolean;
  caption_color: string;
  caption_upper: boolean;
  caption_size: number;
  caption_pos: number;
  caption_words: number;
  title_on: boolean;
  title_secs: number;
  title_bg: "putih" | "kuning" | "hitam";
  title_size: number;
  progress_bar: boolean;
  handle: string;
  loudnorm: boolean;
}

export interface Settings {
  has_key: boolean;
  ai_model: string;
  whisper_model: string;
  language: Language;
  n_clips: number;
  min_len: number;
  max_len: number;
  auto_render: boolean;
  cookies_browser: string;
  style: Style;
  gpu: { device: "cuda" | "cpu"; error: string };
}

export interface TranscriptLine {
  start: number;
  end: number;
  text: string;
}
