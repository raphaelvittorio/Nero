// Bentuk data dari API fitur Clip Maker (features/clip/api.py, di bawah /api/clip)

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
  /** asal clip dari kolom referensi: timeline riset, link clip referensi, atau titik waktu */
  ref?: "timeline" | "link" | "titik" | null;
  /** subtitle dikoreksi setelah render terakhir: perlu render ulang */
  subs_changed?: boolean;
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
  /** isi kolom "Referensi & instruksi" */
  brief?: string;
  clips?: Clip[];
}

/** Hasil /api/parse-brief: apa saja yang dikenali dari kolom referensi */
export interface BriefSummary {
  ranges: { start: number; end: number; note: string }[];
  points: { t: number; note: string }[];
  links: string[];
  instructions: string;
  keywords: string[];
  avoid: string[];
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
  caption_font: "impact" | "montserrat" | "anton" | "bebas" | "poppins" | "arial";
  /** warna teks subtitle selain kata yang disorot */
  caption_base: string;
  /** angka & kata pemancing perhatian selalu disorot dan sedikit lebih besar */
  caption_emphasis: boolean;
  /** buang diam lebih lama dari ini (detik); 0 = tidak */
  cut_pauses: number;
}

/** Pengaturan khusus Clip Maker. API key, model AI & cookies ada di pengaturan umum Nero (useNero). */
export interface Settings {
  whisper_model: string;
  language: Language;
  n_clips: number;
  min_len: number;
  max_len: number;
  auto_render: boolean;
  style: Style;
  gpu: { device: "cuda" | "cpu"; error: string; encoder?: "h264_nvenc" | "libx264" };
}

export interface TranscriptLine {
  start: number;
  end: number;
  text: string;
}
