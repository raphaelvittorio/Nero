"use client";

import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { api, post } from "@/lib/api";

import { API, isBusy } from "./api";
import type { AppState, Clip, Language, Project, Settings, Style } from "./types";

export type PlayerState =
  | { mode: "preview"; src: string; start: number; end: number; title: string }
  | { mode: "result"; src: string; title: string }
  | null;

type ConfirmOptions = { title: string; description?: string; action?: string; destructive?: boolean };

interface Store {
  settings: Settings | null;
  loadSettings: () => Promise<void>;
  /** ubah sebagian gaya aktif: langsung tampil, lalu disimpan ke server */
  patchStyle: (patch: Partial<Style>) => Promise<void>;
  state: AppState;
  refresh: () => void;
  project: (pid: string) => Project | undefined;
  clip: (pid: string, cid: string) => Clip | undefined;
  // pilihan di kartu "Masukkan video" (ikut berubah saat pengaturan disimpan)
  nClips: number;
  setNClips: (n: number) => void;
  language: Language;
  setLanguage: (l: Language) => void;
  player: PlayerState;
  setPlayer: (p: PlayerState) => void;
  transcriptPid: string | null;
  setTranscriptPid: (pid: string | null) => void;
  settingsOpen: boolean;
  setSettingsOpen: (open: boolean) => void;
  confirm: (opt: ConfirmOptions) => Promise<boolean>;
}

const Ctx = createContext<Store | null>(null);

export function useStore(): Store {
  const s = useContext(Ctx);
  if (!s) throw new Error("useStore harus dipakai di dalam ClipProvider");
  return s;
}

export function ClipProvider({ children }: { children: React.ReactNode }) {
  const [settings, setSettings] = useState<Settings | null>(null);
  const [state, setState] = useState<AppState>({ projects: [], queue: 0 });
  const [kick, setKick] = useState(0);
  const [nClips, setNClips] = useState(5);
  const [language, setLanguage] = useState<Language>("id");
  const [player, setPlayer] = useState<PlayerState>(null);
  const [transcriptPid, setTranscriptPid] = useState<string | null>(null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [confirmState, setConfirmState] = useState<ConfirmOptions | null>(null);
  const confirmResolve = useRef<((ok: boolean) => void) | null>(null);

  const applySettings = useCallback((s: Settings) => {
    setSettings(s);
    setNClips(s.n_clips);
    setLanguage(s.language);
  }, []);
  const loadSettings = useCallback(
    () => api<Settings>(`${API}/settings`).then(applySettings),
    [applySettings],
  );

  const patchStyle = useCallback(
    async (patch: Partial<Style>) => {
      setSettings((s) => (s ? { ...s, style: { ...s.style, ...patch } } : s));
      try {
        await post(`${API}/settings`, { style: patch });
      } catch {
        loadSettings().catch(() => {});
      }
    },
    [loadSettings],
  );

  useEffect(() => {
    let alive = true;
    api<Settings>(`${API}/settings`)
      .then((s) => alive && applySettings(s))
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, [applySettings]);

  // Ambil status berkala: cepat saat ada proses berjalan, lambat saat diam.
  useEffect(() => {
    let alive = true;
    let timer: number | undefined;
    const tick = async () => {
      let next: AppState | null = null;
      try {
        const r = await fetch(`${API}/state`);
        if (r.ok) next = (await r.json()) as AppState;
      } catch {}
      if (!alive) return;
      if (next) setState(next);
      timer = window.setTimeout(tick, next?.projects.some(isBusy) ? 1200 : 4000);
    };
    tick();
    return () => {
      alive = false;
      window.clearTimeout(timer);
    };
  }, [kick]);

  const refresh = useCallback(() => setKick((k) => k + 1), []);
  const project = useCallback((pid: string) => state.projects.find((p) => p.id === pid), [state]);
  const clip = useCallback(
    (pid: string, cid: string) => project(pid)?.clips?.find((c) => c.id === cid),
    [project],
  );

  const confirm = useCallback((opt: ConfirmOptions) => {
    setConfirmState(opt);
    return new Promise<boolean>((resolve) => {
      confirmResolve.current = resolve;
    });
  }, []);
  const closeConfirm = (ok: boolean) => {
    confirmResolve.current?.(ok);
    confirmResolve.current = null;
    setConfirmState(null);
  };

  return (
    <Ctx.Provider
      value={{
        settings,
        loadSettings,
        patchStyle,
        state,
        refresh,
        project,
        clip,
        nClips,
        setNClips,
        language,
        setLanguage,
        player,
        setPlayer,
        transcriptPid,
        setTranscriptPid,
        settingsOpen,
        setSettingsOpen,
        confirm,
      }}
    >
      {children}
      <AlertDialog open={confirmState !== null} onOpenChange={(open) => !open && closeConfirm(false)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{confirmState?.title}</AlertDialogTitle>
            {confirmState?.description && (
              <AlertDialogDescription>{confirmState.description}</AlertDialogDescription>
            )}
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Batal</AlertDialogCancel>
            <AlertDialogAction
              variant={confirmState?.destructive ? "destructive" : "default"}
              onClick={() => closeConfirm(true)}
            >
              {confirmState?.action ?? "Lanjut"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Ctx.Provider>
  );
}
