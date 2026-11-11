import type { Option } from "@/components/fields";

import type { Language, Style } from "./types";

export const LANGUAGES: Option<Language>[] = [
  ["id", "Indonesia"],
  ["en", "Inggris"],
  ["auto", "Deteksi otomatis"],
  ["ms", "Melayu"],
  ["jv", "Jawa"],
];

export const WHISPER_MODELS: Option<string>[] = [
  ["base", "base — paling cepat"],
  ["small", "small — seimbang (disarankan)"],
  ["medium", "medium — lebih akurat, lambat"],
  ["large-v3-turbo", "large-v3-turbo — hampir seakurat large-v3, jauh lebih cepat (GPU)"],
  ["large-v3", "large-v3 — paling akurat, butuh GPU"],
];

export const CAPTION_COLORS: Record<string, string> = {
  kuning: "#ffdd00",
  hijau: "#39ff14",
  merah: "#ff3b3b",
  biru: "#00c8ff",
  pink: "#ff50c8",
  putih: "#ffffff",
};

type Base<K extends keyof Style> = { key: K; label: string };

export type StyleField =
  | (Base<keyof Style> & { type: "bool" })
  | (Base<keyof Style> & { type: "select"; options: Option<string | number>[] })
  | (Base<keyof Style> & { type: "range"; min: number; max: number; step: number })
  | (Base<keyof Style> & { type: "text"; placeholder: string })
  | (Base<keyof Style> & { type: "color" });

export const STYLE_FIELDS: StyleField[] = [
  {
    key: "layout",
    label: "Tata letak",
    type: "select",
    options: [
      ["auto", "Otomatis (wajah / dua orang / blur)"],
      ["face", "Ikuti wajah"],
      ["split", "Dua orang (atas/bawah)"],
      ["blur", "Video utuh + latar blur"],
      ["center", "Potong tengah"],
    ],
  },
  { key: "captions", label: "Subtitle otomatis", type: "bool" },
  {
    key: "caption_font",
    label: "Font",
    type: "select",
    options: [
      ["impact", "Impact (klasik)"],
      ["montserrat", "Montserrat ExtraBold"],
      ["anton", "Anton (tinggi ramping)"],
      ["bebas", "Bebas Neue (kapital)"],
      ["poppins", "Poppins ExtraBold"],
      ["arial", "Arial Black"],
    ],
  },
  { key: "caption_base", label: "Warna teks", type: "color" },
  { key: "caption_color", label: "Warna sorotan kata", type: "color" },
  {
    key: "caption_words",
    label: "Kata per tampilan",
    type: "select",
    options: [
      [1, "1 kata (cepat)"],
      [2, "2 kata"],
      [3, "3 kata"],
      [4, "4 kata"],
    ],
  },
  { key: "caption_upper", label: "HURUF BESAR", type: "bool" },
  { key: "caption_emphasis", label: "Sorot kata kunci", type: "bool" },
  { key: "caption_size", label: "Ukuran subtitle", type: "range", min: 60, max: 120, step: 2 },
  { key: "caption_pos", label: "Posisi subtitle", type: "range", min: 0.5, max: 0.82, step: 0.01 },
  { key: "title_on", label: "Judul/hook di atas", type: "bool" },
  {
    key: "title_bg",
    label: "Gaya judul",
    type: "select",
    options: [
      ["putih", "Kotak putih"],
      ["kuning", "Kotak kuning"],
      ["hitam", "Kotak hitam"],
    ],
  },
  {
    key: "title_secs",
    label: "Tampilkan judul",
    type: "select",
    options: [
      [0, "Sepanjang video"],
      [3, "3 detik pertama"],
      [5, "5 detik pertama"],
    ],
  },
  {
    key: "cut_pauses",
    label: "Hapus jeda",
    type: "select",
    options: [
      [0, "Tidak"],
      [0.3, "Rapat (jeda > 0,3 dtk)"],
      [0.6, "Sedang (jeda > 0,6 dtk)"],
    ],
  },
  { key: "progress_bar", label: "Progress bar bawah", type: "bool" },
  { key: "loudnorm", label: "Ratakan volume suara", type: "bool" },
  { key: "handle", label: "Watermark (@akun)", type: "text", placeholder: "@akunkamu" },
];
