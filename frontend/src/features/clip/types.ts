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
  /** gaya khusus proyek ini dari pustaka (null = ikut gaya aktif) */
  style_id?: string | null;
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
  layout: "auto" | "face" | "split" | "blur" | "hitam" | "center";
  captions: boolean;
  caption_color: string;
  caption_upper: boolean;
  caption_size: number;
  caption_pos: number;
  caption_words: number;
  title_on: boolean;
  title_secs: number;
  title_bg: "putih" | "kuning" | "hitam" | "merah" | "tanpa";
  title_size: number;
  /** posisi judul (porsi tinggi layar dari atas) */
  title_pos: number;
  progress_bar: boolean;
  progress_pos: "bawah" | "atas";
  handle: string;
  handle_pos: "bawah" | "atas";
  loudnorm: boolean;
  caption_font: string;
  /** warna teks subtitle selain kata yang disorot */
  caption_base: string;
  /** angka & kata pemancing perhatian selalu disorot dan sedikit lebih besar */
  caption_emphasis: boolean;
  /** buang diam lebih lama dari ini (detik); 0 = tidak */
  cut_pauses: number;
  /** cara menyorot kata yang sedang diucapkan */
  caption_highlight: "warna" | "kotak" | "karaoke" | "tanpa";
  caption_anim: "pop" | "bounce" | "naik" | "tanpa";
  /** garis tepi huruf: 0 tanpa, 1 tipis, 2 sedang, 3 tebal */
  caption_stroke: number;
  caption_shadow: boolean;
  /** kotak gelap transparan di belakang subtitle */
  caption_box: boolean;
  zoom: "tanpa" | "halus" | "hentak";
  filter: "asli" | "cerah" | "hangat" | "dingin" | "hitamputih" | "sinematik" | "pudar";
}

export type StyleSource = "ukur" | "ai";

/** Satu gaya di pustaka: "Gaya saya" (tersimpan) atau preset bawaan. */
export interface StyleEntry {
  id: string;
  name: string;
  style: Partial<Style>;
  summary?: string;
  preset?: boolean;
  source?: { kind: "referensi" | "manual"; title?: string; url?: string };
  /** kunci gaya yang terbaca dari clip referensi */
  detected?: (keyof Style)[];
  /** asal tiap kunci yang terbaca: pengukuran piksel atau penilaian AI */
  sources?: Partial<Record<keyof Style, StyleSource>>;
  ai_model?: string;
  ai_provider?: "gemini" | "lokal" | "";
  notes?: string[];
  created?: number;
  /** kunci gambar contoh (berubah bila gaya / video contoh berubah) */
  thumb: string;
}

export interface StyleLibrary {
  styles: StyleEntry[];
  presets: StyleEntry[];
  active_id: string;
  /** gaya aktif sudah diubah sejak dipilih dari pustaka */
  active_modified: boolean;
  current_thumb: string;
}

export interface StyleJobResult {
  title: string;
  style_id: string;
  name: string;
  style: Style;
  detected: (keyof Style)[];
  sources: Partial<Record<keyof Style, StyleSource>>;
  notes: string[];
  seconds: number;
  ai: null | { provider: "gemini" | "lokal"; model: string; name: string; summary: string };
  ai_missing?: boolean;
}

/** Pembacaan gaya dari clip referensi yang berjalan di latar belakang. */
export interface StyleJob {
  id: string;
  status: "proses" | "selesai" | "gagal" | "batal";
  stage: string;
  progress: number;
  error: string;
  label?: string;
  result: StyleJobResult | null;
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
  /** gaya pustaka / preset yang terakhir dipakai sebagai gaya aktif ("" = diatur sendiri) */
  active_style_id: string;
  gpu: { device: "cuda" | "cpu"; error: string; encoder?: "h264_nvenc" | "libx264" };
}

export interface TranscriptLine {
  start: number;
  end: number;
  text: string;
}
