import { toast } from "sonner";

type Body = Record<string, unknown> | FormData;

/** Panggil API Flask (app.py). Pesan galat dari server langsung ditampilkan sebagai toast. */
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
    toast.error("Tidak bisa terhubung ke Nero. Buka lagi lewat ikon Nero di Desktop.");
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

/** Buka folder di dalam output/ (mis. "clip" atau "clip/Judul/berkas.mp4") di File Explorer. */
export const openFolder = (path = "") => post("/api/open-folder", { path }).catch(() => {});
