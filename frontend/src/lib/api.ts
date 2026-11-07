import { toast } from "sonner";

import type { Clip, Project } from "./types";

type Body = Record<string, unknown> | FormData;

/** Panggil API Flask. Pesan galat dari server langsung ditampilkan sebagai toast. */
export async function api<T = { ok: boolean; count?: number }>(
  url: string,
  opt: { method?: string; body?: Body } = {},
): Promise<T> {
  const init: RequestInit = { method: opt.method ?? (opt.body ? "POST" : "GET") };
  if (opt.body instanceof FormData) {
    init.body = opt.body;
  } else if (opt.body) {
    init.body = JSON.stringify(opt.body);
    init.headers = { "Content-Type": "application/json" };
  }
  let r: Response;
  try {
    r = await fetch(url, init);
  } catch {
    toast.error("Tidak bisa terhubung ke ClipMaker. Pastikan jendela run.bat masih terbuka.");
    throw new Error("network");
  }
  const j = await r.json().catch(() => ({}));
  if (!r.ok) {
    const msg = (j as { error?: string }).error || "Terjadi kesalahan";
    toast.error(msg);
    throw new Error(msg);
  }
  return j as T;
}

export const post = <T = { ok: boolean; count?: number }>(url: string, body: Body = {}) =>
  api<T>(url, { method: "POST", body });

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
  p.source ? `/media/${p.id}/${encodeURIComponent(p.source)}` : "";
export const outUrl = (c: Clip) =>
  "/out/" + (c.file ?? "").split("/").map(encodeURIComponent).join("/");
