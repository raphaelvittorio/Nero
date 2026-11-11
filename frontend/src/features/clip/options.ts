import type { CSSProperties } from "react";

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

/** Warna subtitle (sama dengan CAPTION_COLORS di engine.py). */
export const CAPTION_COLORS: Record<string, string> = {
  putih: "#ffffff",
  kuning: "#ffdd00",
  oranye: "#ff8c00",
  merah: "#ff3b3b",
  pink: "#ff50c8",
  ungu: "#aa5aff",
  biru: "#00c8ff",
  toska: "#00e6be",
  hijau: "#39ff14",
};

/**
 * Font subtitle. `css` dipakai untuk menampilkan contoh hurufnya di halaman (berkas fontnya diambil dari
 * /api/clip/fonts/<kunci>), `hint` menjelaskan kesannya.
 */
export const FONTS: { key: string; label: string; hint: string; css?: CSSProperties }[] = [
  { key: "impact", label: "Impact", hint: "klasik, tebal ramping" },
  { key: "anton", label: "Anton", hint: "tinggi ramping" },
  { key: "bebas", label: "Bebas Neue", hint: "kapital tipis" },
  { key: "montserrat", label: "Montserrat", hint: "modern tebal", css: { fontWeight: 800 } },
  { key: "poppins", label: "Poppins", hint: "bulat ramah" },
  { key: "arial", label: "Arial Black", hint: "lebar, sangat tebal" },
  { key: "segoe", label: "Segoe UI Black", hint: "bulat bersih" },
  { key: "bahnschrift", label: "Bahnschrift", hint: "ramping teknis", css: { fontVariationSettings: '"wght" 700, "wdth" 75' } },
  { key: "verdana", label: "Verdana", hint: "lebar, mudah dibaca" },
  { key: "georgia", label: "Georgia", hint: "berkait, kesan berita" },
  { key: "comic", label: "Comic Sans", hint: "santai, lucu" },
];

type Base = { key: keyof Style; label: string; hint?: string };

export type StyleField =
  | (Base & { type: "bool" })
  | (Base & { type: "select"; options: Option<string | number>[] })
  | (Base & { type: "range"; min: number; max: number; step: number; unit?: "%" | "px" })
  | (Base & { type: "text"; placeholder: string })
  | (Base & { type: "color" })
  | (Base & { type: "font" });

export interface StyleGroup {
  id: string;
  label: string;
  fields: StyleField[];
}

export const STYLE_GROUPS: StyleGroup[] = [
  {
    id: "subtitle",
    label: "Subtitle",
    fields: [
      { key: "captions", label: "Subtitle otomatis", type: "bool" },
      { key: "caption_font", label: "Font", type: "font" },
      { key: "caption_base", label: "Warna teks", type: "color" },
      { key: "caption_color", label: "Warna sorotan", type: "color" },
      {
        key: "caption_highlight",
        label: "Cara menyorot kata",
        type: "select",
        options: [
          ["warna", "Kata yang diucapkan berwarna"],
          ["kotak", "Kotak berwarna di belakang kata"],
          ["karaoke", "Karaoke (kata terucap tetap berwarna)"],
          ["tanpa", "Tanpa sorotan"],
        ],
      },
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
      {
        key: "caption_anim",
        label: "Animasi muncul",
        type: "select",
        options: [
          ["pop", "Pop kecil"],
          ["bounce", "Memantul"],
          ["naik", "Naik perlahan"],
          ["tanpa", "Tanpa animasi"],
        ],
      },
      {
        key: "caption_stroke",
        label: "Garis tepi huruf",
        type: "select",
        options: [
          [0, "Tanpa"],
          [1, "Tipis"],
          [2, "Sedang"],
          [3, "Tebal"],
        ],
      },
      { key: "caption_size", label: "Ukuran", type: "range", min: 50, max: 130, step: 2, unit: "px" },
      { key: "caption_pos", label: "Posisi dari atas", type: "range", min: 0.25, max: 0.85, step: 0.01, unit: "%" },
      { key: "caption_upper", label: "HURUF BESAR", type: "bool" },
      { key: "caption_emphasis", label: "Sorot kata kunci & angka", type: "bool" },
      { key: "caption_shadow", label: "Bayangan huruf", type: "bool" },
      { key: "caption_box", label: "Kotak gelap di belakang", type: "bool" },
    ],
  },
  {
    id: "judul",
    label: "Judul",
    fields: [
      { key: "title_on", label: "Judul/hook di atas", type: "bool" },
      {
        key: "title_bg",
        label: "Gaya judul",
        type: "select",
        options: [
          ["putih", "Kotak putih"],
          ["kuning", "Kotak kuning"],
          ["merah", "Kotak merah"],
          ["hitam", "Kotak hitam"],
          ["tanpa", "Tulisan saja (tanpa kotak)"],
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
      { key: "title_size", label: "Ukuran judul", type: "range", min: 44, max: 96, step: 2, unit: "px" },
      { key: "title_pos", label: "Posisi judul dari atas", type: "range", min: 0.04, max: 0.35, step: 0.01, unit: "%" },
    ],
  },
  {
    id: "video",
    label: "Video & efek",
    fields: [
      {
        key: "layout",
        label: "Tata letak",
        type: "select",
        options: [
          ["auto", "Otomatis (wajah / dua orang / blur)"],
          ["face", "Ikuti wajah"],
          ["split", "Dua orang (atas/bawah)"],
          ["blur", "Video utuh + latar blur"],
          ["hitam", "Video utuh + latar hitam"],
          ["center", "Potong tengah"],
        ],
      },
      {
        key: "zoom",
        label: "Zoom",
        type: "select",
        hint: "Zoom hentak berganti dekat/jauh di akhir kalimat, seperti potongan jump cut.",
        options: [
          ["tanpa", "Tanpa zoom"],
          ["halus", "Zoom pelan (maju-mundur)"],
          ["hentak", "Zoom hentak tiap kalimat"],
        ],
      },
      {
        key: "filter",
        label: "Filter warna",
        type: "select",
        options: [
          ["asli", "Asli"],
          ["cerah", "Cerah & tajam"],
          ["hangat", "Hangat"],
          ["dingin", "Dingin"],
          ["sinematik", "Sinematik"],
          ["pudar", "Pudar (film lama)"],
          ["hitamputih", "Hitam putih"],
        ],
      },
      {
        key: "cut_pauses",
        label: "Hapus jeda diam",
        type: "select",
        options: [
          [0, "Tidak"],
          [0.3, "Rapat (jeda > 0,3 dtk)"],
          [0.6, "Sedang (jeda > 0,6 dtk)"],
        ],
      },
      { key: "progress_bar", label: "Progress bar", type: "bool" },
      {
        key: "progress_pos",
        label: "Letak progress bar",
        type: "select",
        options: [
          ["bawah", "Bawah"],
          ["atas", "Atas"],
        ],
      },
    ],
  },
  {
    id: "pribadi",
    label: "Watermark & suara",
    fields: [
      {
        key: "handle",
        label: "Watermark (@akun)",
        type: "text",
        placeholder: "@akunkamu",
        hint: "Watermark & suara milik Anda: tidak berubah saat ganti gaya.",
      },
      {
        key: "handle_pos",
        label: "Letak watermark",
        type: "select",
        options: [
          ["bawah", "Bawah"],
          ["atas", "Atas"],
        ],
      },
      { key: "loudnorm", label: "Ratakan volume suara", type: "bool" },
    ],
  },
];

export const STYLE_FIELDS: StyleField[] = STYLE_GROUPS.flatMap((g) => g.fields);

/** Nilai gaya dalam kata-kata, memakai label yang sama dengan kontrolnya. */
export function describe(key: keyof Style, v: unknown): string {
  const f = STYLE_FIELDS.find((x) => x.key === key);
  if (f?.type === "bool") return v ? "ya" : "tidak";
  if (f?.type === "select") return f.options.find(([o]) => o === v)?.[1] ?? String(v);
  if (f?.type === "font") return FONTS.find((x) => x.key === v)?.label ?? String(v);
  if (f?.type === "range" && f.unit === "%") return `${Math.round(Number(v) * 100)}%`;
  return String(v);
}

export const labelOf = (key: keyof Style) => STYLE_FIELDS.find((f) => f.key === key)?.label ?? key;

/** Contoh huruf di halaman memakai berkas font yang sama dengan render. */
export const fontFamily = (key: string) => `nero-${key}`;
