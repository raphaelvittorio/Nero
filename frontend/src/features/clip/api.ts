import type { Clip, Project } from "./types";

/** Semua rute fitur ini ada di bawah /api/clip (features/clip/api.py). */
export const API = "/api/clip";
/** Folder hasil fitur ini di dalam output/. Alamat berkas clip (`Clip.file`) relatif terhadap folder ini. */
export const OUT_DIR = "clip";

/** detik -> "mm:ss.s" */
export function fmt(t: number | undefined): string {
  t = Math.max(0, Number(t) || 0);
  const m = Math.floor(t / 60);
  const s = t - m * 60;
  return String(m).padStart(2, "0") + ":" + s.toFixed(1).padStart(4, "0");
}

/** "mm:ss", "hh:mm:ss" atau detik biasa -> detik */
export function parseT(v: string): number {
  v = String(v).trim().replace(",", ".");
  if (!v.includes(":")) return parseFloat(v) || 0;
  const p = v.split(":").map(Number);
  return p.length === 3 ? p[0] * 3600 + p[1] * 60 + p[2] : p[0] * 60 + p[1];
}

export function sizeText(p: Project): string {
  if (!p.size_mb) return "";
  return p.size_mb >= 1000 ? (p.size_mb / 1000).toFixed(1) + " GB" : Math.round(p.size_mb) + " MB";
}

export const clipBusy = (c: Clip) => c.render_status === "proses" || c.render_status === "antri";
export const projectRunning = (p: Project) => p.status === "proses" || p.status === "antri";
export const isBusy = (p: Project) => projectRunning(p) || (p.clips ?? []).some(clipBusy);

export const mediaUrl = (p: Project) =>
  p.source ? `${API}/media/${p.id}/${encodeURIComponent(p.source)}` : "";
export const outUrl = (c: Clip) =>
  `/out/${OUT_DIR}/` + (c.file ?? "").split("/").map(encodeURIComponent).join("/");
