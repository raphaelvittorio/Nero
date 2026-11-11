"use client";

import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { api, post } from "@/lib/api";

import { API } from "./api";
import { FONTS, fontFamily } from "./options";
import { useStore } from "./store";
import type { StyleEntry, StyleJob, StyleLibrary } from "./types";

interface StyleStore {
  library: StyleLibrary | null;
  loadLibrary: () => Promise<void>;
  /** gaya pustaka / preset berdasarkan id */
  find: (id: string | null | undefined) => StyleEntry | undefined;
  /** nama gaya aktif untuk ditampilkan */
  activeName: string;
  /** jadikan gaya pustaka / preset sebagai gaya aktif */
  apply: (id: string) => Promise<void>;
  /** pembacaan gaya dari clip referensi yang sedang / terakhir berjalan */
  job: StyleJob | null;
  startJob: (body: { url: string; replace_id?: string } | FormData) => Promise<void>;
  cancelJob: () => void;
  clearJob: () => void;
  editorOpen: boolean;
  setEditorOpen: (v: boolean) => void;
  refOpen: boolean;
  setRefOpen: (v: boolean) => void;
  detail: StyleEntry | null;
  setDetail: (s: StyleEntry | null) => void;
}

const Ctx = createContext<StyleStore | null>(null);

export function useStyles(): StyleStore {
  const s = useContext(Ctx);
  if (!s) throw new Error("useStyles harus dipakai di dalam StyleProvider");
  return s;
}

/** Alamat gambar contoh gaya ("current" = gaya aktif). `k` membuat browser memuat ulang bila gayanya berubah. */
export const thumbUrl = (id: string, k: string) => `${API}/styles/${encodeURIComponent(id)}/thumb?k=${k}`;

export function StyleProvider({ children }: { children: React.ReactNode }) {
  const { settings, loadSettings } = useStore();
  const [library, setLibrary] = useState<StyleLibrary | null>(null);
  const [job, setJob] = useState<StyleJob | null>(null);
  const [editorOpen, setEditorOpen] = useState(false);
  const [refOpen, setRefOpen] = useState(false);
  const [detail, setDetail] = useState<StyleEntry | null>(null);
  const seen = useRef<string | null>(null);

  const loadLibrary = useCallback(async () => {
    try {
      const r = await fetch(`${API}/styles`);
      if (r.ok) setLibrary((await r.json()) as StyleLibrary);
    } catch {}
  }, []);

  // gaya aktif berubah (diedit / diganti): perbarui tanda "diubah" & gambar contohnya
  const styleKey = settings ? JSON.stringify(settings.style) + settings.active_style_id : "";
  useEffect(() => {
    if (!styleKey) return;
    const t = window.setTimeout(loadLibrary, 500);
    return () => window.clearTimeout(t);
  }, [styleKey, loadLibrary]);

  const find = useCallback(
    (id: string | null | undefined) =>
      id ? (library?.styles.find((x) => x.id === id) ?? library?.presets.find((x) => x.id === id)) : undefined,
    [library],
  );

  const apply = useCallback(
    async (id: string) => {
      try {
        await post(`${API}/styles/${encodeURIComponent(id)}/apply`);
        await loadSettings();
        await loadLibrary();
        toast.success(`Gaya "${find(id)?.name ?? "pilihan"}" dipakai`);
      } catch {}
    },
    [find, loadLibrary, loadSettings],
  );

  const startJob = useCallback(async (body: { url: string; replace_id?: string } | FormData) => {
    seen.current = null;
    const r = await post<{ ok: boolean; id: string }>(`${API}/style-jobs`, body);
    setJob({ id: r.id, status: "proses", stage: "Memulai...", progress: 0, error: "", result: null });
  }, []);

  const cancelJob = useCallback(() => {
    if (job?.status === "proses") post(`${API}/style-jobs/${job.id}/cancel`).catch(() => {});
  }, [job]);
  const clearJob = useCallback(() => setJob(null), []);

  // pantau pembacaan yang sedang berjalan
  const running = job?.status === "proses" ? job.id : null;
  useEffect(() => {
    if (!running) return;
    let alive = true;
    const tick = async () => {
      try {
        const j = await api<StyleJob>(`${API}/style-jobs/${running}`);
        if (!alive) return;
        setJob(j);
        if (j.status !== "proses" && seen.current !== j.id) {
          seen.current = j.id;
          if (j.status === "selesai") {
            loadLibrary();
            toast.success(`Gaya "${j.result?.name}" tersimpan di Gaya saya`);
          } else if (j.status === "gagal") toast.error(j.error);
        }
      } catch {}
    };
    const t = window.setInterval(tick, 800);
    tick();
    return () => {
      alive = false;
      window.clearInterval(t);
    };
  }, [running, loadLibrary]);

  const activeName = (() => {
    const a = find(settings?.active_style_id);
    if (!a) return "Diatur sendiri";
    return library?.active_modified ? `${a.name} (diubah)` : a.name;
  })();

  return (
    <Ctx.Provider
      value={{
        library,
        loadLibrary,
        find,
        activeName,
        apply,
        job,
        startJob,
        cancelJob,
        clearJob,
        editorOpen,
        setEditorOpen,
        refOpen,
        setRefOpen,
        detail,
        setDetail,
      }}
    >
      <FontFaces />
      {children}
    </Ctx.Provider>
  );
}

/** Font subtitle dimuat dari Nero supaya contoh huruf di halaman sama persis dengan hasil render. */
function FontFaces() {
  const css = FONTS.map(
    (f) => `@font-face{font-family:"${fontFamily(f.key)}";src:url(${API}/fonts/${f.key});font-display:swap}`,
  ).join("\n");
  return <style>{css}</style>;
}
