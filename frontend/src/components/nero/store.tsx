"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";

import { api } from "@/lib/api";

/** Pengaturan umum dari /api/settings (dipakai semua fitur). API key sendiri tidak pernah dikirim. */
export interface GlobalSettings {
  has_key: boolean;
  ai_model: string;
  cookies_browser: string;
  /** Ikon Nero di Desktop & buka otomatis saat Windows menyala (null bila bukan Windows). */
  desktop: { shortcut: boolean; autostart: boolean } | null;
}

/** Ringkasan satu fitur dari /api/overview, untuk menu & Beranda. */
export interface FeatureSummary {
  busy: number;
  queue: number;
  stats: { label: string; value: number }[];
}

interface NeroStore {
  settings: GlobalSettings | null;
  loadSettings: () => Promise<void>;
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

  const loadSettings = useCallback(() => api<GlobalSettings>("/api/settings").then(setSettings), []);

  useEffect(() => {
    let alive = true;
    api<GlobalSettings>("/api/settings")
      .then((s) => alive && setSettings(s))
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, []);

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
      value={{ settings, loadSettings, summaries, online, settingsOpen, setSettingsOpen, shutdownOpen, setShutdownOpen }}
    >
      {children}
    </Ctx.Provider>
  );
}
