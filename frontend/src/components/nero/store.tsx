"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";

import { api } from "@/lib/api";

/** Pengaturan umum dari /api/settings (dipakai semua fitur). API key sendiri tidak pernah dikirim. */
export interface GlobalSettings {
  has_key: boolean;
  ai_model: string;
  cookies_browser: string;
  /** AI lokal gratis (Ollama / LM Studio) */
  local_ai_url: string;
  /** "" = pilih otomatis model yang bisa melihat gambar */
  local_ai_model: string;
  /** pakai AI saat membaca gaya (bila mati: pengukuran piksel saja) */
  local_ai_on: boolean;
  /** kunci server bergaya OpenAI di internet (OpenRouter, Groq) sudah tersimpan */
  has_local_ai_key: boolean;
  /** AI untuk meniru gaya: Gemini (online, gratis) atau AI lokal (Ollama) */
  ai_provider: "lokal" | "gemini";
  has_gemini_key: boolean;
  gemini_model: string;
  /** Ikon Nero di Desktop & buka otomatis saat Windows menyala (null bila bukan Windows). */
  desktop: { shortcut: boolean; autostart: boolean } | null;
}

/** Ringkasan satu fitur dari /api/overview, untuk menu & Beranda. */
export interface FeatureSummary {
  busy: number;
  queue: number;
  stats: { label: string; value: number }[];
}

/** Status AI lokal dari /api/local-ai. */
export interface LocalAIInfo {
  url: string;
  on: boolean;
  model: string;
  /** model yang benar-benar dipakai (pilihan pengguna atau otomatis), null = belum ada */
  chosen: string | null;
  status: {
    ok: boolean;
    kind: "ollama" | "openai" | null;
    models: { name: string; vision: boolean; size_gb: number }[];
    error: string;
  };
  recommended: { name: string; label: string; size_gb: number }[];
  pull: null | { model: string; status: "proses" | "selesai" | "gagal" | "batal"; progress: number; stage: string; error: string };
  provider: "lokal" | "gemini";
  gemini: { has_key: boolean; model: string; key_page: string };
}

/** AI lokal siap membaca gambar? */
export const localAIReady = (ai: LocalAIInfo | null) => Boolean(ai?.on && ai.status.ok && ai.chosen);

/** AI untuk meniru gaya yang akan dipakai sekarang: Gemini (bila dipilih & ada API key), AI lokal, atau tidak ada. */
export function styleAI(ai: LocalAIInfo | null): { ready: boolean; kind: "gemini" | "lokal" | null; label: string } {
  if (!ai?.on) return { ready: false, kind: null, label: "AI dimatikan" };
  if (ai.provider === "gemini" && ai.gemini.has_key) return { ready: true, kind: "gemini", label: `Gemini (${ai.gemini.model})` };
  if (localAIReady(ai)) return { ready: true, kind: "lokal", label: `AI lokal (${ai.chosen})` };
  return { ready: false, kind: null, label: "AI belum siap" };
}

interface NeroStore {
  settings: GlobalSettings | null;
  loadSettings: () => Promise<void>;
  localAI: LocalAIInfo | null;
  loadLocalAI: () => Promise<LocalAIInfo | null>;
  summaries: Record<string, FeatureSummary>;
  online: boolean;
  settingsOpen: boolean;
  setSettingsOpen: (open: boolean) => void;
  shutdownOpen: boolean;
  setShutdownOpen: (open: boolean) => void;
}

const Ctx = createContext<NeroStore | null>(null);

export function useNero(): NeroStore {
  const s = useContext(Ctx);
  if (!s) throw new Error("useNero harus dipakai di dalam NeroProvider");
  return s;
}

export function NeroProvider({ children }: { children: React.ReactNode }) {
  const [settings, setSettings] = useState<GlobalSettings | null>(null);
  const [summaries, setSummaries] = useState<Record<string, FeatureSummary>>({});
  const [online, setOnline] = useState(true);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [shutdownOpen, setShutdownOpen] = useState(false);

  const [localAI, setLocalAI] = useState<LocalAIInfo | null>(null);

  const loadSettings = useCallback(() => api<GlobalSettings>("/api/settings").then(setSettings), []);
  const loadLocalAI = useCallback(async () => {
    try {
      const r = await fetch("/api/local-ai");
      if (!r.ok) return null;
      const info = (await r.json()) as LocalAIInfo;
      setLocalAI(info);
      return info;
    } catch {
      return null;
    }
  }, []);

  useEffect(() => {
    let alive = true;
    api<GlobalSettings>("/api/settings")
      .then((s) => alive && setSettings(s))
      .catch(() => {});
    fetch("/api/local-ai")
      .then((r) => (r.ok ? (r.json() as Promise<LocalAIInfo>) : null))
      .then((info) => alive && info && setLocalAI(info))
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, []);

  // selama model AI diunduh, pantau terus progresnya
  const pulling = localAI?.pull?.status === "proses";
  useEffect(() => {
    if (!pulling) return;
    const t = window.setInterval(loadLocalAI, 1000);
    return () => window.clearInterval(t);
  }, [pulling, loadLocalAI]);

  // Ringkasan berkala: cepat saat ada tugas berjalan, lambat saat diam. Sekaligus tanda koneksi.
  useEffect(() => {
    let alive = true;
    let timer: number | undefined;
    const tick = async () => {
      let next: Record<string, FeatureSummary> | null = null;
      try {
        const r = await fetch("/api/overview");
        if (r.ok) next = ((await r.json()) as { features: Record<string, FeatureSummary> }).features;
      } catch {}
      if (!alive) return;
      setOnline(next !== null);
      if (next) setSummaries(next);
      const busy = next && Object.values(next).some((f) => f.busy > 0);
      timer = window.setTimeout(tick, busy ? 2000 : 5000);
    };
    tick();
    return () => {
      alive = false;
      window.clearTimeout(timer);
    };
  }, []);

  return (
    <Ctx.Provider
      value={{
        settings,
        loadSettings,
        localAI,
        loadLocalAI,
        summaries,
        online,
        settingsOpen,
        setSettingsOpen,
        shutdownOpen,
        setShutdownOpen,
      }}
    >
      {children}
    </Ctx.Provider>
  );
}
