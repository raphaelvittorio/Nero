import { ScissorsIcon, type LucideIcon } from "lucide-react";

/**
 * Daftar fitur Nero (pasangan dari features/__init__.py di backend).
 *
 * Fitur baru:
 *   1. backend: folder features/<id>/ lalu tambahkan ke FEATURES di features/__init__.py
 *   2. tampilan: kode di src/features/<id>/, halaman di src/app/<id>/page.tsx, lalu daftarkan di sini
 * Menu samping dan kartu di Beranda dibuat otomatis dari daftar ini.
 */
export interface Feature {
  /** sama dengan ID di backend: alamat API /api/<id>, folder output/<id> */
  id: string;
  name: string;
  /** satu kalimat pendek di menu & kartu */
  tagline: string;
  description: string;
  href: string;
  icon: LucideIcon;
}

export const FEATURES: Feature[] = [
  {
    id: "clip",
    name: "Clip Maker",
    tagline: "Video panjang jadi clip pendek siap upload",
    description:
      "Ubah video panjang menjadi clip vertikal 9:16 lengkap dengan subtitle, judul hook, dan caption. Untuk TikTok, Reels, dan Shorts.",
    href: "/clip",
    icon: ScissorsIcon,
  },
];
